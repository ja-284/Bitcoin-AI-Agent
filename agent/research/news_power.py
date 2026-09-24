"""
E025 -- how many live hours does the news evaluation need before it can say anything? (planning)

    python -m agent.research.news_power --experiment E025

Roadmap 8.6 / J re-open the question "does the news score carry information?" once 500 live hours
with a usable news score exist. That number was set without a power analysis, and the news score is
unusually persistent (each story stays in the 24-hour window and is re-scored ~19 times). This asks,
before anyone looks at news against outcomes: for N usable hours, what is the smallest correlation
between the news score and the forward return that the planned test could detect?

It reads the NEWS SCORE SERIES ONLY. No return, no outcome, no join to prediction_outcomes -- so
the eventual test stays clean (a test enforces this by reading this module's SQL). It fits nothing
and decides nothing about the live system.

Method, two independent routes that must agree:
  1. Analytic (Bartlett): under no relationship, the variance of a correlation between two
     autocorrelated series is (1/n) * sum_k rho_x(k) * rho_y(k). Hourly returns are close to
     serially uncorrelated, but an h-hour forward return overlaps its neighbours: rho_y(k) =
     max(0, 1 - |k|/h). So the variance inflation is VIF(h) = 1 + 2 * sum_{k=1..h-1} rho_x(k)(1 - k/h),
     the effective sample n/VIF, and the minimum detectable correlation (two-sided 5%, power 80%)
     (1.960 + 0.842) / sqrt(n / VIF).
  2. Simulation of the PLANNED test itself: an AR(1) news series matched to the live lag-1
     autocorrelation, heavy-tailed hourly returns (Student t, 4 df) with a planted correlation, the
     h-hour forward sums, and the 95% interval of Spearman's rho from a 48-hour circular block
     bootstrap -- the procedure every live evaluation in this project uses. Reports how often the
     interval excludes zero: under no effect (false positives) and under planted effects (power).
"""

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

from agent.research.metrics import block_bootstrap
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

Z_ALPHA, Z_POWER = 1.959964, 0.841621   # two-sided 5%, power 80%
HORIZONS = (1, 6, 24)
N_GRID = (500, 1000, 2000, 3000, 5000, 10000)
PLAUSIBLE_RHO = 0.05   # the strongest directional structure this programme has found: |rho| 0.05-0.08 (E008, E015)
BLOCK = 48
# First run (2026-09-24 17:05 UTC) used 200 records x 200 resamples and showed 10-11.5% false positives at
# 500 hours; a precision re-check at the registered 500 resamples gave 7.3% +- 2.1 (600 records) at 500 h and
# 4.3% / 4.0% at 2,000 / 5,000 h -- the first figures were mostly Monte-Carlo noise. The recorded run uses:
SIM = {"reps": 400, "boot": 500, "seed": 25}

NEWS_SQL = """
    SELECT as_of,
           (SELECT (cs->>'score')::float FROM jsonb_array_elements(category_scores) cs
            WHERE cs->>'name' = 'news' AND (cs->>'weight')::float > 0)
    FROM predictions
    WHERE pipeline_version = %s AND run_meta->>'news_error' IS NULL
    ORDER BY as_of
"""


def news_series() -> list[tuple[datetime, float]]:
    """The live news score of every hour that has one. Reads the predictions table, never outcomes."""
    from agent.database.db import get_connection

    with get_connection() as c, c.cursor() as cur:
        cur.execute(NEWS_SQL, (PIPELINE_VERSION,))
        return [(t, float(s)) for t, s in cur.fetchall() if s is not None]


def segments(rows: list[tuple[datetime, float]]) -> list[np.ndarray]:
    """Contiguous hourly runs -- an autocorrelation must never pair hours across a gap."""
    out, cur = [], [rows[0][1]] if rows else []
    for (t0, _), (t1, s1) in zip(rows, rows[1:]):
        if (t1 - t0).total_seconds() == 3600:
            cur.append(s1)
        else:
            out.append(np.array(cur))
            cur = [s1]
    if cur:
        out.append(np.array(cur))
    return out


