"""
Oppdiktede demodata for papirhandelens mobilside: den EKTE papirmotoren (`run.decide_day`, de 118 strategiene i pt-1.0)
kjørt dag for dag på syntetiske kurser fra 2030, pluss en syntetisk Firi-ordrebok og syntetiske handler. Alt er
oppdiktet og merket `"fictional": true`; ingen database, ingen nettverk, ingen ekte data.

    python -m agent.papertrade.demo [--out web/papir/demo.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from agent.papertrade import run as R
from agent.papertrade import snapshot as P
from agent.papertrade import strategies as S

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
NOK_PER_USD = 10.6


def synthetic_record(days: int, seed: int):
    """Timesrader som ser ut som det live registeret: (as_of, close, signal, score) og (as_of, p)."""
    rng = np.random.default_rng(seed)
    n = days * 24
    drift = np.where(np.arange(n) < n * 0.8, 0.00011, -0.00012)  # en stigende og så en fallende periode
    close = 52_000 * np.exp(np.cumsum(rng.normal(drift, 0.0065, n)))
    score = np.clip(rng.normal(0, 0.18, n) + 0.4 * np.r_[0, np.diff(np.log(close))] * 50, -1, 1)
    sig = np.where(score >= 0.15, "BUY", np.where(score <= -0.15, "SELL", "HOLD"))
    p = np.clip(0.3 + 25 * np.abs(rng.normal(0, 0.006, n)) + rng.normal(0, 0.05, n), 0.05, 0.95)
    pred = [(T0 + timedelta(hours=h), float(close[h]), str(sig[h]), float(score[h])) for h in range(n)]
    shadow = [(T0 + timedelta(hours=h), float(p[h])) for h in range(n)]
    return pred, shadow


def build(days: int = 330, paper_days: int = 120, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed + 1)
    df = S.daily_frame(*synthetic_record(days, seed))
    specs = S.strategy_set(df)
    first = len(df) - paper_days
    states: dict = {}
    day_rows, ledger = [], []
    for i in range(first, len(df)):
        mid = float(df["close"].iat[i]) * NOK_PER_USD
        half = mid * rng.uniform(0.0035, 0.0075)
        fetched = datetime.combine(df.index[i].date() + timedelta(days=1), datetime.min.time(), timezone.utc) \
            + timedelta(minutes=12)
        quote = (round(mid - half, 2), round(mid + half, 2), fetched)
        rows = R.decide_day(df, specs, i, states, quote)
        for r in rows:
            states[(r["strategy"], r["book"])] = R.engine.State(**r.pop("state"))
        ledger += rows
        day_rows.append({"day": df.index[i].date(), "close": float(df["close"].iat[i]), "firi_bid": quote[0],
                         "firi_ask": quote[1], "inputs": {}, "strategies": len(specs)})
    end = datetime.combine(df.index[-1].date() + timedelta(days=1), datetime.min.time(), timezone.utc)
    quotes, trades = [], []
    last_mid = day_rows[-1]["firi_bid"]
    for h in range(30 * 24):
        at = end - timedelta(hours=30 * 24 - h)
        spread = 0.008 + 0.006 * (1 + np.sin((at.hour - 3) / 24 * 2 * np.pi)) / 2 + rng.uniform(0, 0.004)
        m = last_mid * (1 + rng.normal(0, 0.01))
        bid, ask = m * (1 - spread / 2), m * (1 + spread / 2)
        quotes.append({"hour": at, "fetched_at": at + timedelta(minutes=12), "bid": bid, "ask": ask,
                       "buy_500_avg": ask, "sell_500_avg": bid, "depth_bid_nok": rng.uniform(4e5, 2e6),
                       "depth_ask_nok": rng.uniform(4e5, 2e6)})
        for _ in range(rng.poisson(20)):
            side = "bid" if rng.random() < 0.6 else "ask"
            t = at + timedelta(minutes=float(rng.uniform(0, 60)))
            price = (ask if side == "bid" else bid) * (1 + rng.normal(0, 0.002))
            amount = float(rng.exponential(0.002))
            trades.append({"traded_at": t, "side": side, "price": price, "amount": amount, "total": price * amount,
                           "fetched_at": min(t + timedelta(minutes=50), end)})
    return P.build_document(day_rows, ledger, quotes, trades, [], now=end + timedelta(minutes=13), fictional=True,
                            first_day=day_rows[0]["day"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="web/papir/demo.json")
    a = ap.parse_args(argv)
    doc = build()
    doc["note"] = "OPPDIKTET DEMO (2030): alle tall er laget for å bygge og teste siden. " + doc["note"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"skrev {a.out}: {len(doc['days'])} dager, {len(doc['books']['firi']['accounts'])} kontoer per bok, "
          f"{Path(a.out).stat().st_size // 1024} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
