"""
E038 (research/experiments/E038_low_frequency_execution.json): low-frequency execution policies on the development
data, registered in 86393c3 before this code existed.

What it does, in the record's order:
  1. Loads the development inputs through the governed readers only: the replay cache (sha256 checked), the spot
     candles for rv_24, and E018's out-of-sample move-size probabilities (its validation Brier must reproduce).
  2. Builds each policy's effective signal, point in time (persistence, daily vote, strong scores, the cost gate).
  3. Simulates every policy with a LEAN copy of rule-1.0 and the engine, after proving on the real path that the copy
     reproduces the production engine exactly (agent.execution: decide + run_hour + SimulatedExchange).
  4. Reports net results, costs, cycles, intervals, a random-timing null, sample sizes and the persistence tables.

Research only: nothing in production imports it, and it does not import agent.execution itself
(tests/test_execution.py keeps the prediction engine and its research free of the execution layer). The comparison
with the production engine lives in tools/e038_low_frequency.py, which is also the command:

    python tools/e038_low_frequency.py            # the registered development run
    python tools/e038_low_frequency.py --live     # the descriptive live run (after the development run)

It writes only research/results/E038/ and never reads past 2025-06-30 23:00 UTC in the development part. The live part
reads the live record through a read-only connection and is descriptive only.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import logging
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REPLAY_SHA256 = "accf1a73d665e91bf04f2cb556d23d2de90197a269de128496f763e0c164c0fb"
E018_VALIDATION_BRIER = 0.22486794688851872
OUT_DIR = Path("research") / "results" / "E038"

COSTS = {"S0_gross": 0.0, "S1_low_cost_reference": 0.0011, "S2_firi_optimistic": 0.008,
         "S3_firi_realistic": 0.0125, "S4_firi_conservative": 0.016}
CAP = 150.0
MIN_ORDER = 10.0
PERSIST_K = 6
STRONG_Q = 0.90
STRONG_MIN_HISTORY = 2000
GATE_MIN_OBS = 500
GATE_HORIZON = 24
BUY_T, SELL_T = 0.15, -0.15  # the scoring's own thresholds, used by the daily vote
RESUME_MIN = 168 * 60  # a halt is lifted after 168 h (the simulation's stand-in for the owner resuming)
DECISION_DELAY_MIN = 73  # decisions at as_of + 1 h 13 min, like the live job
BOOT_BLOCK_DAYS, N_BOOT, SEED = 20, 2000, 31
NULL_SHIFTS, NULL_SEED, NULL_MIN_SHIFT = 200, 2038, 720
PERSIST_BLOCK_HOURS = 168
VALIDATION_START_H = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() // 3600)
DEV_END_H = int(pd.Timestamp("2025-07-01", tz="UTC").timestamp() // 3600)  # exclusive: the holdout's first hour

# the rule-1.0 constants the lean copy mirrors (checked against agent.execution.strategy at run time)
TARGET_HOURLY_VOL, F_VOL_MIN, F_MOVE_MIN, BAND_FRACTION = 0.006, 0.25, 0.5, 0.20
MIN_HOLD_MIN = 6 * 60
DAILY_LOSS_LIMIT, MAX_DRAWDOWN = 0.10, 0.30
SIG_NAME = {1: "BUY", 0: "HOLD", -1: "SELL"}


# ------------------------------------------------------------------------------------------------- inputs
@dataclass
class Inputs:
    hours: np.ndarray  # int64 hours since the epoch of each saved hour (as_of)
    close: np.ndarray
    sig: np.ndarray  # int8: 1 BUY, 0 HOLD, -1 SELL
    score: np.ndarray
    rv: np.ndarray  # NaN where missing
    p: np.ndarray  # NaN where missing
    start: int  # first simulated row (the first hour with an out-of-sample p)
    meta: dict


def _registered_replay():
    """The development bars (governed reader) and the replay cache E038 registered, found through the replay module's
    own naming (agent/research/replay.py), never by a file name written here. Never recomputed: a missing or changed
    cache stops the run."""
    from agent.indicators.engine import HISTORY_HOURS
    from agent.research.history import load_bars
    from agent.research.periods import HOLDOUT
    from agent.research.replay import read_replay, replay_cache_path

    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    path = replay_cache_path(snapshot, bars[HISTORY_HOURS - 1].as_of, bars[-1].as_of)
    if not path.exists():
        raise SystemExit(f"the registered replay cache {path} is missing; it is never recomputed for E038")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != REPLAY_SHA256:
        raise SystemExit(f"replay cache sha256 {sha} != the registered {REPLAY_SHA256}")
    return bars, snapshot, read_replay(path), sha


def load_development() -> Inputs:
    from agent.research.feature_count import FULL, evaluate, prepare
    from agent.research.features import bars_to_frame, volatility_features

    bars, snapshot, rows, sha = _registered_replay()
    idx = pd.DatetimeIndex([pd.Timestamp(r["as_of"]) for r in rows])
    hours = hours_of(idx)
    if hours.max() >= DEV_END_H:
        raise SystemExit("the replay reaches the holdout")
    sig = np.array([{"BUY": 1, "HOLD": 0, "SELL": -1}[r["signal"]] for r in rows], dtype=np.int8)
    close = np.array([r["close"] for r in rows], dtype=float)
    score = np.array([r["overall_score"] for r in rows], dtype=float)

    rv_series = volatility_features(bars_to_frame(bars))["rv_24"]
    rv = rv_series.reindex(idx).to_numpy(float)

    df, spec, folds = prepare()
    res = evaluate(df, spec, folds, FULL, {})
    brier = res["validation"]["brier"]
    if abs(brier - E018_VALIDATION_BRIER) > 1e-9:
        raise SystemExit(f"E018 did not reproduce: validation Brier {brier!r} != {E018_VALIDATION_BRIER!r}")
    p = res["predictions"]["p"].reindex(idx).to_numpy(float)
    start = int(np.argmax(~np.isnan(p)))
    meta = {"replay_sha256": sha, "rows": len(rows), "first_hour": str(idx[0]), "last_hour": str(idx[-1]),
            "simulation_start": str(idx[start]), "e018_validation_brier": brier, "spot_snapshot": snapshot.name,
            "rv_missing_in_simulation": int(np.isnan(rv[start:]).sum()),
            "p_missing_in_simulation": int(np.isnan(p[start:]).sum())}
    return Inputs(hours, close, sig, score, rv, p, start, meta)


def hours_of(index: pd.DatetimeIndex) -> np.ndarray:
    """Whole hours since the epoch, whatever resolution pandas parsed the times at (it may choose microseconds; the
    first launch of E038 divided microseconds as if they were nanoseconds and collapsed every hour into one)."""
    hours = ((index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(hours=1)).to_numpy(np.int64)
    if len(hours) > 1 and not (np.diff(hours) > 0).all():
        raise SystemExit("the hours are not strictly increasing: STOP")
    return hours


# ------------------------------------------------------------------------------------------------- selectors
def run_lengths(hours: np.ndarray, sig: np.ndarray) -> np.ndarray:
    """Consecutive saved hours carrying the same signal, ending at each row; a missing hour breaks the run."""
    h, s = hours.tolist(), sig.tolist()
    out = [1] * len(s)
    for i in range(1, len(s)):
        if h[i] - h[i - 1] == 1 and s[i] == s[i - 1]:
            out[i] = out[i - 1] + 1
    return np.array(out, dtype=np.int64)


def persist(hours, sig, k: int = PERSIST_K) -> np.ndarray:
    return np.where(run_lengths(hours, sig) >= k, sig, 0).astype(np.int8)


def daily_vote(hours, score) -> np.ndarray:
    """On the 23:00 UTC row only: the mean score of that UTC day's saved rows (all at or before 23:00)."""
    day = hours // 24
    frame = pd.DataFrame({"day": day, "score": score})
    mean = frame.groupby("day")["score"].transform("mean").to_numpy()
    eff = np.zeros(len(hours), dtype=np.int8)
    last = (hours % 24) == 23
    eff[last & (mean >= BUY_T)] = 1
    eff[last & (mean <= SELL_T)] = -1
    return eff


