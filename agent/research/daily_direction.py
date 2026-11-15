"""
E039 (research/experiments/E039_direction_trading_horizons.json): direction at trading horizons, on DAILY samples of
the development data. Registered in 6600440 before this code existed.

    python -m agent.research.daily_direction

What it does, in the record's order:
  1. Builds daily closes (the 23:00 UTC candle), daily taker share and 7-day funding through the governed readers only.
  2. Computes 14 fixed signals point in time, and forward returns that never use a close after 2025-06-30 23:00 UTC.
  3. The exactness gate: the 200-day rule must reproduce E038's C3 final equity at all five cost levels.
  4. The lookback x horizon map, the 42 signal tests (Holm), the walk-forward logistic at 7 days, 11 long/cash rules
     with random-timing nulls, and the tail table.
Writes only research/results/E039/. Research only: nothing in production imports it, and it imports nothing from
agent.execution.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

logger = logging.getLogger(__name__)

OUT_DIR = Path("research") / "results" / "E039"
E038_RESULT = Path("research") / "results" / "E038" / "low_frequency.json"
COSTS = {"S0_gross": 0.0, "S1_low_cost_reference": 0.0011, "S2_firi_optimistic": 0.008,
         "S3_firi_realistic": 0.0125, "S4_firi_conservative": 0.016}
CAP = 150.0
VALIDATION_START = pd.Timestamp("2024-01-01", tz="UTC")
DEV_LAST_DAY = pd.Timestamp("2025-06-30", tz="UTC")  # the last UTC day whose 23:00 candle is development data
E038_EXPLORATION_START_HOUR = pd.Timestamp("2018-11-27 15:00", tz="UTC")  # E038's simulation start (its first 23:00 row is that day)

RETURN_LOOKBACKS = (1, 7, 14, 28, 84, 182)
MAP_LOOKBACKS = (1, 3, 7, 14, 28, 56, 84, 182)
MAP_HORIZONS = (1, 3, 7, 14, 30)
HORIZONS = (1, 7, 30)
SIGNALS = ["R1", "R7", "R14", "R28", "R84", "R182", "MA20", "MA200", "X50_200", "H52", "TREND", "TREND_VS",
           "FUND7", "TAKER7"]
SIGN_SIGNALS = ["R1", "R7", "R14", "R28", "R84", "R182", "MA20", "MA200", "X50_200", "TREND"]
MODEL_INPUTS = [s for s in SIGNALS if s != "FUND7"]
RULES = ["T_R7", "T_R14", "T_R28", "T_R84", "T_R182", "T_MA20", "T_MA200", "T_X50_200", "T_TREND", "T_TREND_VS", "T_M7"]
DAILY_VOL_TARGET = 0.0294  # rule-1.0's 0.6% an hour, as a daily figure (0.006 * sqrt(24))
REBALANCE_BAND = 0.20
SIGMA_DAYS, SIGMA_MIN = 30, 20
FUNDING_SETTLEMENTS = 21
N_BOOT, SEED = 2000, 31
BOOT_BLOCK_TRADING = 20
NULL_SHIFTS, NULL_SEED, NULL_MIN_SHIFT = 200, 2039, 60
MODEL_BLOCKS = [("2020", "2020-01-01", "2021-01-01"), ("2021", "2021-01-01", "2022-01-01"),
                ("2022", "2022-01-01", "2023-01-01"), ("2023", "2023-01-01", "2024-01-01"),
                ("2024", "2024-01-01", "2025-01-01"), ("2025", "2025-01-01", "2025-07-01")]
LARGE_FALL = -0.20


# ------------------------------------------------------------------------------------------------- data
def daily_closes(bars) -> pd.Series:
    """Close of each UTC day's 23:00 candle, indexed by the day (UTC midnight). A day without it has no row."""
    rows = [(b.as_of, b.close) for b in bars if b.as_of.hour == 23]
    idx = pd.DatetimeIndex([pd.Timestamp(t).floor("D") for t, _ in rows]).as_unit("ns")
    s = pd.Series([c for _, c in rows], index=idx, name="close", dtype=float)
    if not s.index.is_monotonic_increasing or s.index.has_duplicates:
        raise SystemExit("daily closes are not strictly increasing: STOP")
    return s


