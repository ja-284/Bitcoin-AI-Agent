"""
E041 (research/experiments/E041_move_size_sizing.json): gir mer penger inn ved mer forventet bevegelse et bedre
resultat på eierens mål? Registrert i 0281953 før denne koden.

    python -m agent.research.move_size_sizing

Fire grunnregler fra E040 x fire størrelsesregler (full, msmore, msless, vol), kjørt med papirhandelens egen motor
(agent/papertrade/engine.py) på E040s perioder og mål. Porten først: motoren i modus «full» må gi E040s tall nøyaktig.
Bare utviklingsdata; skriver bare research/results/E041/.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.papertrade import engine
from agent.research import daily_direction as dd
from agent.research import protection_goal as pg

logger = logging.getLogger(__name__)
OUT_DIR = Path("research") / "results" / "E041"
BASES = ["G_up55_down20", "C_MA100_b5", "A_sig23", "BH"]
MODES = ["full", "msmore", "msless", "vol"]
EXPLORATION_START = pd.Timestamp("2018-11-28", tz="UTC")


def daily_pbar(days: pd.DatetimeIndex, hours: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Snittet av dagens timesvise move-size-sannsynligheter, minst 20 av 24, ellers NaN."""
    s = pd.Series(p, index=pd.to_datetime(hours * 3600, unit="s", utc=True).as_unit("ns"))
    g = s.groupby(s.index.floor("D"))
    mean, count = g.mean(), g.count()
    return mean.where(count >= 20).reindex(days).to_numpy(float)


def run(des, close, s, e, c, mode, pbar, sigma, ov) -> float:
    st = engine.State(cash=1.0)
    for i in range(s, e):
        size = engine.size_for(mode, None if math.isnan(pbar[i]) else pbar[i], None if math.isnan(sigma[i]) else sigma[i])
        st = engine.step(st, des[i], close[i], c, size=size, **ov).state
    return st.cash + st.btc * close[e]