def strong_threshold(score) -> np.ndarray:
    """The 90th percentile (numpy's linear rule) of |score| over all EARLIER rows; NaN until 2,000 exist."""
    out = np.full(len(score), np.nan)
    seen: list[float] = []
    for i, x in enumerate(np.abs(score).tolist()):
        m = len(seen)
        if m >= STRONG_MIN_HISTORY:
            pos = STRONG_Q * (m - 1)
            lo = int(math.floor(pos))
            hi = min(lo + 1, m - 1)
            out[i] = seen[lo] + (seen[hi] - seen[lo]) * (pos - lo)
        bisect.insort(seen, x)
    return out


def strong(score, q=None) -> np.ndarray:
    q = strong_threshold(score) if q is None else q
    eff = np.zeros(len(score), dtype=np.int8)
    ok = ~np.isnan(q)
    eff[ok & (score >= q)] = 1
    eff[ok & (score <= -q)] = -1
    return eff


def run_bucket(runs: np.ndarray) -> np.ndarray:
    return np.where(runs <= 5, 0, np.where(runs <= 23, 1, 2))


def forward_returns(hours, close, horizon: int) -> np.ndarray:
    pos = {int(h): i for i, h in enumerate(hours.tolist())}
    out = np.full(len(hours), np.nan)
    for i, h in enumerate(hours.tolist()):
        j = pos.get(h + horizon)
        if j is not None:
            out[i] = close[j] / close[i] - 1
    return out


def gate_mu(hours, close, sig) -> np.ndarray:
    """mu(s) at each row: the mean 24 h forward return of all earlier rows in the same state whose outcome was known
    at decision time (as_of <= t - 24 h); NaN until 500 such rows exist. State = (signal, run-length bucket)."""
    fwd = forward_returns(hours, close, GATE_HORIZON)
    state = ((sig.astype(np.int64) + 1) * 3 + run_bucket(run_lengths(hours, sig))).tolist()
    sums, counts = [0.0] * 9, [0] * 9
    out = np.full(len(hours), np.nan)
    h, f = hours.tolist(), fwd.tolist()
    u = 0
    for t in range(len(h)):
        while u < len(h) and h[u] + GATE_HORIZON <= h[t]:
            if not math.isnan(f[u]):
                sums[state[u]] += f[u]
                counts[state[u]] += 1
            u += 1
        s = state[t]
        if counts[s] >= GATE_MIN_OBS:
            out[t] = sums[s] / counts[s]
    return out


def gate(mu: np.ndarray, c: float) -> np.ndarray:
    eff = np.zeros(len(mu), dtype=np.int8)
    ok = ~np.isnan(mu)
    eff[ok & (mu > 2 * c)] = 1
    eff[ok & (mu < -2 * c)] = -1
    return eff