def calendar(s: pd.Series) -> pd.Series:
    full = pd.date_range(s.index[0], s.index[-1], freq="D", tz="UTC")
    return s.reindex(full)


def rolling_mean_available(closes: list[float], n: int) -> list[float]:
    """mean of the last n available closes, today included, as sum(window) / n (E038's C3 arithmetic, exactly)."""
    out, window = [], deque(maxlen=n)
    for c in closes:
        window.append(c)
        out.append(sum(window) / n if len(window) == n else math.nan)
    return out


def build_signals(daily: pd.Series, taker24: pd.Series, funding21: pd.Series) -> pd.DataFrame:
    """
    Every signal for each available day, from information known at that day's close only. `taker24` and `funding21`
    are the reviewed route's own features at each day's 23:00 row (agent.research.feature_test.compute_group_features:
    taker_buy_share_24h, and funding_sum_21 = the sum of the last 21 settlements at or before the day's close).
    """
    cal = calendar(daily)
    df = pd.DataFrame(index=daily.index)
    df["close"] = daily
    for k in MAP_LOOKBACKS:
        df[f"R{k}"] = (cal / cal.shift(k) - 1).reindex(daily.index)
    closes = daily.tolist()
    sma = {n: pd.Series(rolling_mean_available(closes, n), index=daily.index) for n in (20, 50, 200)}
    df["SMA20"], df["SMA200"] = sma[20], sma[200]
    df["MA20"] = daily / sma[20] - 1
    df["MA200"] = daily / sma[200] - 1
    df["X50_200"] = sma[50] / sma[200] - 1
    rmax = cal.rolling(365, min_periods=1).max().reindex(daily.index)
    first_full = daily.index[0] + pd.Timedelta(days=364)
    df["H52"] = (daily / rmax).where(daily.index >= first_full)
    signs = np.sign(df[["R7", "R14", "R28", "R84", "R182"]])
    df["TREND"] = signs.mean(axis=1, skipna=False)
    logret = np.log(cal / cal.shift(1))
    sigma = logret.rolling(SIGMA_DAYS, min_periods=SIGMA_MIN).std().reindex(daily.index)
    df["SIGMA30"] = sigma
    df["TREND_VS"] = df["TREND"] / sigma
    df["FUND7"] = funding21.reindex(daily.index) / FUNDING_SETTLEMENTS
    tk = taker24.reindex(pd.date_range(daily.index[0], daily.index[-1], freq="D", tz="UTC"))
    df["TAKER7"] = tk.rolling(7, min_periods=7).mean().reindex(daily.index)  # mean of the last 7 daily shares
    return df


def forward_returns(daily: pd.Series, horizon: int) -> pd.Series:
    cal = calendar(daily)
    fwd = (cal.shift(-horizon) / cal - 1).reindex(daily.index)
    return fwd


def day_rows(features: pd.DataFrame, column: str) -> pd.Series:
    """A reviewed-route feature at each day's 23:00 UTC row, indexed by the day."""
    s = features[column]
    s = s[s.index.hour == 23]
    s.index = pd.DatetimeIndex(s.index.floor("D")).as_unit("ns")
    return s


def load() -> tuple[pd.DataFrame, dict]:
    from agent.research.feature_test import compute_group_features
    from agent.research.history import load_bars
    from agent.research.periods import HOLDOUT

    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    daily = daily_closes(bars)
    if daily.index[-1] > DEV_LAST_DAY:
        raise SystemExit("daily closes reach the holdout: STOP")
    # side data only through the one reviewed route (research/HOLDOUT_ROUTES.md), cut at the candles' own cutoff
    taker = day_rows(compute_group_features("microstructure", bars), "taker_buy_share_24h")
    funding = day_rows(compute_group_features("derivatives", bars), "funding_sum_21")
    df = build_signals(daily, taker, funding)
    for h in sorted(set(MAP_HORIZONS) | set(HORIZONS)):
        df[f"F{h}"] = forward_returns(daily, h)
    # a forward return exists only when its close is a development close; assert it explicitly
    for h in sorted(set(MAP_HORIZONS) | set(HORIZONS)):
        last = df.index[df[f"F{h}"].notna()].max()
        if last + pd.Timedelta(days=h) > DEV_LAST_DAY:
            raise SystemExit(f"a {h}-day forward return uses a close after 2025-06-30: STOP")
    core = [s for s in SIGNALS if s != "FUND7"]
    start = df.index[df[core].notna().all(axis=1)][0]
    meta = {"spot_snapshot": snapshot.name, "daily_rows": int(len(daily)), "first_day": str(daily.index[0].date()),
            "last_day": str(daily.index[-1].date()), "study_start": str(start.date()),
            "missing_calendar_days": int(len(calendar(daily)) - len(daily)),
            "fund7_first_day": str(df.index[df["FUND7"].notna()][0].date())}
    return df, meta | {"start": start}


