"""
Print a reporting document as JSON. Reads the record read-only; writes nothing, anywhere.

    python -m agent.reporting latest
    python -m agent.reporting runs [--limit 24] [--before 2026-09-27T06:00:00+00:00]
    python -m agent.reporting run --hour 2026-09-27T06:00:00+00:00
    python -m agent.reporting statistics
    python -m agent.reporting health
    python -m agent.reporting all
        [--at <ISO time>]   the record exactly as it stood at that moment (default: now)
        [--pretty]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.reporting import views
from agent.reporting.source import load
from agent.research.live_checkpoint import CHECKPOINTS, OUT_DIR, TERCILES_PATH

KINDS = ("latest", "runs", "run", "statistics", "health", "all")


def _utc(text: str) -> datetime:
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def computed_readings(out_dir: Path = OUT_DIR) -> dict[int, str]:
    """Registered checkpoint readings that exist on disk (written once by live_checkpoint, never here)."""
    return {c: str(out_dir / f"checkpoint_{c}h.md") for c in CHECKPOINTS if (out_dir / f"checkpoint_{c}h.md").exists()}


def frozen_terciles(path: Path = TERCILES_PATH) -> tuple[float, float] | None:
    if not path.exists():
        return None
    return tuple(json.loads(path.read_text(encoding="utf-8"))["tercile_cut_points"])


def build(kind: str, at: datetime, now: datetime, limit: int = 24, before: datetime | None = None,
          hour: datetime | None = None) -> dict:
    records = load(detail_hour=hour if kind == "run" else None)
    computed, terciles = computed_readings(), frozen_terciles()
    if kind == "latest":
        body = views.latest_run(records, at)
    elif kind == "runs":
        body = views.recent_runs(records, at, limit=limit, before=before)
    elif kind == "run":
        body = views.run_at(records, at, hour) or {"found": False, "hour": views.iso(hour),
                                                    "reason": "no run for this hour was saved by the requested time"}
    elif kind == "statistics":
        body = {"signal": views.signal_statistics(records, at),
                "move_size": views.move_size_statistics(records, at, computed),
                "move_size_breakdowns": views.move_size_breakdowns(records, at, terciles)}
    elif kind == "health":
        body = views.health(records, at, computed)
    else:
        body = views.report(records, at, terciles, computed)
    return views.document(kind, body, at, now)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only statistics and reporting over the live record.")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--at", help="view the record exactly as it stood at this ISO time (default: now)")
    parser.add_argument("--limit", type=int, default=24, help="runs: how many, newest first")
    parser.add_argument("--before", help="runs: only hours strictly before this ISO time (paging)")
    parser.add_argument("--hour", help="run: the reference hour (ISO)")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    at = _utc(args.at) if args.at else now
    if at > now:
        parser.error("--at cannot be in the future")
    if args.kind == "run" and not args.hour:
        parser.error("run needs --hour")
    doc = build(args.kind, at, now, limit=args.limit, before=_utc(args.before) if args.before else None,
                hour=_utc(args.hour) if args.hour else None)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(doc, indent=2 if args.pretty else None, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