# ------------------------------------------------------------------------------------------------- simulation
def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def simulate(hours, close, eff, rv, p, lo: int, hi: int, c: float, max_actions: int, resize: bool) -> dict:
    """
    The lean copy of rule-1.0 + the engine + the simulated exchange (fee_rate = c, slippage 0), on rows lo..hi-1.
    `eff` is the policy's effective signal; resize=False makes a BUY while invested a HOLD (the B designs).
    Mirrors agent.execution exactly, including the order of every float operation (checked by exactness_gate).
    """
    H, P, E = hours.tolist(), close.tolist(), eff.tolist()
    RV = [None if math.isnan(x) else x for x in rv.tolist()]
    PL = [None if math.isnan(x) else x for x in p.tolist()]
    cash, btc, peak = CAP, 0.0, CAP
    last_t, last_side = None, 0
    times: deque = deque()
    halted, halt_t, halts = False, None, 0
    eq_by_hour: dict[int, float] = {}
    n = hi - lo
    eq_after, eq_before, expo_after = [0.0] * n, [0.0] * n, [0.0] * n
    actions = []  # (row, side, notional, cost, risk_exit)
    band = BAND_FRACTION * CAP
    for k, i in enumerate(range(lo, hi)):
        now = H[i] * 60 + DECISION_DELAY_MIN
        price = P[i]
        if halted and now - halt_t >= RESUME_MIN:
            halted, peak = False, cash + btc * price
        equity = cash + btc * price
        exposure = btc * price
        eq_before[k] = equity
        side, qty, amount, risk, halt = 0, 0.0, 0.0, False, False
        if not halted:
            pk = max(peak, equity)
            dd = 0.0 if pk <= 0 else 1 - equity / pk
            e24 = eq_by_hour.get(H[i] - 24)
            daily = None if not e24 else 1 - equity / e24
            if not (dd <= MAX_DRAWDOWN and (daily is None or daily <= DAILY_LOSS_LIMIT)):
                risk, halt = True, True
                if btc * price >= MIN_ORDER:
                    side, qty = -1, btc
            else:
                r = RV[i]
                f_vol = _clip(TARGET_HOURLY_VOL / r, F_VOL_MIN, 1.0) if (r and r > 0) else F_VOL_MIN
                f_move = _clip(1.5 - PL[i], F_MOVE_MIN, 1.0) if PL[i] is not None else F_MOVE_MIN
                size = min(f_vol, f_move)
                base = min(CAP, equity)
                s = E[i]
                if s == 1 and not resize and exposure >= MIN_ORDER:
                    s = 0
                if s == 1:
                    target = base * size
                elif s == -1:
                    target = 0.0
                else:
                    target = min(exposure, base)
                delta = target - exposure
                if abs(delta) >= 1e-9:
                    want = 1 if delta > 0 else -1
                    full_exit = target == 0.0
                    while times and now - times[0] >= 1440:
                        times.popleft()
                    reversal = last_side != 0 and last_side != want
                    held = None if last_t is None else now - last_t
                    if len(times) < max_actions and (not reversal or held is None or held >= MIN_HOLD_MIN):
                        resize_o = not full_exit and exposure > 0
                        need = max(band, MIN_ORDER) if resize_o else MIN_ORDER
                        if abs(delta) >= need:
                            if want == 1:
                                amount = min(delta, cash)
                                if amount >= MIN_ORDER:
                                    side = 1
                            else:
                                side, qty = -1, (btc if full_exit else min(btc, -delta / price))
        if side == 1:
            fee = amount * c
            got = (amount - fee) / price
            cash, btc = max(cash - amount, 0.0), btc + got
            actions.append((i, 1, amount, fee, risk))
        elif side == -1:
            gross = qty * price
            fee = gross * c
            cash, btc = cash + (gross - fee), max(btc - qty, 0.0)
            actions.append((i, -1, gross, fee, risk))
        if side != 0:
            last_t, last_side = now, side
            times.append(now)
        equity_after = cash + btc * price
        peak = max(peak, equity_after)
        if halt:
            halted, halt_t, halts = True, now, halts + 1
        eq_by_hour[H[i]] = equity_after
        eq_after[k], expo_after[k] = equity_after, btc * price
    return {"eq_after": np.array(eq_after), "eq_before": np.array(eq_before), "expo": np.array(expo_after),
            "actions": actions, "halts": halts}


def simulate_buy_and_hold(close, lo, hi, c) -> dict:
    btc = (CAP - CAP * c) / close[lo]
    eq = btc * close[lo:hi]
    return {"eq_after": eq, "eq_before": np.concatenate([[CAP], eq[:-1]]), "expo": eq.copy(),
            "actions": [(lo, 1, CAP, CAP * c, False)], "halts": 0}


def simulate_cash(lo, hi) -> dict:
    eq = np.full(hi - lo, CAP)
    return {"eq_after": eq, "eq_before": eq.copy(), "expo": np.zeros(hi - lo), "actions": [], "halts": 0}


def ma200_wanted(hours, close) -> np.ndarray:
    """On each 23:00 UTC row: 1 if the close is above the mean of the last 200 daily 23:00 closes (today included)."""
    want = np.full(len(hours), -2, dtype=np.int8)  # -2 = no decision this row
    daily: deque = deque(maxlen=200)
    for i, h in enumerate(hours.tolist()):
        if h % 24 == 23:
            daily.append(close[i])
            if len(daily) == 200:
                want[i] = 1 if close[i] > sum(daily) / 200 else 0
    return want