# ------------------------------------------------------------------------------------------------- statistics
def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = rankdata(x), rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return math.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def boot(arr: np.ndarray, stat, block: int) -> tuple[float, float, float, float]:
    """(point, low 95, high 95, two-sided bootstrap p) by E036's formula."""
    from agent.research.metrics import block_bootstrap_estimates
    point, est = block_bootstrap_estimates(arr, stat, block, N_BOOT, SEED)
    est = est[~np.isnan(est)]
    if len(est) == 0:
        return point, math.nan, math.nan, math.nan
    p = min(1.0, 2 * min(1 + (est <= 0).sum(), 1 + (est >= 0).sum()) / (1 + N_BOOT))
    return point, float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5)), float(p)


def period_mask(index: pd.DatetimeIndex, horizon: int, period: str) -> np.ndarray:
    """Rows of the period whose H-day outcome lies inside the same period."""
    end_ok = index + pd.Timedelta(days=horizon)
    if period == "exploration":
        return np.asarray((index < VALIDATION_START) & (end_ok < VALIDATION_START))
    return np.asarray((index >= VALIDATION_START) & (end_ok <= DEV_LAST_DAY))


def correlation_cell(df, start, x: str, h: int, period: str) -> dict:
    m = period_mask(df.index, h, period) & np.asarray(df.index >= start)
    sub = df.loc[m, [x, f"F{h}"]].dropna()
    n = len(sub)
    if n < 60:
        return {"n": n}
    arr = sub.to_numpy(float)
    point, lo, hi, p = boot(arr, lambda a: spearman(a[:, 0], a[:, 1]), max(2 * h, 14))
    out = {"n": n, "n_eff": n / h, "rho": point, "ci95": [lo, hi], "p": p, "mde_rho": 2.80 / math.sqrt(n / h)}
    if x in SIGN_SIGNALS:
        s, f = np.sign(arr[:, 0]), np.sign(arr[:, 1])
        keep = (s != 0) & (f != 0)
        out["hit_rate"] = float((s[keep] == f[keep]).mean()) if keep.any() else None
        out["up_share"] = float((f[keep] > 0).mean()) if keep.any() else None
    return out


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    items = sorted((p, k) for k, p in pvalues.items() if not math.isnan(p))
    m, adj, running = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return adj


# ------------------------------------------------------------------------------------------------- the fitted model
def walk_forward_m7(df, start) -> pd.DataFrame:
    from agent.research.model_test import LogisticModel
    data = df.loc[df.index >= start, MODEL_INPUTS + ["F7"]].copy()
    data["y"] = (data["F7"] > 0).astype(float).where(data["F7"].notna())
    rows = []
    for name, a, b in MODEL_BLOCKS:
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        train = data[(data.index <= a - pd.Timedelta(days=8))].dropna()
        test = data[(data.index >= a) & (data.index < b)].dropna(subset=MODEL_INPUTS)
        if len(train) < 365 or len(test) == 0:
            raise SystemExit(f"model block {name}: {len(train)} training rows, {len(test)} test rows: STOP")
        m = LogisticModel(C=0.1)
        m.fit(train[MODEL_INPUTS], train["y"].to_numpy())
        p = m.predict_proba(test[MODEL_INPUTS])
        rows.append(pd.DataFrame({"block": name, "p": p, "base": float(train["y"].mean()), "y": test["y"],
                                  "train_rows": len(train), "coef": [m.coefficients(MODEL_INPUTS)] * len(test)},
                                 index=test.index))
    return pd.concat(rows)


