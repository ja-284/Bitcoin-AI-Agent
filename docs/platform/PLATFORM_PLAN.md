# The trading platform: investigation, plan and progress (started 2026-11-14)

**What this is.** The user's brief of 2026-11-14: a website (later a PWA) connected to the existing system, with
**automatic, real-money** BUY/HOLD/SELL execution every hour, capital the user deposits (starting around NOK 150),
position sizing from volatility, move size and confidence, a statistics page with a value chart (6h to 1 year), light
and dark mode, a premium design, and **NOK 0 of additional cost**. The user's clarifications the same day:
**this is not paper trading**, and **the weekly audits continue**: the system is not finished because the website is
being built.

**What this is not.** It does not declare the model finished. The signal, the sizing and the strategy are a starting
point that is versioned and replaceable. Research, data collection, the registered checkpoints and the weekly audits
continue exactly as before.

**Status of the plan (2026-11-14).** The owner decided (section 12): **Firi**, principle 10 replaced (real-money
automatic trading through this layer), and **going live after tests**. Built: P0, P1, the execution core and the Firi
adapter (P2, P4 code), and the website on demo data (P6, first version). Not yet: production tables, the hourly step
and the dry run, which need the owner's Firi key first (section 12, "what is left").

---

## 1. Phase 1: what the project actually is today (investigated, not assumed)

| Area | State | Evidence |
|---|---|---|
| Hourly analysis (data, indicators, news, scoring, explanation, storage) | **Working.** 1,313 of 1,324 hours since go-live; none missed since 2026-10-07 | weekly audit 2026-11-13 |
| Scheduling | **Working.** Supabase `pg_cron` dispatch at :12, GitHub backup slots, heartbeat, watchdog | `.github/workflows/hourly.yml`, STATUS.md |
| BUY/HOLD/SELL signal (scoring 0.2.0) | **Working as software, no demonstrated predictive value.** Thresholds ±0.15 on a hand-set five-category score | E001, E017; live 1h acted accuracy 0.507 vs 0.511 naive |
| "Confidence" | **Working as software, uninformative as a number.** Agreement + completeness; stated 0.97 when right 52% of the time (ECE 0.41) | weekly report 2026-11-13 |
| Move-size model `move_size_1h_v1` | **Working, the one model with prospective skill** (descriptive, n = 1,258): P(next-hour move > 0.25%); says nothing about direction | weekly report 2026-11-13 |
| Direction model `direction_1h_v1` | **Collecting, blind** until its registered readings (1,000 h ≈ 2026-11-26; verdict at 6,500 h ≈ 2027-07) | `research/DIRECTION_TRACK.md` |
| Read-only reporting layer + three published tables | **Working.** Readable only by the dedicated dashboard account in a two-factor session | `docs/api/stats_access.md` |
| Dashboard data contract | **Documented, fictional fixtures**, client code untested | `docs/api/dashboard/` |
| Execution (orders, balances, exchange) | **Missing entirely.** `status.json`: `trading_capability: false` | `docs/FUTURE_EXECUTION_ARCHITECTURE.md` |
| Writable settings for a user | **Missing.** Every API surface is read-only by design | `agent/database/security.py` |
| Website | **Missing** (a separate Lovable dashboard exists on fictional data, not connected) | CLAUDE.md |
| Database backup | **Missing (open risk).** The only copy of the record is the live database | STATUS.md |

**What must exist before automatic trading can run safely:** an execution layer separate from the prediction
engine; an exchange account and a trade-only key held by the user; a place to run orders from that the exchange
accepts; a kill switch; idempotent orders; reconciliation against the exchange; an audit log of every decision; and
writable settings that only the owner can change.

---

## 2. The evidence that must shape the trading design

### 2.1 What the user's rule would have done since go-live (descriptive, computed 2026-11-14)

The rule, fixed before computing: start in cash; BUY → fully invested; SELL → fully in cash; HOLD → keep. NOK 150.
Live record 2026-09-19 20:00 → 2026-11-14 14:00 UTC (1,335 hours, pipeline 0.2.0), filled at each hour's reference
close plus 0.01% slippage. Read-only, nothing tuned, no variant chosen from the result.

