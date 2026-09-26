# Research roadmap — progress tracker

Operating rules: `CLAUDE.md` → "Research phase". Every experiment: `EXPERIMENTS.md`.
A phase is marked complete only when its objective is met, tests pass, outputs were
inspected, and no known important error remains. A quality gate (tests, outputs,
point-in-time behaviour, data quality, side effects, live = research) runs before
every new phase.

## Checklist

- [x] **PHASE 1 — Correctness, leakage, data quality, automation** (2026-09-19/20; pipeline 0.2.0; `CHANGELOG.md`; external trigger live 2026-09-20 08:12 UTC)
- [x] **PHASE 2 — Verification and correctness testing** (84 tests: cutoffs, news timing, future-data guards ×3, horizons across gaps, candle quality, fallback, outcome timing, replay = live, formulas pinned; live runs inspected)
- [x] **PHASE 3 — Target and label definition** (`agent/research/labels.py`: binary and three-class, fixed or point-in-time volatility-scaled band, five horizons; tested. *Primary horizon deliberately undecided — see adjustment 3*)
- [x] **PHASE 4 — Baseline evaluation** (E001: scoring 0.1.0 vs random / majority / always-HOLD / momentum / MA / buy-and-hold, five horizons, block-bootstrap CIs, per year, per regime, confidence reliability. Criterion not met anywhere.)
- [x] **PHASE 5 — Current feature diagnosis** (E002: per-category rank correlations both periods, decile shapes, regime slices, redundancy)
- [x] **PHASE 7 — Feature ablation** (E002: leave-one-out on the stored replay — see adjustment 1)
- [x] **PHASE 8 — New feature groups** (complete 2026-09-20 except 8.6, deferred until the live news archive is large enough; 8.8 unavailable). Outcome: 47 candidate features across 6 groups; **no directional feature meets the criterion with a usable size**; one consistent tiny *reversal* family at 1–6h (momentum, volume, taker-buy share; |ρ| ≤ 0.05); **two strong move-size predictors** (recent volatility, trade intensity) plus a time-of-day effect. Watch list for live re-tests: funding (24h contrarian), dollar/yield 5-day (168h negative).
  - [x] 8.1 Volatility (E003 — magnitude information strong at 1–24h; no directional signal; `tr_mean_14_rel` adopted as the uncertainty input, vol-scaled bands justified)
  - [x] 8.2 Market regime / long-horizon trend (E004 — no consistent directional information; first run caught a harness name-collision bug, now guarded by tests and a tripwire)
  - [x] 8.3 Derivatives (E005 — funding/premium usable, OI/liquidations UNAVAILABLE; contrarian sign consistent 2019–23 but absent 2024–25 → not adopted, on the live watch list)
  - [x] 8.4 Macro / cross-market (E006 — daily bars visible from 22:00 UTC; no pass; dollar/yield weekly negative sign a near-miss → live watch list)
  - [x] 8.5 On-chain (E007 — daily series usable with a D+1 06:00 UTC rule; no pass; sign flip between periods)
  - [ ] 8.6 News improvements — **deferred**: only the live archive is usable (no history; LLM-knowledge leakage), and it is far too small (tens of hours). Re-opens when ≥ 500 live hours with news exist (~3 weeks after go-live).
  - [x] 8.7 Microstructure (E008 — taker-buy share: consistent *reversal* at 1–6h, tiny; trade intensity: strong move-size predictor; depth/spread UNAVAILABLE)
  - [ ] 8.8 Social — UNAVAILABLE/UNSAFE (no free, timestamped, reproducible history); no experiment
