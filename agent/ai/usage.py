"""
What each AI call actually consumed, so the project's cost is measured rather than estimated.

Until 2026-09-23 the cost of the two AI calls was a back-of-envelope figure ("about $0.02 a run"),
and the one open cost decision (docs/ops/open_user_actions.md, item 4) rested on it. The API
reports the exact token counts with every answer; this module keeps them.

The AI modules call record() after each answer arrives. The orchestrator opens a recording()
around the run and stores what was collected in run_meta["ai_usage"]. Nothing else changes: the
calls, prompts and schemas are untouched, and no function signature moved, so the validated AI
components (E009) are exactly what they were.

Recording is bookkeeping and must never cost the analysis anything, so record() cannot raise. An
answer that arrives without usage figures is recorded as such -- visibly unavailable, never zero.
"""

from contextlib import contextmanager
from typing import Iterator

_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
_sink: dict | None = None


@contextmanager
def recording() -> Iterator[dict]:
    """Collect the usage of every AI call made inside the block, keyed by step."""
    global _sink
    previous, _sink = _sink, {}
    try:
        yield _sink
    finally:
        _sink = previous


def record(step: str, model: str, response) -> None:
    """Keep what one answer consumed. Outside a recording() it does nothing."""
    if _sink is None:
        return
    try:
        usage = getattr(response, "usage", None)
        counts = {f: getattr(usage, f) for f in _FIELDS if isinstance(getattr(usage, f, None), int)}
        _sink[step] = {"model": model, **counts} if "input_tokens" in counts and "output_tokens" in counts \
            else {"model": model, "usage_unavailable": True}
    except Exception:  # noqa: BLE001 -- bookkeeping must never be able to fail a run
        _sink[step] = {"model": model, "usage_unavailable": True}