def model_scores(pred: pd.DataFrame) -> dict:
    from agent.research.block_calibration import calibration_line
    from agent.research.metrics import brier_score
    out = {}
    for period in ("exploration", "validation"):
        m = period_mask(pred.index, 7, period)
        sub = pred[m].dropna(subset=["y"])
        p, base, y = sub["p"].to_numpy(), sub["base"].to_numpy(), sub["y"].to_numpy()
        arr = np.column_stack([p, base, y])
        d, lo, hi, pv = boot(arr, lambda a: brier_score(a[:, 1], a[:, 2]) - brier_score(a[:, 0], a[:, 2]), 14)
        bb = brier_score(base, y)
        out[period] = {"n": int(len(sub)), "brier_model": brier_score(p, y), "brier_base": bb,
                       "skill": 1 - brier_score(p, y) / bb, "d_base_minus_model": d, "d_ci95": [lo, hi], "p": pv,
                       "calibration": calibration_line(p, y), "mean_p": float(p.mean()), "up_share": float(y.mean())}
    out["coefficients_by_block"] = {b: pred.loc[pred["block"] == b, "coef"].iloc[0] for b in pred["block"].unique()}
    return out


# ------------------------------------------------------------------------------------------------- trading
def rule_targets(df: pd.DataFrame, m7: pd.DataFrame | None) -> dict[str, np.ndarray]:
    """Target exposure per day (1 invested, 0 cash, a fraction for TREND_VS; NaN = no decision, keep)."""
    t = {}
    for k in (7, 14, 28, 84, 182):
        r = df[f"R{k}"].to_numpy()
        t[f"T_R{k}"] = np.where(np.isnan(r), np.nan, (r > 0).astype(float))
    close = df["close"].to_numpy()
    for n, name in ((20, "T_MA20"), (200, "T_MA200")):
        s = df[f"SMA{n}"].to_numpy()
        t[name] = np.where(np.isnan(s), np.nan, (close > s).astype(float))  # E038's comparison, exactly
    x = df["X50_200"].to_numpy()
    t["T_X50_200"] = np.where(np.isnan(x), np.nan, (x > 0).astype(float))
    tr = df["TREND"].to_numpy()
    t["T_TREND"] = np.where(np.isnan(tr), np.nan, (tr > 0).astype(float))
    sig = df["SIGMA30"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        vs = np.minimum(1.0, np.maximum(0.0, tr) * DAILY_VOL_TARGET / sig)
    t["T_TREND_VS"] = np.where(np.isnan(tr) | np.isnan(sig) | (sig <= 0), np.nan, vs)
    m = np.full(len(df), np.nan)
    if m7 is not None:
        pos = df.index.get_indexer(m7.index)
        m[pos] = (m7["p"].to_numpy() > 0.5).astype(float)
    t["T_M7"] = m
    return t


def simulate(close: np.ndarray, target: np.ndarray, c: float, fractional: bool = False) -> dict:
    """Daily long/cash simulation with E038's cost arithmetic. NaN target = keep the current position."""
    cash, btc = CAP, 0.0
    n = len(close)
    eq, expo = np.empty(n), np.empty(n)
    actions = []  # (row, side, notional, fee)
    for i in range(n):
        price = close[i]
        tg = target[i]
        if not math.isnan(tg):
            if not fractional:
                if tg == 1.0 and btc == 0.0:
                    fee = cash * c
                    actions.append((i, 1, cash, fee))
                    btc, cash = (cash - fee) / price, 0.0
                elif tg == 0.0 and btc > 0.0:
                    gross = btc * price
                    fee = gross * c
                    actions.append((i, -1, gross, fee))
                    cash, btc = gross - fee, 0.0
            else:
                equity = cash + btc * price
                cur = btc * price / equity if equity > 0 else 0.0
                enter, leave = tg > 0 and btc == 0.0, tg == 0.0 and btc > 0.0
                if enter or leave or abs(tg - cur) >= REBALANCE_BAND:
                    delta = tg * equity - btc * price
                    if delta > 0:
                        q = min(delta, cash)
                        fee = q * c
                        actions.append((i, 1, q, fee))
                        btc, cash = btc + (q - fee) / price, cash - q
                    elif delta < 0:
                        x = btc if leave else min(btc, -delta / price)
                        gross = x * price
                        fee = gross * c
                        actions.append((i, -1, gross, fee))
                        cash, btc = cash + gross - fee, max(btc - x, 0.0)
        eq[i] = cash + btc * price
        expo[i] = btc * price
    return {"eq": eq, "expo": expo, "actions": actions}


def summarise(res: dict, days: pd.DatetimeIndex, close: np.ndarray) -> dict:
    from agent.research.metrics import block_bootstrap_estimates
    eq = res["eq"]
    dr = eq / np.r_[CAP, eq[:-1]] - 1
    point, est = block_bootstrap_estimates(dr, np.mean, BOOT_BLOCK_TRADING, N_BOOT, SEED)
    years = (days[-1] - days[0]).days / 365.25
    sd = dr.std(ddof=1)
    peak = np.maximum.accumulate(np.r_[CAP, eq])[1:]
    share = np.where(eq > 0, res["expo"] / eq, 0.0)
    flat_before = np.r_[True, res["expo"][:-1] < 1e-9]
    flat_after = res["expo"] < 1e-9
    cycles, open_at = [], None
    for i in range(len(eq)):
        if flat_before[i] and not flat_after[i]:
            open_at = i
        elif not flat_before[i] and flat_after[i] and open_at is not None:
            start_eq = eq[open_at - 1] if open_at > 0 else CAP
            cycles.append({"ret": eq[i] / start_eq - 1, "days": int((days[i] - days[open_at]).days)})
            open_at = None
    rets = np.array([x["ret"] for x in cycles])
    per_year, prev = {}, CAP
    for y in sorted(set(days.year)):
        last = eq[np.asarray(days.year == y)][-1]
        per_year[str(y)] = float(last / prev - 1)
        prev = last
    bh = close / close[0]
    e = float(share.mean())
    matched = CAP * np.cumprod(1 + e * (np.r_[1.0, close[1:] / close[:-1]] - 1))
    return {"final_equity": float(eq[-1]), "net_return": float(eq[-1] / CAP - 1),
            "annualised_return": float((eq[-1] / CAP) ** (1 / years) - 1) if eq[-1] > 0 else -1.0,
            "mean_daily_return": float(point),
            "mean_daily_ci95": [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))],
            "sharpe": float(dr.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0,
            "max_drawdown": float(np.max(1 - eq / peak)), "actions": len(res["actions"]),
            "actions_per_year": len(res["actions"]) / years, "cycles": len(cycles),
            "cycle_mean": float(rets.mean()) if len(rets) else None,
            "cycle_win_rate": float((rets > 0).mean()) if len(rets) else None,
            "mean_hold_days": float(np.mean([x["days"] for x in cycles])) if cycles else None,
            "mean_exposure": e, "costs_paid": float(sum(a[3] for a in res["actions"])),
            "per_year": per_year, "buy_and_hold_net": float(bh[-1] - 1),
            "exposure_matched_bh_net": float(matched[-1] / CAP - 1), "_daily": dr}


