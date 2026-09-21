# Backend readiness gate — assessment of 2026-09-21

The strict checklist from the master operating prompt, item by item, with the evidence and
an honest status. **Verified** = checked and proven today; **Partial** = in place but
waiting on something outside the code; **Not yet** = not satisfied.

"Backend ready for frontend" means: reliable, research-valid, observable, reproducible,
secure and stable enough that a frontend can be built on it without treating it as a
prototype. It does **not** mean the system predicts the market.

## Research correctness

| item | status | evidence |
|---|---|---|
| point-in-time behaviour verified | **Verified** | `test_point_in_time.py`, `test_features_point_in_time.py` (future garbled → past unchanged), `test_news_cutoff.py`, `test_orchestrator_cutoff.py`; live: 0 timestamp-rule violations in 48 rows; CHECK constraints in the database |
| leakage protections tested | **Verified** | walk-forward purge/embargo demonstrated on an overlapping-label leak (`test_walkforward.py`); E010 controls (memoriser at chance, last-label no head start); feature-name tripwire (`test_feature_harness_guards.py`); holdout loader guard (`test_research_guards.py`) |
| target construction verified | **Verified** | `test_labels.py`, `test_horizon_lookup.py`; tracker = labels across a gap (`test_parity.py`); live tracker returns = research candles (46/46) |
| validation framework verified | **Verified** | Phase 6 / E010: 5 of 5 pre-registered checks on real data |
| calibration process verified | **Verified** | E013 (Platt chosen by rule; ECE ≤ 0.03 every year); `test_calibration.py` (calibrator sees only the purged slice) |
| final holdout protected | **Verified** | `research/HOLDOUT_ACCESS.log` does not exist; loader truncates; `build_frame` takes holdout candles only through the logged route; E014 pre-registered, not run |
| experiment history complete | **Verified** | E000–E014 in `research/EXPERIMENTS.md` + JSON each; results committed; per-hour dumps regenerable |

## Engineering correctness

| item | status | evidence |
|---|---|---|
| live/research parity checked | **Verified** | `agent/research/parity.py`: 44/44 live hours identical; `docs/research/parity.md`; weekly §4 |
| data validation strong | **Verified** | candle validation (impossible data raises, gaps flagged, zero volume counted), kline schema checks, staleness rule, bounded RSS/AI/DB calls (Phase B) |
| failure handling tested | **Verified** | `test_failure_modes.py`, `test_data_hardening.py`, `test_llm_robustness.py`, `test_market_data_fallback.py`; `docs/research/failure_modes.md` |
| retries safe | **Verified** | one retry per exchange endpoint (none on rate limits), SDK retries bounded, no DB retry (next slot recomputes; idempotent writes) |
| duplicate execution safe | **Verified** | early exit before AI; `ON CONFLICT DO NOTHING` everywhere; proven on real Postgres in a scratch schema (`tests/integration`, 7/7) |
| database integrity checked | **Verified** | UNIQUE keys, CHECKs (cutoff rule, fetch-after-cutoff, outcome status/consistency), append-only triggers, schema version — applied live |
| important code paths covered by meaningful tests | **Verified** | 185 unit tests + 7 integration; every guard has a test that fails when the guard is removed (perturbation tests in parity, golden scoring pin, artefact hash, fingerprint) |
| reproducibility demonstrated | **Verified** | `docs/research/reproducibility.md`: parity 44/44, shadow rows 1e-12, E012 re-run bit-identical; requirements now pinned exactly |

## Operational reliability

| item | status | evidence |
|---|---|---|
| hourly execution monitored | **Verified** | self-check step, 3-hourly watchdog, weekly report §1; 100% of hours since the trigger fix |
| failures detectable | **Partial** | job failures email via GitHub; missed hours fail the next job; weekly report lists them. The external alarm (healthchecks.io heartbeat) is **still not set up** — a user action (`HEARTBEAT_URL` secret) |
| data-source failures handled safely | **Verified** | fallback + flags; stale → failure; news degrade → weight 0; `docs/research/failure_modes.md` |
| logs useful | **Verified** | every degradation lands in `run_meta`; step logs name the endpoint/attempt/reason; no secrets |
| state persisted | **Verified** | predictions, outcomes, shadow rows (append-only); research state in `research/`; roadmap/CLAUDE.md kept current |
| model/version identification reliable | **Verified** | `docs/research/versions.md`; golden pin, fingerprint, artefact hash, schema version, git SHA per row |