def evaluate(des, close, wins, c, mode, pbar, sigma, ov) -> dict:
    res = np.array([run(des, close, s, e, c, mode, pbar, sigma, ov) for s, e in wins]) - 1.0
    up = np.array([close[e] > close[s] for s, e in wins])
    ge = res >= -1e-12
    return {"n": int(len(res)), "share_ge0": float(ge.mean()), "share_gt0": float((res > 1e-12).mean()),
            "share_ge0_rising": float(ge[up].mean()), "share_ge0_falling": float(ge[~up].mean()),
            "mean": float(res.mean()), "median": float(np.median(res))}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    from agent.research import low_frequency as lf
    df, meta = dd.load()
    meta.pop("start")
    _, _, rows, _ = lf._registered_replay()
    df = pg.add_inputs(df.join(pg.daily_signal_inputs(df, rows)))
    strat = pg.strategies(df)
    des_of = {b: (np.ones(len(df)) if b == "BH" else strat[b][0]).tolist() for b in BASES}
    inp = lf.load_development()
    pbar = daily_pbar(df.index, inp.hours, inp.p)
    sigma = df["SIGMA30"].to_numpy(float)
    close = df["close"].tolist()
    days = df.index
    prows = {"exploration": (int(days.searchsorted(EXPLORATION_START)),
                             int(days.searchsorted(dd.VALIDATION_START - pd.Timedelta(days=1), side="right")) - 1),
             "validation": (int(days.searchsorted(dd.VALIDATION_START)), int(days.searchsorted(dd.DEV_LAST_DAY, side="right")) - 1)}
    wins = {(p, w): pg.windows(days, *prows[p], w) for p in prows for w in pg.WINDOWS}
    # the gate: the engine in mode "full" must reproduce E040's run_window to the last bit
    worst = 0.0
    for b in BASES:
        for key, ws in wins.items():
            for s, e in ws:
                a = run(des_of[b], close, s, e, 0.0125, "full", pbar, sigma, {})
                ref = pg.run_window(des_of[b], close, s, e, 0.0125)[0]
                worst = max(worst, abs(a - ref) / ref)
    if worst > 1e-12:
        raise SystemExit(f"exactness gate FAILED: largest relative difference {worst!r}")
    logger.info("gate passed (largest relative difference %r, %.0f s)", worst, time.time() - t0)
    results = {}
    for b in BASES:
        for m in MODES:
            for scen, c in pg.COSTS.items():
                for p, (lo, hi) in prows.items():
                    entry = {f"W{w}": evaluate(des_of[b], close, wins[(p, w)], c, m, pbar, sigma, {}) for w in pg.WINDOWS}
                    st = engine.State(cash=1.0)
                    for i in range(lo, hi):
                        size = engine.size_for(m, None if math.isnan(pbar[i]) else pbar[i],
                                               None if math.isnan(sigma[i]) else sigma[i])
                        st = engine.step(st, des_of[b][i], close[i], c, size=size).state
                    entry["continuous"] = {"net": st.cash + st.btc * close[hi] - 1, "trades": st.trades}
                    results[f"{b}/{m}/{scen}/{p}"] = entry
        logger.info("%s done (%.0f s)", b, time.time() - t0)
    verdicts = {}
    S = "S3_firi_realistisk"
    for b in BASES:
        for m in MODES[1:]:
            better, worse = [], []
            for p in prows:
                v, f = results[f"{b}/{m}/{S}/{p}"]["W30"], results[f"{b}/full/{S}/{p}"]["W30"]
                better.append(v["share_ge0"] >= f["share_ge0"] and v["mean"] >= f["mean"])
                worse.append(v["share_ge0"] < f["share_ge0"] and v["mean"] < f["mean"])
            goal = all(all(results[f"{b}/{m}/{S}/{p}"][f"W{w}"]["share_ge0"] >= pg.GOAL and
                           results[f"{b}/{m}/{S}/{p}"][f"W{w}"]["mean"] > 0 for w in pg.WINDOWS) and
                       results[f"{b}/{m}/{S}/{p}"]["continuous"]["net"] > 0 for p in prows) and \
                all(results[f"{b}/{m}/S4_firi_konservativ/{p}"]["W30"]["mean"] > 0 for p in prows)
            verdicts[f"{b}/{m}"] = {"verdict": "IMPROVES" if all(better) else "WORSE" if all(worse) else "MIXED",
                                    "meets_owner_goal": bool(goal)}
    doc = {"experiment": "E041", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "gate_largest_relative_difference": worst, "window_counts": {f"{p}/W{w}": len(v) for (p, w), v in wins.items()},
           "pbar_days": int(np.isfinite(pbar[prows["exploration"][0]:]).sum()), "results": results, "verdicts": verdicts,
           "runtime_seconds": round(time.time() - t0, 1)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "move_size_sizing.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    L = ["# E041 — størrelse etter forventet bevegelse (utviklingsdata, 1,25 % per side)", "",
         f"Laget {doc['generated_at']}. Port: største relative avvik mot E040 {worst!r}.", "",
         "| grunnregel / størrelse | 30 d uten tap (utf / val) | 5 d uten tap | snitt 30 d | netto samlet | dom | når målet |",
         "|---|---|---|---|---|---|---|"]
    for b in BASES:
        for m in MODES:
            e, v = results[f"{b}/{m}/{S}/exploration"], results[f"{b}/{m}/{S}/validation"]
            vd = verdicts.get(f"{b}/{m}", {"verdict": "(grunnregel)", "meets_owner_goal": None})
            L.append(f"| {b} / {m} | {e['W30']['share_ge0']:.0%} / {v['W30']['share_ge0']:.0%} | {e['W5']['share_ge0']:.0%} / "
                     f"{v['W5']['share_ge0']:.0%} | {e['W30']['mean']:+.2%} / {v['W30']['mean']:+.2%} | "
                     f"{e['continuous']['net']:+.0%} / {v['continuous']['net']:+.0%} | {vd['verdict']} | {vd['meets_owner_goal']} |")
    (OUT_DIR / "move_size_sizing.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    if Path("research/HOLDOUT_ACCESS.log").exists():
        raise SystemExit("research/HOLDOUT_ACCESS.log exists after the run: STOP")
    print(f"E041 written to {OUT_DIR} in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