def null_percentiles(close, target, c, fractional, actual) -> dict:
    n = len(target)
    shifts = np.random.default_rng(NULL_SEED).integers(NULL_MIN_SHIFT, n - NULL_MIN_SHIFT + 1, size=NULL_SHIFTS)
    vals = np.array([simulate(close, np.roll(target, int(k)), c, fractional)["eq"][-1] for k in shifts])
    return {"percentile": float((vals < actual).mean() * 100 + (vals == actual).mean() * 50),
            "null_median": float(np.median(vals)), "null_p95": float(np.percentile(vals, 95))}


def trading(df, start, m7) -> dict:
    targets = rule_targets(df, m7)
    out = {}
    for period in ("exploration", "validation"):
        if period == "exploration":
            pm = np.asarray((df.index >= start) & (df.index < VALIDATION_START))
        else:
            pm = np.asarray((df.index >= VALIDATION_START) & (df.index <= DEV_LAST_DAY))
        for rule in RULES:
            m = pm.copy()
            if rule == "T_M7":
                m &= ~np.isnan(targets[rule])
                first = np.argmax(m)
                m[first:] = pm[first:]  # from M7's first out-of-sample day to the period's end
            days = df.index[m]
            close = df["close"].to_numpy()[m]
            tg = targets[rule][m]
            frac = rule == "T_TREND_VS"
            for scen, c in COSTS.items():
                res = simulate(close, tg, c, frac)
                s = summarise(res, days, close)
                bh = simulate(close, np.r_[1.0, np.full(len(close) - 1, np.nan)], c)
                bh_daily = bh["eq"] / np.r_[CAP, bh["eq"][:-1]] - 1
                d = s.pop("_daily")
                s["vs_buy_and_hold_daily"] = list(boot(d - bh_daily, np.mean, BOOT_BLOCK_TRADING)[:3])
                s["buy_and_hold_final"] = float(bh["eq"][-1])
                s["first_day"], s["last_day"] = str(days[0].date()), str(days[-1].date())
                if scen in ("S0_gross", "S3_firi_realistic"):
                    s["null"] = null_percentiles(close, tg, c, frac, float(res["eq"][-1]))
                out[f"{period}/{scen}/{rule}"] = s
    return out


