"""
Version stamps stored with every prediction, so later analysis never silently mixes
results produced by different versions of the system.

- PIPELINE_VERSION: how data is gathered, time-bounded and validated. Bumped whenever a
  fix changes what information a prediction could see (e.g. the news cutoff fix).
- SCORING_VERSION (in agent/scoring/scorer.py): the formulas, weights and thresholds.

History:
  pipeline 0.1.0  go-live 2026-09-19. News was collected up to fetch time, i.e. after
                  the reference candle had closed (leakage into short horizons).
  pipeline 0.2.0  explicit information cutoff = reference candle close; news limited to
                  items available at or before the cutoff; undated items excluded.

  scoring 0.1.0   the original formulas; the baseline evaluated by E001, E002 and E011.
                  "Enough history" counted ROWS, so a window containing missing hours was
                  treated as consecutive.
  scoring 0.2.0   2026-09-22. Same formulas, weights and thresholds; history is now counted
                  in CONSECUTIVE hours. Indicators run on the unbroken run ending at the
                  reference candle, the volume category looks its reference hour up by
                  timestamp, and the trend-structure window is 20 real hours. Anything whose
                  hours are missing is unavailable rather than wrong. Identical output on a
                  gap-free window, which is every live hour so far; it differs only on the
                  9.26% of historical hours whose window had a gap.
"""

PIPELINE_VERSION = "0.2.0"