- [x] **PHASE 8A — AI component tests** (E009 — 8 of 9 criteria pass; news scorer reliable/stable/discriminating with a small order-sensitivity bias recorded; explainer faithful and provably decision-neutral; "does news add information" deferred to 8.6)
- [x] **PHASE 6 — Walk-forward / time-series validation** (2026-09-20; `agent/research/walkforward.py`, 8 unit tests + E010 on real data. Design: purge = horizon, embargo 24h, quarterly test blocks, ≥ 365 training days, expanding primary / rolling 730d robustness, optional purged calibration slice. E010: all five pre-registered checks pass — a memorising model scores exactly chance, a last-label model gets no head start, expanding/rolling test blocks identical, scoring 0.1.0 reproduces its E001 character (0.478) on the same 59,775 rows.)
- [x] **PHASE 9 — Model architecture research** (experiments 2026-09-20; gate + report 2026-09-21). E011 (direction, 15 runs): no pass anywhere — no combinable directional signal in the free data; the 1h reversal family gives ~+2 points of accuracy with zero return edge. E012 (move size, 6 runs): **pass at 1h** (Brier −15%/−9%, ρ 0.45/0.36, accuracy +15/+10 points), 6h near-miss, 24h no pass.
- [x] **PHASE 10 — Weight and threshold optimisation** — **closed without optimisation (decision recorded 2026-09-21, see adjustment 6).** E001/E002 showed none of the four categories carries direction; E011 showed a fitted combination of them plus every usable candidate input still has zero return edge. There is nothing to re-weight towards, so any weight/threshold search would only fit noise (rule 4). Not revisited unless a later pre-registered test finds a directional input.
- [x] **PHASE 11 — Probability calibration** (E013, 2026-09-21: Platt scaling on a purged 90-day slice, chosen by the pre-registered rule; validation ECE 0.014, ≤ 0.03 every year since 2018, ranking preserved; raw and isotonic fail. Direction probability stays ≈ base rate, stated as such — nothing to calibrate there. Tests: `tests/test_calibration.py` (calibrator sees only the slice; over-confidence corrected; monotone; refused without a slice).)
- [ ] **PHASE 12 — Final untouched holdout evaluation** (once) — **PREPARED 2026-09-21, SEALED BY DECISION 2026-09-21 (master operating prompt).** Pre-registered in `research/experiments/E014_holdout_evaluation.json`; script `agent/research/holdout_eval.py` (`--dry-run` reproduced validation; `research/HOLDOUT_ACCESS.log` must not exist). **Moved to after the backend readiness gate** (see "Backend hardening roadmap" below): the holdout opens only when Phase 13 is mature, backend correctness work is complete, the research version under confirmation is frozen and named, and a final no-access audit passes. No deadline. If maturity is ambiguous, ask the user — never assume.
- [~] **PHASE 13 — Live / paper research monitoring** — hourly predictions + outcomes running since 2026-09-19; **weekly report built 2026-09-21** (`python -m agent.research.weekly_report` → `research/monitoring/weekly_<date>.md/.json`; 7 unit tests): health (missed hours, delays, sources, errors, outcome coverage), the live scoring 0.1.0 record with intervals once ≥ 2 blocks of hours exist, the E012 + Platt move-size **paper** record on live hours (after the fact, from point-in-time candle features; model fitted before the holdout) with a built-in check that the live outcome tracker's returns equal the research candles' (46/46 hours agree to 1e-16), and the watch-list counters. Open decisions (user): run the weekly report on a schedule (a workflow that commits the report would also reset GitHub's 60-day inactivity clock); add a live *shadow* computation of the move-size probability to the hourly job (a separate table; would not touch the signal). First report: `research/monitoring/weekly_2026-09-21.md`. Remaining: watch-list re-tests at 6 months; news evaluation at 500 hours; Phase 12 first.

## Backend hardening roadmap (adopted 2026-09-21 from the master operating prompt; runs after/alongside Phase 13, before the final holdout decision)

Order is binding unless a documented reason changes it. Each stage: check the system → do the work → test → audit → commit.

- [~] **Phase 13 (continuing)** — weekly report built; **live shadow record running from GitHub since 2026-09-21 19:12 UTC** (first GitHub-side row 18:00 UTC: `live_close_match = true`, git SHA stamped; first graded row's return equals the live tracker's to 1e-16); news accumulating with availability-vs-retrieval timing; audits: parity (§4), drift (§5), health (§1) weekly. Continues until the Phase H checkpoints.
- [x] **A — Live / research parity** (2026-09-21): rules table + known differences in `docs/research/parity.md`; automated check `agent/research/parity.py` re-analyses every live hour with the research replay on today's candles and compares close, volume, 9 indicators, 4 category scores + weights and the news-free overall score — **44/44 hours identical**, runs in every weekly report (§4); `tests/test_parity.py` (perturbations break, unjudgeable rows skipped explicitly, live tracker = research labels across a gap). Shadow model parity: window features = full-series features (test), two implementations agree on live hours.
- [x] **B — Data pipeline hardening** (2026-09-21, `fee6016`): kline schema validation, one retry per endpoint (none on rate limits), stale-provider rule (newest candle must be the last closed hour → fallback / loud failure), zero-volume count, bounded RSS download (15 s), bounded AI calls (90 s / 2 retries), DB connect timeout, `run_meta.code_commit`; `docs/research/data_sources.md` documents every source. 12 new tests. Pipeline version kept at 0.2.0 (information rules unchanged; `CHANGELOG.md` records the hardening).
- [x] **C — Failure and recovery testing** (2026-09-21): `tests/test_failure_modes.py` (news model garbage/empty → unavailable not neutral; explainer failure never touches the decision; DB down at save raises; conflict at save leaves the row untouched; late run labels the hour by its candle; short history lowers completeness; partial model answers flagged) on top of the existing fallback/validation/cutoff/tracker tests; `docs/research/failure_modes.md` — every failure, its behaviour, where it is recorded, whether a prediction is produced, and the proving test; residual risks listed. News scorer hardened: an empty model answer is an error (weight 0), a partial one is flagged in the stored detail.
- [x] **D — Idempotency / duplicate safety** (2026-09-21): every write is `INSERT … ON CONFLICT DO NOTHING` on a UNIQUE key (predictions `as_of`; outcomes `(prediction_id, horizon)`; shadow `as_of`), the shadow outcome is `UPDATE … WHERE outcome_status IS NULL`, the tracker queries only ungraded rows, and a repeated hour exits before any AI call. Proven against **real Postgres** in a self-created, self-dropped scratch schema (`tests/integration/test_db_idempotency.py`, run with `BITCOIN_AGENT_DB_TESTS=1`; guarded so it refuses to run if the pooler ignored the schema switch): 6/6 pass — double save, retry after a failed save, double grading in both orders, tracker run twice, shadow double save/grade, constraints exist. News is stored per run as that run's input snapshot (no separate ingestion table; first-seen time derivable).
- [x] **E — Database integrity** (2026-09-21, applied to the live database via `init_schema()` + `ensure_schema()`): `cutoff_at`/`pipeline_version` NOT NULL; CHECK `cutoff_at = as_of + 1h`, CHECK `fetched_at >= cutoff_at`; outcome status CHECK (was missing on the live table — migration gap found and closed) + status/values consistency CHECK; **append-only triggers** on predictions and outcomes (UPDATE/DELETE refused; a deliberate correction must disable the trigger visibly); shadow rows: prediction part immutable, outcome written once, deletes refused. Proven in the scratch-schema integration test (7/7). Model artefacts are immutable: the export refuses to overwrite and a canonical-JSON hash is pinned in `tests/test_shadow.py`. Experiment records live in git.
- [x] **F — Reproducibility** (2026-09-21, `docs/research/reproducibility.md`): what each stored prediction / shadow row / experiment carries; demonstrated — 44/44 live hours rebuilt by the replay, every shadow probability rebuilt from stored features + artefact (1e-12), E012 1h **re-run bit-identical** from its recorded command, frozen model = research fit, tracker = label rule; no secret-like strings in tracked files or stored rows; `.env` ignored, `.env.example` placeholders only. Known limits documented (fallback rows, LLM non-determinism, snapshots re-downloadable).
- [x] **G — Versioning** (2026-09-21, `docs/research/versions.md`): every identifier, where it lives, when it must change, and the check that catches a silent change — **golden test pins scoring 0.1.0 end to end** (`tests/golden_scoring_0_1_0.json`); **feature fingerprint** stored in each model artefact and re-checked at load (old coefficients can never run on changed feature definitions); artefact hash pinned; `SCHEMA_VERSION` = 3 written to `schema_meta` and shown in the weekly report; git SHA in every GitHub-produced row. v1 artefact regenerated to add the fingerprint — model numbers and training metadata verified identical before replacing.
- [~] **H — Live evaluation of E012/E013** — protocol **pre-registered** in `research/LIVE_EVALUATION.md` (2026-09-21): prospective shadow rows only; criteria copied from E012/E013; 48h block-bootstrap intervals once ≥ 192 hours; checkpoints at 500 / 2,000 / 5,000 hours; regime slices descriptive only; failure demotes, never retunes. Machinery in the weekly report (§3, intervals gated by sample size). **Continuing** — the verdicts depend on hours that do not exist yet.
- [x] **I — Drift / regime monitoring** (2026-09-21, machinery built; running weekly): `agent/research/drift.py` compares live shadow inputs, calibrated probabilities, large-move share, blank share and fetch timing against **frozen development reference distributions** (`research/monitoring/reference_distributions_v1.json`, built once, never updated from live data); descriptive flags (median shift > 1 dev IQR, > 10% outside the dev 1–99% band, outcome share outside its interval, > 5% blanks), never below 100 rows; weekly report §5. Calibration drift is covered by Phase H's reliability buckets. 4 tests. A flag means investigate and document — never retrain.
- [ ] **J — News component maturity** — **live observations 2026-09-22 (64 corrected-pipeline runs), which already shape the design:**
  (a) **the input barely moves**: 2,140 headline-slots but only **114 distinct stories**; the average story is scored **18.8 times** (one, 63 times) because it stays inside the 24-hour window, and the resulting news score changes by only **0.046 per hour** on a [−1, +1] scale. A near-constant input cannot explain hourly variation — any Phase J test must treat the news score as a slow-moving, strongly autocorrelated series, not 500 independent observations.
  (b) **it has never been negative**: 47 hours with a score, range **+0.03 to +0.55**, mean **+0.28**, so news adds roughly +0.04 to the overall score every hour. Whether that is the world or the scorer needs testing — E009 checked sign correctness on crafted headlines, never the calibration of the aggregate.
  *Update 2026-09-24 (E025, 97 usable hours):* no longer true — **5 hours were negative** (minimum −0.032); mean +0.224, sd 0.133. Still strongly positive on average.
  **(d) E025 (2026-09-24) sized the test before anyone looks at news against outcomes** (`research/results/E025/`; it read the news score only). The score's autocorrelation is 0.88 at 1 h, 0.56 at 6 h, ≈ 0 by 24 h. Because next-hour returns are close to independent, **the 1-hour test loses nothing to that persistence**, but the 6h and 24h tests do (variance inflation ≈ 5 and ≈ 12). Smallest detectable correlation (80% power) at 500 usable hours: **0.125 (1h), 0.27 (6h), 0.42 (24h)** — far above anything this programme has ever found (|ρ| 0.05–0.08). Detecting 0.05 needs **≈ 3,140 usable hours at 1h** (~4½ months), ≈ 15,000 at 6h and ≈ 35,000 at 24h.
  **Design adopted from E025, registered before any news–outcome figure exists:** the primary news test is **1h direction** (Spearman of the news score with the next-hour return, 48h block bootstrap, 500 resamples); **500 usable hours = a first look with no verdict** (at that size the interval is also liberal — about 9% false positives instead of 5%, simulated and pooled over two independent seeds); **a verdict only from 3,140 usable hours**; 6h and 24h are descriptive only, since no feasible record could power them. Secondary hypotheses (e.g. news *volume* against move size) are to be registered before the verdict point, not after.
  (c) **95% of what the news model is paid to read, it has already read.** Caching a score per story URL would cut that cost ~19× and make it deterministic per story, but it changes the call's context (E009 measured a small order/context sensitivity), so it is an option for the user, not a unilateral change.
  Original scope (when ≥ 500 trustworthy live hours; 43 on 2026-09-21): relevance, sentiment, order, duplicates, first-seen timing, sources, volume, novelty; stays separate from the numerical core until evidence supports integration. Audit note 2026-09-21: every stored item carries headline, source, url, availability time (later of published/updated), the run's `fetched_at` is the retrieval time, undated items are excluded, duplicates counted; first-seen time is derivable (earliest `fetched_at` containing the url). Summaries contain raw HTML — cleaning them would change the scorer's input and is therefore a controlled change for Phase J, not now.
- [~] **K — Move-size model maturity** — prospective evaluation running (Phase H protocol); drift watch (Phase I). **Deferred by decision (2026-09-21):** threshold / horizon variants (e.g. the 6h near-miss) are not re-tested until the 1h model has ≥ 2,000 prospective hours — testing variants now, with the same development data, would be a search. When re-opened: one pre-registered experiment per variant, logged as E0xx.
- [ ] **L — Directional research only if justified** — **nothing justified now** (2026-09-21): E011 is the standing null; the live watch list (funding 24h, dollar/yield 168h at ≥ 6 months; news at ≥ 500 hours) is the only planned source of new evidence. Any test follows the pre-registration template. The null is accepted, not worked around.
- [x] **M — LLM robustness** (2026-09-21): `tests/test_llm_robustness.py` (SDK timeout / rate-limit / connection / overload errors propagate from both calls and are recorded by the orchestrator; explainer with no text or blank text is an error, never an empty success; the news schema rejects NaN, ∞, out-of-range and missing fields; clients are constructed bounded) + `tests/test_failure_modes.py` (empty / partial model answers) + `tests/test_explainer_isolation.py` (decision-neutral by construction) + E009 (repeatability, relevance, order sensitivity on the real model). Explainer hardened: blank output → `explanation_error`. LLM authority unchanged: news → one structured score; explanation after the decision.
- [x] **Security audit** (2026-09-21, `docs/ops/security.md`): secrets inventory and scans (tracked files, stored rows, logs — clean); workflows set to `permissions: contents: read`; psycopg errors do not echo the DSN; Vault-held dispatch token; research-only boundary confirmed (no execution code exists). Open items: least-privilege DB role (user action, low urgency), healthchecks.io heartbeat, PAT renewal 2027-09-20.
- [x] **Performance / reliability review** (2026-09-21, `docs/ops/performance.md`): dispatch runs median 54 s (30–67 s) of a 15-min budget, ~8 Binance + 3 RSS + 2 Anthropic calls and ~20 short DB connections per hour, no unnecessary recomputation, trigger 100% since the fix; **no optimisation warranted** (connection reuse would save seconds and add shared state).
- [x] **Backend readiness gate — assessed 2026-09-21** (`docs/research/readiness_gate.md`): every engineering, security and maintainability item verified except two external user actions (healthchecks.io heartbeat; least-privilege DB role — mitigated by append-only triggers). Research items verified; prospective live evidence has only just begun (by the calendar, not by a defect). **Judgement: engineering is release-candidate quality for a read-only frontend that shows the research state truthfully. The holdout stays sealed.** Requirements pinned exactly; README rewritten.
- [ ] **Final holdout decision → one-time confirmation (Phase 12) → final backend confirmation → frontend.** Holdout: sealed, waits for the Phase H checkpoints and the user's decision. Frontend: may start as a read-only consumer of the record at any time (contract in `readiness_gate.md`); the backend continues under the same discipline.

## 2026-09-22 (evening) — second pass: sections 14-25 and 39-42 of the master plan

Added after the readiness gate, in the order the master plan's operating loop sets out. None of
it changed anything that runs.

- [x] **Sections 14-19 — signal discovery, ablation, redundancy, feature count** (E018). Applied to
  the only model that ever passed a pre-registered test. One of its nine inputs is arithmetic;
  six carry 99.4% of the skill. Also found and recorded a defect in my own pre-registered rule.
- [x] **Sections 24-25 — model selection** (E019, E020). The model beats a rule that needs no
  fitting by 2.47x, and neither gradient-boosted trees nor an interaction model clears the bar to
  replace it. Its complexity is now defended rather than assumed.
- [x] **Section 20 — threshold definition** (E021). Pays the debt recorded on 2026-09-19. The fixed
  target stands; the decomposition it produced is the more valuable output.
- [x] **Sections 14-19 again, on the isolated signal** (E022, exploratory). Which inputs carry the
  part that is genuinely the model's. Recorded as a hypothesis with its cautions attached.
- [x] **Sections 39 & 52 — the backend contract** (`agent/api/state.py`, `docs/api/contract_v1.md`).
  Read-only, versioned, tested. Transport deliberately undecided, with a recommendation.
- [x] **Section 42 — observability review** (`docs/ops/observability.md`). Sixteen failure paths
  audited; one invisible failure found and fixed; one gap that is not code (the heartbeat).
- [x] **Section 30 — the last untested failure**: a stale database schema now stops the run before
  anything is written. Verified against the live database before being committed.
- [x] **Section 50 — readiness gate revision 2**: the 22 categories scored individually,
  19 PASS / 3 PARTIAL / 0 FAIL / 0 UNKNOWN.
- [x] **Section 36 — the open user actions written up properly** (`docs/ops/open_user_actions.md`).

### Where the research programme actually stands

**There is no non-gated research work left.** Every remaining item waits on one of three things:

| waiting on | items |
|---|---|
| elapsed time | 8.6 / J (news, at 500 live hours with news — 69 now), H (checkpoints at 500 / 2,000 / 5,000 prospective shadow hours — 19 now), K (move-size variants at 2,000), the watch-list re-tests at 6 months |
| a user decision | Phase 12 / the sealed holdout |
| evidence that does not exist | L (directional research — nothing justified; E011 is the standing null) |

And one thing that argues against manufacturing more work: **validation wear**. Twenty-plus
experiments have now examined the validation period. Continuing to mine it would produce
findings of steadily decreasing trustworthiness while spending the credibility of the only clean
arbiter left. The correct action is to stop and let time pass, which is what the monitoring
rhythm is for.

## 2026-09-23 — security finding, schema 4, and the migration entry point

Resumed from the 2026-09-22 pause under the master-plan addendum (explicit exit gates, hard vs
soft quality gates, validation wear enforced, security alerts first). The planned first step —
wiring `agent.api.publish` into the hourly job — was deliberately put behind a higher-priority
item: a Supabase security warning.

- [x] **Security: every table was reachable through Supabase's public API** — RLS off on all six
  tables, full privileges for `anon`/`authenticated`. Investigated before touching anything; no
  sign in the data of any outside write. Closed with two independent layers in every schema file,
  applied live, proven by behaviour (48/48 anonymous probes refused) and per layer against real
  Postgres; detected every 3h by the watchdog. `docs/ops/security_2026-09-23_public_api_exposure.md`.
- [x] **Schema version 4**, applied database-first then code, after changing the schema guard to
  require "at least" the code's version (exact equality made every migration a failure window).
- [x] **My 2026-09-21 security audit was wrong** — it never checked what the platform exposes by
  default. The readiness gate carries a dated correction: Security was really FAIL until today.
- [x] **One migration entry point (`python -m agent.migrate`), no schema DDL on the hourly path.**
  Found while fixing the above: the shadow step re-applied its schema every hour, publishing did
  the same, and the documented fresh-database command built only one of three schema files.
  Acceptance criteria set before deploying: unit (every .sql migrated, in order, one transaction,
  a failing file commits nothing, no hourly-path module applies schema SQL) PASS; integration 11/11
  through `migrate()` PASS; `python -m agent.migrate` on the live database PASS (schema 4, nothing
  exposed); manual run of the new shadow code against the live database PASS (found the hour,
  exited 0, no errors); **first scheduled run on the new code PASS** — GitHub's 15:09 UTC slot (72938ce,
  which contains the change) wrote the 14:00 prediction and its shadow row, every step green, 0 shadow
  errors; the 15:12 dispatch then took the already-saved path, also all green.
