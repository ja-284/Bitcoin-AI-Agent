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
- [~] **PHASE 9 — Model architecture research** — both experiments run and recorded 2026-09-20; **phase report + quality gate still to be done at resume** (see "Paused" below). E011 (direction, 15 runs): no pass anywhere — no combinable directional signal in the free data; the 1h reversal family gives ~+2 points of accuracy with zero return edge. E012 (move size, 6 runs): **pass at 1h** (Brier −15%/−9%, ρ 0.45/0.36, accuracy +15/+10 points), 6h near-miss, 24h no pass.
- [ ] **PHASE 10 — Weight and threshold optimisation** — decision pending at resume; E011's recorded consequence is that there is nothing to re-weight scoring 0.1.0 towards (standing finding below)
- [ ] **PHASE 11 — Probability calibration** — next: calibrate the E012 1h move-size model on a purged calibration slice (raw vs Platt vs isotonic; reliability buckets with intervals); state the direction probability honestly as ≈ base rate
- [ ] **PHASE 12 — Final untouched holdout evaluation** (once)
- [ ] **PHASE 13 — Live / paper research monitoring** (partly running: hourly predictions + outcomes since 2026-09-19; weekly report not yet built)

## Roadmap adjustments (documented before acting)

1. **Phases 5 and 7 completed together (E002).** For a rules-based system, ablation is a recombination of the same stored category scores — running it separately from the diagnosis would repeat identical work. Nothing was skipped: every category was tested alone, and every leave-one-out variant was evaluated in both periods with uncertainty.
2. **Phase 6 moved after Phase 8, immediately before Phase 9.** Walk-forward validation (train on the past, test on the next slice, step forward, with an embargo so overlapping outcome windows can't leak) only has meaning once something is *fitted*. The feature-group tests in Phase 8 fit nothing: each feature is judged by a pre-registered rank-correlation criterion that must hold in two fixed, chronologically separate periods. Building walk-forward first would produce infrastructure with no consumer and delay the feature evidence. It will be built — and its purging/embargo design justified against the chosen label — right before the first fitted model.
3. **Primary-horizon decision deferred.** Phase 3 asks for the horizon to be chosen on evidence; E001/E002 show the current system carries no information at *any* horizon, so its evidence cannot rank horizons. Definitions for all five horizons exist and are tested; the choice is made when a feature with demonstrable signal exists (its horizon of effect decides).
4. **Phase 8A inserted — AI component tests.** The earlier brief (Part M) requires testing the two LLM components themselves; the 13-phase list omits it. Placed after the first two feature groups: it is independent of the numeric research, uses live data only (historical news is unavailable), and costs a few API calls.
5. **Feature-group order kept**, but each group starts with an availability/timestamp check that can mark it UNAVAILABLE or UNSAFE before any code is written.

## Standing findings that constrain later phases

- Scoring 0.1.0 has no predictive value (E001) and none of its four categories does alone (E002). Re-weighting it (Phase 10) is pointless unless a feature with signal is found in Phase 8. If none is, Phase 10 collapses to "drop redundant categories" and the honest deliverable is calibrated *uncertainty* rather than direction.
- Momentum and volume are weakly anti-correlated with the next hour's return in both periods (|ρ| 0.02–0.04). Recorded; not acted on.
- Historical news is UNAVAILABLE; news is evaluated on the live archive only, once it is large enough (hundreds of hours).

## Paused 2026-09-20 (evening) — exact resume point

**Where work stopped.** Phase 9's two pre-registered experiments (E011 direction, E012 move size) have been run, evaluated against their written criteria, and recorded (`research/experiments/E011_*.json`, `E012_*.json`, `research/results/E011/summary.md`, `research/results/E012/summary.md`, all committed). Tests: 120 pass. Live system untouched and healthy (25 predictions, no missed hours since the 08:12 UTC trigger fix).

**Not yet done for Phase 9 (do these first on resume, in order):**
1. Quality gate (tests, live-run check, git clean) — the standard one.
2. Phase 9 completion report in the fixed structure (PHASE COMPLETED / STATUS / WHAT I DID / … / NEXT).
3. Record the Phase 10 decision in this file with a reason (E011 found nothing to re-weight towards; the standing finding already says Phase 10 then collapses to "drop redundant categories", which is a live-scoring change and therefore NOT done from research results).
4. Then Phase 11 = E013: calibrate the **1h** E012 model only (6h/24h did not pass): same bench with `calib_days=90` (purged slice), compare raw logistic vs Platt vs isotonic on validation reliability (buckets with intervals, ECE, Brier); pre-register the criterion before running. Tooling already exists: `WalkForwardSpec(calib_days=...)`, `run_walk_forward(make_calibrator=...)`; `model_test.py` needs a `--calibrator` option.

**Commands that reproduce E011/E012** (per-hour CSV dumps are git-ignored; summaries are committed):
`python -m agent.research.model_test --experiment E012 --model logistic --target large_move --threshold 0.0025 --horizon 1 --features tr_mean_14_rel,rv_24,rv_168,vol_ratio_24_168,trades_rel_24h,trades_rel_168h,hour_sin,hour_cos,is_weekend --log-features tr_mean_14_rel,rv_24,rv_168,vol_ratio_24_168,trades_rel_24h,trades_rel_168h --scheme expanding --tag size_expanding_1h` (6h: threshold 0.0075; 24h: 0.015; `--scheme rolling` for robustness). E011: `--features` set A/B lists in its JSON, `--target direction` (default).

**Small code facts worth knowing on resume:** a `calendar` feature group (hour_sin, hour_cos, is_weekend) was added to `agent/research/features.py` and is blanked in candle gaps like every other feature (this masking was added after E012 ran; it cannot change E012 because the replay index contains only real candle hours). The reliability-bucket flag in result JSONs is `enough_rows` (n ≥ 100), not a calibration statement.