def pooled_acf(segs: list[np.ndarray], max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Autocorrelation pooled over segments (common mean and variance). Returns (acf, pairs per lag)."""
    x = np.concatenate(segs)
    mu, var = x.mean(), x.var()
    acf, pairs = np.full(max_lag + 1, np.nan), np.zeros(max_lag + 1, int)
    for k in range(max_lag + 1):
        a = np.concatenate([s[:len(s) - k] for s in segs if len(s) > k]) if k else x
        b = np.concatenate([s[k:] for s in segs if len(s) > k]) if k else x
        pairs[k] = len(a)
        if len(a) >= 10:
            acf[k] = float(np.mean((a - mu) * (b - mu)) / var)
    return acf, pairs


def vif(acf: np.ndarray, h: int) -> float:
    """Variance inflation of a correlation with an h-hour overlapping forward return (Bartlett)."""
    return 1.0 + 2.0 * sum(acf[k] * (1 - k / h) for k in range(1, h))


def mde(n: float, inflation: float) -> float:
    """Smallest |correlation| detected with 80% power, two-sided 5%."""
    return (Z_ALPHA + Z_POWER) / math.sqrt(n / inflation)


def hours_needed(rho: float, inflation: float) -> int:
    return int(math.ceil(inflation * ((Z_ALPHA + Z_POWER) / rho) ** 2))


def _fast_spearman(a: np.ndarray) -> float:
    rx = np.argsort(np.argsort(a[:, 0]))
    ry = np.argsort(np.argsort(a[:, 1]))
    return float(np.corrcoef(rx, ry)[0, 1])


def simulate(n: int, h: int, rho_1h: float, phi: float, reps: int, boot: int, seed: int) -> float:
    """
    Share of simulated records in which the planned test's interval excludes zero. The planted effect
    is a correlation of `rho_1h` between the news score and the NEXT hour's return; the h-hour target
    is the sum of the next h hourly returns, exactly as a live h-hour outcome is built.
    """
    rng = np.random.default_rng(seed)
    hits = 0
    for r in range(reps):
        m = n + h + 200
        x = lfilter([math.sqrt(1 - phi * phi)], [1.0, -phi], rng.standard_normal(m))  # AR(1), unit variance after burn-in
        noise = rng.standard_t(4, size=m) / math.sqrt(2.0)              # unit variance, heavy tails
        ret = rho_1h * x + math.sqrt(1 - rho_1h ** 2) * noise           # ret[t] = the hour AFTER x[t]
        x, ret = x[200:], ret[200:]
        fwd = np.convolve(ret, np.ones(h), mode="valid")[:n]            # sum of the next h hours
        pairs = np.column_stack([x[:n], fwd])
        _, lo, hi = block_bootstrap(pairs, _fast_spearman, block=BLOCK, n_boot=boot, seed=seed * 1000 + r)
        hits += int(lo > 0 or hi < 0)
    return hits / reps


def run(experiment: str) -> Path:
    rows = news_series()
    segs = segments(rows)
    acf, pairs = pooled_acf(segs, max_lag=47)
    x = np.array([s for _, s in rows])
    trusted = acf.copy()
    trusted[pairs < 30] = np.nan  # too few pairs to estimate
    phi = float(acf[1])
    ar1 = np.array([phi ** k for k in range(48)])
    inflations = {}
    for h in HORIZONS:
        measured = vif(np.nan_to_num(trusted, nan=0.0), h) if not np.isnan(trusted[1:h]).any() else float("nan")
        inflations[h] = {"measured_acf": measured, "ar1_model": vif(ar1, h),
                         "triangular_24h_window": vif(np.array([max(0.0, 1 - k / 24) for k in range(48)]), h)}
    table = {h: {n: {"mde_measured": mde(n, v["measured_acf"]) if not math.isnan(v["measured_acf"]) else None,
                     "mde_ar1": mde(n, v["ar1_model"])} for n in N_GRID} for h, v in inflations.items()}
    need = {h: {"rho_0.05": hours_needed(PLAUSIBLE_RHO, v["ar1_model"]), "rho_0.03": hours_needed(0.03, v["ar1_model"]),
                "rho_0.10": hours_needed(0.10, v["ar1_model"])} for h, v in inflations.items()}
    sim = {}
    cells = [(500, 1, 0.0), (500, 6, 0.0), (500, 24, 0.0), (2000, 24, 0.0),
             (500, 1, 0.05), (2000, 1, 0.05), (3000, 1, 0.05), (500, 1, 0.10), (2000, 1, 0.10),
             (2000, 24, 0.05), (5000, 24, 0.05)]
    for n, h, r in cells:
        rate = simulate(n, h, r, phi, SIM["reps"], SIM["boot"], SIM["seed"])
        sim[f"n={n} h={h} rho={r}"] = rate
        logger.info("simulated n=%d h=%d rho=%.2f -> interval excludes zero in %.1f%%", n, h, r, 100 * rate)
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
           "pipeline_version": PIPELINE_VERSION,
           "news_hours": len(rows), "first_hour": rows[0][0].isoformat(), "last_hour": rows[-1][0].isoformat(),
           "segments": [len(s) for s in segs],
           "score": {"mean": float(x.mean()), "sd": float(x.std()), "min": float(x.min()), "max": float(x.max()),
                     "hours_negative": int((x < 0).sum()), "mean_abs_hourly_change": float(np.mean(np.abs(np.concatenate([np.diff(s) for s in segs if len(s) > 1]))))},
           "acf": {int(k): (None if np.isnan(acf[k]) else float(acf[k])) for k in range(48)},
           "acf_pairs": {int(k): int(pairs[k]) for k in range(48)},
           "ar1_phi": phi, "variance_inflation": inflations, "mde": table, "hours_needed": need,
           "simulation": {"settings": SIM | {"block": BLOCK, "noise": "Student t, 4 df", "news": "AR(1), phi = live lag-1 ACF"},
                          "share_interval_excludes_zero": sim}}
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "news_power.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "news_power.md").write_text(render(res), encoding="utf-8")
    return out_dir / "news_power.md"


def render(r: dict) -> str:
    acf = r["acf"]
    L = ["# E025 — how many live hours does the news evaluation need? (planning)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['news_hours']} usable news hours "
         f"({r['first_hour'][:13]} → {r['last_hour'][:13]}), contiguous segments {r['segments']}.", "",
         "**Reads the news score only — no return or outcome was touched, so the eventual test stays clean.**", "",
         "## The news score is a slow-moving series", "",
         f"Mean {r['score']['mean']:+.3f}, sd {r['score']['sd']:.3f}, range {r['score']['min']:+.3f} to {r['score']['max']:+.3f} "
         f"({r['score']['hours_negative']} negative hours); average change per hour {r['score']['mean_abs_hourly_change']:.3f}.", "",
         "| lag (hours) | 1 | 2 | 3 | 6 | 12 | 18 | 23 |", "|---|---|---|---|---|---|---|---|",
         "| autocorrelation | " + " | ".join("n/a" if acf[k] is None else f"{acf[k]:+.2f}" for k in (1, 2, 3, 6, 12, 18, 23)) + " |",
         "| pairs | " + " | ".join(str(r["acf_pairs"][k]) for k in (1, 2, 3, 6, 12, 18, 23)) + " |", "",
         f"An AR(1) with φ = {r['ar1_phi']:.3f} (the live lag-1 value) reproduces the decay closely enough for planning.", "",
         "## How much each hour is worth", "",
         "| horizon | variance inflation (live ACF) | (AR(1) model) | (24h window model) |", "|---|---|---|---|"]
    for h, v in r["variance_inflation"].items():
        meas = "n/a" if v["measured_acf"] is None or (isinstance(v["measured_acf"], float) and math.isnan(v["measured_acf"])) else f"{v['measured_acf']:.1f}"
        L.append(f"| {h}h | {meas} | {v['ar1_model']:.1f} | {v['triangular_24h_window']:.1f} |")
    L += ["", "Next-hour returns are close to independent from hour to hour, so at 1h the news score's persistence does **not**",
          "reduce the information per hour (inflation 1.0). At 6h and 24h the forward returns overlap, and a persistent predictor",
          "then counts several times over.", "",
          "## Smallest correlation the planned test can detect (80% power, two-sided 5%)", "",
          "| usable news hours | " + " | ".join(f"{h}h" for h in r["mde"]) + " |", "|---|" + "---|" * len(r["mde"])]
    for n in N_GRID:
        L.append(f"| {n:,} | " + " | ".join(f"{r['mde'][h][n]['mde_ar1']:.3f}" for h in r["mde"]) + " |")
    L += ["", "| horizon | hours for ρ = 0.10 | ρ = 0.05 | ρ = 0.03 |", "|---|---|---|---|"]
    for h, v in r["hours_needed"].items():
        L.append(f"| {h}h | {v['rho_0.10']:,} | {v['rho_0.05']:,} | {v['rho_0.03']:,} |")
    L += ["", "## The planned test itself, simulated", "",
          f"{r['simulation']['settings']['reps']} simulated records per cell; 48h circular block bootstrap "
          f"({r['simulation']['settings']['boot']} resamples); heavy-tailed returns. Share of records whose 95% interval excludes zero:", "",
          "| cell | share |", "|---|---|"]
    for k, v in r["simulation"]["share_interval_excludes_zero"].items():
        L.append(f"| {k} | {100 * v:.1f}% |")
    L += ["", "Rows with ρ = 0 are the false-positive rate (should be near 5%); the others are power.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E025")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