def exactness_gate(df) -> dict:
    """T_MA200 on E038's ranges must reproduce E038's C3 final equity at all five cost levels (1e-9 relative)."""
    ref = json.loads(E038_RESULT.read_text(encoding="utf-8"))["results"]
    targets = rule_targets(df, None)["T_MA200"]
    out = {}
    for period, (a, b) in {"exploration": (E038_EXPLORATION_START_HOUR.floor("D"), VALIDATION_START - pd.Timedelta(days=1)),
                           "validation": (VALIDATION_START, DEV_LAST_DAY)}.items():
        m = np.asarray((df.index >= a) & (df.index <= b))
        for scen, c in COSTS.items():
            got = simulate(df["close"].to_numpy()[m], targets[m], c)["eq"][-1]
            want = ref[f"{period}/{scen}/C3_ma200d"]["final_equity"]
            rel = abs(got - want) / want
            out[f"{period}/{scen}"] = {"got": got, "e038": want, "rel_diff": rel, "ok": rel <= 1e-9}
            if rel > 1e-9:
                raise SystemExit(f"exactness gate FAILED at {period}/{scen}: {got!r} vs E038 {want!r}")
    return out


# ------------------------------------------------------------------------------------------------- tail table
def tail_table(df, start) -> dict:
    out = {}
    for period in ("exploration", "validation"):
        m = period_mask(df.index, 30, period) & np.asarray(df.index >= start)
        sub = df.loc[m, ["F30", "MA200", "TREND"]].dropna()
        f = sub["F30"].to_numpy()
        fall = (f < LARGE_FALL).astype(float)
        groups = {"all": np.ones(len(sub), bool), "above 200-day": sub["MA200"].to_numpy() > 0,
                  "below 200-day": sub["MA200"].to_numpy() <= 0}
        for v in (-1.0, -0.6, -0.2, 0.2, 0.6, 1.0):
            groups[f"TREND {v:+.1f}"] = np.isclose(sub["TREND"].to_numpy(), v)
        table = {}
        for g, mask in groups.items():
            if mask.sum() < 30:
                table[g] = {"n": int(mask.sum())}
                continue
            arr = np.column_stack([fall, f, mask.astype(float)])
            rate = boot(arr, lambda a: a[a[:, 2] > 0, 0].mean() if (a[:, 2] > 0).any() else math.nan, 60)
            mean = boot(arr, lambda a: a[a[:, 2] > 0, 1].mean() if (a[:, 2] > 0).any() else math.nan, 60)
            table[g] = {"n": int(mask.sum()), "large_fall_rate": rate[0], "large_fall_ci95": [rate[1], rate[2]],
                        "mean_30d_return": mean[0], "mean_ci95": [mean[1], mean[2]]}
        out[period] = table
    return out


