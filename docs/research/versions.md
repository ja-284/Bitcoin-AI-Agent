# Version identifiers — "exactly what produced this row?" (Backend Phase G)

| what | identifier | lives in | stored with each row | must change when | how a silent change is caught |
|---|---|---|---|---|---|
| information rules (how data is gathered, time-bounded, validated) | `PIPELINE_VERSION` = 0.2.0 | `agent/version.py` | `predictions.pipeline_version`, `shadow_move_size.pipeline_version` | a rule about what a prediction may know changes (cutoff, window, fallback semantics, validation that alters inputs) | `tests/test_scoring_golden.py` pins the value; the parity check refuses to compare rows of another version; `CHANGELOG.md` |
| scoring formulas, weights, thresholds | `SCORING_VERSION` = 0.1.0 | `agent/scoring/scorer.py` | `predictions.scoring_version` | any formula/weight/threshold/window change | **golden test**: three windows of a fixed synthetic series must reproduce pinned indicators, scores, patterns, confidence and signal (`tests/golden_scoring_0_1_0.json`) |
| the exact code | git commit SHA | GitHub run env `GITHUB_SHA` | `predictions.run_meta.code_commit`, `shadow_move_size.code_commit` (NULL for manual runs) | every commit | — (it is the ground truth) |
| AI models | model ids | `agent/ai/news_scorer.py`, `agent/ai/explainer.py` | `predictions.ai_model_news`, `ai_model_explanation` | a model id changes | stored per row; E009 re-run if prompts change |
| research feature definitions | **feature reference values** (the features' values on a fixed reference series) | computed by `agent/shadow/features.py::feature_reference_values` | inside each model artefact (`feature_reference`) | any change to `agent/research/features.py` / `microstructure.py` that alters a value by more than `rtol = 1e-6` | `load_model()` recomputes them and **refuses to run old coefficients on changed features** (`ModelVersionError`); `tests/test_shadow.py` checks both directions: a 1% definition change raises, floating-point noise from 1e-15 to 1e-9 does not |
| research models | artefact version, e.g. `move_size_1h_v1` | `agent/shadow/models/<version>.json` (immutable: export refuses to overwrite; canonical-JSON sha256 pinned in `tests/test_shadow.py`) | `shadow_move_size.model_version` | a new fit, new inputs, new threshold, new calibration | the pinned hash; a new fit is a new file |
| calibration | part of the model artefact (`platt_a`, `platt_b`, calibration range) | same artefact | via `model_version` | recalibration → new model version | same |
| target definitions | `LabelSpec` fields (horizon, kind, threshold kind/value, lookback) | `agent/research/labels.py`; recorded in each experiment JSON | experiment records; `shadow_move_size.threshold`, `horizon_hours` | a target definition changes → a new experiment | `tests/test_labels.py`; experiments are pre-registered |
| research datasets | dated snapshot filenames (`btcusdt_1h_2026-09-19.csv`, …) | `data/` (git-ignored, re-downloadable), named in every experiment and artefact | experiment records, artefact `training.snapshot` | a new download | replay cache keyed by snapshot + range + versions |
| database schema | `SCHEMA_VERSION` = 4 (4 = public-API lockdown, 2026-09-23) | `agent/database/db.py`; written to `schema_meta` by `python -m agent.migrate`, which applies all three schema files in one transaction | one row per database | any migration — applied to the database FIRST, code deployed second | `tests/test_scoring_golden.py` pins code = SQL; the hourly job refuses a database OLDER than the code (a newer one is accepted, because migrations are additive); the weekly report prints both and flags an incompatible pair |
| experiments | `E000`–`E014` | `research/experiments/*.json` (+ `git_commit`), `research/EXPERIMENTS.md` | — | never edited after `done` except to append; a re-run is a new experiment | git history |

A guard that compares numbers across machines uses a **tolerance**, never a bit-exact hash:
the first version of the feature guard hashed 12-digit values and broke the live shadow job on
roughly half of all GitHub runs (`docs/ops/incident_2026-09-21_shadow_step.md`).

Rule: a model update creates a new artefact version; a formula change bumps `SCORING_VERSION`
and re-pins the golden file in the same commit; an information-rule change bumps
`PIPELINE_VERSION` and gets a `CHANGELOG.md` entry; a migration bumps `SCHEMA_VERSION` in
both places. None of these can happen silently: each has a test or a database check that fails.
