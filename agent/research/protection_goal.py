"""
E040 (research/experiments/E040_protection_goal.json): eierens beskyttelsesmål. Registrert i b223385 før denne koden.

    python -m agent.research.protection_goal

For hver av 104 forhåndsbestemte daglige strategier, og ved tre Firi-kostnadsnivåer: andelen perioder på 5 og 30 dager
(fersk start i kontanter, én start per dag) som ender på startverdien eller høyere, delt på stigende og fallende
perioder, med gjennomsnitt, median og en sammenhengende kjøring. Porten mot E038 kjøres først. Kandidater testes mot
tilfeldig forskjøvne posisjonsbaner (timing mot eksponering). Bare utviklingsdata; skriver bare research/results/E040/.
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

from agent.research import daily_direction as dd

logger = logging.getLogger(__name__)

OUT_DIR = Path("research") / "results" / "E040"
COSTS = {"S2_firi_optimistisk": 0.008, "S3_firi_realistisk": 0.0125, "S4_firi_konservativ": 0.016}
WINDOWS = (5, 30)
GOAL = 0.75
N_BOOT, SEED, BLOCK = 2000, 31, 60
NULL_SHIFTS, NULL_SEED, NULL_MIN_SHIFT = 200, 2040, 60
TRIPWIRE_SHARE, TRIPWIRE_MEAN = 0.95, 0.03


# ------------------------------------------------------------------------------------------------- inputs
def daily_signal_inputs(df: pd.DataFrame, replay_rows: list[dict]) -> pd.DataFrame:
    """sig23 (the replay's BUY/HOLD/SELL on the day's 23:00 hour) and vote (the day's mean overall_score)."""
    idx = pd.DatetimeIndex([pd.Timestamp(r["as_of"]) for r in replay_rows]).as_unit("ns")
    rep = pd.DataFrame({"sig": [{"BUY": 1, "HOLD": 0, "SELL": -1}[r["signal"]] for r in replay_rows],
                        "score": [r["overall_score"] for r in replay_rows]}, index=idx)
    day = rep.index.floor("D")
    at23 = rep[rep.index.hour == 23]
    out = pd.DataFrame(index=df.index)
    out["sig23"] = pd.Series(at23["sig"].to_numpy(), index=at23.index.floor("D")).reindex(df.index)
    out["vote"] = rep["score"].groupby(day).mean().reindex(df.index)
    return out


def add_inputs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    closes = df["close"].tolist()
    for n in (50, 100):
        df[f"SMA{n}"] = dd.rolling_mean_available(closes, n)
    df["MA50"] = df["close"] / df["SMA50"] - 1
    df["MA100"] = df["close"] / df["SMA100"] - 1
    df["X20_100"] = df["SMA20"] / df["SMA100"] - 1
    sig = df["SIGMA30"].to_numpy()
    calm = np.full(len(df), np.nan)
    seen: list[float] = []
    import bisect
    for i, x in enumerate(sig):
        if seen and not math.isnan(x):
            m = len(seen)
            med = seen[m // 2] if m % 2 else (seen[m // 2 - 1] + seen[m // 2]) / 2
            calm[i] = 1.0 if x <= med else 0.0
        if not math.isnan(x):
            bisect.insort(seen, x)
    df["calm"] = calm
    prior = df["close"].shift(1)
    for n in (20, 55, 10):
        df[f"HI{n}"] = prior.rolling(n, min_periods=n).max()
        df[f"LO{n}"] = prior.rolling(n, min_periods=n).min()
    return df


# ------------------------------------------------------------------------------------------------- strategies
def _sign_rule(x: np.ndarray) -> np.ndarray:
    return np.where(np.isnan(x), np.nan, (x > 0).astype(float))


def _band(x: np.ndarray, b: float) -> np.ndarray:
    out = np.full(len(x), np.nan)
    out[x > b] = 1.0
    out[x < -b] = 0.0
    return out


def strategies(df: pd.DataFrame) -> dict[str, tuple[np.ndarray, dict]]:
    """name -> (desired position per day: 1 own, 0 cash, NaN keep; overlay settings)."""
    s = {}
    col = lambda c: df[c].to_numpy(float)
    sig23, vote = col("sig23"), col("vote")
    a_sig = np.where(sig23 == 1, 1.0, np.where(sig23 == -1, 0.0, np.nan))
    a_vote = np.where(vote >= 0.15, 1.0, np.where(vote <= -0.15, 0.0, np.nan))
    prev = np.r_[np.nan, sig23[:-1]]
    a_conf = np.where((sig23 == 1) & (prev == 1), 1.0, np.where((sig23 == -1) & (prev == -1), 0.0, np.nan))
    s["A_sig23"], s["A_vote"], s["A_confirm2"] = (a_sig, {}), (a_vote, {}), (a_conf, {})
    base = {}
    for c in ("R7", "R14", "R28", "R56", "R84", "R182", "MA20", "MA50", "MA100", "MA200", "X20_100", "X50_200"):
        base[f"B_{c}"] = _sign_rule(col(c))
    tr = col("TREND")
    base["B_TREND02"] = np.where(np.isnan(tr), np.nan, (tr >= 0.2).astype(float))
    base["B_TREND06"] = np.where(np.isnan(tr), np.nan, (tr >= 0.6).astype(float))
    base["B_TREND10"] = np.where(np.isnan(tr), np.nan, (tr >= 0.999).astype(float))
    for c in ("MA50", "MA100", "MA200"):
        for b in (0.01, 0.03, 0.05):
            base[f"C_{c}_b{int(b * 100)}"] = _band(col(c), b)
    close = col("close")
    for n in (20, 55):
        for m in (10, 20):
            g = np.full(len(df), np.nan)
            g[close > col(f"HI{n}")] = 1.0
            g[close < col(f"LO{m}")] = 0.0
            base[f"G_up{n}_down{m}"] = g
    for k, v in base.items():
        s[k] = (v, {})
    ma200_ok, trend_ok = col("MA200") > 0, tr >= 0.6
    for name, a in (("sig23", a_sig), ("vote", a_vote)):
        s[f"D_{name}_ma200"] = (np.where(~ma200_ok, 0.0, a), {})
        s[f"D_{name}_trend"] = (np.where(~trend_ok, 0.0, a), {})
    calm = col("calm")
    s["E_calm_ma200"] = (np.where(np.isnan(calm), np.nan, ((calm == 1) & ma200_ok).astype(float)), {})
    s["E_calm"] = (np.where(np.isnan(calm), np.nan, (calm == 1).astype(float)), {})
    r1 = col("R1")
    for x in (0.03, 0.05, 0.08):
        for h in (3, 7, 14):
            s[f"F_dip{int(x * 100)}_hold{h}"] = (np.where(r1 <= -x, 1.0, np.nan), {"tstop": h})
    overlay_bases = {**base, "BH": np.ones(len(df))}
    for k, v in overlay_bases.items():
        s[f"H_{k}_sl10"] = (v, {"sl": 0.10})
        s[f"H_{k}_tr15"] = (v, {"tr": 0.15})
    return s


# ------------------------------------------------------------------------------------------------- the engine
def run_window(des: list, close: list, s: int, e: int, c: float, sl=None, tr=None, tstop=None, path=False):
    """Fresh start in cash (value 1). Decisions at the close of rows s..e-1, value marked at the close of row e.
    E038's cost arithmetic. Stop-loss / trailing stop block re-entry until the base rule has been 0 for a day; the time
    stop (family F) does not block."""
    cash, btc = 1.0, 0.0
    entry = peak = 0.0
    held, blocked, trades, invested = 0, False, 0, 0
    values = [] if path else None
    for i in range(s, e):
        price, w = close[i], des[i]
        if btc > 0.0:
            held += 1
            peak = max(peak, price)
            stopped = (sl is not None and price <= entry * (1 - sl)) or (tr is not None and price <= peak * (1 - tr))
            timed = tstop is not None and held >= tstop
            if stopped or timed or w == 0.0:
                gross = btc * price
                fee = gross * c
                cash, btc, trades = gross - fee, 0.0, trades + 1
                if stopped and w != 0.0:
                    blocked = True
        elif w == 1.0 and not blocked:
            fee = cash * c
            btc, cash, trades = (cash - fee) / price, 0.0, trades + 1
            entry = peak = price
            held = 0
        if blocked and w == 0.0:
            blocked = False
        if btc > 0.0:
            invested += 1
        if path:
            values.append(cash + btc * price)
    final = cash + btc * close[e]
    return (final, trades, invested, values) if path else (final, trades, invested)


def period_rows(days: pd.DatetimeIndex, start: pd.Timestamp, period: str) -> tuple[int, int]:
    if period == "exploration":
        a, b = start, dd.VALIDATION_START - pd.Timedelta(days=1)
    else:
        a, b = dd.VALIDATION_START, dd.DEV_LAST_DAY
    return int(days.searchsorted(a)), int(days.searchsorted(b, side="right")) - 1


def windows(days: pd.DatetimeIndex, lo: int, hi: int, w: int) -> list[tuple[int, int]]:
    """(s, e) row pairs with e = the row exactly w calendar days after s, both inside [lo, hi]."""
    pos = {d.value: i for i, d in enumerate(days)}
    out = []
    for s in range(lo, hi + 1):
        e = pos.get((days[s] + pd.Timedelta(days=w)).value)
        if e is not None and e <= hi:
            out.append((s, e))
    return out


def evaluate(des, ov, close, wins, c) -> dict:
    res = np.array([run_window(des, close, s, e, c, **ov)[0] for s, e in wins]) - 1.0
    up = np.array([close[e] > close[s] for s, e in wins])
    ge = res >= -1e-12
    from agent.research.metrics import block_bootstrap_estimates
    point, est = block_bootstrap_estimates(ge.astype(float), np.mean, BLOCK, N_BOOT, SEED)
    return {"n": int(len(res)), "share_ge0": float(ge.mean()),
            "share_ge0_ci95": [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))] if len(est) else None,
            "share_gt0": float((res > 1e-12).mean()), "share_ge0_rising": float(ge[up].mean()) if up.any() else None,
            "share_ge0_falling": float(ge[~up].mean()) if (~up).any() else None,
            "share_gt0_rising": float((res[up] > 1e-12).mean()) if up.any() else None,
            "mean": float(res.mean()), "median": float(np.median(res)), "rising_share": float(up.mean()), "_res": res}