- [x] **Test the tests (`tools/guard_mutations.py`)**: 18 critical guards broken on purpose — cutoff, news
  cutoff, two feature leaks, label horizons, outcome timing, walk-forward purge, the holdout truncation, both
  scoring 0.1.0 gap bugs, stale data, the schema guard, the staleness check, the prospective rule, the
  exposure detector, the confidence label — and **all 18 caught**, each by the test written for that
  property. Two controls make that meaningful: the unmutated suite passes, and a comment-only change survives.
  **Round two (8 more, research-validity guards) found two real gaps**: the historical replay (the engine behind
  E001/E017) could read a candle from the future without any test noticing, and E023's evaluation could train its
  two compared models on different rows. Both closed with new tests, each proven to kill its mutation. **26 of 26.**
  Two more for the AI cost record, then **one full pass: 28 of 28 caught, both controls held, every file
  restored byte for byte** (2026-09-23 ~15:45 UTC).
- [x] **E023 pre-registered (NOT run):** this week's findings (E018–E022) registered as secondary hypotheses
  for the sealed holdout, because validation wear means they can only be confirmed on clean data. Extending
  `holdout_eval.py` for them, and dry-running it on validation, is now a prerequisite of unsealing.
- [x] **E024, power of the live checkpoints:** E012's 2,000-hour verdict is sound; E013's 5,000-hour bucket rule
  fails a perfectly calibrated forecaster 8% of the time and the real model 27%; ECE above 0.03 is expected at
  the 500-hour first look. No rule changed — the protocol now states these error rates.
