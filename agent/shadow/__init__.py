"""
The live SHADOW record of the research move-size model (Phase 13).

Every hour, next to the live analysis, this package computes the research model's
probability that the next hour's move exceeds its threshold and stores it with enough
metadata to reproduce it. It is judged only after the outcome candle exists.

Hard boundaries:
  - it never reads or changes the live BUY/HOLD/SELL decision, its scores or its confidence
  - it never places or simulates orders
  - its model is a frozen, versioned JSON artefact (agent/shadow/models/); a new model is a
    new version, never an edit
  - its rows live in their own table (shadow_move_size); the live tables are untouched
"""