def simulate_ma200(hours, close, lo, hi, c, want=None) -> dict:
    want = ma200_wanted(hours, close) if want is None else want
    cash, btc = CAP, 0.0
    n = hi - lo
    eq_after, eq_before, expo = np.empty(n), np.empty(n), np.empty(n)
    actions = []
    for k, i in enumerate(range(lo, hi)):
        price = close[i]
        eq_before[k] = cash + btc * price
        if want[i] == 1 and btc == 0.0:
            fee = cash * c
            btc, cash = (cash - fee) / price, 0.0
            actions.append((i, 1, eq_before[k], fee, False))
        elif want[i] == 0 and btc > 0.0:
            gross = btc * price
            fee = gross * c
            cash, btc = gross - fee, 0.0
            actions.append((i, -1, gross, fee, False))
        eq_after[k], expo[k] = cash + btc * price, btc * price
    return {"eq_after": eq_after, "eq_before": eq_before, "expo": expo, "actions": actions, "halts": 0}


# ------------------------------------------------------------------------------------------------- policies
POLICIES = ["A4", "A2", "A1", "B1_persist_cap1", "B1_persist_cap2", "B2_daily_vote", "B3_strong_cap1",
            "B3_strong_cap2", "B4_gate_cap1", "B4_gate_cap2", "C1_buy_and_hold", "C2_cash", "C3_ma200d"]
NULL_POLICIES = ["A4", "A2", "A1", "B1_persist_cap1", "B1_persist_cap2", "B2_daily_vote", "B3_strong_cap1", "B3_strong_cap2"]


def effective_signals(hours, close, sig, score, strong_q=None) -> dict:
    return {"raw": sig, "persist": persist(hours, sig), "daily": daily_vote(hours, score),
            "strong": strong(score, strong_q)}


def run_policy(name, hours, close, eff, rv, p, lo, hi, c, mu=None, ma_want=None) -> dict:
    if name in ("A4", "A2", "A1"):
        return simulate(hours, close, eff["raw"], rv, p, lo, hi, c, int(name[1]), True)
    if name.startswith("B1"):
        return simulate(hours, close, eff["persist"], rv, p, lo, hi, c, int(name[-1]), False)
    if name == "B2_daily_vote":
        return simulate(hours, close, eff["daily"], rv, p, lo, hi, c, 1, False)
    if name.startswith("B3"):
        return simulate(hours, close, eff["strong"], rv, p, lo, hi, c, int(name[-1]), False)
    if name.startswith("B4"):
        return simulate(hours, close, gate(mu, c), rv, p, lo, hi, c, int(name[-1]), False)
    if name == "C1_buy_and_hold":
        return simulate_buy_and_hold(close, lo, hi, c)
    if name == "C2_cash":
        return simulate_cash(lo, hi)
    if name == "C3_ma200d":
        return simulate_ma200(hours, close, lo, hi, c, ma_want)
    raise ValueError(name)


