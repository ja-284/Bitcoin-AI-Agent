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
  (c) **95% of what the news model is paid to read, it has already read.** Caching a score per story URL would cut that cost ~19× and make it deterministic per story, but it changes the call's context (E009 measured a small order/context sensitivity), so it is an option for the user, not a unilateral change.
  Original scope (when ≥ 500 trustworthy live hours; 43 on 2026-09-21): relevance, sentiment, order, duplicates, first-seen timing, sources, volume, novelty; stays separate from the numerical core until evidence supports integration. Audit note 2026-09-21: every stored item carries headline, source, url, availability time (later of published/updated), the run's `fetched_at` is the retrieval time, undated items are excluded, duplicates counted; first-seen time is derivable (earliest `fetched_at` containing the url). Summaries contain raw HTML — cleaning them would change the scorer's input and is therefore a controlled change for Phase J, not now.
- [~] **K — Move-size model maturity** — prospective evaluation running (Phase H protocol); drift watch (Phase I). **Deferred by decision (2026-09-21):** threshold / horizon variants (e.g. the 6h near-miss) are not re-tested until the 1h model has ≥ 2,000 prospective hours — testing variants now, with the same development data, would be a search. When re-opened: one pre-registered experiment per variant, logged as E0xx.
- [ ] **L — Directional research only if justified** — **nothing justified now** (2026-09-21): E011 is the standing null; the live watch list (funding 24h, dollar/yield 168h at ≥ 6 months; news at ≥ 500 hours) is the only planned source of new evidence. Any test follows the pre-registration template. The null is accepted, not worked around.
- [x] **M — LLM robustness** (2026-09-21): `tests/test_llm_robustness.py` (SDK timeout / rate-limit / connection / overload errors propagate from both calls and are recorded by the orchestrator; explainer with no text or blank text is an error, never an empty success; the news schema rejects NaN, ∞, out-of-range and missing fields; clients are constructed bounded) + `tests/test_failure_modes.py` (empty / partial model answers) + `tests/test_explainer_isolation.py` (decision-neutral by construction) + E009 (repeatability, relevance, order sensitivity on the real model). Explainer hardened: blank output → `explanation_error`. LLM authority unchanged: news → one structured score; explanation after the decision.
- [x] **Security audit** (2026-09-21, `docs/ops/security.md`): secrets inventory and scans (tracked files, stored rows, logs — clean); workflows set to `permissions: contents: read`; psycopg errors do not echo the DSN; Vault-held dispatch token; research-only boundary confirmed (no execution code exists). Open items: least-privilege DB role (user action, low urgency), healthchecks.io heartbeat, PAT renewal 2027-09-20.
- [x] **Performance / reliability review** (2026-09-21, `docs/ops/performance.md`): dispatch runs median 54 s (30–67 s) of a 15-min budget, ~8 Binance + 3 RSS + 2 Anthropic calls and ~20 short DB connections per hour, no unnecessary recomputation, trigger 100% since the fix; **no optimisation warranted** (connection reuse would save seconds and add shared state).
- [x] **Backend readiness gate — assessed 2026-09-21** (`docs/research/readiness_gate.md`): every engineering, security and maintainability item verified except two external user actions (healthchecks.io heartbeat; least-privilege DB role — mitigated by append-only triggers). Research items verified; prospective live evidence has only just begun (by the calendar, not by a defect). **Judgement: engineering is release-candidate quality for a read-only frontend that shows the research state truthfully. The holdout stays sealed.** Requirements pinned exactly; README rewritten.
- [ ] **Final holdout decision → one-time confirmation (Phase 12) → final backend confirmation → frontend.** Holdout: sealed, waits for the Phase H checkpoints and the user's decision. Frontend: may start as a read-only consumer of the record at any time (contract in `readiness_gate.md`); the backend continues under the same discipline.

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
