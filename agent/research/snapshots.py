"""
The governed reader for the stored research snapshots under data/ (master plan "Safe signal research", Phase 1,
2026-10-17). Before it, each side-data loader (trade counts, funding, premium, macro, on-chain, difficulty) read its
WHOLE dated file -- the sealed holdout's period included -- into memory, and quietly downloaded a fresh file whenever
none was found. Nothing of the holdout was ever scored that way (every feature is cut to a candle grid that stops at
the holdout), but prohibited rows did enter the research pipeline, and a missing file would have been replaced by a
different version without anyone deciding it.

What this module guarantees:
  * Only REGISTERED snapshots are served: a fixed file name; the count and sha256 of its development rows; the whole
    file's size and sha256. A missing, changed, re-ordered or unregistered file is refused (SnapshotError). Nothing
    is downloaded, and no other or newer file is ever substituted.
  * Rows are cut by when their information became VISIBLE, using each dataset's own point-in-time rule
    (`visible_after`): only rows visible at or before `until` are served. `until` may not pass the last development
    cutoff -- HOLDOUT.start, the close of the 2025-06-30 23:00 candle -- unless the holdout was opened in this process
    through history.load_bars(allow_holdout=True, reason=...), the one logged route.
  * Up to that cutoff the file is read line by line, and reading STOPS at the first row that is not yet visible: only
    that row's timestamp is decoded, and no later byte is read.
  * A refused snapshot is never opened.

Why the cut cannot change a development result: every feature at reference hour t uses only rows visible at its
cutoff t + 1 h, and the latest development cutoff is HOLDOUT.start. Serving exactly the rows visible at that instant
therefore leaves every development feature value as it was (tests/test_snapshots.py proves it on synthetic data).
"""

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from agent.research import history
from agent.research.periods import HOLDOUT

DATA_DIR = history.DATA_DIR
DEVELOPMENT_CUTOFF = HOLDOUT.start  # the information cutoff of the last development hour, 2025-06-30 23:00 UTC


class SnapshotError(RuntimeError):
    """A snapshot that cannot be served exactly as registered: missing, changed, out of order, unregistered or refused."""


@dataclass(frozen=True)
class Snapshot:
    file: str
    time_column: str             # the first column: the row's own timestamp
    visible_after: timedelta     # the dataset's point-in-time rule: a row stamped T is known from T + visible_after
    development_rows: int        # rows visible at or before DEVELOPMENT_CUTOFF
    development_sha256: str      # of the header line plus exactly those rows, as stored bytes
    file_bytes: int
    file_sha256: str             # of the whole file: checked only on the logged holdout route
    refused: str = ""            # non-empty: never served, for this reason


# Registered 2026-10-17 from a structural scan that decoded only each row's timestamp (counts, order and hashes; no
# value). Every file is strictly increasing in time, so the development rows are exactly the file's leading rows.
REGISTERED: dict[str, Snapshot] = {
    "klines_extra": Snapshot("klines_extra_btcusdt_1h_2026-09-20.csv", "as_of", timedelta(hours=1), 68868,
                             "04f0a2a0eed976cb5a683be8af8f79aee66a6681a9ee156448ff33c30dac7fa8", 4349306,
                             "2ffa82b08affa136f1b666bb51d00e78d82355bd5e30f9b299ff62235a39ee86"),
    "funding": Snapshot("funding_btcusdt_2026-09-20.csv", "funding_time", timedelta(0), 6362,
                        "7d29ef1a44e1927223f3dcc93c5e7665a18e16e3b363e33551e5e4e926929b76", 301405,
                        "77b269d5382ea58a1a91c200b5a22da792049d7f00235304237fcd970c569d13"),
    "premium": Snapshot("premium_btcusdt_1h_2026-09-20.csv", "as_of", timedelta(hours=1), 48380,
                        "047be9d9aaed6d11c34990ddf6a17eaf9f1961b21c4793b856c45350fa1e8f10", 4284447,
                        "246068a95f078f2e041160c0099379ce117e46d6360cc267593e218a26b1fd97"),
    "onchain": Snapshot("onchain_2026-09-20.csv", "day", timedelta(hours=30), 6022,
                        "93efc841bcbe15ed4c281ac6437c263554c03a1735c949c8e78233d4fe3ea473", 496245,
                        "38ce35f708ef5f44d2029ad3efb553eb84e6eef196a836d88da12c84ef18945b"),
    "difficulty": Snapshot("difficulty_adjustments_2026-09-20.csv", "adjusted_at", timedelta(0), 434,
                           "0e950a6146b960b3e4e8d08da368fb88a584f23f5f97803d061b028a46edd348", 28123,
                           "567fd953a4ea9e17384e401a7d4cfa036d8e307b0ce9fc0b359408b0dc31f386"),
    "macro": Snapshot("macro_2026-09-20.csv", "trading_date", timedelta(hours=22), 488,
                      "36367624183ec40c84fddaf8739fafeed969d377625c969b8b5816a311aee51b", 28574,
                      "6d15db0de4ad51515293086fa1c3ea3b4d092f31b2de6bd57ac1be3ed6f9a9bd",
                      refused="its rows are not daily closes: Yahoo returned one bar per quarter (S&P, Nasdaq, dollar, "
                              "10-year yield) or roughly per month (gold, oil), each stamped at its START and holding "
                              "the close at its END. Read as daily bars visible at D 22:00 UTC, each value was seen up "
                              "to about three months before it existed (found 2026-10-17; E006 and E011's set B are "
                              "affected). A daily snapshot must be downloaded and registered before macro is served."),
}