# ------------------------------------------------------------------------------------------------- metrics
def daily_returns(hours_slice: np.ndarray, eq: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Equity at the last saved hour of each UTC day; returns from day to day, the first against the start (150)."""
    day = hours_slice // 24
    last = np.r_[day[1:] != day[:-1], True]
    eq_d = eq[last]
    prev = np.r_[CAP, eq_d[:-1]]
    return day[last], eq_d / prev - 1


def boot_mean(x: np.ndarray) -> tuple[float, float, float]:
    from agent.research.metrics import block_bootstrap_estimates
    point, est = block_bootstrap_estimates(np.asarray(x, float), np.mean, BOOT_BLOCK_DAYS, N_BOOT, SEED)
    if len(est) == 0:
        return point, float("nan"), float("nan")
    return point, float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))


def cycles(res: dict, hours_slice: np.ndarray, lo: int) -> list[dict]:
    """flat -> invested -> flat, from the per-row equity and exposure (flat = exposure below the venue minimum)."""
    out, open_at = [], None
    expo, eqb, eqa = res["expo"], res["eq_before"], res["eq_after"]
    for k in range(len(expo)):
        before_flat = (expo[k - 1] if k else 0.0) < MIN_ORDER
        after_flat = expo[k] < MIN_ORDER
        if before_flat and not after_flat:
            open_at = k
        elif not before_flat and after_flat and open_at is not None:
            out.append({"ret": eqa[k] / eqb[open_at] - 1, "hours": int(hours_slice[k] - hours_slice[open_at])})
            open_at = None
    return out


def summarise(res: dict, hours_slice: np.ndarray, close_slice: np.ndarray, lo: int, years: float) -> dict:
    eq = res["eq_after"]
    days, dr = daily_returns(hours_slice, eq)
    mean, lo95, hi95 = boot_mean(dr)
    sd = float(np.std(dr, ddof=1)) if len(dr) > 1 else 0.0
    peak = np.maximum.accumulate(np.r_[CAP, eq])[1:]
    normal = [a for a in res["actions"] if not a[4]]
    risk = [a for a in res["actions"] if a[4]]
    cyc = cycles(res, hours_slice, lo)
    rets = np.array([c["ret"] for c in cyc])
    gains, losses = rets[rets > 0], rets[rets <= 0]
    final = float(eq[-1])
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(eq > 0, res["expo"] / eq, 0.0)
    return {
        "final_equity": final, "net_return": final / CAP - 1,
        "annualised_return": (final / CAP) ** (1 / years) - 1 if final > 0 else -1.0,
        "mean_daily_return": mean, "mean_daily_return_ci95": [lo95, hi95],
        "sharpe_annualised": (mean / sd * math.sqrt(365)) if sd > 0 else 0.0,
        "max_drawdown": float(np.max(1 - eq / peak)),
        "normal_actions": len(normal), "risk_exits": len(risk), "halts": res["halts"],
        "actions_per_year": len(normal) / years,
        "cycles": len(cyc), "cycles_per_year": len(cyc) / years,
        "cycle_mean": float(rets.mean()) if len(rets) else None,
        "cycle_median": float(np.median(rets)) if len(rets) else None,
        "cycle_sd": float(rets.std(ddof=1)) if len(rets) > 1 else None,
        "cycle_win_rate": float((rets > 0).mean()) if len(rets) else None,
        "avg_gain": float(gains.mean()) if len(gains) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(gains.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else None,
        "mean_hold_hours": float(np.mean([c["hours"] for c in cyc])) if cyc else None,
        "mean_exposure_share": float(share.mean()),
        "costs_paid": float(sum(a[3] for a in res["actions"])),
        "_daily": dr, "_days": days,
    }


def per_year(res: dict, hours_slice: np.ndarray) -> dict:
    eq = res["eq_after"]
    years = pd.to_datetime(hours_slice * 3600, unit="s", utc=True).year.to_numpy()
    out, prev = {}, CAP
    for y in np.unique(years):
        last = eq[years == y][-1]
        out[str(int(y))] = float(last / prev - 1)
        prev = last
    return out


def regime_blocks(res: dict, bh: dict, hours_slice: np.ndarray) -> dict:
    """30-day blocks from the start, classed AFTERWARDS by buy-and-hold's return in the block (descriptive)."""
    day = (hours_slice - hours_slice[0]) // 24
    block = day // 30
    out = {"up": [], "down": [], "flat": []}
    prev_s, prev_b = CAP, float(bh["eq_before"][0])
    for b in np.unique(block):
        m = block == b
        s_end, b_end = res["eq_after"][m][-1], bh["eq_after"][m][-1]
        rb = b_end / prev_b - 1
        cls = "up" if rb > 0.10 else "down" if rb < -0.10 else "flat"
        out[cls].append(s_end / prev_s - 1)
        prev_s, prev_b = s_end, b_end
    return {k: {"blocks": len(v), "mean_return": float(np.mean(v)) if v else None} for k, v in out.items()}


def sample_sizes(summary: dict) -> dict:
    sd, rate = summary.get("cycle_sd"), summary.get("cycles_per_year")
    if not sd or not rate:
        return {}
    out = {}
    for delta in (0.005, 0.01, 0.02):
        n = math.ceil(((1.96 + 0.84) * sd / delta) ** 2)
        out[f"{delta:.1%}"] = {"cycles": n, "years_at_this_rate": n / rate}
    return out


# ------------------------------------------------------------------------------------------------- the null
_NULL: dict = {}


def _null_init(payload):
    _NULL.update(payload)


def _null_one(k: int) -> dict:
    d = _NULL
    sig = np.roll(d["sig"], k)
    score = np.roll(d["score"], k)
    eff = effective_signals(d["hours"], d["close"], sig, score)
    out = {}
    for period, (lo, hi) in d["ranges"].items():
        for name in NULL_POLICIES:
            r = run_policy(name, d["hours"], d["close"], eff, d["rv"], d["p"], lo, hi, 0.0)
            out[f"{period}/{name}"] = float(r["eq_after"][-1])
    return out


def random_timing_null(inp: Inputs, ranges: dict, processes: int | None = None) -> dict:
    n = len(inp.hours)
    shifts = np.random.default_rng(NULL_SEED).integers(NULL_MIN_SHIFT, n - NULL_MIN_SHIFT + 1, size=NULL_SHIFTS)
    payload = {"hours": inp.hours, "close": inp.close, "sig": inp.sig, "score": inp.score, "rv": inp.rv, "p": inp.p,
               "ranges": ranges}
    with Pool(processes=processes, initializer=_null_init, initargs=(payload,)) as pool:
        results = pool.map(_null_one, shifts.tolist(), chunksize=4)
    keys = results[0].keys()
    return {"shifts": shifts.tolist(), "values": {key: [r[key] for r in results] for key in keys}}


# ------------------------------------------------------------------------------------------------- persistence
def persistence_tables(inp: Inputs) -> dict:
    """Descriptive: forward 24 h / 72 h mean return by signal x run-length bucket and by score quintile, minus the
    period's unconditional mean; 168 h block bootstrap (2,000, seed 31). Every development row, not just simulated."""
    from agent.research.metrics import block_bootstrap_estimates
    runs = run_bucket(run_lengths(inp.hours, inp.sig))
    out = {}
    for horizon in (24, 72):
        fwd = forward_returns(inp.hours, inp.close, horizon)
        for period, m in (("exploration", inp.hours < VALIDATION_START_H), ("validation", inp.hours >= VALIDATION_START_H)):
            keep = m & ~np.isnan(fwd)
            f, s, b, sc = fwd[keep], inp.sig[keep], runs[keep], inp.score[keep]
            edges = np.quantile(sc, [0.2, 0.4, 0.6, 0.8])
            quint = np.searchsorted(edges, sc, side="right")
            groups = {}
            for sv, sn in ((1, "BUY"), (0, "HOLD"), (-1, "SELL")):
                for bv, bn in ((0, "run 1-5 h"), (1, "run 6-23 h"), (2, "run >= 24 h")):
                    groups[f"{sn} {bn}"] = (s == sv) & (b == bv)
            for q in range(5):
                groups[f"score quintile {q + 1}"] = quint == q
            table = {}
            for gname, mask in groups.items():
                if mask.sum() < 50:
                    table[gname] = {"n": int(mask.sum())}
                    continue
                arr = np.column_stack([f, mask.astype(float)])

                def stat(a):
                    sel = a[:, 1] > 0
                    return a[sel, 0].mean() - a[:, 0].mean() if sel.any() else float("nan")

                point, est = block_bootstrap_estimates(arr, stat, PERSIST_BLOCK_HOURS, N_BOOT, SEED)
                est = est[~np.isnan(est)]
                table[gname] = {"n": int(mask.sum()), "mean": float(f[mask].mean()), "excess": point,
                                "excess_ci95": [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))]}
            out[f"{horizon}h/{period}"] = {"unconditional_mean": float(f.mean()), "n": int(len(f)), "groups": table}
    return out


