"""
E029 (RESEARCH-ONLY, pre-registered, interim plan task H1): how fast could a simple sequential detector
tell a PERSISTENT calibration offset from noise, and how often would it cry wolf on the move-size model
family's own development record? (research/experiments/E029_drift_detector.json)

    python -m agent.research.drift_detector --experiment E029

Two-sided CUSUM on the residual "stated probability minus outcome". Development data only: this module is
not run on the live or shadow record, is imported by nothing in the live path, and cannot change a
registered checkpoint rule.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

K = 0.025
H_GRID_START, H_GRID_STEP, H_GRID_END = 1.0, 0.5, 100.0
TARGET_ALARMS_PER_1000 = 0.2           # average run length >= 5,000 hours on the calibrated control
CONTROL_SIMS_FOR_H, CONTROL_SIMS_FOR_DELAY, SEED = 20, 5, 29
WINDOW, STEP, CHANGE = 3000, 500, 500
DELTAS = (0.03, 0.05, 0.10, -0.03, -0.05, -0.10)
CLIP = (0.001, 0.999)


def cusum(residuals, k: float, h: float) -> list[tuple[int, int]]:
    """Alarms as (index, direction): +1 over-statement, -1 under-statement. Both sums reset after an alarm."""
    up = down = 0.0
    alarms = []
    for i, r in enumerate(np.asarray(residuals, float).tolist()):
        up = max(0.0, up + r - k)
        down = max(0.0, down - r - k)
        if up > h or down > h:
            alarms.append((i, 1 if up > h else -1))
            up = down = 0.0
    return alarms


def alarms_per_1000(residuals, k: float, h: float) -> float:
    return 1000.0 * len(cusum(residuals, k, h)) / len(residuals)


def choose_h(p, k: float = K, target: float = TARGET_ALARMS_PER_1000, sims: int = CONTROL_SIMS_FOR_H, seed: int = SEED) -> dict:
    """The registered rule: the smallest h on the grid at which a perfectly calibrated control alarms <= target."""
    p = np.asarray(p, float)
    rng = np.random.default_rng(seed)
    controls = [p - (rng.random(len(p)) < p) for _ in range(sims)]     # outcomes drawn from the stated p itself
    h = H_GRID_START
    while h <= H_GRID_END:
        rate = float(np.mean([alarms_per_1000(r, k, h) for r in controls]))
        if rate <= target:
            return {"h": h, "control_alarms_per_1000": rate}
        h += H_GRID_STEP
    raise RuntimeError("no h on the grid meets the target")


def window_delays(p, y, k: float, h: float, delta: float, window: int = WINDOW, step: int = STEP, change: int = CHANGE) -> list[dict]:
    """Inject a persistent offset at `change` of every window (real outcomes kept) and time the detector."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    direction = 1 if delta > 0 else -1
    out = []
    for start in range(0, len(p) - window + 1, step):
        ps = p[start:start + window].copy()
        ps[change:] = np.clip(ps[change:] + delta, *CLIP)
        alarms = cusum(ps - y[start:start + window], k, h)
        hit = next((i for i, d in alarms if i >= change and d == direction), None)
        out.append({"start": start, "pre_change_alarms": sum(1 for i, _ in alarms if i < change),
                    "delay": None if hit is None else hit - change + 1})
    return out


def summarise(windows: list[dict], follow_up: int = WINDOW - CHANGE) -> dict:
    d = np.array([w["delay"] if w["delay"] is not None else np.inf for w in windows], float)
    return {"windows": len(d), "median_delay": float(np.median(d)),
            "detected_within": {str(n): float(np.mean(d <= n)) for n in (250, 500, 1000, 2000, follow_up)},
            "pre_change_alarm_windows": float(np.mean([w["pre_change_alarms"] > 0 for w in windows]))}


def judge(real_rate: float, delay: dict, control_delay: dict) -> dict:
    """The three pre-registered hypotheses, exactly as written. Pure."""
    big, mid = delay["+0.10"], delay["+0.05"]
    h_b = big["median_delay"] <= 500 and mid["detected_within"]["2000"] >= 0.90
    real_m, ctrl_m = mid["median_delay"], control_delay["+0.05"]["median_delay"]
    h_c = bool(np.isfinite(real_m) and np.isfinite(ctrl_m) and abs(real_m / ctrl_m - 1) <= 0.30)
    return {"H_a_false_alarms": bool(real_rate <= 0.4), "H_b_detection": bool(h_b), "H_c_real_like_control": h_c}


