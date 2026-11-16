"""
Henter E043s tre nye øyeblikksbilder (research/experiments/E043_fall_sources.json, registrert i 9a67dea før dette
verktøyet fantes) til data/, og skriver ut det som skal inn i agent/research/snapshots.py REGISTERED.

    python tools/fetch_e043_snapshots.py

- Bare offentlige endepunkter, ingen nøkkel.
- Bare til og med lyset som åpner 2025-06-30 22:00 UTC: ingen rad fra den forseglede holdout-perioden lastes ned, og
  verktøyet stopper hvis en kilde likevel gir en senere rad.
- Overskriver aldri en fil som finnes (et registrert øyeblikksbilde endres ikke).
- Radene er sortert og strengt økende i tid, med kildens egne verdier (Bybit gir tekst; den lagres slik den kom).
"""

from __future__ import annotations

import hashlib
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.research import history  # noqa: E402

LAST = datetime(2025, 6, 30, 22, tzinfo=timezone.utc)   # det siste lyset; det er ferdig ved utviklingsgrensen 23:00
LAST_MS = int(LAST.timestamp() * 1000)
STAMP = "2026-11-16"
UA = {"User-Agent": "bitcoin-agent-research/1.0"}
H = 3_600_000


def _get(url: str, params: dict) -> object:
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=30, headers=UA)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"{url}: rate limited five times")


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def fetch_dvol() -> list[tuple[int, list]]:
    start = int(datetime(2021, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows: dict[int, list] = {}
    t = start
    while t <= LAST_MS:
        end = min(t + 30 * 24 * H, LAST_MS)
        d = _get("https://www.deribit.com/api/v2/public/get_volatility_index_data",
                 {"currency": "BTC", "start_timestamp": t, "end_timestamp": end, "resolution": 3600})
        for ts, o, hi, lo, c in d["result"]["data"]:
            if int(ts) <= LAST_MS:
                rows[int(ts)] = [o, hi, lo, c]
        t = end + H
        time.sleep(0.2)
    return sorted(rows.items())


def fetch_oi_bybit() -> list[tuple[int, list]]:
    rows: dict[int, list] = {}
    t = int(datetime(2020, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while t <= LAST_MS:
        end = min(t + 199 * H, LAST_MS)
        d = _get("https://api.bybit.com/v5/market/open-interest",
                 {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h", "startTime": t, "endTime": end,
                  "limit": 200})
        for x in d["result"]["list"]:
            ts = int(x["timestamp"])
            if ts <= LAST_MS:
                rows[ts] = [x["openInterest"]]
        t = end + H
        time.sleep(0.15)
    return sorted(rows.items())


def fetch_margin_bitfinex() -> list[tuple[int, list]]:
    out = {}
    for side in ("long", "short"):
        t = int(datetime(2021, 2, 1, tzinfo=timezone.utc).timestamp() * 1000)
        series = {}
        while t <= LAST_MS:
            d = _get(f"https://api-pub.bitfinex.com/v2/stats1/pos.size:1h:tBTCUSD:{side}/hist",
                     {"limit": 10000, "sort": 1, "start": t, "end": LAST_MS})
            if not d:
                break
            for ts, v in d:
                if int(ts) <= LAST_MS:
                    series[int(ts)] = v
            last = max(int(x[0]) for x in d)
            if last <= t:
                break
            t = last + 1
            time.sleep(1.5)
        out[side] = series
    stamps = sorted(set(out["long"]) & set(out["short"]))  # bare timer der begge sidene finnes
    return [(ts, [out["long"][ts], out["short"][ts]]) for ts in stamps]


def write(name: str, header: str, rows: list[tuple[int, list]]) -> dict:
    path = history.DATA_DIR / name
    if path.exists():
        raise SystemExit(f"{path} finnes allerede: et registrert øyeblikksbilde overskrives aldri")
    assert rows, name
    assert all(ts % H == 0 for ts, _ in rows), f"{name}: et tidsstempel er ikke på hel time"
    assert rows[-1][0] <= LAST_MS, f"{name}: en rad etter utviklingsperioden"
    assert all(a[0] < b[0] for a, b in zip(rows, rows[1:])), f"{name}: ikke strengt økende"
    lines = [header + "\n"] + [",".join([iso(ts)] + [repr(v) if isinstance(v, float) else str(v) for v in vals]) + "\n"
                               for ts, vals in rows]
    data = "".join(lines).encode("ascii")
    path.write_bytes(data)
    return {"file": name, "rows": len(rows), "first": iso(rows[0][0]), "last": iso(rows[-1][0]),
            "gaps": sum(1 for a, b in zip(rows, rows[1:]) if b[0] - a[0] != H),
            "development_sha256": hashlib.sha256(data).hexdigest(), "file_bytes": len(data)}


def main() -> int:
    plans = [("dvol", f"dvol_btc_1h_{STAMP}.csv", "as_of,open,high,low,close", fetch_dvol),
             ("oi_bybit", f"oi_bybit_btcusdt_1h_{STAMP}.csv", "as_of,open_interest", fetch_oi_bybit),
             ("margin_bitfinex", f"margin_bitfinex_btcusd_1h_{STAMP}.csv", "as_of,longs,shorts", fetch_margin_bitfinex)]
    for key, name, header, fetch in plans:
        info = write(name, header, fetch())
        print(key, info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
