"""
E030 -- the news first look (roadmap 8.6), exactly as registered: E025's design (2026-09-24) with the execution
details fixed in E030's registration commit (014cdef) before any news-versus-outcome figure existed.

    python -m agent.research.news_first_look --experiment E030

Spearman rho of the hour's stored news category score with the stored forward return, on EXACTLY the first 500
usable news hours (a fixed prefix): 1h primary, 6h and 24h descriptive. 95% interval from a 48h circular block
bootstrap, 500 resamples, seed 17 (the checkpoint's own functions). DESCRIPTIVE, NO VERDICT: E025 showed that at
500 hours only |rho| >= 0.125 is detectable at 1h and the interval is liberal (about 9% false positives).

Reads the predictions and their outcomes (read-only transaction); fits nothing, selects nothing, changes nothing in
the live system. Writes research/results/E030/news_first_look.md/.json once, and refuses to overwrite them.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.diagnose import spearman
from agent.research.metrics import block_bootstrap
from agent.research.news_power import NEWS_SQL
from agent.version import PIPELINE_VERSION

FIRST_LOOK_HOURS = 500        # E025: the first look, at 500 usable news hours
VERDICT_HOURS = 3140          # E025: the registered verdict point
HORIZONS = (1, 6, 24)         # 1h primary; 6h and 24h descriptive only
PRIMARY = 1
BLOCK, N_BOOT, SEED = 48, 500, 17
MIN_DETECTABLE_RHO_AT_500 = {1: 0.125, 6: 0.274, 24: 0.416}  # E025, 80% power, two-sided 5%
OUT_DIR = Path("research") / "results" / "E030"
OUTCOME_SQL = """
    SELECT p.as_of, o.horizon_hours, o.pct_change_from_prediction
    FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id
    WHERE o.status = 'ok' AND o.horizon_hours = ANY(%s) AND p.as_of = ANY(%s)
"""


def first_look(news: list[tuple[datetime, float]], returns: dict[tuple[datetime, int], float]) -> dict:
    """
    news: (as_of, news score) of every usable hour, in time order. returns: (as_of, horizon) -> forward return,
    'ok' outcomes only. Uses exactly the first FIRST_LOOK_HOURS usable hours; later ones are ignored.
    """
    if len(news) < FIRST_LOOK_HOURS:
        raise ValueError(f"only {len(news)} usable news hours; the first look is registered at {FIRST_LOOK_HOURS}")
    if any(b[0] <= a[0] for a, b in zip(news, news[1:])):
        raise ValueError("the news hours are not in strictly increasing time order")
    prefix = news[:FIRST_LOOK_HOURS]
    scores = np.array([s for _, s in prefix], float)
    out = {"hours": {"first": prefix[0][0].isoformat(), "last": prefix[-1][0].isoformat(), "n": len(prefix),
                     "usable_available": len(news)},
           "news_score": {"mean": float(scores.mean()), "sd": float(scores.std(ddof=1)), "min": float(scores.min()),
                          "max": float(scores.max()), "hours_negative": int((scores < 0).sum())},
           "horizons": {}}
    for h in HORIZONS:
        pairs = [(s, returns[(t, h)]) for t, s in prefix if (t, h) in returns]
        stacked = np.array(pairs, float)
        rho, lo, hi = block_bootstrap(stacked, lambda a: spearman(a[:, 0], a[:, 1]), block=BLOCK, n_boot=N_BOOT, seed=SEED)
        out["horizons"][f"{h}h"] = {
            "role": "primary" if h == PRIMARY else "descriptive only",
            "n": len(pairs), "left_out_without_ok_outcome": len(prefix) - len(pairs),
            "rho": float(rho), "ci95": [float(lo), float(hi)], "interval_excludes_zero": bool(lo > 0 or hi < 0),
            "min_detectable_rho_80pct_power_at_500h": MIN_DETECTABLE_RHO_AT_500[h],
        }
    out["verdict"] = None
    return out


def _md(r: dict, now: datetime) -> str:
    hrs, ns = r["hours"], r["news_score"]
    L = ["# E030 — news first look (roadmap 8.6)", "",
         f"Written {now:%Y-%m-%d %H:%M} UTC by `python -m agent.research.news_first_look`. Hours "
         f"{hrs['first'][:16]} → {hrs['last'][:16]} UTC — exactly the first {hrs['n']} usable news hours "
         f"({hrs['usable_available']} available). Intervals: 48h circular block bootstrap, {N_BOOT} resamples, seed {SEED}.", "",
         "**Registered (E025, 2026-09-24; execution details E030, `014cdef`, before any news-versus-outcome figure "
         "existed): a first look, descriptive, NO verdict.** The verdict point is "
         f"{VERDICT_HOURS:,} usable hours.", "",
         "**What this size can see (E025):** only |ρ| ≥ 0.125 at 1h (0.27 at 6h, 0.42 at 24h) with 80% power. That is far "
         "above anything this programme has found (|ρ| 0.05–0.08). The interval is also liberal here: under no effect it "
         "excludes zero about 9% of the time instead of 5%. A null here is not evidence of no effect, and an interval "
         "that excludes zero is not evidence of one.", "",
         f"News score in these hours: mean {ns['mean']:+.3f}, sd {ns['sd']:.3f}, range {ns['min']:+.3f} to "
         f"{ns['max']:+.3f}; {ns['hours_negative']} hours negative.", "",
         "| horizon | role | n | Spearman ρ(news score, forward return) | 95% interval | excludes 0? | smallest ρ this size can detect (E025) |",
         "|---|---|---|---|---|---|---|"]
    for k, v in r["horizons"].items():
        L.append(f"| {k} | {v['role']} | {v['n']} | {v['rho']:+.3f} | [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] | "
                 f"{'yes' if v['interval_excludes_zero'] else 'no'} | {v['min_detectable_rho_80pct_power_at_500h']:.3f} |")
    left = {k: v["left_out_without_ok_outcome"] for k, v in r["horizons"].items() if v["left_out_without_ok_outcome"]}
    L += ["", f"Hours left out for lack of an 'ok' outcome: {left if left else 'none'}.", "",
          "**No verdict, by registration.** No news weight, model parameter, feature, threshold, prompt or live signal "
          "changes because of this look."]
    return "\n".join(L) + "\n"


def _read() -> tuple[list[tuple[datetime, float]], dict[tuple[datetime, int], float]]:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(NEWS_SQL, (PIPELINE_VERSION,))
            news = [(t, float(s)) for t, s in cur.fetchall() if s is not None]
            first = [t for t, _ in news[:FIRST_LOOK_HOURS]]
            cur.execute(OUTCOME_SQL, (list(HORIZONS), first))  # only the prefix's outcomes are ever read
            returns = {(t, int(h)): float(r) for t, h, r in cur.fetchall()}
    return news, returns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True, choices=["E030"])
    parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    md, js = OUT_DIR / "news_first_look.md", OUT_DIR / "news_first_look.json"
    if md.exists() or js.exists():
        print(f"E030 already computed: {md} (written once; never rewritten)")
        return 0
    news, returns = _read()
    now = datetime.now(timezone.utc)
    result = first_look(news, returns)
    result["computed_at"] = now.isoformat()
    result["registration"] = "E025 adopted_design_for_8_6 (2026-09-24); E030 execution details (commit 014cdef)"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    md.write_text(_md(result, now), encoding="utf-8")
    print(md.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
