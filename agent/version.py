"""
Version stamps stored with every prediction, so later analysis never silently mixes
results produced by different versions of the system.

- PIPELINE_VERSION: how data is gathered, time-bounded and validated. Bumped whenever a
  fix changes what information a prediction could see (e.g. the news cutoff fix).
- SCORING_VERSION (in agent/scoring/scorer.py): the formulas, weights and thresholds.
  Unchanged since 0.1.0 -- the original scoring is the baseline under evaluation.

History:
  pipeline 0.1.0  go-live 2026-09-19. News was collected up to fetch time, i.e. after
                  the reference candle had closed (leakage into short horizons).
  pipeline 0.2.0  explicit information cutoff = reference candle close; news limited to
                  items available at or before the cutoff; undated items excluded.
"""

PIPELINE_VERSION = "0.2.0"