| | result |
|---|---|
| the rule, no fees | −9.4% |
| the rule, 0.10% per side (Binance regular, verified) | **−12.3%** (32 trades; NOK 4.63 fees) |
| the rule, 0.80% per side (Kraken Pro level-1 taker, verified) | −30.0% |
| buy-and-hold | −18.9% (BTC 81,155 → 65,914 USDT) |
| cash | 0% |

**Reading it honestly.** The rule lost less than buy-and-hold only because it was in cash 67% of the hours of a
falling market. Random timing with the same exposure would have lost about 6.6% before fees; the rule lost 9.4%. One
path and 32 trades prove nothing either way, but nothing here contradicts the research: **the signal has no
demonstrated predictive value**, so trading it costs fees for no demonstrated benefit.

### 2.2 Facts about venues, costs and tax (checked 2026-11-14; sources in section 15)

- **Firi** (Norwegian, NOK): API trading is supported ("create and delete orders"); **withdrawals through the API are
  impossible**; keys are created under Settings → API; an official Node.js SDK exists. The trading fee is reported as
  **0.7% per side**, not yet confirmed on Firi's own page. Bank and Open Banking deposits are free.
- **Binance**: 0.10% per side, but it refuses requests from US addresses (HTTP 451), and GitHub's job machines are
  in the US. NOK funding for Norway is not confirmed by any official source found.
- **Kraken Pro**: 0.40% / 0.80% maker/taker at level 1 (verified 2026-10-16).
- **Tax (Skatteetaten)**: every sale realises a gain (taxed at 22%) or a deductible loss; the owner must document the
  purchase and sale value of every unit and report the total. Hourly trading can create many taxable events, so a
  complete trade export is a requirement, not a nicety. *(Information, not tax advice.)*

**Consequence:** at 0.7% per side, the user's rule's 32 trades in eight weeks would cost about 22% of the capital in
fees alone. **Trade frequency is the single biggest controllable cost.** The design therefore makes every trade earn
its fee: bands, minimum holding times and daily caps (section 3).

### 2.3 Firi's API and order book (read 2026-11-14)

- **API** (developers.firi.com): base `https://api.firi.com`; private calls signed with HMAC-SHA256 over
  `JSON.stringify({timestamp, validity, ...body})` (headers `firi-user-signature`, `firi-user-clientid`; `timestamp`
  and `validity` in the query). **Limit orders only** (`bid` / `ask`, price and amount), **no client order id**, no
  API withdrawals. Balances `GET /v2/balances`; orders `POST /v2/orders`, `GET /v2/order/{id}`,
  `DELETE /v2/orders/{id}/detailed`; public ticker `GET /v2/markets/BTCNOK/ticker`. Markets: BTC, ETH, SOL, XRP, ADA
  and USDC against NOK.
- **Order book, one snapshot (14:3x UTC):** bid 625,329, ask 633,447 NOK: a **spread of 1.29%**, and 8.44 BTC traded
  in 24 h. A small order crosses half of it, about 0.65%, on top of the fee (about 0.7%, unconfirmed): **a buy and a
  later sell cost about 2.7%**. One snapshot is not a statistic; the engine records the spread at every decision.
- **Reachability:** the public API answered from Norway. Whether it accepts GitHub's US runners is checked in the
  dry run (P4).

### 2.4 The real engine on invented data (fictional, `python -m agent.execution.demo --fee …`)

Invented 400-day price path, invented signals with no edge, strategy `rule-1.0`, NOK 150:

| fee per side | end value | trades | fees | buy-and-hold |
|---|---|---|---|---|
| 0.7% | 19.91 | 312 | 136.65 | 152.69 |
| 0.1% | 101.50 | 422 | 46.68 | 153.62 |

The turnover controls are not enough while the signal has no edge: the strategy loses about what it pays. At 0.7% the
account also fell below the venue minimum and could no longer trade. **A stricter turnover setting for Firi is
recommended before going live** (section 12).

---

## 3. Phase 2: the current strategy, critically, and what to change