def information_cutoff(bars) -> datetime:
    """The last instant whose information a set of candles may use: the close of the latest one."""
    return max(b.as_of for b in bars) + timedelta(hours=1)


def _time(field: bytes) -> datetime:
    t = datetime.fromisoformat(field.decode("ascii"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)  # a date-only stamp (macro) is a UTC date


def read_snapshot_rows(name: str, until: datetime = DEVELOPMENT_CUTOFF) -> bytes:
    """The registered snapshot's header plus its rows visible at or before `until`, exactly as stored."""
    snap = REGISTERED.get(name)
    if snap is None:
        raise SnapshotError(f"{name!r} is not a registered snapshot (agent/research/snapshots.py REGISTERED)")
    if snap.refused:
        raise SnapshotError(f"{name} ({snap.file}) is refused: {snap.refused}")
    if until.tzinfo is None:
        raise ValueError("until must be timezone-aware (UTC)")
    whole = until > DEVELOPMENT_CUTOFF
    if whole and not history.holdout_opened():
        raise history.HoldoutAccessError(
            f"{name}: rows visible after {DEVELOPMENT_CUTOFF.isoformat()} belong to the sealed holdout; they are served "
            "only after history.load_bars(allow_holdout=True, reason=...) opened it in this process (logged)")
    path = DATA_DIR / snap.file
    if not path.is_file():
        raise SnapshotError(f"{path.as_posix()} is missing. Governed research never downloads a replacement or uses "
                            "another file: restore the registered snapshot, or register a new one in a reviewed commit")

    dev_hash, file_hash = hashlib.sha256(), hashlib.sha256()
    dev_rows, previous, in_development = 0, None, True
    with path.open("rb") as f:
        header = f.readline()
        if header.split(b",", 1)[0].strip() != snap.time_column.encode():
            raise SnapshotError(f"{snap.file}: the first column is not {snap.time_column!r}")
        kept = [header]
        dev_hash.update(header)
        file_hash.update(header)
        for line in f:
            t = _time(line.split(b",", 1)[0])
            if previous is not None and t <= previous:
                raise SnapshotError(f"{snap.file}: rows are not strictly increasing in time at {t.isoformat()}")
            previous = t
            visible = t + snap.visible_after
            if in_development and visible > DEVELOPMENT_CUTOFF:
                in_development = False
                if not whole:
                    break  # the first row not visible at the last development cutoff: nothing after it is read
            if in_development:
                dev_hash.update(line)
                dev_rows += 1
            file_hash.update(line)
            if visible <= until:
                kept.append(line)
    if dev_rows != snap.development_rows or dev_hash.hexdigest() != snap.development_sha256:
        raise SnapshotError(f"{snap.file}: the development rows are not the registered ones ({dev_rows} rows, sha256 "
                            f"{dev_hash.hexdigest()[:12]}...; registered {snap.development_rows}, {snap.development_sha256[:12]}...)")
    if whole and (file_hash.hexdigest() != snap.file_sha256 or path.stat().st_size != snap.file_bytes):
        raise SnapshotError(f"{snap.file}: the file is not the registered one (size or sha256 differs)")
    return b"".join(kept)


def read_snapshot_frame(name: str, until: datetime = DEVELOPMENT_CUTOFF, **read_csv_kwargs) -> pd.DataFrame:
    """read_snapshot_rows(), parsed bit-exactly (float_precision="round_trip", tests/test_numeric_precision.py)."""
    return pd.read_csv(io.BytesIO(read_snapshot_rows(name, until)), float_precision="round_trip", **read_csv_kwargs)