def signal_stability(hours, sig, lo, hi) -> dict:
    s, h = sig[lo:hi], hours[lo:hi]
    changes = int(((s[1:] != s[:-1]) & (np.diff(h) == 1)).sum())
    runs = run_lengths(h, s)
    ends = np.r_[runs[1:] <= runs[:-1], True]
    lengths = runs[ends]
    days = (h[-1] - h[0]) / 24
    return {"changes_per_day": changes / days, "median_run_hours": float(np.median(lengths)),
            "share_runs_under_6h": float((lengths < 6).mean()), "mix": {SIG_NAME[v]: float((s == v).mean()) for v in (1, 0, -1)}}


# ------------------------------------------------------------------------------------------------- the run
def evaluate_all(inp: Inputs, ranges: dict, mu: np.ndarray, eff: dict, ma_want: np.ndarray) -> dict:
    out = {}
    for period, (lo, hi) in ranges.items():
        hs, cs = inp.hours[lo:hi], inp.close[lo:hi]
        years = (hs[-1] - hs[0] + 1) / 8766
        for scen, c in COSTS.items():
            bh = run_policy("C1_buy_and_hold", inp.hours, inp.close, eff, inp.rv, inp.p, lo, hi, c)
            bh_daily = summarise(bh, hs, cs, lo, years)["_daily"]
            res_by = {}
            for name in POLICIES:
                r = bh if name == "C1_buy_and_hold" else run_policy(name, inp.hours, inp.close, eff, inp.rv, inp.p,
                                                                     lo, hi, c, mu, ma_want)
                res_by[name] = (r, summarise(r, hs, cs, lo, years))
            for name, (r, sm) in res_by.items():
                d = sm.pop("_daily")
                sm.pop("_days")
                sm["vs_buy_and_hold_daily"] = list(boot_mean(d - bh_daily)) if name != "C1_buy_and_hold" else None
                if period == "full":
                    sm["per_year"] = per_year(r, hs)
                    sm["regime_blocks"] = regime_blocks(r, bh, hs)
                sm["sample_sizes"] = sample_sizes(sm)
                sm["_d"] = d
                out[f"{period}/{scen}/{name}"] = sm
            for x, y in (("A1", "A2"), ("A2", "A4"), ("A1", "A4"), ("B1_persist_cap1", "B1_persist_cap2"),
                         ("B3_strong_cap1", "B3_strong_cap2")):
                out[f"{period}/{scen}/paired {x} - {y}"] = list(boot_mean(out[f"{period}/{scen}/{x}"]["_d"] - out[f"{period}/{scen}/{y}"]["_d"]))
        for key in [k for k in out if k.startswith(period + "/")]:
            if isinstance(out[key], dict):
                out[key].pop("_d", None)
    return out


def ranges_of(inp: Inputs) -> dict:
    lo = inp.start
    v = int(np.searchsorted(inp.hours, VALIDATION_START_H))
    return {"exploration": (lo, v), "validation": (v, len(inp.hours)), "full": (lo, len(inp.hours))}


