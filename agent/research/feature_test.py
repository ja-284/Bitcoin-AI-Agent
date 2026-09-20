"""
Generic, fit-free test of a feature group against forward returns (Phase 8).

For every feature and horizon, in exploration and validation separately, with
block-bootstrap intervals:
  direction  Spearman(feature, forward return)
  magnitude  Spearman(feature, |forward return|)
Verdicts follow the pre-registered rules in the experiment record: both periods, same
sign, interval excluding zero (and |rho| >= MAGNITUDE_FLOOR for magnitude). Decile
tables (exploration only) show the shape; per-year signs show stability. Nothing is
fitted and no threshold is chosen by looking at outcomes.

    python -m agent.research.feature_test --experiment E003 --group volatility
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.diagnose import _spearman_stat, spearman
from agent.research.evaluate import HORIZONS, N_BOOT
from agent.research.features import REGIME_FEATURES, RESERVED_PREFIXES, VOLATILITY_FEATURES, all_features
from agent.research.history import load_bars
from agent.research.labels import forward_returns
from agent.research.metrics import block_bootstrap
from agent.research.periods import HOLDOUT, period_of
from agent.research.regimes import trend_regime
from agent.research.replay import replay_cached
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

MAGNITUDE_FLOOR = 0.10
TRIPWIRE_RHO = 0.5  # no honest candle-derived feature correlates this strongly with the future; stop and investigate
GROUPS = {"volatility": VOLATILITY_FEATURES, "regime": REGIME_FEATURES}


class SuspiciousResultError(RuntimeError):
    """A result too good to be true. The brief's rule: investigate before believing."""


def check_feature_names(feature_names: list[str], frame_columns) -> None:
    for name in feature_names:
        if name.startswith(RESERVED_PREFIXES):
            raise ValueError(f"feature {name!r} uses a reserved target prefix {RESERVED_PREFIXES}; rename it")
        if name in frame_columns:
            raise ValueError(f"feature {name!r} collides with an existing column of the replay frame")


