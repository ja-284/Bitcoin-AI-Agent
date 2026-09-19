# Experiment records

One JSON file per experiment, named `EXXX_<slug>.json`. Fields (all required unless
marked optional; use `null` when genuinely not applicable):

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