def _jsonable(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def main_development(processes: int | None, exactness_gate, check_constants) -> int:
    """The registered run. The exactness gate and the constants check come from tools/e038_low_frequency.py, the one
    place allowed to import both this module and agent.execution (tests/test_execution.py keeps agent/ free of it)."""
    t0 = time.time()
    check_constants()
    inp = load_development()
    rng = ranges_of(inp)
    logger.info("inputs loaded (%.0f s): %s", time.time() - t0, inp.meta)
    gate_result = exactness_gate(inp, {k: rng[k] for k in ("exploration", "validation")})
    logger.info("exactness gate passed (%d checks, %.0f s)", len(gate_result), time.time() - t0)
    eff = effective_signals(inp.hours, inp.close, inp.sig, inp.score)
    mu = gate_mu(inp.hours, inp.close, inp.sig)
    ma_want = ma200_wanted(inp.hours, inp.close)
    results = evaluate_all(inp, rng, mu, eff, ma_want)
    logger.info("policies evaluated (%.0f s)", time.time() - t0)
    null = random_timing_null(inp, {k: rng[k] for k in ("exploration", "validation")}, processes)
    null_read = {}
    for key, vals in null["values"].items():
        period, name = key.split("/")
        actual = results[f"{period}/S0_gross/{name}"]["final_equity"]
        arr = np.array(vals)
        null_read[key] = {"actual": actual, "null_p95": float(np.percentile(arr, 95)), "null_median": float(np.median(arr)),
                          "percentile": float((arr < actual).mean() * 100 + (arr == actual).mean() * 50)}
    logger.info("null done (%.0f s)", time.time() - t0)
    doc = {
        "experiment": "E038", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": inp.meta, "ranges": {k: [str(pd.Timestamp(inp.hours[a] * 3600, unit="s", tz="UTC")),
                                           str(pd.Timestamp(inp.hours[b - 1] * 3600, unit="s", tz="UTC"))] for k, (a, b) in rng.items()},
        "costs_per_side": COSTS, "exactness_gate": gate_result,
        "signal_stability": {k: signal_stability(inp.hours, inp.sig, a, b) for k, (a, b) in rng.items()},
        "results": results, "random_timing_null": null_read, "null_shifts": null["shifts"],
        "persistence": persistence_tables(inp), "runtime_seconds": round(time.time() - t0, 1),
    }
    # the cost gate's estimates at the end of each period (what it 'believed')
    runs_b = run_bucket(run_lengths(inp.hours, inp.sig))
    for period, (lo, hi) in rng.items():
        snap = {}
        for s in (1, 0, -1):
            for b in range(3):
                rows = np.where((inp.sig[lo:hi] == s) & (runs_b[lo:hi] == b))[0]
                snap[f"{SIG_NAME[s]} run {['1-5', '6-23', '>=24'][b]} h"] = float(mu[lo + rows[-1]]) if len(rows) and not math.isnan(mu[lo + rows[-1]]) else None
        doc[f"gate_mu_at_end_{period}"] = snap
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "low_frequency.json").write_text(json.dumps(doc, indent=1, default=_jsonable), encoding="utf-8")
    (OUT_DIR / "low_frequency.md").write_text(render(doc), encoding="utf-8")
    if Path("research/HOLDOUT_ACCESS.log").exists():
        raise SystemExit("research/HOLDOUT_ACCESS.log exists after the run: STOP")
    print(f"E038 written to {OUT_DIR} in {time.time() - t0:.0f} s")
    return 0


# ------------------------------------------------------------------------------------------------- render
def _pct(x, d=2):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.{d}f}%"


def render(doc: dict) -> str:
    R = doc["results"]
    L = ["# E038 — low-frequency execution policies (development data, technical-only)", "",
         f"Generated {doc['generated_at']}. Simulation {doc['ranges']['full'][0]} → {doc['ranges']['full'][1]}; "
         f"exploration {doc['ranges']['exploration'][0]} → {doc['ranges']['exploration'][1]}; validation "
         f"{doc['ranges']['validation'][0]} → {doc['ranges']['validation'][1]}. Start 150 in cash each period. "
         "Hypothesis-generating only (validation wear); news absent (weight 0).", "",
         f"Exactness gate: {len(doc['exactness_gate'])} checks, all identical to the production engine.", ""]
    for period in ("validation", "exploration"):
        for scen in COSTS:
            L += [f"## {period} — {scen} ({COSTS[scen]:.2%} per side)", "",
                  "| policy | final | net | vs cash: mean daily [95% CI] | vs B&H daily [95% CI] | Sharpe | max DD | actions/yr | risk exits | cycles | cycle mean | win | PF | hold h | exposure | costs |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for name in POLICIES:
                s = R[f"{period}/{scen}/{name}"]
                ci = s["mean_daily_return_ci95"]
                vb = s["vs_buy_and_hold_daily"]
                L.append(f"| {name} | {s['final_equity']:.1f} | {_pct(s['net_return'], 1)} | {_pct(s['mean_daily_return'], 3)} [{_pct(ci[0], 3)}, {_pct(ci[1], 3)}] | "
                         + ("—" if vb is None else f"{_pct(vb[0], 3)} [{_pct(vb[1], 3)}, {_pct(vb[2], 3)}]")
                         + f" | {s['sharpe_annualised']:.2f} | {s['max_drawdown']:.1%} | {s['actions_per_year']:.0f} | {s['risk_exits']} | {s['cycles']} | "
                         f"{_pct(s['cycle_mean'])} | {'n/a' if s['cycle_win_rate'] is None else f'{s['cycle_win_rate']:.0%}'} | "
                         f"{'n/a' if s['profit_factor'] is None else f'{s['profit_factor']:.2f}'} | "
                         f"{'n/a' if s['mean_hold_hours'] is None else f'{s['mean_hold_hours']:.0f}'} | {s['mean_exposure_share']:.0%} | {s['costs_paid']:.1f} |")
            L.append("")
            for key in [k for k in R if k.startswith(f"{period}/{scen}/paired")]:
                v = R[key]
                L.append(f"- {key.split('/')[-1]}: mean daily difference {_pct(v[0], 4)} [{_pct(v[1], 4)}, {_pct(v[2], 4)}]")
            L.append("")
    L += ["## Random-timing null (zero cost; 200 circular shifts of the signal against prices)", "",
          "| period / policy | actual final | null median | null 95th pct | percentile |", "|---|---|---|---|---|"]
    for key, v in doc["random_timing_null"].items():
        L.append(f"| {key} | {v['actual']:.1f} | {v['null_median']:.1f} | {v['null_p95']:.1f} | {v['percentile']:.0f} |")
    L += ["", "## Per calendar year (full run, Firi realistic S3)", "", "| policy | " + " | ".join(R[f"full/S3_firi_realistic/A4"]["per_year"]) + " |",
          "|---|" + "---|" * len(R["full/S3_firi_realistic/A4"]["per_year"])]
    for name in POLICIES:
        py = R[f"full/S3_firi_realistic/{name}"]["per_year"]
        L.append(f"| {name} | " + " | ".join(_pct(v, 1) for v in py.values()) + " |")
    L += ["", "## Persistence and strength (descriptive): forward return minus the period's mean", ""]
    for key, t in doc["persistence"].items():
        L += [f"### {key} (unconditional mean {_pct(t['unconditional_mean'], 3)}, n {t['n']})", "", "| group | n | excess [95% CI] |", "|---|---|---|"]
        for g, v in t["groups"].items():
            L.append(f"| {g} | {v['n']} | " + ("too few" if "excess" not in v else f"{_pct(v['excess'], 3)} [{_pct(v['excess_ci95'][0], 3)}, {_pct(v['excess_ci95'][1], 3)}]") + " |")
        L.append("")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------- live (descriptive)
def load_live() -> tuple[Inputs, dict]:
    """The live record through a server-confirmed read-only connection: pipeline 0.2.0 predictions and the move-size
    shadow rows. Descriptive only (E038: never used to choose anything)."""
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            if cur.fetchone()[0] != "on":
                raise SystemExit("the connection is not read-only: STOP")
            cur.execute("""SELECT p.as_of, p.close_price, p.signal, p.overall_score,
                                  (s.features ->> 'rv_24')::float, s.p_calibrated
                           FROM predictions p LEFT JOIN shadow_move_size s ON s.as_of = p.as_of AND s.status = 'ok'
                           WHERE p.pipeline_version = '0.2.0' ORDER BY p.as_of""")
            rows = cur.fetchall()
        conn.rollback()
    hours = hours_of(pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows]))
    inp = Inputs(hours, np.array([float(r[1]) for r in rows]),
                 np.array([{"BUY": 1, "HOLD": 0, "SELL": -1}[r[2]] for r in rows], dtype=np.int8),
                 np.array([float(r[3]) for r in rows]),
                 np.array([np.nan if r[4] is None else r[4] for r in rows], dtype=float),
                 np.array([np.nan if r[5] is None else r[5] for r in rows], dtype=float), 0,
                 {"rows": len(rows), "first_hour": str(rows[0][0]), "last_hour": str(rows[-1][0])})
    return inp, {}