def _corr_with_ci(x: np.ndarray, y: np.ndarray, block: int, seed: int) -> dict:
    m = ~np.isnan(x) & ~np.isnan(y)
    if m.sum() < block * 2:
        return {"n": int(m.sum()), "point": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    rho, lo, hi = block_bootstrap(np.column_stack([x[m], y[m]]), _spearman_stat, block=block, n_boot=N_BOOT, seed=seed)
    return {"n": int(m.sum()), "point": rho, "ci_low": lo, "ci_high": hi}


def _verdict(e: dict, v: dict, floor: float = 0.0) -> str:
    if any(np.isnan(d["point"]) for d in (e, v)):
        return "insufficient data"
    same_sign = np.sign(e["point"]) == np.sign(v["point"]) and e["point"] != 0
    excl = (e["ci_low"] > 0 and v["ci_low"] > 0) or (e["ci_high"] < 0 and v["ci_high"] < 0)
    big = abs(e["point"]) >= floor and abs(v["point"]) >= floor
    if same_sign and excl and big:
        return "information (positive)" if e["point"] > 0 else "information (negative)"
    if same_sign and excl:
        return "consistent but below size floor"
    return "no evidence"


def run(experiment: str, group: str) -> Path:
    feature_names = GROUPS[group]
    bars, quality, snapshot = load_bars(end=HOLDOUT.start)
    feats = all_features(bars)
    rows = replay_cached(bars, snapshot)
    df = pd.DataFrame(rows)
    df["as_of"] = pd.to_datetime(df["as_of"])
    df = df.set_index("as_of")
    df["period"] = [period_of(t.to_pydatetime()) for t in df.index]
    df["year"] = df.index.year
    df["trend_regime"] = trend_regime(rows)
    check_feature_names(feature_names, df.columns)
    for col in feature_names:
        df[col] = feats[col].reindex(df.index).to_numpy()
    for h in HORIZONS:
        df[f"fwd_{h}h"] = forward_returns(bars, h).reindex(df.index).to_numpy()

    periods = {"exploration": (df["period"] == "exploration").to_numpy(), "validation": (df["period"] == "validation").to_numpy()}
    results: dict = {
        "experiment": experiment, "group": group, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "scoring_version": SCORING_VERSION, "snapshot": snapshot.name,
        "hours": len(df), "magnitude_floor": MAGNITUDE_FLOOR, "features": {}, "interaction": {},
        "feature_availability": {c: float(df[c].notna().mean()) for c in feature_names},
        "feature_correlation_exploration": df.loc[periods["exploration"], feature_names].corr(method="spearman").round(3).to_dict(),
    }

    for col in feature_names:
        x = df[col].to_numpy(dtype=float)
        entry: dict = {}
        for h in HORIZONS:
            ret = df[f"fwd_{h}h"].to_numpy(dtype=float)
            block = max(48, 2 * h)
            hz: dict = {"direction": {}, "magnitude": {}}
            for pname, pmask in periods.items():
                xm, rm = np.where(pmask, x, np.nan), np.where(pmask, ret, np.nan)
                hz["direction"][pname] = _corr_with_ci(xm, rm, block, seed=21)
                hz["magnitude"][pname] = _corr_with_ci(xm, np.abs(rm), block, seed=22)
                rho = hz["direction"][pname]["point"]
                if not np.isnan(rho) and abs(rho) > TRIPWIRE_RHO:
                    raise SuspiciousResultError(
                        f"{col} at {h}h ({pname}): direction rho={rho:+.3f} exceeds {TRIPWIRE_RHO}. "
                        "This is not credible for a past-only feature -- check for leakage or a column mix-up."
                    )
            hz["direction"]["verdict"] = _verdict(hz["direction"]["exploration"], hz["direction"]["validation"])
            hz["magnitude"]["verdict"] = _verdict(hz["magnitude"]["exploration"], hz["magnitude"]["validation"], MAGNITUDE_FLOOR)
            m = periods["exploration"] & ~np.isnan(x) & ~np.isnan(ret)
            if m.sum() > 1000:
                deciles = pd.qcut(pd.Series(x[m]).rank(method="first"), 10, labels=False).to_numpy()
                hz["decile_mean_return_exploration"] = [float(np.mean(ret[m][deciles == d])) for d in range(10)]
                hz["decile_mean_abs_return_exploration"] = [float(np.mean(np.abs(ret[m])[deciles == d])) for d in range(10)]
            hz["direction_by_year"] = {}
            for year in sorted(df["year"].unique()):
                ym = (df["year"].to_numpy() == year) & ~np.isnan(x) & ~np.isnan(ret)
                if ym.sum() > 500:
                    hz["direction_by_year"][int(year)] = spearman(x[ym], ret[ym])
            entry[f"{h}h"] = hz
        results["features"][col] = entry

    if group == "volatility":
        # Does the weak 1h mean reversion (E002) depend on how volatile the market is?
        rv = df["rv_24"].to_numpy(dtype=float)
        expl_rv = rv[periods["exploration"] & ~np.isnan(rv)]
        lo_cut, hi_cut = np.percentile(expl_rv, [33.3, 66.7])
        results["interaction"]["rv_24_tercile_cuts_from_exploration"] = [float(lo_cut), float(hi_cut)]
        ret1 = df["fwd_1h"].to_numpy(dtype=float)
        for cat in ("momentum", "volume"):
            s = df[f"{cat}_score"].to_numpy(dtype=float)
            results["interaction"][f"{cat}_1h_by_vol_tercile"] = {}
            for pname, pmask in periods.items():
                per = {}
                for name, tm in (("low", rv <= lo_cut), ("mid", (rv > lo_cut) & (rv <= hi_cut)), ("high", rv > hi_cut)):
                    m = pmask & tm & ~np.isnan(ret1) & ~np.isnan(rv)
                    per[name] = {"n": int(m.sum()), "spearman": spearman(s[m], ret1[m]) if m.sum() > 500 else float("nan")}
                results["interaction"][f"{cat}_1h_by_vol_tercile"][pname] = per

    if group == "regime":
        # Mean forward return by 30-day trend regime (descriptive): does the regime itself lean one way?
        for h in (24, 168):
            ret = df[f"fwd_{h}h"].to_numpy(dtype=float)
            results["interaction"][f"mean_return_{h}h_by_trend_regime"] = {}
            for pname, pmask in periods.items():
                per = {}
                for reg in ("uptrend", "sideways", "downtrend"):
                    m = pmask & (df["trend_regime"].to_numpy() == reg) & ~np.isnan(ret)
                    per[reg] = {"n": int(m.sum()), "mean_return": float(ret[m].mean()) if m.sum() else float("nan")}
                results["interaction"][f"mean_return_{h}h_by_trend_regime"][pname] = per

    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(render(results), encoding="utf-8")
    return out_dir


def _ci(d: dict) -> str:
    if np.isnan(d["point"]):
        return "n/a"
    return f"{d['point']:+.3f} [{d['ci_low']:+.3f}, {d['ci_high']:+.3f}]"


def render(res: dict) -> str:
    L = [f"# {res['experiment']} — feature group: {res['group']}", "",
         f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · {res['hours']} hours · fit-free · magnitude floor |ρ| ≥ {res['magnitude_floor']}", "",
         "Availability (share of hours with a value): " + ", ".join(f"{k}: {v:.2f}" for k, v in res["feature_availability"].items()), "",
         "## Direction: Spearman(feature, forward return)", "",
         "| feature | horizon | exploration | validation | verdict |", "|---|---|---|---|---|"]
    for col, entry in res["features"].items():
        for h in HORIZONS:
            d = entry[f"{h}h"]["direction"]
            L.append(f"| {col} | {h}h | {_ci(d['exploration'])} | {_ci(d['validation'])} | {d['verdict']} |")
    L += ["", "## Magnitude: Spearman(feature, |forward return|)", "", "| feature | horizon | exploration | validation | verdict |", "|---|---|---|---|---|"]
    for col, entry in res["features"].items():
        for h in HORIZONS:
            d = entry[f"{h}h"]["magnitude"]
            L.append(f"| {col} | {h}h | {_ci(d['exploration'])} | {_ci(d['validation'])} | {d['verdict']} |")
    L += ["", "## Shape at 24h (exploration): mean |return| by feature decile (1 = lowest feature value)", ""]
    for col, entry in res["features"].items():
        dec = entry["24h"].get("decile_mean_abs_return_exploration")
        if dec:
            L.append(f"- {col}: " + " ".join(f"{v * 100:.2f}" for v in dec))
    L += ["", "## Direction by year at 24h (Spearman point estimates)", ""]
    for col, entry in res["features"].items():
        yrs = entry["24h"]["direction_by_year"]
        L.append(f"- {col}: " + " · ".join(f"{y}: {v:+.3f}" for y, v in yrs.items()))
    if res["interaction"]:
        L += ["", "## Interactions / conditioning", "", "```", json.dumps(res["interaction"], indent=1, default=str), "```"]
    L += ["", "## Feature correlation (Spearman, exploration)", ""]
    corr = res["feature_correlation_exploration"]
    names = list(corr)
    L.append("| | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    for a in names:
        L.append(f"| {a} | " + " | ".join(f"{corr[a][b]:+.2f}" for b in names) + " |")
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--group", required=True, choices=list(GROUPS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run(args.experiment, args.group)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print((out / "summary.md").read_text(encoding="utf-8"))