# ------------------------------------------------------------------------------------------------- the run
def _jsonable(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, (np.ndarray, pd.Timestamp)):
        return o.tolist() if isinstance(o, np.ndarray) else str(o)
    raise TypeError(type(o))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    df, meta = load()
    start = meta.pop("start")
    logger.info("data: %s (%.0f s)", meta, time.time() - t0)
    gate = exactness_gate(df)
    logger.info("exactness gate passed (%d checks)", len(gate))
    cmap = {f"R{k}/F{h}/{p}": correlation_cell(df, start, f"R{k}", h, p)
            for k in MAP_LOOKBACKS for h in MAP_HORIZONS for p in ("exploration", "validation")}
    logger.info("map done (%.0f s)", time.time() - t0)
    tests = {f"{s}/F{h}/{p}": correlation_cell(df, start, s, h, p)
             for s in SIGNALS for h in HORIZONS for p in ("exploration", "validation")}
    adj = holm({k.replace("/exploration", ""): v["p"] for k, v in tests.items()
                if k.endswith("/exploration") and "p" in v})
    verdicts = {}
    for key, padj in adj.items():
        e, v = tests[f"{key}/exploration"], tests[f"{key}/validation"]
        lead = padj < 0.05 and "rho" in v and np.sign(v["rho"]) == np.sign(e["rho"])
        rep = lead and (v["ci95"][0] > 0 if e["rho"] > 0 else v["ci95"][1] < 0)
        verdicts[key] = {"holm_p": padj, "verdict": "REPLICATED" if rep else "LEAD" if lead else "NO EVIDENCE"}
    tripwire = [k for k, v in tests.items() if k.endswith("/exploration") and "/F30/" not in k
                and abs(v.get("rho", 0) or 0) > 0.40]
    logger.info("signal tests done (%.0f s)", time.time() - t0)
    pred = walk_forward_m7(df, start)
    model = model_scores(pred)
    logger.info("model done (%.0f s)", time.time() - t0)
    trade = trading(df, start, pred)
    candidates = []
    for rule in RULES:
        ok = True
        for period in ("exploration", "validation"):
            s3 = trade[f"{period}/S3_firi_realistic/{rule}"]
            s4 = trade[f"{period}/S4_firi_conservative/{rule}"]
            s0 = trade[f"{period}/S0_gross/{rule}"]
            ok &= s3["mean_daily_ci95"][0] > 0 and s4["mean_daily_return"] > 0 and s0["null"]["percentile"] >= 95 \
                and s3["cycles"] >= 8
        candidates.append({"rule": rule, "trading_candidate": bool(ok)})
    sharpe_trip = [r for r in RULES if all(trade[f"{p}/S3_firi_realistic/{r}"]["sharpe"] > 2.5
                                            for p in ("exploration", "validation"))]
    logger.info("trading done (%.0f s)", time.time() - t0)
    tail = tail_table(df, start)
    doc = {"experiment": "E039", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "inputs": meta, "exactness_gate": gate, "map": cmap, "signal_tests": tests, "verdicts": verdicts,
           "model": model, "trading": trade, "trading_candidates": candidates, "tail": tail,
           "tripwires": {"rho_above_0.40": tripwire, "sharpe_above_2.5_both": sharpe_trip},
           "runtime_seconds": round(time.time() - t0, 1)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "daily_direction.json").write_text(json.dumps(doc, indent=1, default=_jsonable), encoding="utf-8")
    (OUT_DIR / "daily_direction.md").write_text(render(doc), encoding="utf-8")
    if Path("research/HOLDOUT_ACCESS.log").exists():
        raise SystemExit("research/HOLDOUT_ACCESS.log exists after the run: STOP")
    if tripwire or sharpe_trip:
        print(f"TRIPWIRE: {tripwire} {sharpe_trip} -- check the point-in-time path before reading")
    print(f"E039 written to {OUT_DIR} in {time.time() - t0:.0f} s")
    return 0


def _f(x, d=3, pct=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:+.{d}f}%" if pct else f"{x:+.{d}f}"