| Weakness | Why it matters | Improvement | When |
|---|---|---|---|
| The signal has no demonstrated edge | Trading it is a coin flip minus fees | Keep it as the version-1 input, labelled honestly everywhere; make the signal **swappable** (a "signal provider" with a version) so a validated model can replace it without a rewrite | now (interface), later (replacement) |
| All-in / all-out on every flip | Maximises turnover and fees | **Target exposure** instead of flips; **no-trade band** (trade only if the change exceeds a share of the cap); **minimum holding time**; **max trades per 24 h** | now |
| "Confidence" scales nothing useful | Measured as uninformative (ECE 0.41) | **Do not size by it** in version 1; show it as disabled with the reason; replace with calibrated probabilities only once one passes its registered test | now (disabled), later (calibrated) |
| No risk sizing | One-shot exposure regardless of conditions | **Volatility targeting** from the stored 24 h realised volatility; **move-size dampening** from the frozen move-size probability (the one input with prospective skill) | now |
| No loss limits | A bad run is unbounded within the cap | **Daily loss limit** and **maximum drawdown stop**: flatten and pause until the owner resumes | now |
| Momentum treated as continuation | The measured 1 h structure is reversal (direction review 2026-10-21) | A registered decision-layer redesign after the 2,000-hour reading, on paper and pre-registered, never tuned on the live record | later (research) |
| Hourly horizon only | Hourly direction is weakly efficient (external evidence) | A daily target is on the research roadmap, deferred | later (research) |
| Data problems could trigger orders | Fallback prices, stale or degraded hours | **Data-quality veto** on any risk-increasing order; risk-reducing orders stay allowed | now |

**What is deliberately not changed:** the frozen `move_size_1h_v1`, scoring 0.2.0, the direction track, the registered
checkpoints and the holdout. The execution layer **reads** the prediction record and never writes to it, so the
prospective evaluation stays valid. The direction track's outputs are **not** used or shown (it is blind).

### 3.1 Strategy `rule-1.0` (the first versioned execution strategy)

| Element | Rule (every parameter is a stated, unvalidated choice, shown in the app) |
|---|---|
| Target on BUY | `cap × size` |
| Target on SELL | 0 (all cash) |
| Target on HOLD | keep the current exposure (trimmed if above the cap) |
| `size` | `min(f_vol, f_move)`; `f_conf` = 1 (disabled, not calibrated) |
| `f_vol` | `clip(0.006 / rv_24, 0.25, 1)`: full size unless the last 24 h moved more than ~0.6% an hour |
| `f_move` | `clip(1.5 − p_large, 0.5, 1)`: full size up to P(large move) = 0.5, down to half at 1.0 |
| No-trade band | skip if the change is under 20% of the cap or under the venue's minimum order |
| Minimum holding | no reversal within 6 h of an entry, except a risk exit |
| Turnover cap | at most 4 trades in any 24 h |
| Data-quality veto | no risk-increasing order if the hour is stale (> 2 h), synthetic, of an unexpected version, or the move-size row is missing (then `f_move` = 0.5) |
| Daily loss limit | value down > 10% vs 24 h ago → flatten and pause |
| Drawdown stop | value down > 30% from its peak → flatten and pause |
| Kill switch | paused → no order of any kind; "flatten now" is a separate explicit action |
| Hard cap in code | the owner's cap can never exceed `HARD_MAX_ALLOCATION` (500 in the account currency) without a reviewed commit |

---

## 4. Phase 3: ideas, evaluated

