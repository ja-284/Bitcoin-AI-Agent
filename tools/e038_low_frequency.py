"""
E038's command (research/experiments/E038_low_frequency_execution.json), and the one place that imports both the
research simulator (agent/research/low_frequency.py) and the production execution layer (agent/execution). The
prediction engine and its research must never import the execution layer (tests/test_execution.py), so the check that
the simulator's lean copy of rule-1.0 reproduces the real engine exactly lives here, in tools/.

    python tools/e038_low_frequency.py            # the registered development run
    python tools/e038_low_frequency.py --live     # the descriptive live run (read-only database)
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.execution import strategy as st  # noqa: E402
from agent.execution.engine import run_hour  # noqa: E402
from agent.execution.exchange import SimulatedExchange  # noqa: E402
from agent.research import low_frequency as lf  # noqa: E402


def check_constants() -> None:
    got = (st.TARGET_HOURLY_VOL, st.F_VOL_MIN, st.F_MOVE_MIN, st.BAND_FRACTION, st.MIN_HOLD_HOURS * 60,
           st.DAILY_LOSS_LIMIT, st.MAX_DRAWDOWN, st.MAX_TRADES_24H, st.MAX_SIGNAL_AGE_HOURS)
    want = (lf.TARGET_HOURLY_VOL, lf.F_VOL_MIN, lf.F_MOVE_MIN, lf.BAND_FRACTION, lf.MIN_HOLD_MIN, lf.DAILY_LOSS_LIMIT,
            lf.MAX_DRAWDOWN, 4, 2.0)
    if got != want:
        raise SystemExit(f"rule-1.0's constants changed since E038 was registered: {got} != {want}")


def reference_run(hours, close, eff, rv, p, lo, hi, c, max_actions) -> tuple[list, float]:
    """The production engine on the same path: agent.execution.engine.run_hour + strategy.decide + SimulatedExchange
    (fee_rate = c, slippage 0). The driver does what the storage layer will: the equity 24 h earlier, the trade times
    of the last 24 h, and (the simulation's stand-in for the owner) lifting a halt after 168 h with the peak reset."""
    old = st.MAX_TRADES_24H
    st.MAX_TRADES_24H = max_actions
    try:
        settings = st.Settings(allocation_cap=lf.CAP, min_order_value=lf.MIN_ORDER)
        ex = SimulatedExchange(lf.CAP, fee_rate=c, slippage=0.0)
        pf = st.Portfolio(cash=lf.CAP, peak_equity=lf.CAP)
        eq_by_hour: dict[int, float] = {}
        actions, halt_at, day = [], None, timedelta(hours=24)
        H, P, E, RV, PL = hours.tolist(), close.tolist(), eff.tolist(), rv.tolist(), p.tolist()
        for i in range(lo, hi):
            as_of = datetime.fromtimestamp(H[i] * 3600, tz=timezone.utc)
            now = as_of + timedelta(minutes=lf.DECISION_DELAY_MIN)
            price = P[i]
            ex.price = price
            if pf.halted and now - halt_at >= timedelta(minutes=lf.RESUME_MIN):
                pf = replace(pf, halted=None, peak_equity=pf.cash + pf.btc * price)
            pf = replace(pf, equity_24h_ago=eq_by_hour.get(H[i] - 24),
                         trade_times=tuple(t for t in pf.trade_times if now - t < day))
            snap = st.Snapshot(as_of=as_of, signal=lf.SIG_NAME[E[i]], price=price,
                               rv_24=None if math.isnan(RV[i]) else RV[i], p_large=None if math.isnan(PL[i]) else PL[i],
                               pipeline_version="0.2.0", scoring_version="0.2.0")
            r = run_hour(snap, pf, settings, ex, now)
            if r.fill is not None:
                actions.append((i, 1 if r.fill.side == "BUY" else -1))
            if r.decision is not None and r.decision.halt:
                halt_at = now
            pf = r.portfolio
            eq_by_hour[H[i]] = pf.cash + pf.btc * price
        return actions, pf.cash + pf.btc * P[hi - 1]
    finally:
        st.MAX_TRADES_24H = old


def exactness_gate(inp: lf.Inputs, ranges: dict) -> dict:
    """E038's gate: A4, A2 and A1 at every cost level in both periods must give the identical (hour, side) actions and
    the final equity within 1e-9 relative. Anything else stops the run."""
    out = {}
    for period, (lo, hi) in ranges.items():
        for cap in (4, 2, 1):
            for name, c in lf.COSTS.items():
                ref_actions, ref_eq = reference_run(inp.hours, inp.close, inp.sig, inp.rv, inp.p, lo, hi, c, cap)
                lean = lf.simulate(inp.hours, inp.close, inp.sig, inp.rv, inp.p, lo, hi, c, cap, True)
                lean_actions = [(a[0], a[1]) for a in lean["actions"]]
                rel = abs(lean["eq_after"][-1] - ref_eq) / ref_eq
                key = f"{period}/A{cap}/{name}"
                out[key] = {"actions": len(ref_actions), "same_actions": lean_actions == ref_actions,
                            "final_equity_rel_diff": rel, "ok": lean_actions == ref_actions and rel <= 1e-9}
                if not out[key]["ok"]:
                    raise SystemExit(f"exactness gate FAILED at {key}: {out[key]}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E038: low-frequency execution policies")
    ap.add_argument("--live", action="store_true", help="the descriptive live run (read-only database)")
    ap.add_argument("--processes", type=int, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.live:
        return lf.main_live()
    return lf.main_development(args.processes, exactness_gate, check_constants)


if __name__ == "__main__":
    sys.exit(main())