- [x] **Holdout readiness, part of it:** E023 made testable (`agent/research/holdout_secondary.py`) and dry-run on
  validation; **E014 amended while sealed** — it still named scoring 0.1.0 as object A while the live signal is 0.2.0,
  so registration and code disagreed about what the one-time run would test. The script now refuses to start on an
  unregistered scoring version, before loading a single candle. Nothing about the seal changed.
- [x] **Wire `agent.api.publish` into the hourly workflow** — deployed 2026-09-23 ~15:20 UTC, last among
  the real steps and unable to fail the job. Acceptance: the next hourly run is green in every step and
  `backend_state.generated_at` advances to that run's time, describing the hour it just saved. **PASS** at
  the 16:12 UTC run (59c4c76): every step green, snapshot written 16:13:14 describing the 15:00 hour, health ok.
- [x] **Live checkpoints prepared before their data exists (2026-09-23 ~20:00 UTC, 42 of 500 hours):**
  `python -m agent.research.live_checkpoint` computes the registered 500 / 2,000 / 5,000-hour readings
  exactly as `research/LIVE_EVALUATION.md` says — on a fixed prefix (the first N prospective hours,
  clarification 8), with E024's own pass-rule code (9), and with the 5,000-hour regime cut points frozen
  now from development data (10). It refuses to run early; nothing is computed on live data yet.