def render(doc: dict) -> str:
    L = ["# E039 — direction at trading horizons (daily samples, development data)", "",
         f"Generated {doc['generated_at']}. Inputs: {doc['inputs']}. Hypothesis-generating only (validation wear).", "",
         f"Exactness gate: {len(doc['exactness_gate'])} checks against E038's C3, all within 1e-9.", "",
         "## 1. Map: Spearman rho(past return over L days, forward return over H days)", ""]
    for p in ("exploration", "validation"):
        L += [f"### {p}", "", "| lookback \\ horizon | " + " | ".join(f"{h} d" for h in MAP_HORIZONS) + " |",
              "|---|" + "---|" * len(MAP_HORIZONS)]
        for k in MAP_LOOKBACKS:
            cells = []
            for h in MAP_HORIZONS:
                c = doc["map"][f"R{k}/F{h}/{p}"]
                cells.append("n/a" if "rho" not in c else f"{c['rho']:+.3f} [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}]")
            L.append(f"| {k} d | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## 2. Signal tests (Holm over the 42 exploration tests)", "",
          "| signal / horizon | exploration rho [CI] | n_eff | validation rho [CI] | n_eff | hit (expl / val) | Holm p | verdict |",
          "|---|---|---|---|---|---|---|---|"]
    for key, v in doc["verdicts"].items():
        e, va = doc["signal_tests"][f"{key}/exploration"], doc["signal_tests"][f"{key}/validation"]
        hit = f"{e.get('hit_rate', float('nan')):.3f} / {va.get('hit_rate', float('nan')):.3f}" if "hit_rate" in e and "hit_rate" in va else ""
        L.append(f"| {key} | {e['rho']:+.3f} [{e['ci95'][0]:+.3f}, {e['ci95'][1]:+.3f}] | {e['n_eff']:.0f} | "
                 + ("n/a" if "rho" not in va else f"{va['rho']:+.3f} [{va['ci95'][0]:+.3f}, {va['ci95'][1]:+.3f}] | {va['n_eff']:.0f}")
                 + f" | {hit} | {v['holm_p']:.3f} | {v['verdict']} |")
    m = doc["model"]
    L += ["", "## 3. The walk-forward logistic M7 (7-day direction)", "",
          "| period | n | Brier M7 | Brier base | skill | base − M7 [CI] | calibration slope |", "|---|---|---|---|---|---|---|"]
    for p in ("exploration", "validation"):
        s = m[p]
        L.append(f"| {p} | {s['n']} | {s['brier_model']:.4f} | {s['brier_base']:.4f} | {s['skill']:+.4f} | "
                 f"{s['d_base_minus_model']:+.4f} [{s['d_ci95'][0]:+.4f}, {s['d_ci95'][1]:+.4f}] | {s['calibration']['slope']:.2f} |")
    L += ["", "## 4. Trading rules (daily decision, long/cash)", ""]
    for p in ("validation", "exploration"):
        for scen in ("S0_gross", "S3_firi_realistic"):
            L += [f"### {p} — {scen}", "",
                  "| rule | net | B&H | exposure-matched B&H | mean daily [CI] | Sharpe | max DD | actions/yr | cycles | exposure | null pct |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
            for r in RULES:
                s = doc["trading"][f"{p}/{scen}/{r}"]
                ci = s["mean_daily_ci95"]
                L.append(f"| {r} | {_f(s['net_return'], 1, True)} | {_f(s['buy_and_hold_net'], 1, True)} | {_f(s['exposure_matched_bh_net'], 1, True)} | "
                         f"{_f(s['mean_daily_return'], 3, True)} [{_f(ci[0], 3, True)}, {_f(ci[1], 3, True)}] | {s['sharpe']:.2f} | "
                         f"{s['max_drawdown']:.0%} | {s['actions_per_year']:.1f} | {s['cycles']} | {s['mean_exposure']:.0%} | "
                         f"{s['null']['percentile']:.0f} |")
            L.append("")
    chosen = ", ".join(c["rule"] for c in doc["trading_candidates"] if c["trading_candidate"]) or "none"
    L += [f"Trading candidates: {chosen}", "",
          "## 5. Tail table: share of days followed by a 30-day fall worse than −20%", ""]
    for p in ("exploration", "validation"):
        L += [f"### {p}", "", "| state | n | rate [CI] | mean 30-day return [CI] |", "|---|---|---|---|"]
        for g, v in doc["tail"][p].items():
            if "large_fall_rate" not in v:
                L.append(f"| {g} | {v['n']} | too few | |")
                continue
            L.append(f"| {g} | {v['n']} | {v['large_fall_rate']:.3f} [{v['large_fall_ci95'][0]:.3f}, {v['large_fall_ci95'][1]:.3f}] | "
                     f"{_f(v['mean_30d_return'], 2, True)} [{_f(v['mean_ci95'][0], 2, True)}, {_f(v['mean_ci95'][1], 2, True)}] |")
        L.append("")
    L.append(f"Tripwires: {doc['tripwires']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
