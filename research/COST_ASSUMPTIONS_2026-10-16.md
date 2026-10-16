# Trading-cost assumptions, checked against primary sources (2026-10-16)

**What this is:** a dated, read-only check of the fee, spread and slippage assumptions used for the *descriptive*
economics of the research tracks (master plan addendum 2026-10-16, item 7). It is a note for future economic
analysis only.

**What it is not:**
- It changes **nothing** registered. E034's cost grid (`research/DIRECTION_TRACK.md` section 9: 0.11% / 0.085% /
  0.02% one way), its criteria, thresholds and protocol stay exactly as registered.
- It is not a venue choice, not trading, and not a plan to trade. The project is analysis only (principle 10).

**No trading venue is selected.** The project's market data comes from Binance's public BTC/USDT spot data, so
Binance is the natural reference. Other venues are listed to show the range a different choice would bring. Which
venue a person can legally use depends on where they live; that is not assessed here.

## 1. Exchange fees, from the exchanges' own pages (accessed 2026-10-16)

| venue | product, pair | account tier | maker | taker | source | status |
|---|---|---|---|---|---|---|
| Binance (global) | spot, e.g. BTC/USDT | Regular User (the base tier) | 0.100% | 0.100% | [binance.com/en/fee/schedule](https://www.binance.com/en/fee/schedule) | **verified** |
| Binance (global), fees paid in BNB | same | Regular User | 0.075% | 0.075% | same page ("BNB 25% off") | **verified** |
| Binance (global) | same | VIP 1 | — | — | same page: VIP 1 needs ≥ 1,000,000 USD of 30-day volume and ≥ 5 BNB | threshold **verified as displayed**; VIP 1 rates not recorded |
| Binance.US | spot | VIP 0 (< 500,000 USD 30-day volume) | 0.1000% (0.0750% with BNB) | 0.1000% (0.0750% with BNB) | [support.binance.us, article dated 2025-03-05](https://support.binance.us/en/articles/9843536-binance-us-launches-trading-fee-discount-and-vip-program-with-bnb) | **verified**, but the article is from 2025 and its BNB discount is "subject to change" |
| Kraken Pro | spot crypto, e.g. BTC/USD | Level 1 (USD 0+) | 0.40% | 0.80% | [kraken.com/features/fee-schedule](https://www.kraken.com/features/fee-schedule) | **verified** (Level 2, USD 2,500+: 0.30% / 0.60%; Level 3, USD 10,000+: 0.22% / 0.38%) |
| Kraken (support article) | spot | range | −0.02% | up to 0.80% | [support.kraken.com, "How trading fees work"](https://support.kraken.com/articles/201893638-How-trading-fees-work-on-Kraken), updated 2026-10-01 | **verified** (a range only; the article's worked examples are illustrations) |
| Coinbase Advanced | spot | lowest tier | ? | ? | help.coinbase.com and coinbase.com/advanced-fees refused the fetch (HTTP 403) | **UNVERIFIED.** Third-party summaries disagree, and one says the full schedule needs a log-in |
| OKX | spot | regular | ? | ? | okx.com/fees showed no figures to the fetch | **UNVERIFIED** |

**How these were checked:**
- Each page was read by an automated fetch, which summarised it.
- For Binance's fee page, a script-rendered page, the figures are as the fetch returned them on 2026-10-16. They
  should be confirmed in a browser before any real decision rests on them.
- Exchanges change their schedules (Kraken's base tier changed in 2026, by third-party accounts).
- No figure here may be quoted later without its date.

## 2. Spread and slippage on Binance BTC/USDT (measured 2026-10-16 14:03:49 UTC)

One snapshot of the public order book: `data-api.binance.vision/api/v3/depth`, 5,000 levels, the project's own data
mirror; read-only, no account.

| | value |
|---|---|
| tick size | 0.01 USDT |
| spread | 1 tick, about **0.00001%** of the price (half-spread about 0.000006%) |
| market order of 1,000 USDT: average fill away from mid | buy 0.00001%, sell 0.00001% |
| 10,000 USDT | buy 0.00001%, sell 0.0038% |
| 100,000 USDT | buy 0.00001%, sell 0.0098% |
| 1,000,000 USDT | buy 0.00001%, sell 0.023% |

**What this can and cannot say:**
- It is a single moment. Depth changes by the hour and thins out in fast markets, so this is not a statistical
  estimate.
- It does not include the price moving between a signal and an order. E034 handles that separately: it enters each
  hour at `price_at_prediction`, the last trade price when the prediction existed, not at the reference close.

## 3. What follows, as a range rather than one number

One way, a round trip is twice:

| situation | fee | spread and slippage, small order (≤ 100,000 USDT) | one way | round trip |
|---|---|---|---|---|
| Binance regular account, taker | 0.100% | 0.000–0.010% | **0.100–0.110%** | 0.20–0.22% |
| Binance regular account, taker, fees in BNB | 0.075% | 0.000–0.010% | **0.075–0.085%** | 0.15–0.17% |
| Binance regular account, maker (limit orders) | 0.100% | about 0 (no slippage, but fills are not guaranteed) | **0.100%** | 0.20% |
| Kraken Pro, Level 1, taker | 0.80% | not measured | **≥ 0.80%** | ≥ 1.60% |
| Kraken Pro, Level 3, taker | 0.38% | not measured | **≥ 0.38%** | ≥ 0.76% |

**How this compares with E034's registered grid (not changed):**
- E034's *standard* 0.11% one way sits at the top of the verified Binance regular-account taker range.
- Its *discounted* 0.085% sits at the top of the BNB range. Both are defensible as registered.
- Its *optimistic* 0.02% is **below every verified regular-account rate**. That includes Binance's maker rate,
  which is 0.100% at the base tier. Section 9 of the protocol already calls it "below what a retail account pays":
  it stands for a high-volume or promotional rate, not something a regular account can get.
- At Kraken's base tier, costs would be several times higher than anything in the grid.

So any economic reading of the direction track should be stated against the Binance standard figure first, and
noted as optimistic for other venues.

## 4. What remains uncertain

- **Coinbase Advanced and OKX:** unverified.
- **Binance's VIP 1 rates, and any zero-fee promotional pairs:** not recorded.
- **Spread and slippage:** one snapshot only. They are not measured at all for other venues or in volatile hours.
- **Jurisdiction:** which venue and which product a person can use was not assessed.
- **Funding costs** of any derivative used to go short: not modelled. Protocol section 9 already reports "sign" for
  comparison only.