- [x] **Security review on the user's instruction (2026-09-23 evening):** root cause (default privileges)
  closed live; detector covers views, functions, default grants; `net` rights proven unrevocable by the
  project (Exposed-schemas setting = the user's 10-second check); least-privilege switch made checkable
  (`agent.database.role_check`, `run_meta.db_role`). Details: `docs/ops/security_2026-09-23_public_api_exposure.md`.
- [x] **AI cost measured, not estimated** — every run records the API's own token counts
  (`run_meta.ai_usage`); the weekly report prices them against a dated list-price table. Real reading
  before deploying (one unsaved run, 56 headlines): $0.0164 a run, ≈ $11.80 a month. Deployed
  2026-09-23 ~15:30 UTC. Acceptance: the 15:00 UTC prediction carries `ai_usage` with figures for both
  calls, every job step green. **PASS**: the 15:00 prediction (written 16:12:33 by 59c4c76, 58 headlines) carries
  news 1,782 in / 2,310 out and explanation 509 in / 268 out tokens ≈ $0.0170; shadow row ok, 0 shadow errors.
  (GitHub's own backup slots at :22/:37/:52 and the 15:33 watchdog did not fire this hour — its scheduler, not
  the code; the watchdog's first security check now falls to 18:33 UTC.)

**Quality assessment of the security step** (the addendum's 0-100 per dimension; a summary, never
a substitute for the critical items below it): correctness 95 · robustness 90 · security 90 ·
data integrity 95 · reproducibility 95 · observability 90 · maintainability 88 · performance 95 —
**about 92**. Critical items: exposure closed PASS; no outside writes PASS; live automation PASS
once the scheduled run is confirmed; holdout sealed PASS; no trading capability PASS; whether the
exposure was used to READ data **UNKNOWN** (only the dashboard's API logs can say — recorded as a
user action, and not critical to integrity because nothing was written). The score was not
tuned; the two lowest dimensions are held down by real things — the lockdown block is duplicated
across three schema files (deliberate, so each file stays self-contained), and the least-privilege
role and the API-log check remain open.

## 2026-09-26 — under the pre-500h interim plan (`research/INTERIM_PLAN_PRE_500H.md`)

- Session loop run: 14/14 overnight hours (all `db_role = bitcoin_agent`), 25/25 runs, heartbeat ping on
  every run, 2/2 watchdog runs green after the switch, 0 shadow errors, 103 of 500 prospective hours.
- Watchdog now verifies the jobs' database role and its exact rights (`role_check --connected`).
- Absence readiness: `docs/ops/STATUS.md` / `status.json`; storage and alarm paths checked.
- **Open:** the first watchdog run with the new step (it fails loudly if the secret is not
  `bitcoin_agent`, so a green run proves the watchdog runs under the restricted role).
- **Later the same session:** full mutation run 43/43 (both controls held); the report and the checkpoint
  agree on every point value (test); every stored shadow probability reproduces from its stored inputs
  (106/106, 5e-16) — now an integrity line in every checkpoint; the weekly report checks the candles →
  inputs link too (106 × 9 inputs, 2.9e-15).
- **Drift flag, 2026-09-26 — investigated, documented, nothing changed.** First OUTCOMES flag: large moves
  in 34.3% of live hours [25.2%, 43.4%] vs 47.5% on validation — a **calmer market** (every volatility input
  below its development median, none outside the development range); the pipeline is not the cause (parity
  156/156, shadow inputs identical, tracker = research candles). The model's stated median fell less (0.432 vs
  0.468): a possible over-prediction in a calm market, **not established at 105 hours**. **E026** (pre-registered,
  development data) shows the model family *was* calibrated in calm markets historically — so **WATCH ITEM:**
  if the live over-prediction in calm conditions persists, it is a genuine live deviation, to be read at the
  registered 500-hour first look and judged only at 2,000 / 5,000 hours. Never retuned.

## Resumed 2026-09-25 13:44 UTC — status check, nothing regressed

- **Live record since the last check (as_of 2026-09-24 16:00 → 2026-09-25 12:00): 21 of 21 hours**, 0
  timestamp-rule violations, all Binance, 0 synthetic, 0 news / explanation errors, completeness 1.0;
  every row `db_role = postgres`. 21 shadow rows, all prospective, 0 close mismatches, **0 shadow errors
  ever**; outcomes current; `backend_state` fresh; schema 4.
- **GitHub:** 40/40 hourly runs green (21 dispatched, 19 backup slots), heartbeat steps *skipped* (no
  secret); 4/4 watchdog runs green (≈ 4 of 7 slots fired); 6/6 test runs green.
- **Shadow record:** 84 graded prospective hours of 500 — the first checkpoint ≈ 17 days away
  (≈ 2026-10-12). Separate from the live signal: none of the signal's code imports the shadow package
  and the shadow code only reads the live record — **now enforced by `tests/test_shadow_separation.py`**
  (two mutations prove it); parity 135/135.
- **Report `weekly_2026-09-25.md`:** parity 135/135, drift none; shadow skill +1.1% and ahead of the free
  EWMA rule by 0.0069 Brier on 84 hours (far too few to mean anything; ECE 0.075 at this size is expected, E024).
- **The cost rise explained, not a trend:** news volume follows the week — the weekend of go-live carried
  16–20 headlines, weekdays carry 55–72 (3 sources, no duplicates, a correct 24h window). Cost has only
  been measured on weekdays (since Wed 2026-09-23), so "$13.62–14.20 per 30 days" over-states a month;
  with weekends at about a third of the headlines the estimate is ≈ $12. The report now says "partial
  week" until a full week is measured; the weekend of 2026-09-26/27 settles it.
- **User-owned items:** *Exposed schemas* **DONE** (2026-09-24: `public`, `graphql_public`); least-privilege
  role **OPEN** (`role_check`: NOT READY — the one-command `setup_role` is ready); heartbeat **OPEN** (secret
  not set). Holdout sealed.
- **Same evening, both closed by the user:** the least-privilege role is live — the 19:12 UTC run wrote as
  `bitcoin_agent` in every write path, all green (readiness row 17 → PASS); the heartbeat secret is set and
  the 19:12 run pinged (row 16 → PASS once the ping is seen on healthchecks.io). **To observe next:** the
  first watchdog run as `bitcoin_agent`; healthchecks.io showing the pings.

## Paused 2026-09-24 ~17:45 UTC — resume point (read this first tomorrow)

**State.** `main` = `origin/main`, tree clean; 424 unit tests pass with no database reachable;
19 integration tests; mutation testing 38 of 38; holdout **sealed** (`research/HOLDOUT_ACCESS.log`
does not exist); schema 4; live system healthy (the 16:00 prediction written 17:12 with its shadow
row, `backend_state` refreshed 17:13, 0 shadow errors). E025 done and recorded.

**First thing tomorrow, with the user: the *Exposed schemas* check** (Supabase → Project Settings →
API, `…/settings/api`). The user asked to do it first. Expected: only `public` and `graphql_public`.
If `net`, `vault`, `cron`, `extensions`, `realtime` or `storage` is listed, that is a finding: record
it, and remove it with the user (the project never uses the REST API, so nothing can break).
Then record the result in `docs/ops/open_user_actions.md` item 5, the security record and the
readiness gate (it closes the last UNKNOWN in "critical security").

**Then:** verify the overnight runs (hours, GitHub runs, watchdog) as on 2026-09-24; the remaining
user items (least-privilege role — run `python -m agent.database.role_check` once created; heartbeat
retry); keep the cost flag in view (≈ $13.13 per 30 days, flag at $15). Time-gated: the 500-hour
checkpoint ≈ 2026-10-12, the news first look at 500 usable hours ≈ 2026-10-11, the news verdict at
3,140 usable hours. **Do not** tune on validation, change scoring, swap the frozen artefact, or open
the holdout.

## Resumed 2026-09-24 16:53 UTC — the pause verified, nothing regressed

- **Live record since the pause (as_of 2026-09-23 19:00 → 2026-09-24 15:00): 21 of 21 hours**, none
  missing, 0 timestamp-rule violations, all Binance, 0 synthetic, 0 news / explanation errors,
  completeness 1.0 every hour; every row carries `ai_usage` and `db_role = postgres`. 21 shadow rows,
  all prospective, 0 close mismatches, **0 shadow errors ever**; outcomes current at every horizon;
  `backend_state` refreshed 16:13 describing 15:00, health ok; schema 4.
- **GitHub, verified run by run, not assumed:** 38 hourly runs (20 dispatched from Supabase, 18 by
  GitHub's backup slots), **38 successful**; in both kinds, "Heartbeat ping" and "Heartbeat failure
  signal" show *skipped* — **the heartbeat workflow change `d71c09f` is verified**. 3 watchdog runs, all
  green including the widened security check (GitHub fired 3 of its 7 slots, as before).
- **Weekly audit:** integration + drift 19/19 (the live database still matches the repository);
  report `research/monitoring/weekly_2026-09-24.md` — parity 114/114, drift flags none, AI cost
  $0.0182/run ≈ $13.13/30 days (below the $15 flag, rising with headline volume, 57–66 per hour),
  63 prospective shadow hours evaluated (model ahead of the free EWMA rule by 0.0088 Brier — n far too
  small to mean anything), 97 of 500 hours with a usable news score.
- **User-owned items, checked rather than assumed — none done yet:** heartbeat secret not set (steps
  skipped); `bitcoin_agent` role does not exist (`role_check`: NOT READY; every row written by
  `postgres`); *Exposed schemas* not verifiable from the database — still UNKNOWN.

## Paused 2026-09-23 ~20:15 UTC — resume point (read this first tomorrow)

**State.** `main` = `origin/main`, tree clean. 415 unit tests pass with no database reachable; 19
integration tests on real Postgres; mutation testing 36 of 36. Holdout **sealed**
(`research/HOLDOUT_ACCESS.log` does not exist). Schema version 4. Live system healthy: the 19:00 UTC
prediction was written 20:12:33 by `12a9519`, carrying `ai_usage` and the new `db_role = postgres`
stamp — both verified live. 0 shadow errors. 42 of 500 prospective shadow hours.

**Pushed at the pause, NOT yet seen in a scheduled run** (first thing to check tomorrow): the heartbeat
workflow change (`d71c09f` — `continue-on-error` on the ping, a new *Heartbeat failure signal* step).
Both steps are inert without the `HEARTBEAT_URL` secret, and the YAML was reviewed character by
character, but the next hourly run is the first to read the new file. **Check: the hourly runs after
20:15 UTC on 2026-09-23 are green, and both heartbeat steps show *skipped*.** If a run failed to start,
revert `d71c09f` first and investigate second. Also confirm the watchdog's next run passes with the
widened security check (views / functions / default grants).

**Done today, evening:** API-log check recorded with its limits (earlier days UNKNOWN permanently);
root cause of the exposure closed live (default privileges 24 → 0); detector widened; `net` rights
proven unrevocable by the project; least-privilege switch made checkable (`agent.database.role_check`,
`run_meta.db_role`); heartbeat hardened; news cost decided (~$12/month, flag above $15); report
counting fixes; live checkpoints prepared with three clarifications registered before any data.

**Waiting on the user (none blocking):** *Exposed schemas* check, 10 s — now the single control over
`net`; least-privilege role, ~10 min (steps + `role_check` in `docs/ops/open_user_actions.md` item 2);
heartbeat retry (tell me what failed); optionally dispatch the watchdog from Supabase (GitHub ran 3 of
8 watchdog slots in a day).

**Then, in order:** verify the above; weekly rhythm (report + `BITCOIN_AGENT_DB_TESTS=1` drift check);
run `python -m agent.database.role_check` the moment the user creates the role; the 500-hour checkpoint
computes itself around 2026-10-12 (`python -m agent.research.live_checkpoint`). **Do not:** tune
anything on validation, change scoring, swap the frozen artefact, or touch the holdout.

## Paused 2026-09-22 ~20:15 UTC — resume point

**State.** Tree clean, `main` = `origin/main`, last commit `9c60010`. **296 tests pass, and they
pass with no database reachable** (CI enforces that with an unreachable `DATABASE_URL`).
Holdout **sealed** (`research/HOLDOUT_ACCESS.log` does not exist). Live system healthy: 73+
predictions, 0 missing hours in 48, 0 shadow errors, 0 fallback rows, 0 timestamp violations.

**Done today, second pass** (all committed): E018 (feature count / redundancy), E019 (the
no-fitting baseline), E020 (model family), E021 (threshold definition), E022 (which inputs carry
the isolated signal); backend contract v1 + its transport; observability review; schema-mismatch
guard; readiness gate scored across 22 categories; README and open-user-actions docs.

**The schema guard is VERIFIED IN PRODUCTION** (this was the one open question at the pause, and
it was answered before stopping). The 19:00 UTC prediction was written at 20:12:38 by commit
`0732a10` — after the guard commit `2cef624` — with its shadow row, no `shadow_run_errors`, no
fallback data and no timestamp violations. 74 predictions, 20 shadow rows, 0 missing hours in 48.
Nothing about today's work is left unobserved in the live system.

**Then, in order:**
1. Wire the publish step into `.github/workflows/hourly.yml` — one step after
   `agent.shadow.outcomes`, exact YAML in `docs/api/contract_v1.md`. Deliberately left unadded so
   it can be introduced and then watched on the next run rather than deployed unattended. It
   cannot fail the job by construction (logged, exit 0), but watch a run anyway.
2. Resume the monitoring rhythm: weekly report + audit. Nothing else is due.

**There is no non-gated research work left** (see the section above). Everything waits on elapsed
time, on a user decision, or on evidence that does not exist — and validation wear is now an
argument against inventing more.

**Open user actions, unchanged:** healthchecks.io heartbeat (the one worth hurrying — every alarm
lives inside GitHub, so GitHub going quiet looks like success); least-privilege database role;
the news-cost judgement; PAT renewal before 2027-09-20. Details in `docs/ops/open_user_actions.md`.

**Do not**, on resume: re-run completed experiments, tune anything against validation, change
scoring, swap the frozen artefact, or touch the holdout.

## Roadmap adjustments (documented before acting)

1. **Phases 5 and 7 completed together (E002).** For a rules-based system, ablation is a recombination of the same stored category scores — running it separately from the diagnosis would repeat identical work. Nothing was skipped: every category was tested alone, and every leave-one-out variant was evaluated in both periods with uncertainty.
2. **Phase 6 moved after Phase 8, immediately before Phase 9.** Walk-forward validation (train on the past, test on the next slice, step forward, with an embargo so overlapping outcome windows can't leak) only has meaning once something is *fitted*. The feature-group tests in Phase 8 fit nothing: each feature is judged by a pre-registered rank-correlation criterion that must hold in two fixed, chronologically separate periods. Building walk-forward first would produce infrastructure with no consumer and delay the feature evidence. It will be built — and its purging/embargo design justified against the chosen label — right before the first fitted model.
3. **Primary-horizon decision deferred.** Phase 3 asks for the horizon to be chosen on evidence; E001/E002 show the current system carries no information at *any* horizon, so its evidence cannot rank horizons. Definitions for all five horizons exist and are tested; the choice is made when a feature with demonstrable signal exists (its horizon of effect decides).
4. **Phase 8A inserted — AI component tests.** The earlier brief (Part M) requires testing the two LLM components themselves; the 13-phase list omits it. Placed after the first two feature groups: it is independent of the numeric research, uses live data only (historical news is unavailable), and costs a few API calls.
5. **Feature-group order kept**, but each group starts with an availability/timestamp check that can mark it UNAVAILABLE or UNSAFE before any code is written.

6. **Phase 10 closed without running an optimisation (2026-09-21).** *What:* no weight or threshold search on scoring 0.1.0. *Why:* the inputs to such a search have been shown to carry no direction — fit-free (E001, E002, E003–E008) and fitted (E011: 15 walk-forward runs, zero return edge). *Problem this avoids:* a search over signal-free inputs always finds a "best" setting, and that setting is noise — exactly the overfitting rule 4 forbids. *Why appropriate:* the roadmap's own condition for Phase 10 ("only if justified") is not met; the live scoring stays 0.1.0, unchanged, as the frozen thing under test. *Re-opens if:* a pre-registered test on live data (funding 24h, dollar/yield 168h watch list; news at ≥ 500 live hours) finds a directional input.

7. **Feature-count research (E018) inserted at the front of the master plan's sections 14-19 work (2026-09-22).** *What:* redundancy, group ablation, forward selection and coefficient stability were run on the 1h move-size model before any new feature groups were added. *Why:* the master plan asks "how many signals should the final model use?" and forbids maximising feature count; the honest place to ask that first is the one model that has ever passed a pre-registered test, not a model that does not exist yet. *Problem this avoids:* adding new candidate groups to a model whose existing inputs have never been checked for duplication, and carrying an over-featured model into Phase 12's one-way holdout evaluation. *Why appropriate:* it uses only existing data and existing machinery, changes nothing that runs, and its result feeds directly into the Phase 12 freeze decision.

## Standing findings that constrain later phases

- **The gap flaw is FIXED in scoring 0.2.0** (2026-09-22, on the user's decision; found the same
  day by reading the live scoring path). 6,357 of 68,619 replayed hours (9.26%) had a gap inside
  their 250-candle window, up to 33 missing hours; scoring 0.1.0 treated those windows as
  consecutive and `score_volume` looked its reference candle up by row position. Now every
  indicator runs on the unbroken run ending at the reference candle, the volume reference hour
  is found by timestamp, and trend structure needs 20 real hours; anything whose hours are
  missing is unavailable instead of wrong. **Verified before deployment (E016):** identical
  output on all 62,262 gap-free hours (worst relative difference 3e-16), while on gap-affected
  hours mean completeness falls 0.850 → 0.568 and 42.5% of signals change (3.94% of the whole
  record). **Consequence:** E001, E002 and E011 are statements about scoring **0.1.0** and stay
  valid as such; every future comparison must name its version.
- **The baseline was re-run under 0.2.0 and the conclusion did not change (E017, 2026-09-22).**
  No evidence of information beyond trivial baselines at any of the five horizons, by E001's own
  criterion applied to both result files (`agent/research/compare_baselines.py`). Validation
  figures are identical to E001 to the digit — that period contains no gap-affected hour, which
  independently confirms E016. Every *exploration* edge shrank once the system stopped scoring
  hours it could not see, and the one interval that had excluded zero (6h, +0.092% [+0.002,
  +0.172]) now includes it (+0.076% [−0.011, +0.155]). **Lesson recorded: a borderline result
  sitting on the edge of its interval should be checked against data-quality flags before it is
  believed.** Scoring 0.2.0 is now the object under test; E001 stays the record for 0.1.0.

- **A hypothesis, not a finding: the model's own contribution may come from TRADE INTENSITY, not volatility
  (E022, 2026-09-22, exploratory).** Running E018's feature machinery against E021's volatility-scaled target —
  which removes the freely-available level signal from the question — flips the picture. The volatility group's
  ablation cost falls from 61% to **14%** of skill while trade intensity rises to **23%**, the largest of the
  three. Forward selection's first pick changes from `tr_mean_14_rel` to **`trades_rel_168h`**, which on its own
  reaches 88% of the nine-feature skill. The absolute-volatility coefficients REVERSE sign (rv_24 +0.110 → −0.055,
  rv_168 +0.177 → −0.087), and the two trade-intensity inputs take opposite signs (+0.277 vs −0.149), pointing at
  the weekly-versus-daily activity *contrast* as the informative quantity. Sign agreement is 0.93–1.00, so these
  are stable across folds. **Not adopted, and not to be adopted from this:** validation had been examined by
  twenty experiments before this one, and one feature carrying 88% of a small skill is exactly the shape of a
  noise artefact. Confirming it needs its own pre-registration and, in the end, the sealed holdout.
- **VALIDATION WEAR (recorded 2026-09-22, applies from here on).** Twenty experiments had examined the validation
  period before E022. Each was pre-registered and honest, but selection pressure accumulates ACROSS experiments
  even when no single one searches. Three consequences, now binding: (1) validation results are
  hypothesis-generating, not confirmatory; (2) **the sealed holdout is the only clean arbiter left**, which is an
  argument for keeping it sealed until there is something definite to confirm, not for spending it sooner;
  (3) any future claim that something "works" must state how many experiments had already seen the data it works on.
- **Where the move-size model's skill actually comes from (E021, 2026-09-22).** Scoring the E019
  reference against two target definitions splits it in two. Against the FIXED 0.25% target the no-fitting
  24h EWMA scores +0.0398 and the model +0.0983. Against a VOLATILITY-SCALED target — which divides the
  recent volatility level out of the question — the EWMA scores **+0.0003, nothing at all**, and the model
  still scores +0.0736. **Most of the model's apparent skill is knowledge of the volatility level, which is
  free; the part that is genuinely its own is within-regime timing, worth about +0.074 skill.** Every future
  description of the deliverable should say this rather than quoting the headline number alone.
- **The fixed target's meaning is not stable, and that is now measured (E021).** Its positive rate ranges
  from 0.336 (2023) to 0.676 (2018, 2021) — "a move bigger than 0.25%" is a different question in a calm
  year than in a wild one. The volatility-scaled alternative holds 0.476–0.508. **The fixed target stands
  anyway** because it is clearly more predictable (skill 0.098 vs 0.074, bar 0.90x, ratio 0.75x) and the
  scaled one ranks realised move size no better (rho 0.338 vs 0.360, a tie that technically failed by 0.002).
  **Constraint on later phases:** this instability belongs in the contract's limitations; and if the
  2026-09-22 live watch item survives the 500-hour checkpoint, the scaled target is the first thing to
  reconsider — as a deliberate trade of skill for stability, made with the user, never as a side-effect.
- **WATCH ITEM CLOSED (2026-09-23, E024): the 18-hour reading was a one-in-four event.** Measured on
  every contiguous 18-hour window of the validation out-of-sample record, a model exactly as good as it was
  on validation is BEHIND the free EWMA rule in 25% of them. Nothing about the model is suggested by that
  reading, and the larger paper sample (100 hours) already had it ahead. Closed as explained; the
  checkpoint comparisons continue as pre-registered.
- **WATCH ITEM UPDATE, same day: it largely dissolved on a larger sample, exactly as it was written to be
  able to.** The 18-hour reading below was taken on the shadow record alone. The paper record covers **82**
  live hours — every hour since go-live, not just the ones the shadow existed for — and on those the model is
  **ahead** of the no-fitting reference, not behind: Brier 0.2058 against 0.2192, a difference of −0.0134 in
  the model's favour, skill +5.0% against −1.2%. The market was still quiet (large moves in 32% of hours
  against ~47% in development) and the model was still the better forecaster in it. Two honest qualifications:
  the 18 shadow hours are a SUBSET of these 82, so this is the same question on more data rather than
  independent confirmation; and the paper record is computed after the fact, which is fine for comparing two
  models on identical rows but is not prospective evidence that either works. **Status: the concern is much
  weaker than it looked, and still not settled. Read at the 500-hour checkpoint.** This is what the watch
  item was for — it could not be forgotten if it persisted, and it could not become a finding when it did not.
- **WATCH ITEM (opened 2026-09-22, do not act on it): the first 18 prospective shadow hours ran BEHIND
  the no-fitting reference.** Model Brier 0.2574 vs the E019 EWMA rule's 0.2258 — the model is 0.032 worse,
  where development data said it should be roughly twice as skilful. Large moves occurred in 33% of those
  hours against ~47% in development, and the model kept stating 0.47–0.55: a quieter market than it was
  fitted on, which the purely recency-based reference tracked down faster than the model did. **n = 18.
  The report itself says intervals need 192 hours.** This is recorded here so that it cannot be quietly
  forgotten if it persists, and so that it cannot be treated as a finding if it disappears — which at this
  sample size it very well might. Read it at the 500-hour checkpoint, not before. Nothing changes now.
  (The comparison was wired into the weekly report BEFORE this was visible, which is the only reason it
  can be believed at all later.)
- **A fancier model does not help, and that is now tested rather than assumed (E020, 2026-09-22).** Three
  families with settings fixed in advance, run once each on identical rows. Gradient-boosted trees reach 1.04x
  the logistic's validation skill — the paired interval excludes zero (+0.00093 [+0.00006, +0.00178]) but the
  practical bar of 1.10x fails: *statistically better, practically equivalent*. A logistic with 21 squared and
  product terms reaches 1.01x and **fails calibration** (worst bucket 0.054 > 0.05), which disqualifies it
  regardless of Brier because the deliverable is a calibrated probability, not a ranking. **Constraint on later
  phases:** master plan section 24's ladder is satisfied at this rung — do not reach for a bigger model family
  again without a new reason, and if the deliverable ever becomes calibration-critical, the trees' ECE of 0.007
  is the recorded starting point.
- **The move-size model's complexity is DEFENDED, not assumed (E019, 2026-09-22).** It had never been
  compared against a rule that adapts — E012 compared it to the base rate, which is a far lower bar than it
  looks. Against six alternatives on identical validation rows, the incumbent's skill (+0.098) is **2.47x**
  the best non-fitted rule's (a 24-hour EWMA of "did the last hours move a lot?", +0.040), with a paired
  Brier difference of +0.01459 [+0.01261, +0.01652]. Giving every simple rule the incumbent's own Platt
  calibration helps them and changes nothing (2.33x, both bars still pass). **Consequences:** model-family
  research may proceed from a defended starting point; and **every future move-size result must be reported
  against the 24h EWMA rule, not only against the base rate** — 40% of the model's skill is available with
  no fitting at all, so a comparison to the base rate alone flatters any model.
- **The move-size model is over-featured, and one of its nine inputs is arithmetic (E018, 2026-09-22).**
  After the declared log transforms `vol_ratio_24_168` equals `rv_24` minus `rv_168` **exactly**
  (largest disagreement 1.0e-15 over 51,053 hours), so `move_size_1h_v1` carries **eight**
  independent inputs, not nine; removing the redundant one moves validation Brier by +0.0045%
  relative. Six features reach 99.4% of the best validation skill and four reach 95.6% — features
  seven to nine together add 0.6%. Group ablation ranks the sources: dropping volatility costs 61%
  of the model's skill, trade intensity 18%, calendar 6%. Coefficient signs are stable (1.00 for
  five inputs, 0.78 for the weakest, `is_weekend`). **Nothing was changed:** the smaller sets are
  not better, only indistinguishable in practice and slightly worse in point estimate, and swapping
  the artefact would reset the prospective shadow record. **Constraint on later phases:** the model
  must be described as eight inputs of which about six carry its skill; Phase 12's freeze decision
  has this evidence in front of it; and any future feature work starts from the knowledge that this
  model's inputs already duplicate each other heavily (`tr_mean_14_rel`/`rv_24` rho +0.92,
  `trades_rel_24h`/`trades_rel_168h` +0.78).