def continuous(des, ov, close, days, lo, hi, c) -> dict:
    final, trades, invested, values = run_window(des, close, lo, hi, c, path=True, **ov)
    v = np.array(values + [final])
    peak = np.maximum.accumulate(np.r_[1.0, v])[1:]
    years = (days[hi] - days[lo]).days / 365.25
    return {"net": float(final - 1), "max_drawdown": float(np.max(1 - v / peak)), "trades_per_year": trades / years,
            "share_invested": invested / (hi - lo)}


# ------------------------------------------------------------------------------------------------- gate, null, references
def exactness_gate(df) -> dict:
    ref = json.loads(dd.E038_RESULT.read_text(encoding="utf-8"))["results"]
    des = dd.rule_targets(df, None)["T_MA200"].tolist()
    close = df["close"].tolist()
    out = {}
    e038_costs = {"S0_gross": 0.0, "S1_low_cost_reference": 0.0011, "S2_firi_optimistic": 0.008,
                  "S3_firi_realistic": 0.0125, "S4_firi_conservative": 0.016}
    ranges = {"exploration": (dd.E038_EXPLORATION_START_HOUR.floor("D"), dd.VALIDATION_START - pd.Timedelta(days=1)),
              "validation": (dd.VALIDATION_START, dd.DEV_LAST_DAY)}
    for period, (a, b) in ranges.items():
        lo, hi = int(df.index.searchsorted(a)), int(df.index.searchsorted(b, side="right")) - 1
        for scen, c in e038_costs.items():
            got = run_window_inclusive(des, close, lo, hi, c) * 150.0
            want = ref[f"{period}/{scen}/C3_ma200d"]["final_equity"]
            rel = abs(got - want) / want
            out[f"{period}/{scen}"] = {"got": got, "e038": want, "rel_diff": rel, "ok": rel <= 1e-9}
            if rel > 1e-9:
                raise SystemExit(f"exactness gate FAILED at {period}/{scen}: {got!r} vs {want!r}")
    return out