def main_live() -> int:
    """The same policies on the live record, with point-in-time history carried over from the development rows (the
    strong-score quantile and the cost gate's estimates). C3 is not run: its 200-day window would read the sealed
    holdout period."""
    dev = load_development_light()
    live, _ = load_live()
    hours = np.r_[dev.hours, live.hours]
    close = np.r_[dev.close, live.close]
    sig = np.r_[dev.sig, live.sig]
    score = np.r_[dev.score, live.score]
    rv = np.r_[np.full(len(dev.hours), np.nan), live.rv]
    p = np.r_[np.full(len(dev.hours), np.nan), live.p]
    lo, hi = len(dev.hours), len(hours)
    eff = effective_signals(hours, close, sig, score)
    mu = gate_mu(hours, close, sig)
    hs, cs = hours[lo:hi], close[lo:hi]
    years = (hs[-1] - hs[0] + 1) / 8766
    out = {}
    for scen, c in COSTS.items():
        for name in [n for n in POLICIES if n != "C3_ma200d"]:
            r = run_policy(name, hours, close, eff, rv, p, lo, hi, c, mu)
            s = summarise(r, hs, cs, lo, years)
            s.pop("_daily"); s.pop("_days")
            out[f"live/{scen}/{name}"] = {k: s[k] for k in ("final_equity", "net_return", "max_drawdown", "normal_actions",
                                                            "risk_exits", "cycles", "mean_exposure_share", "costs_paid")}
    doc = {"experiment": "E038 (live, descriptive only)", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "live": live.meta, "signal_stability": signal_stability(hours, sig, lo, hi), "results": out,
           "rv_missing": int(np.isnan(live.rv).sum()), "p_missing": int(np.isnan(live.p).sum())}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "low_frequency_live.json").write_text(json.dumps(doc, indent=1, default=_jsonable), encoding="utf-8")
    print(json.dumps({k: v for k, v in doc.items() if k != "results"}, indent=1, default=_jsonable))
    for key, v in out.items():
        print(f"{key:48s} final {v['final_equity']:7.2f} net {v['net_return']:+.2%} actions {v['normal_actions']:3d} "
              f"cycles {v['cycles']:3d} exposure {v['mean_exposure_share']:.0%} costs {v['costs_paid']:.2f}")
    return 0


def load_development_light() -> Inputs:
    """The replay rows only (no move-size fit): the history the live run's point-in-time selectors carry over."""
    _, _, rows, _ = _registered_replay()
    hours = hours_of(pd.DatetimeIndex([pd.Timestamp(r["as_of"]) for r in rows]))
    return Inputs(hours, np.array([r["close"] for r in rows]),
                  np.array([{"BUY": 1, "HOLD": 0, "SELL": -1}[r["signal"]] for r in rows], dtype=np.int8),
                  np.array([r["overall_score"] for r in rows]), np.full(len(rows), np.nan), np.full(len(rows), np.nan), 0, {})