- **A one-standard-error rule must use the standard error of the metric, not of the paired
  difference (E018, method lesson).** I pre-registered the paired version. Paired, the standard
  error shrinks as fast as the difference it measures — at k = 8 a 0.005% relative Brier difference
  came with an SE of 0.000005 — so the rule degenerates into "pick the largest model" on any large
  sample. The pre-registered answer (k = 9) is recorded as the primary result because that is what
  pre-registration means; the classical unpaired rule (k = 4) is recorded beside it as exploratory.
  **Applies to all model-selection work still to come.**

- Scoring 0.1.0 has no predictive value (E001) and none of its four categories does alone (E002). Re-weighting it (Phase 10) is pointless unless a feature with signal is found in Phase 8. If none is, Phase 10 collapses to "drop redundant categories" and the honest deliverable is calibrated *uncertainty* rather than direction.
- Momentum and volume are weakly anti-correlated with the next hour's return in both periods (|ρ| 0.02–0.04). Recorded; not acted on.
- Historical news is UNAVAILABLE; news is evaluated on the live archive only, once it is large enough (hundreds of hours).

## Incident 2026-09-21/22 — the hourly job failed on ~half of all runs (fixed 2026-09-22)

Full post-mortem: `docs/ops/incident_2026-09-21_shadow_step.md`. Summary for this roadmap:

- **What broke:** only the research shadow step (added 2026-09-21 19:12). Its
  feature-definition guard hashed values printed to 12 significant digits; GitHub runners
  differ from the development machine in the last few bits, so `load_model()` raised on about
  half of all runs (measured locally: a 1e-14 relative difference flips that hash 56% of the
  time; failing steps took 0 s, i.e. before any network call).
- **What was affected:** the live record, not at all (18/18 hourly predictions in the window,
  no fallback data, no timestamp violations, outcomes complete, parity 62/62). The shadow
  record lost **8 hours** (2026-09-21 19:00; 09-22 01, 02, 04, 05, 07, 09, 11 UTC).
- **No backfill.** Recomputing those hours now would create numbers that look prospective but
  are not (`LIVE_EVALUATION.md` rule 1). The gap stays, visible in the weekly report.
- **Fixed** (`d222bd7`): tolerance-based guard (`rtol = 1e-6`) with regression tests in both
  directions; artefact regenerated with model numbers proven identical; shadow failures
  recorded in `shadow_run_errors` instead of failing the job; watchdog alarm for persistent
  shadow failures; weekly report shows the errors. Also closed while here: the pre-registered
  prospective rule is now enforced in code, not only documented.
- **Readiness gate reopened and revised** (`docs/research/readiness_gate.md`): two rows
  corrected, judgement re-dated to after the fix.