## Security

| item | status | evidence |
|---|---|---|
| secrets protected | **Verified** | `docs/ops/security.md`; scans of tracked files and stored rows clean |
| workflow permissions reviewed | **Verified** | `permissions: contents: read` on both workflows |
| credentials absent from Git | **Verified** | `.env` ignored; `.env.example` placeholders; git grep clean |
| logs checked for secret leakage | **Verified** | code never logs secrets; psycopg errors do not echo the DSN |
| research-only boundary maintained | **Verified** | no execution code exists; documented |
| least-privilege database role | **Not yet** (low urgency) | the job uses the project's `postgres` role; a restricted role is a Supabase change for the user; mitigated by append-only triggers |

## Research quality

| item | status | evidence |
|---|---|---|
| E011 conclusion preserved | **Verified** | recorded; Phase L states nothing directional is justified |
| E012 conclusion evaluated honestly | **Verified** | pre-registered, 1h pass / 6h near-miss / 24h no, coverage check, by-move-size breakdown; prospective protocol pre-registered |
| E013 calibration validated | **Verified on validation data** | Platt ECE 0.014, ≤ 0.03 each year; the holdout confirmation is deliberately still ahead |
| live evidence tracked | **Verified (started)** | shadow record live since 2026-09-21 19:12 UTC; 2 rows; checkpoints at 500 / 2,000 / 5,000 hours |
| uncertainty reported | **Verified** | block-bootstrap intervals everywhere, gated by sample size; "no intervals yet" stated when too few |
| known limitations documented | **Verified** | README, `data_sources.md`, `reproducibility.md`, `failure_modes.md`, E-summaries |

## Maintainability

| item | status | evidence |
|---|---|---|
| architecture understandable | **Verified** | README rewritten (module map, how it runs, findings); module docstrings |
| modules reasonably separated | **Verified** | providers / indicators / scoring / news / ai / database / shadow / research; the research bench never imports the live orchestrator; the live job never imports research fitting code (only feature definitions for the shadow) |
| important dependencies documented | **Verified** | `requirements.txt` pinned exactly with the reason |
| no unnecessary complexity | **Verified** | performance review declined the one optimisation on offer; models are plain logistic + Platt in JSON |
| experiments reproducible | **Verified** | commands recorded; E012 re-run bit-identical |
| changes traceable through Git | **Verified** | one commit per phase/experiment; git SHA in every GitHub-produced row |

## Judgement

**Engineering: release-candidate quality.** Every engineering, security and maintainability
item is verified except two that are not code: the external heartbeat alarm and a
least-privilege database role — both user actions in external services, both mitigated,
neither blocking a frontend that only *reads* the record.

**Research: correct, honest, and early.** The research is valid and fully documented, but the
prospective live evidence is hours old. That is not a defect of the backend; it is the
calendar. The frontend can be built against a backend whose data is trustworthy today, as
long as the frontend shows the research state truthfully: the direction signal is an
instrument under test with no demonstrated edge; the move-size probability is calibrated on
development data and being tested live; confidence is a labelled heuristic.

**The holdout stays sealed.** Nothing about frontend work changes that; the one-time
confirmation waits for the Phase H checkpoints (see `research/ROADMAP.md`).

## What the frontend may rely on (read-only contract)

`predictions` (signal, scores, confidence with its two components, explanation, versions,
data-quality flags), `prediction_outcomes` (raw returns per horizon; "right/wrong" is decided
by the reader with a stated rule), `shadow_move_size` (calibrated probability, honest blanks,
outcomes), `research/monitoring/weekly_*.json` (health, record, parity, drift). All
append-only; the frontend must never write to them.