| Idea | Verdict | Reason |
|---|---|---|
| **Connect the exchange once, manage everything in Settings** (the user's own example) | **adopt** | The money stays on the user's exchange account; the app sets the cap, the risk profile and the pause |
| Card deposits inside the website | **reject** | Taking cards needs a payment processor (fees, PCI duties) and would make the system hold money. Deposits happen in the exchange's own app; the website shows the balance and guides |
| Trade-only API key, withdrawals off, IP-restricted where possible | **adopt** | A stolen key cannot move money out. Firi forbids API withdrawals outright |
| Hard cap in code + cap in Settings + only the cap funded on the exchange | **adopt** | Three independent limits on what can be lost |
| Kill switch in the app **and** a repository variable | **adopt** | Two independent ways to stop, one of them outside the website and the database |
| Benchmark lines on the chart (buy-and-hold, cash) | **adopt** | The only honest way to read a value chart |
| Per-decision "why" page (inputs, factors, checks passed and blocked, fees) | **adopt** | Transparency for every BUY/HOLD/SELL, including the trades not made |
| Strategy version markers on the chart | **adopt** | Results from different strategies must never blur together |
| Trade export (CSV) with NOK values for the tax return | **adopt** | Required by Skatteetaten's documentation rule |
| Push notifications (PWA, free Web Push) for trades, pauses and failures | **adopt later** | Free, but needs a sender key; after the core works |
| Telegram or email alerts | **defer** | Healthchecks.io email already exists; Telegram is free but another account |
| Several strategies at once with separate pockets of capital | **defer** | Splits NOK 150 into pieces below exchange minimums; revisit with more capital |
| DCA (buy a fixed amount on a schedule) as an alternative mode | **adopt as an option later** | A transparent, low-turnover mode the user can choose; shown as a benchmark first |
| A "what-if" simulator in the app | **defer** | Easy to misuse as tuning on the live record |
| Showing the direction model's probabilities | **reject until its readings** | It is blind by registration; showing it would end the experiment |
| Leverage, margin, shorting, other coins | **reject** | Raises the loss beyond the deposit; out of scope |
| Self-hosted runner on the user's PC | **reject** | The system must not depend on the PC being on |

---

## 5. Architecture

```
prediction engine (unchanged)          execution layer (new, separate)              website (new)
  run.py -> predictions table   --->   agent/execution: read the newest hour,  <--- reads published execution
  shadow -> shadow_move_size    --->   decide (rule-1.0), check risk, place an      tables (two-factor account)
                                       idempotent order, record everything          writes only owner settings
                                         |                                           and the pause, through a
                                         v                                           narrow, logged path
                                       exchange adapter (Firi / other) -> exchange
```

- **Separation:** the execution package imports nothing that writes the prediction record, and nothing in the
  prediction engine imports it (to be tested like the reporting layer's isolation).
- **Idempotency:** at most one decision and one order per hour and strategy; the client order id is
  `<strategy>:<hour>`; a rerun finds the earlier order instead of placing a second.
- **Reconciliation:** each run compares the ledger with the exchange's balances; a mismatch pauses trading and
  alarms.
- **Audit log:** every decision, including "no trade, and why", is an append-only row with all inputs.
- **Where orders run (open, section 12):** a GitHub Actions step (US addresses) works only with a venue that accepts
  them. The fallback that keeps NOK 0 is a Supabase Edge Function pinned to an EU region, which executes an "order
  intent" the hourly job writes. The job then never holds the exchange key. To verify before choosing.
- **Failure isolation:** an execution failure must never fail the hourly record. It gets its own alarm.

### 5.1 Data model (to be applied only after approval)

| Table | Kind | Purpose |
|---|---|---|
| `execution_settings` | one row, owner-editable through a logged path | cap, risk profile, paused, mode, strategy version |
| `execution_settings_log` | append-only | every change, who, when, from what to what |
| `execution_decisions` | append-only, one per hour | inputs, factors, target, action, every check, reasons |
| `execution_orders` | append-only status history | intent, client id, venue answer, status |
| `execution_fills` | append-only | price, quantity, fee, currency |
| `execution_portfolio` | one row per hour | cash, BTC, value, benchmark values, peak, drawdown |

---

## 6. Deposits, capital and the account

1. The owner opens an exchange account (KYC is the owner's), deposits through the exchange (card or bank transfer at
   the exchange's own fees), and creates a **trade-only key with withdrawals off**. I never create accounts or enter
   keys.
2. The key goes into a secret store (GitHub secret or the Edge Function's secrets) by the owner. It is never in the
   website, the repository or the database.
3. In the app's Settings the owner sets the **allocation cap** (e.g. NOK 150), which the engine never exceeds even if
   the account holds more. The code's hard cap bounds the setting.
4. The **Funding** page shows the exchange balance, the allocated capital, the unallocated rest and a link to the
   exchange's deposit page. Withdrawals are done by the owner in the exchange's app.

---

## 7. How the website talks to the backend

- **Read:** Supabase's API with the existing dedicated account in a two-factor session (`control_center_read`),
  extended to the new execution tables after approval. No other account and no anonymous access.
- **Write:** only `execution_settings` (specific columns) and the pause, by that account at two-factor level, with
  database constraints (the cap is bounded, values are validated) and an append-only log. The security check is
  extended to fail on anything wider.
- **No secrets in the browser:** the publishable key only; the Supabase host and key are injected at deploy, never
  committed (the repository's secret scan watches for the host).
- **Hosting at NOK 0:** GitHub Pages (static files; the data stays behind the two-factor login).
- **Development data:** a fictional demo data set produced by the real execution engine, committed; real data never
  leaves the database except through the login.

---

## 8. Pages

| Page | Contents |
|---|---|
| **Home** | portfolio value and change (24 h, 7 d, all), current position (BTC vs cash), the last decision and its reason, the next run, system and trading status (live / paused), alerts, the honest research banner |
| **Portfolio** | value chart with 6h, 12h, 1d, 3d, 5d, 7d, 14d, 21d, 1m, 3m, 6m, 9m, 1y; buy-and-hold and cash benchmarks; trade markers; strategy-version markers; P&L, fees paid, drawdown |
| **Activity** | every hour: signal, decision, trade or "no trade and why", price, fee, the hour's result (green or red), filters, CSV export |
| **Decision detail** | the full "why": signal and category scores, move-size probability, the sizing factors, every risk check, the order and fill, the explanation text |
| **Signals & research** | what each input means and how good it is (the evidence labels), model versions, checkpoint progress, what is blind and why |
| **Risk** | cap, exposure, drawdown, daily loss, turnover, the limits and how close each is |
| **Funding** | exchange connection, balances, allocated vs unallocated, how to deposit and withdraw |
| **Settings** | cap, risk profile, pause / resume / flatten (two-factor), notifications, theme |
| **System** | run history, incidents, freshness, alarms, versions |
| **About** | how it works, the risks, what is not proven |

Design: one token system for light and dark, a calm premium look, mobile first (PWA), no external libraries (no
supply-chain risk, NOK 0), so Lovable can later restyle it without touching behaviour.

---

## 9. How the system keeps improving

- **Weekly audits continue** and gain execution checks: ledger vs exchange reconciliation, decision completeness (one
  per hour), kill-switch state, cap and limit compliance, fee totals, and the website's read/write surface.
- **Strategy changes are versioned.** A new strategy is registered first, tested on development data only, compared
  against the running one in a shadow, and switched only with the owner's approval. The chart marks the switch.
- **Research continues unchanged:** the 2,000-hour reading (≈ 2026-12-14), the direction readings, the news verdict,
  the funding re-test. Their verdicts decide which inputs the strategy may use.
- **The website shows the research state**, so a better model shows up in the app the day it is approved.

---

## 10. Phases, tests and exit gates

| Phase | Work | Verified by | Needs |
|---|---|---|---|
| P0 | investigation, evidence, plan | this document | — |
| P1 | the owner's decisions (section 12) and the CLAUDE.md decisions-log entry that replaces principle 10 | the owner's reply | **the owner** |
| P2 | execution core: strategy, sizing, risk, idempotent orders, ledger, reconciliation, simulated exchange | unit tests, mutation guards | — (in progress) |
| P3 | storage and security: tables, constraints, the owner's write path, the security check | integration tests, the live security and role checks | approval to change production |
| P4 | exchange adapter for the chosen venue; location check; dry run and the venue's test mode if it has one | tests against recorded answers, a dry run with no order, then one minimum-size order watched by the owner | the venue, the account, the key (owner) |
| P5 | wiring into the hourly run as an isolated step; its own alarm | live runs observed; the record unaffected | approval |
| P6 | the website on demo data, then on real data | browser checks in both themes and at phone width; then the owner's two-factor login test | approval to publish |
| P7 | go-live: the owner funds ≤ the cap and switches to live | the first trades reconciled; the kill switch tested live | **the owner** |
| P8 | continuous: weekly audits, research, versioned strategies | weekly reports | — |

---

## 11. NOK 0 budget

| Item | Cost | Note |
|---|---|---|
| GitHub Actions, GitHub Pages | 0 | public repository |
| Supabase (database, two-factor auth, Edge Functions) | 0 | free tier; 49.6 of 500 MB used |
| healthchecks.io | 0 | existing |
| Anthropic API | unchanged (~$10–12/month) | existing, not increased |
| Exchange account and API | 0 | the venue's trading and deposit fees come out of the traded capital; they are the main cost of the strategy itself (section 2.2) |
| Libraries | 0 | none added to the website; the execution core uses the existing Python stack |

Anything that would cost money is stopped and raised first.

---

## 12. Decisions

**Made by the owner on 2026-11-14:**
1. **Principle 10 replaced** (recorded in CLAUDE.md): real-money automatic trading through this layer, hard cap NOK 500
   in code, the owner's cap from NOK 150, the safeguards of section 3.1.
2. **Venue: Firi.**
3. **Go live after tests:** the production tables and the hourly step are added once the tests and a no-order dry run
   pass; the first real order is a minimum-size one the owner watches.

**What is left, in order:**
1. **The owner:** a Firi account with NOK deposited (the cap, e.g. NOK 150); an API key with trading rights; the key,
   client id and secret stored as the GitHub repository secrets `FIRI_API_KEY`, `FIRI_CLIENT_ID`, `FIRI_SECRET_KEY`.
   I never see or type them.
2. **The owner's choice on turnover for Firi** (section 2.4): keep `rule-1.0` (up to 4 trades a day, 6 h minimum
   hold), or a stricter `rule-1.1` (for example 1 trade a day and 24 h minimum hold) before the first real order.
3. **Me, after 1:** the storage (tables, the owner's write path, the security check), then the dry run: a signed,
   read-only balance check from a GitHub runner. If Firi refuses GitHub's US addresses, orders move to a Supabase Edge
   Function in the EU (free tier); that design is in section 5.
4. **The owner's go-ahead to publish the website** (GitHub Pages, free; the data behind the two-factor login).

---

## 13. Risks

| Risk | Control |
|---|---|
| The strategy loses money (no demonstrated edge) | caps, loss limits, low turnover, honest labels, benchmarks; the owner decides |
| A bug places repeated or oversized orders | idempotent client ids, one order per hour, hard cap in code, reconciliation, kill switch |
| A stolen key | trade-only, withdrawals off, never in the browser or repository |
| The venue refuses the runner's location | verify first; EU Edge Function fallback |
| Execution failure hides behind a green job | its own alarm and heartbeat |
| Execution changes the evaluation | read-only access to the prediction record; tested isolation |
| Tax reporting burden | complete trade export with NOK values |
| No database backup (existing open risk) | the ledger is also reconstructable from the exchange's history; backup stays the owner's open decision |

---

## 14. Progress log

- **2026-11-14:**
  - P0 done (sections 1–13), with the live-record replay (section 2.1).
  - The owner's decisions recorded (section 12; CLAUDE.md principle 10 and the decisions log;
    `docs/FUTURE_EXECUTION_ARCHITECTURE.md`).
  - P2: `agent/execution` (strategy `rule-1.0`, the engine with idempotency and reconciliation, the simulated
    exchange, fictional demo data); 18 tests.
  - P4 code: the Firi adapter (`agent/execution/firi.py`); its signature matches Firi's reference implementation
    (Node.js, the documentation's own example); 6 tests against a fake connection, no request sent.
  - 12 mutation guards on the trading rules (area `execution`).
  - P6: the website (`web/`): ten pages, light and dark, phone and desktop, the value chart with 13 periods, on
    fictional data; checked in a browser at 1280 px and 375 px, with no sideways overflow on any page.
  - Nothing in production, the database, the workflows or any published page changed.
  - Correction, the same day: the demo file first lived in `web/data/`, which the repository's `data/` ignore rule
    (it protects the research snapshots) kept out of the commit. It now lives in `web/fixtures/demo.json`, and a test
    requires it to be the fictional 2030 run and the website's only JSON file.

## 15. Sources (accessed 2026-11-14)

- Firi API trading: <https://firi.com/about/trading-api>
- Firi fee figure (secondary, unconfirmed): <https://sandboxfiri.com/articles/cheap-crypto-exchange>
- Binance location restriction (HTTP 451): <https://dev.binance.vision/t/wrong-binance-geographic-restriction/16983>
- Skatteetaten on virtual assets: <https://www.skatteetaten.no/bedrift-og-organisasjon/rapportering-og-bransjer/bransjer-med-egne-regler/internett/skatte--og-merverdiavgiftsmessig-behandling-av-bitcoins-og-andre-virtuelle-valutaer/>
- Kraken and Binance fees: `research/COST_ASSUMPTIONS_2026-10-16.md`