- **A second, unrelated defect was found during the response** (weekly report, §1): the news
  scorer's answer was truncated once the 24h window passed ~50 headlines, so **17 predictions
  (2026-09-21 20:00 → 2026-09-22 12:00 UTC) were made with news unavailable**. Those rows are
  self-describing (`completeness_score` 0.85, news weight 0, `ai_model_news` NULL,
  `run_meta.news_error`) — research using the live record should treat them as four-category
  hours, not discard them silently. Fixed the same day; the prompt and schema are unchanged,
  so E009's validation still applies.
- **New safety net:** the test suite now runs on GitHub's runners on every push
  (`.github/workflows/tests.yml`) — the check that would have caught the first defect before
  deployment, since the guard test loads the model on a GitHub runner.

## Where the project stands after the incident response (2026-09-22)

Done today: root cause found and fixed, second defect found and fixed, both documented, CI
test workflow added, full post-fix audit clean (67 predictions, 0 cutoff/fetch/version
violations, 0 fallback rows, parity 63/63, shadow rows reproduce their probabilities, all
append-only guards in place, schema 3 = code 3, holdout untouched), 194 tests pass locally
**and on GitHub's runners**.

**Next actions, in order:**
1. Confirm the 14:12 UTC run writes the 13:00 prediction **with news present** (the first run
   after the news fix) and a shadow row for 13:00. Then confirm a few more hourly runs stay
   green — one success does not disprove a ~50% failure rate.
2. Re-run the weekly report and commit it (the Phase 13 weekly audit).
3. Resume the monitoring rhythm: weekly report + audit; Phase H checkpoints at 500 / 2,000 /
   5,000 **prospective** shadow hours; Phase J when ≥ 500 live hours with news; watch-list
   re-tests at 6 months; the holdout decision only after those, and only with the user.

**Open user decisions:** healthchecks.io heartbeat; least-privilege database role; whether to
halve the AI cost by dropping the echoed headline from the news schema (a change to the AI's
task — would need E009 re-run); whether to automate the weekly report commit. PAT renewal
before 2027-09-20.

## Paused 2026-09-21 19:58 UTC — resume point (history; superseded by the incident work above)

**State.** Everything in the "Backend hardening roadmap" above is recorded as done except the calendar-bound stages (Phase 13 continuing; H, J, K continuing/deferred; L nothing justified; the final holdout decision). Last commit `2fdf7bb` (readiness gate, pinned requirements, README); tree clean, `main` = `origin/main`. Tests: 185 pass + 7 opt-in integration. Holdout: **sealed** (`research/HOLDOUT_ACCESS.log` does not exist). Live system: healthy; shadow record running from GitHub since 19:12 UTC (rows for 17:00 and 18:00 UTC; the 17:00 row graded).

**Pending external verification (not yet seen — do this FIRST on resume):**
1. The **20:12 UTC hourly run (2026-09-21) is the first to install the exactly-pinned `requirements.txt` and to carry `permissions: contents: read`** (commits `4597904`, `2fdf7bb`). Check it: GitHub Actions run list (public API `repos/ja-284/Bitcoin-AI-Agent/actions/runs`) → conclusion must be `success`; then `predictions` must have `as_of = 2026-09-21 19:00 UTC` with `run_meta.code_commit = 2fdf7bb…`, and `shadow_move_size` a row for 19:00 UTC. If the run failed on `pip install` (a pinned wheel missing on Linux), fix the pin(s), commit, re-dispatch, and verify — nothing else about the pins is negotiable.
2. Confirm the 18:00 UTC shadow row was graded by the 20:12 run (outcome_status `ok`) and equals the live tracker's 1h return.

**Then:** run `python -m agent.research.weekly_report` (it is the weekly audit; §1 health, §3 shadow, §4 parity, §5 drift) and commit the report. After that the project is in its monitoring rhythm: weekly report + audit; Phase H checkpoints at 500 / 2,000 / 5,000 prospective shadow hours; Phase J when ≥ 500 live hours with news; watch-list re-tests at 6 months; the holdout decision only after those and only with the user. Open user actions: healthchecks.io heartbeat (`HEARTBEAT_URL` secret), least-privilege DB role, dispatch-PAT renewal before 2027-09-20; optional: a scheduled workflow that commits the weekly report (also resets GitHub's 60-day inactivity clock) — offered, not decided.

**Do not** re-run completed phases, re-open E011/E012/E013, change scoring 0.1.0, or touch the holdout.

## Resumed 2026-09-21 — quality gate result

Tests 120/120. Live system over the 22-hour pause: 22/22 hourly predictions, 0 missed, median fetch 12.5 min after candle close (Supabase :12 dispatch; GitHub's own cron fired 19 of 88 backup slots — still unreliable, still not needed), 0 failed Actions runs, 24/24 pg_cron runs succeeded (HTTP 204), 21/21 on Binance (0 synthetic), 0 timestamp-rule violations, news + explanation present every run, outcomes complete (45 @1h, 40 @6h, 22 @24h; none overdue, none graded early). No live change made. Signals 20 BUY / 1 HOLD — scoring 0.1.0 leaning BUY in an uptrend, as documented.

## Paused 2026-09-20 (evening) — resume point (history; steps 1–3 done 2026-09-21, step 4 = E013 in progress)

**Where work stopped.** Phase 9's two pre-registered experiments (E011 direction, E012 move size) have been run, evaluated against their written criteria, and recorded (`research/experiments/E011_*.json`, `E012_*.json`, `research/results/E011/summary.md`, `research/results/E012/summary.md`, all committed). Tests: 120 pass. Live system untouched and healthy (25 predictions, no missed hours since the 08:12 UTC trigger fix).

**Not yet done for Phase 9 (do these first on resume, in order):**
1. Quality gate (tests, live-run check, git clean) — the standard one.
2. Phase 9 completion report in the fixed structure (PHASE COMPLETED / STATUS / WHAT I DID / … / NEXT).
3. Record the Phase 10 decision in this file with a reason (E011 found nothing to re-weight towards; the standing finding already says Phase 10 then collapses to "drop redundant categories", which is a live-scoring change and therefore NOT done from research results).
4. Then Phase 11 = E013: calibrate the **1h** E012 model only (6h/24h did not pass): same bench with `calib_days=90` (purged slice), compare raw logistic vs Platt vs isotonic on validation reliability (buckets with intervals, ECE, Brier); pre-register the criterion before running. Tooling already exists: `WalkForwardSpec(calib_days=...)`, `run_walk_forward(make_calibrator=...)`; `model_test.py` needs a `--calibrator` option.

**Commands that reproduce E011/E012** (per-hour CSV dumps are git-ignored; summaries are committed):
`python -m agent.research.model_test --experiment E012 --model logistic --target large_move --threshold 0.0025 --horizon 1 --features tr_mean_14_rel,rv_24,rv_168,vol_ratio_24_168,trades_rel_24h,trades_rel_168h,hour_sin,hour_cos,is_weekend --log-features tr_mean_14_rel,rv_24,rv_168,vol_ratio_24_168,trades_rel_24h,trades_rel_168h --scheme expanding --tag size_expanding_1h` (6h: threshold 0.0075; 24h: 0.015; `--scheme rolling` for robustness). E011: `--features` set A/B lists in its JSON, `--target direction` (default).

**Small code facts worth knowing on resume:** a `calendar` feature group (hour_sin, hour_cos, is_weekend) was added to `agent/research/features.py` and is blanked in candle gaps like every other feature (this masking was added after E012 ran; it cannot change E012 because the replay index contains only real candle hours). The reliability-bucket flag in result JSONs is `enough_rows` (n ≥ 100), not a calibration statement.
