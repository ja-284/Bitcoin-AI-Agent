"""
Fictional demo data for the website (web/fixtures/demo.json): the real execution engine (strategy rule-1.0) run hour by
hour over an INVENTED price path in 2030, with invented signals that have no edge, a simulated exchange (default
fee 0.1% per side; `--fee`) and the owner's cap of 150. Every value is fictional and the document says so (`"fictional": true`). Real data never
goes into the repository: the website reads it through the two-factor login (docs/platform/PLATFORM_PLAN.md
section 7).

    python -m agent.execution.demo [--out web/fixtures/demo.json] [--days 400] [--fee 0.001]
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from agent.execution import strategy as st
from agent.execution.engine import run_hour
from agent.execution.exchange import SimulatedExchange
from agent.execution.strategy import Portfolio, Settings, Snapshot

START = datetime(2030, 1, 1, tzinfo=timezone.utc)
CAP = 150.0
CATEGORIES = ("trend", "momentum", "volume", "chart_pattern", "news")


def _path(hours: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """An invented BTC/NOK path: calm and volatile regimes that switch now and then, no drift."""
    vol = np.empty(hours)
    regime = 0
    for i in range(hours):
        if rng.random() < 1 / 400:
            regime = 1 - regime
        vol[i] = 0.0035 if regime == 0 else 0.009
    rets = rng.standard_t(5, hours) * vol / math.sqrt(5 / 3)
    price = 650_000 * np.exp(np.cumsum(rets))
    return price, rets


def _signals(hours: int, rng: np.random.Generator) -> list[str]:
    """Sticky invented signals with no relation to the path (the honest assumption for the current signal)."""
    out, cur = [], "HOLD"
    for _ in range(hours):
        if rng.random() < 0.16:
            cur = rng.choice(["BUY", "HOLD", "SELL"], p=[0.25, 0.37, 0.38])
        out.append(str(cur))
    return out


def build(days: int = 400, seed: int = 2030, fee: float = 0.001) -> dict:
    rng = np.random.default_rng(seed)
    hours = days * 24
    price, rets = _path(hours + 24, rng)
    sigs = _signals(hours + 24, rng)
    ex = SimulatedExchange(CAP, fee_rate=fee)
    settings = Settings(allocation_cap=CAP, min_order_value=20.0)
    pf = Portfolio(cash=CAP, peak_equity=CAP, equity_24h_ago=None)
    equity, bh, px_series, decisions, trades, events = [], [], [], [], [], []
    bh_btc = CAP * (1 - fee) / price[24]
    halted_since = None
    for k in range(hours):
        i = k + 24
        as_of = START + timedelta(hours=k)
        now = as_of + timedelta(hours=1, minutes=13)
        rv = float(np.std(rets[i - 24:i]))
        p_large = float(1 / (1 + math.exp(-(1.6 * math.log(rv / 0.0045)) + 0.6)))
        ex.price = float(price[i])
        if pf.halted and halted_since and now - halted_since >= timedelta(hours=12):
            events.append({"t": now.isoformat(), "kind": "resumed", "text": f"The owner resumed trading after: {pf.halted}"})
            pf, halted_since = replace(pf, halted=None, peak_equity=pf.equity(ex.price)), None
        pf = replace(pf, equity_24h_ago=equity[-24] if len(equity) >= 24 else None)
        snap = Snapshot(as_of=as_of, signal=sigs[i], price=ex.price, rv_24=rv, p_large=p_large,
                        pipeline_version="0.2.0", scoring_version="0.2.0",
                        overall_score=float(np.clip(rng.normal(0, 0.12) + {"BUY": 0.2, "SELL": -0.2, "HOLD": 0}[sigs[i]], -1, 1)),
                        confidence=float(np.clip(rng.normal(0.9, 0.06), 0.5, 1.0)))
        before = pf
        r = run_hour(snap, pf, settings, ex, now)
        pf = r.portfolio
        if r.decision and r.decision.halt and halted_since is None:
            halted_since = now
            events.append({"t": now.isoformat(), "kind": "halted", "text": r.decision.halt})
        eq = pf.equity(ex.price)
        equity.append(round(eq, 2))
        bh.append(round(bh_btc * ex.price, 2))
        px_series.append(round(ex.price))
        if r.fill:
            trades.append({"t": now.isoformat(), "as_of": as_of.isoformat(), "side": r.fill.side, "qty": round(r.fill.base_qty, 8),
                           "price": round(r.fill.price, 2), "amount": round(r.fill.quote_amount, 2), "fee": round(r.fill.fee, 2)})
        d = r.decision
        prev_eq = before.equity(float(price[i - 1])) if k else CAP
        decisions.append({
            "as_of": as_of.isoformat(), "decided_at": now.isoformat(), "signal": snap.signal, "action": d.action,
            "price": round(ex.price, 2), "equity": round(eq, 2), "hour_change": round(eq - prev_eq, 2),
            "exposure_before": round(d.exposure_before, 2), "target": round(d.target_exposure, 2),
            "factors": {k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in d.factors.items()},
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in d.checks],
            "reasons": list(d.reasons), "overall_score": round(snap.overall_score, 3), "confidence": round(snap.confidence, 3),
            "p_large": round(p_large, 3), "rv_24": round(rv, 5),
            "category_scores": {c: round(float(np.clip(rng.normal(snap.overall_score, 0.25), -1, 1)), 2) for c in CATEGORIES},
            "explanation": f"Fictional demo explanation for {as_of:%d %b %H:00}: the invented signal was {snap.signal}; "
                           f"{d.reasons[-1] if d.reasons else ''}.",
            "fill": trades[-1] if r.fill else None,
        })
    last = len(equity) - 1
    eq_now, price_now = equity[last], px_series[last]
    peak = max(equity)
    detail = decisions[-14 * 24:]
    compact = [{k2: x[k2] for k2 in ("as_of", "signal", "action", "equity", "hour_change")} for x in decisions[-90 * 24:]]
    as_of_last = START + timedelta(hours=last)
    return {
        "fictional": True,
        "note": "Every value in this file is invented (2030). It exists to build and test the website.",
        "schema": "platform-state 0 (draft)",
        "generated_at": (as_of_last + timedelta(hours=1, minutes=14)).isoformat(),
        "account": {"currency": "NOK", "venue": "Demo exchange (simulated)", "mode": "halted" if pf.halted else "live",
                    "halted": pf.halted, "strategy_version": st.STRATEGY_VERSION, "allocation_cap": CAP,
                    "hard_max": st.HARD_MAX_ALLOCATION, "deposited": CAP,
                    "exchange_balance": {"cash": round(ex.balances()["cash"], 2), "btc": round(ex.balances()["btc"], 8)},
                    "unallocated": 0.0, "fee_rate": fee},
        "portfolio": {"equity": eq_now, "cash": round(pf.cash, 2), "btc": round(pf.btc, 8), "btc_value": round(pf.btc * price_now, 2),
                      "price": price_now, "peak": peak, "drawdown": round(1 - eq_now / peak, 4),
                      "fees_paid": round(sum(t["fee"] for t in trades), 2), "trades": len(trades),
                      "buy_hold": bh[last]},
        "series": {"start": START.isoformat(), "step_hours": 1, "equity": equity, "buy_hold": bh, "price": px_series},
        "trades": trades, "events": events, "decisions": detail, "activity": compact,
        "limits": {"band_fraction": st.BAND_FRACTION, "min_hold_hours": st.MIN_HOLD_HOURS, "max_trades_24h": st.MAX_TRADES_24H,
                   "daily_loss_limit": st.DAILY_LOSS_LIMIT, "max_drawdown": st.MAX_DRAWDOWN,
                   "target_hourly_vol": st.TARGET_HOURLY_VOL, "min_order_value": settings.min_order_value},
        "system": {"runs_7d": 168, "missing_7d": 0, "last_run": (as_of_last + timedelta(hours=1, minutes=13)).isoformat(),
                   "next_run": (as_of_last + timedelta(hours=2, minutes=12)).isoformat(), "heartbeat": "ok",
                   "incidents": [{"t": (as_of_last - timedelta(days=4)).isoformat(), "kind": "github_internal_error",
                                  "text": "Fictional: a reporting run failed on GitHub's side; the next one published."}]},
        "research": {
            "signal_label": "no demonstrated predictive value",
            "inputs": [
                {"name": "BUY/HOLD/SELL signal", "version": "scoring 0.2.0", "status": "no demonstrated predictive value",
                 "used_for": "direction of the target"},
                {"name": "Move-size probability", "version": "move_size_1h_v1", "status": "skill on prospective data so far (descriptive)",
                 "used_for": "size (f_move)"},
                {"name": "24 h realised volatility", "version": "stored input", "status": "a risk measure, not a forecast",
                 "used_for": "size (f_vol)"},
                {"name": "Confidence heuristic", "version": "agreement + completeness", "status": "uninformative (not calibrated)",
                 "used_for": "nothing (disabled)"},
                {"name": "Direction model", "version": "direction_1h_v1", "status": "blind until its registered readings",
                 "used_for": "nothing, not shown"}],
            "checkpoints": [{"name": "Move-size, 2,000 h (E012 verdict)", "done": 1640, "of": 2000, "eta": "fictional"},
                            {"name": "Direction first look, 1,000 h", "done": 820, "of": 1000, "eta": "fictional"},
                            {"name": "News verdict, 3,140 h", "done": 1590, "of": 3140, "eta": "fictional"}]},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", default="web/fixtures/demo.json")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--fee", type=float, default=0.001)
    args = ap.parse_args()
    doc = build(args.days, fee=args.fee)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    p = doc["portfolio"]
    print(f"wrote {args.out}: {len(doc['series']['equity'])} hours, {p['trades']} trades, equity {p['equity']} "
          f"(buy-and-hold {p['buy_hold']}), fees {p['fees_paid']}, mode {doc['account']['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
