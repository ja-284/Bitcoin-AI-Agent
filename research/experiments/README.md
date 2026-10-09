# Experiment records

One JSON file per experiment, named `EXXX_<slug>.json`, and one row per experiment in
`research/EXPERIMENTS.md`. A failed or negative experiment is never deleted.

**What every record must carry (enforced by `tests/test_experiment_log.py`, 2026-10-09):**
- `id` (matching the file name), `date`, `git_commit` and `status`;
- what was fixed **in advance**: at least one of `hypothesis`, `hypothesis_H`, `hypotheses`,
  `acceptance_criterion`, `what_each_answer_means_decided_in_advance`, `expectation_stated_in_advance`,
  `pass_rules_copied_unchanged`, or, for descriptive planning and verification, `why` / `question` /
  `method`;
- what happened: `results`, `result` or `metrics` ("(filled after the one-time run)" for a
  registered experiment that has not run).

**How the schema actually evolved (recorded 2026-10-09, nothing rewritten):**
- E000–E022 follow the template below closely.
- From E023, the planning studies and the pre-registered descriptive studies use the names above
  (`hypothesis_H`, `what_each_answer_means_decided_in_advance`, `result`, `validation_wear`, `command`).
- Many `git_commit` values are free text such as "(this commit)"; the file's own git history names the
  commit. Old records are left as written. New records should give a real short SHA where one exists.

The original template (fields marked optional may be left out; use `null` when genuinely not applicable):

```json
{
  "id": "E001",
  "date": "2026-09-20",
  "git_commit": "abc1234",
  "status": "exploratory | confirmatory",
  "hypothesis": "one sentence, stated before running",
  "acceptance_criterion": "what result would count as support, stated before running",
  "pipeline_version": "0.2.0",
  "scoring_version": "0.1.0",
  "feature_version": "which feature set / group under test",
  "dataset": {"source": "binance BTCUSDT 1h", "snapshot": "fetched YYYY-MM-DD", "range": "start → end"},
  "periods": {"exploration": "...", "validation": "...", "calibration": null, "holdout": "sealed | evaluated"},
  "horizons_hours": [1, 6, 24],
  "target": {"definition": "binary direction | three-class", "threshold": "...", "reference": "close of reference candle", "outcome": "close of candle opening at as_of+H"},
  "features": ["trend", "momentum", "..."],
  "hyperparameters": {},
  "calibration_method": null,
  "metrics": {},
  "results": "what actually happened, with uncertainty",
  "consistent_across_time": "yes | no | mixed — say where",
  "leakage_check": "what was checked and how",
  "overfitting_suspected": "yes | no — why",
  "affected_design": "did this change any later decision?",
  "notes": "optional"
}
```