def run_window_inclusive(des, close, lo, hi, c) -> float:
    """Decisions at rows lo..hi INCLUDING hi, value at the close of hi (E038's continuous convention): the same engine
    on a copy whose extra last row repeats hi's close and makes no decision."""
    return run_window(list(des[:hi + 1]) + [math.nan], list(close[:hi + 1]) + [close[hi]], lo, hi + 1, c)[0]


def null_test(des, ov, close, wins, lo, hi, c, actual_share, actual_mean) -> dict:
    n = hi - lo + 1
    shifts = np.random.default_rng(NULL_SEED).integers(NULL_MIN_SHIFT, n - NULL_MIN_SHIFT + 1, size=NULL_SHIFTS)
    arr = np.array(des, dtype=float)
    shares, means = [], []
    for k in shifts:
        d2 = arr.copy()
        d2[lo:hi + 1] = np.roll(arr[lo:hi + 1], int(k))
        r = evaluate(d2.tolist(), ov, close, wins, c)
        shares.append(r["share_ge0"])
        means.append(r["mean"])
    pct = lambda vals, x: float((np.array(vals) < x).mean() * 100 + (np.array(vals) == x).mean() * 50)
    return {"share_percentile": pct(shares, actual_share), "mean_percentile": pct(means, actual_mean),
            "null_share_median": float(np.median(shares)), "null_mean_median": float(np.median(means))}