def run(experiment: str) -> Path:
    from agent.research.feature_count import FULL, evaluate, prepare

    df, spec, folds = prepare()
    oos = evaluate(df, spec, folds, FULL, {})["predictions"].sort_index()
    p, y = oos["p"].to_numpy(float), oos["y"].to_numpy(float)
    chosen = choose_h(p)
    h = chosen["h"]
    alarms = cusum(p - y, K, h)
    periods = oos["period"].to_numpy()
    by_period = {per: {"hours": int((periods == per).sum()),
                       "alarms": sum(1 for i, _ in alarms if periods[i] == per)} for per in ("exploration", "validation")}
    for v in by_period.values():
        v["alarms_per_1000"] = 1000.0 * v["alarms"] / v["hours"]
    real_rate = 1000.0 * len(alarms) / len(p)

    rng = np.random.default_rng(SEED)
    control_ys = [(rng.random(len(p)) < p).astype(float) for _ in range(CONTROL_SIMS_FOR_DELAY)]
    delay, control_delay = {}, {}
    for delta in DELTAS:
        key = f"{delta:+.2f}"
        delay[key] = summarise(window_delays(p, y, K, h, delta))
        control_delay[key] = summarise([w for yc in control_ys for w in window_delays(p, yc, K, h, delta)])
        logger.info("delta %s: real median %s, control median %s", key, delay[key]["median_delay"], control_delay[key]["median_delay"])

    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(p)), "k": K, "h": h, "control_alarms_per_1000": chosen["control_alarms_per_1000"],
           "real_alarms_per_1000": real_rate, "real_by_period": by_period,
           "real_alarms": [{"at": oos.index[i].isoformat(), "direction": "over" if d > 0 else "under", "period": periods[i]} for i, d in alarms],
           "overall_stated_minus_observed": {per: float(np.mean(p[periods == per] - y[periods == per])) for per in ("exploration", "validation")},
           "delay_real": delay, "delay_control": control_delay}
    res["verdict"] = judge(real_rate, delay, control_delay)
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "drift_detector.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "drift_detector.md").write_text(render(res), encoding="utf-8")
    return out_dir / "drift_detector.md"


def _hours(x: float) -> str:
    return "not within 2,500" if not np.isfinite(x) else f"{x:,.0f}"


def render(r: dict) -> str:
    L = ["# E029 — a sequential calibration-drift detector on the move-size model family (research-only)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['rows']:,} development hours · two-sided CUSUM, k = {r['k']}, "
         f"h = {r['h']} (control: {r['control_alarms_per_1000']:.3f} alarms per 1,000 h) · never run on live data", "",
         "## False alarms on the real record (no injection)", "",
         f"{r['real_alarms_per_1000']:.3f} alarms per 1,000 hours over the whole record "
         f"({len(r['real_alarms'])} alarms); control {r['control_alarms_per_1000']:.3f}.", ""]
    for per, v in r["real_by_period"].items():
        L.append(f"- {per}: {v['alarms']} alarms in {v['hours']:,} h ({v['alarms_per_1000']:.3f} per 1,000 h); "
                 f"overall stated − observed {r['overall_stated_minus_observed'][per]:+.4f}")
    if r["real_alarms"]:
        L += ["", "Alarms: " + ", ".join(f"{a['at'][:10]} ({a['direction']})" for a in r["real_alarms"])]
    L += ["", "## Detection delay after a persistent offset (hours)", "",
          "| offset | real: median | real: within 500 / 2,000 | control: median | control: within 500 / 2,000 |", "|---|---|---|---|---|"]
    for key, d in r["delay_real"].items():
        c = r["delay_control"][key]
        L.append(f"| {key} | {_hours(d['median_delay'])} | {d['detected_within']['500']:.0%} / {d['detected_within']['2000']:.0%} | "
                 f"{_hours(c['median_delay'])} | {c['detected_within']['500']:.0%} / {c['detected_within']['2000']:.0%} |")
    L += ["", f"{r['delay_real']['+0.05']['windows']} windows of {WINDOW:,} h (offset from hour {CHANGE}); control = outcomes "
          f"simulated from the original probabilities ({CONTROL_SIMS_FOR_DELAY} simulations).", "",
          "## Pre-registered hypotheses", ""] + [f"- {k}: **{'HOLDS' if ok else 'FAILS'}**" for k, ok in r["verdict"].items()]
    L += ["", "*Research-only and hypothesis-generating. Not wired to anything; the registered checkpoints remain the only "
          "judgement of the live record, and move_size_1h_v1 is unchanged.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E029")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
