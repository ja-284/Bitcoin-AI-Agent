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
- [ ] **PHASE 8 — New feature groups**, one at a time, pre-registered criteria, fit-free
  - [x] 8.1 Volatility (E003 — magnitude information strong at 1–24h; no directional signal; `tr_mean_14_rel` adopted as the uncertainty input, vol-scaled bands justified)
  - [x] 8.2 Market regime / long-horizon trend (E004 — no consistent directional information; first run caught a harness name-collision bug, now guarded by tests and a tripwire)
  - [x] 8.3 Derivatives (E005 — funding/premium usable, OI/liquidations UNAVAILABLE; contrarian sign consistent 2019–23 but absent 2024–25 → not adopted, on the live watch list)
  - [ ] 8.4 Macro / cross-market (market-hours alignment)
  - [ ] 8.5 On-chain (free daily series only)
  - [ ] 8.6 News improvements (live archive only)
  - [ ] 8.7 Microstructure — expected UNAVAILABLE historically
  - [ ] 8.8 Social — expected UNAVAILABLE/UNSAFE
- [ ] **PHASE 8A — AI component tests** (inserted, see adjustment 4): news-scorer schema reliability, reproducibility, relevance/sentiment behaviour, duplicate/missing handling; explainer faithfulness to the numbers and zero influence on the decision
- [ ] **PHASE 6 — Walk-forward / time-series validation** (moved: built immediately before the first fitted model — see adjustment 2)
- [ ] **PHASE 9 — Model architecture research**
- [ ] **PHASE 10 — Weight and threshold optimisation**
- [ ] **PHASE 11 — Probability calibration**
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