def hourly_references(days, starts_by_key: dict) -> dict:
    """rule-1.0 on the hourly grid (E038's verified lean copy), windows starting at 00:00 UTC the day after day s."""
    from agent.research import low_frequency as lf
    lf.CAP, lf.MIN_ORDER = 300.0, 50.0
    inp = lf.load_development()
    out = {}
    for name, cap in (("REF_rule1_as_built", 4), ("REF_rule1_cap1", 1)):
        for (period, w), wins in starts_by_key.items():
            for scen, c in COSTS.items():
                res = []
                for s, _ in wins:
                    h0 = int((days[s] + pd.Timedelta(days=1)).value // 3_600_000_000_000)
                    lo = int(np.searchsorted(inp.hours, h0))
                    hi = int(np.searchsorted(inp.hours, h0 + w * 24))
                    if hi - lo < w * 24 * 0.95 or hi > len(inp.hours):
                        continue
                    sl = slice(lo, hi)
                    r = lf.simulate(inp.hours[sl], inp.close[sl], inp.sig[sl], inp.rv[sl], inp.p[sl], 0, hi - lo, c, cap, True)
                    res.append(r["eq_after"][-1] / 300.0 - 1)
                res = np.array(res)
                out[f"{name}/{scen}/{period}/W{w}"] = {"n": int(len(res)), "share_ge0": float((res >= -1e-12).mean()),
                                                       "share_gt0": float((res > 1e-12).mean()), "mean": float(res.mean())}
    return out


# ------------------------------------------------------------------------------------------------- the run
def _jsonable(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    from agent.research import low_frequency as lf
    df, meta = dd.load()
    start = meta.pop("start")
    _, _, rows, _ = lf._registered_replay()
    df = add_inputs(df.join(daily_signal_inputs(df, rows)))
    gate = exactness_gate(df)
    logger.info("exactness gate passed (%d)", len(gate))
    strat = strategies(df)
    if len(strat) != 104:
        raise SystemExit(f"{len(strat)} strategies, not the registered 104: STOP")
    close = df["close"].tolist()
    days = df.index
    prows = {p: period_rows(days, start, p) for p in ("exploration", "validation")}
    wins = {(p, w): windows(days, *prows[p], w) for p in prows for w in WINDOWS}
    results = {}
    for name, (des, ov) in {**strat, "BASE_buy_and_hold": (np.ones(len(df)), {}),
                            "BASE_cash": (np.zeros(len(df)), {})}.items():
        dl = des.tolist()
        for scen, c in COSTS.items():
            for p, (lo, hi) in prows.items():
                entry = {"continuous": continuous(dl, ov, close, days, lo, hi, c)}
                for w in WINDOWS:
                    r = evaluate(dl, ov, close, wins[(p, w)], c)
                    r.pop("_res")
                    entry[f"W{w}"] = r
                results[f"{name}/{scen}/{p}"] = entry
    logger.info("strategies evaluated (%.0f s)", time.time() - t0)

    def passes(name, scen, p):
        e = results[f"{name}/{scen}/{p}"]
        return all(e[f"W{w}"]["share_ge0"] >= GOAL and e[f"W{w}"]["mean"] > 0 for w in WINDOWS) and e["continuous"]["net"] > 0

    shortlist = [n for n in strat if passes(n, "S3_firi_realistisk", "exploration")]
    candidates = [n for n in shortlist if passes(n, "S3_firi_realistisk", "validation")
                  and all(results[f"{n}/S4_firi_konservativ/{p}"]["W30"]["mean"] > 0 for p in prows)]
    timing = {}
    for n in candidates:
        des, ov = strat[n]
        timing[n] = {}
        for p, (lo, hi) in prows.items():
            r = results[f"{n}/S3_firi_realistisk/{p}"]["W30"]
            timing[n][p] = null_test(des.tolist(), ov, close, wins[(p, 30)], lo, hi, 0.0125, r["share_ge0"], r["mean"])
        timing[n]["label"] = "timing" if all(timing[n][p]["share_percentile"] >= 95 and timing[n][p]["mean_percentile"] >= 95
                                              for p in prows) else "eksponering"
    trip = [n for n in strat if all(results[f"{n}/S3_firi_realistisk/{p}"]["W30"]["share_ge0"] > TRIPWIRE_SHARE and
                                    results[f"{n}/S3_firi_realistisk/{p}"]["W30"]["mean"] > TRIPWIRE_MEAN for p in prows)]
    logger.info("shortlist %d, candidates %d (%.0f s)", len(shortlist), len(candidates), time.time() - t0)
    refs = hourly_references(days, wins)
    logger.info("hourly references done (%.0f s)", time.time() - t0)
    doc = {"experiment": "E040", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "inputs": meta | {"study_start": str(start.date())}, "exactness_gate": gate,
           "window_counts": {f"{p}/W{w}": len(v) for (p, w), v in wins.items()},
           "results": results, "shortlist": shortlist, "candidates": candidates, "timing": timing,
           "hourly_references": refs, "tripwire": trip, "runtime_seconds": round(time.time() - t0, 1)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "protection_goal.json").write_text(json.dumps(doc, indent=1, default=_jsonable), encoding="utf-8")
    (OUT_DIR / "protection_goal.md").write_text(render(doc), encoding="utf-8")
    if Path("research/HOLDOUT_ACCESS.log").exists():
        raise SystemExit("research/HOLDOUT_ACCESS.log exists after the run: STOP")
    if trip:
        print(f"TRIPWIRE: {trip} -- check the point-in-time path before reading")
    print(f"E040 written to {OUT_DIR} in {time.time() - t0:.0f} s")
    return 0


def render(doc: dict) -> str:
    R = doc["results"]
    names = sorted({k.split("/")[0] for k in R})
    L = ["# E040 — eierens beskyttelsesmål (utviklingsdata)", "",
         f"Laget {doc['generated_at']}. Porten mot E038: {len(doc['exactness_gate'])} kontroller innen 1e-9. Perioder: {doc['window_counts']}.", "",
         f"SHORTLIST (S3, utforsking): {', '.join(doc['shortlist']) or 'ingen'}", f"CANDIDATE: {', '.join(doc['candidates']) or 'ingen'}",
         f"Timing mot eksponering: {json.dumps(doc['timing'], ensure_ascii=False)}", ""]
    for p in ("exploration", "validation"):
        L += [f"## {p}, S3 (1,25 % per side)", "",
              "| strategi | >=0 5 d | >=0 30 d [KI] | >=0 30 d stigende / fallende | >0 30 d | snitt 5 d | snitt 30 d | netto samlet | maks fall | handler/år | investert |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in sorted(names, key=lambda n: -R[f"{n}/S3_firi_realistisk/{p}"]["W30"]["share_ge0"]):
            e = R[f"{n}/S3_firi_realistisk/{p}"]
            w5, w30, cc = e["W5"], e["W30"], e["continuous"]
            ci = w30["share_ge0_ci95"] or [math.nan, math.nan]
            fmt = lambda x: "n/a" if x is None else f"{x:.0%}"
            L.append(f"| {n} | {w5['share_ge0']:.0%} | {w30['share_ge0']:.0%} [{ci[0]:.0%}, {ci[1]:.0%}] | "
                     f"{fmt(w30['share_ge0_rising'])} / {fmt(w30['share_ge0_falling'])} | {w30['share_gt0']:.0%} | {w5['mean']:+.2%} | "
                     f"{w30['mean']:+.2%} | {cc['net']:+.0%} | {cc['max_drawdown']:.0%} | {cc['trades_per_year']:.1f} | {cc['share_invested']:.0%} |")
        L.append("")
    L += ["## Referanser på timesnivå (dagens modell)", "", "| nøkkel | n | >=0 | >0 | snitt |", "|---|---|---|---|---|"]
    for k, v in doc["hourly_references"].items():
        L.append(f"| {k} | {v['n']} | {v['share_ge0']:.0%} | {v['share_gt0']:.0%} | {v['mean']:+.2%} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
