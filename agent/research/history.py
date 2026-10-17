"""
Downloads, validates, caches and serves the full hourly history for research.

- One snapshot per download date under data/ (git-ignored): experiments record which
  snapshot they used, so a re-run months later can use the same bytes.
- Every load is validated (see data_providers/quality.py): impossible data raises, gaps
  are reported and never filled.
- load_bars() reads only the registered snapshot, through the governed reader in
  agent/research/snapshots.py: it never downloads (download_snapshot() is run by hand only,
  and a new file is used only after it is registered in a reviewed commit).
- The sealed holdout is protected here: load_bars() refuses candles at or after
  HOLDOUT.start unless allow_holdout=True, and every allowed access is appended to
  research/HOLDOUT_ACCESS.log so it can never happen quietly.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from agent.data_providers.binance import BinanceProvider
from agent.data_providers.quality import BarQualityReport, validate_bars
from agent.research.periods import DATA_START, HOLDOUT
from agent.shared.types import PriceBar

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
HOLDOUT_LOG = Path("research") / "HOLDOUT_ACCESS.log"
FIELDS = ["as_of", "open", "high", "low", "close", "volume"]


class HoldoutAccessError(RuntimeError):
    pass


# The logged reason, set only by load_bars(allow_holdout=True, reason=...) in this process. The side-data reader
# (agent/research/snapshots.py) serves rows past the holdout's start only when it is set.
_HOLDOUT_OPENED_FOR = ""


def holdout_opened() -> bool:
    return bool(_HOLDOUT_OPENED_FOR)


def snapshot_path(snapshot_date: str) -> Path:
    return DATA_DIR / f"btcusdt_1h_{snapshot_date}.csv"


def download_snapshot(end: datetime | None = None) -> Path:
    """Fetches the whole history up to `end` (default: last closed hour) and writes one CSV snapshot."""
    end = end or datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = int((end - DATA_START).total_seconds() // 3600) + 1
    logger.info("Downloading %d hours of history ending %s", hours, end.isoformat())
    bars = BinanceProvider().get_history(end=end, hours=hours)
    report = validate_bars(bars)
    logger.info("Downloaded %d candles, %d gap(s), %d missing hour(s)", report.count, len(report.gaps), report.missing_hours)

    DATA_DIR.mkdir(exist_ok=True)
    path = snapshot_path(datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for b in bars:
            writer.writerow([b.as_of.isoformat(), b.open, b.high, b.low, b.close, b.volume])
    return path


def _parse(text: str) -> list[PriceBar]:
    return [
        PriceBar(
            as_of=datetime.fromisoformat(row["as_of"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            source="binance",
        )
        for row in csv.DictReader(io.StringIO(text, newline=""))
    ]


def load_bars(
    start: datetime | None = None,
    end: datetime | None = None,
    allow_holdout: bool = False,
    reason: str = "",
) -> tuple[list[PriceBar], BarQualityReport, Path]:
    """
    Candles with start <= as_of < end from the REGISTERED snapshot ("spot" in agent/research/snapshots.py), through
    the governed reader: never downloaded, never another or newer file (since 2026-10-17; until then it took the
    newest file, downloaded one when none existed, and parsed the whole file before cutting it). Without
    allow_holdout, `end` is cut to HOLDOUT.start and reading stops at the holdout's first candle. allow_holdout=True
    needs a written reason, which is logged to research/HOLDOUT_ACCESS.log before a byte past the cutoff is read.
    """
    from agent.research import snapshots  # here, not at the top: snapshots imports this module

    if allow_holdout:
        if not reason:
            raise HoldoutAccessError("allow_holdout=True requires a written reason")
        HOLDOUT_LOG.parent.mkdir(exist_ok=True)
        with HOLDOUT_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(tz=timezone.utc).isoformat()}\t{reason}\n")
        logger.warning("HOLDOUT ACCESS: %s", reason)
        global _HOLDOUT_OPENED_FOR
        _HOLDOUT_OPENED_FOR = reason
        requested_end = end or datetime(2100, 1, 1, tzinfo=timezone.utc)
    else:
        requested_end = end or HOLDOUT.start
        if requested_end > HOLDOUT.start:
            logger.warning("Requested range reaches the sealed holdout; truncating at %s", HOLDOUT.start.isoformat())
            requested_end = HOLDOUT.start

    # An hourly candle opened at as_of is known from as_of + 1 h, so "visible by requested_end" is "as_of < requested_end".
    bars = _parse(snapshots.read_snapshot_rows("spot", requested_end).decode("utf-8"))
    selected = [b for b in bars if (start is None or b.as_of >= start) and b.as_of < requested_end]
    if not selected:
        raise ValueError("no candles in the requested range")
    return selected, validate_bars(selected), snapshots.DATA_DIR / snapshots.REGISTERED["spot"].file
