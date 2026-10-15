"""
The news cost-and-value review (master plan 3D, 2026-10-15), read-only and reproducible:

    python tools/news_cost_value.py > research/monitoring/news_cost_value_<date>.json

Measures, from the live record only, what the news call costs (the API's own token counts priced at the dated list
prices in agent/research/weekly_report.py), how reliable it is, and how often it changes the stored BUY/HOLD/SELL
signal (recombined without news exactly as the parity check does). It reads NO outcome: whether news predicts returns
is E030's registered question, and any new outcome test here would be unregistered. Read-only transaction; the owner
connection in the local .env. Changes nothing.
"""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np

from agent.decision.decision import decide_signal
from agent.database.db import get_connection
from agent.research.parity import overall_without_news
from agent.research.weekly_report import AI_PRICES_USD_PER_MTOK, AI_PRICES_AS_OF, ai_cost

with get_connection() as c:
    c.read_only = True
    cur = c.cursor()
    cur.execute("""SELECT as_of, pipeline_version, signal, overall_score, category_scores, run_meta, ai_model_news,
                          COALESCE(jsonb_array_length(news_items), 0), fetched_at, cutoff_at
                   FROM predictions WHERE pipeline_version = '0.2.0' ORDER BY as_of""")
    cols = ["as_of", "pipeline_version", "signal", "overall_score", "category_scores", "run_meta", "ai_model_news",
            "news_items_n", "fetched_at", "cutoff_at"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
now = datetime.now(timezone.utc)
out = {"generated_at": now.isoformat(), "rows_pipeline_0_2_0": len(rows), "first": rows[0]["as_of"].isoformat(),
       "last": rows[-1]["as_of"].isoformat(), "prices": {"usd_per_mtok": AI_PRICES_USD_PER_MTOK, "as_of": AI_PRICES_AS_OF}}

# 1. cost, by step, from the API's own token counts (recorded since 2026-09-23)
def step_cost(u):
    p = AI_PRICES_USD_PER_MTOK.get(u.get("model"))
    if p is None or "input_tokens" not in u:
        return None
    return (u["input_tokens"] * p[0] + u["output_tokens"] * p[1]) / 1e6

for label, days in (("last_7_days", 7), ("last_30_days", 30)):
    since = now - timedelta(days=days)
    win = [r for r in rows if r["as_of"] >= since and (r["run_meta"] or {}).get("ai_usage")]
    per_step = {}
    for step in ("news", "explanation"):
        costs = [step_cost(r["run_meta"]["ai_usage"][step]) for r in win if step in r["run_meta"]["ai_usage"]]
        costs = [x for x in costs if x is not None]
        tin = [r["run_meta"]["ai_usage"][step]["input_tokens"] for r in win if step in r["run_meta"]["ai_usage"]
               and "input_tokens" in r["run_meta"]["ai_usage"][step]]
        tout = [r["run_meta"]["ai_usage"][step]["output_tokens"] for r in win if step in r["run_meta"]["ai_usage"]
                and "output_tokens" in r["run_meta"]["ai_usage"][step]]
        per_step[step] = {"calls": len(costs), "mean_cost_usd": float(np.mean(costs)) if costs else None,
                          "mean_input_tokens": float(np.mean(tin)) if tin else None, "mean_output_tokens": float(np.mean(tout)) if tout else None,
                          "projected_30_days_usd": float(np.mean(costs)) * 24 * 30 if costs else None,
                          "models": dict(Counter(r["run_meta"]["ai_usage"][step].get("model") for r in win if step in r["run_meta"]["ai_usage"]))}
    total = sum(v["projected_30_days_usd"] or 0 for v in per_step.values())
    out[f"cost_{label}"] = {"runs": len(win), "by_step": per_step, "projected_30_days_usd_total": total,
                            "news_share_of_cost": (per_step["news"]["projected_30_days_usd"] or 0) / total if total else None}
out["cost_cross_check_weekly_report_function_7d"] = {k: ai_cost(rows, now - timedelta(days=7))[k]
                                                     for k in ("mean_cost_per_run_usd", "projected_30_days_usd", "runs_priced")}

# 2. reliability of the news step
since30 = now - timedelta(days=30)
def news_err(r):
    m = r["run_meta"] or {}
    return m.get("news_error_type") or ("error" if m.get("news_error") else None)
out["reliability"] = {
    "news_errors_all_time": dict(Counter(news_err(r) for r in rows if news_err(r))),
    "news_errors_last_30_days": dict(Counter(news_err(r) for r in rows if r["as_of"] >= since30 and news_err(r))),
    "explanation_errors_all_time": sum(1 for r in rows if (r["run_meta"] or {}).get("explanation_error")),
    "hours_with_a_failed_feed_all_time": sum(1 for r in rows if ((r["run_meta"] or {}).get("news") or {}).get("sources_failed")),
    "hours_with_zero_news_items_used": sum(1 for r in rows if r["news_items_n"] == 0),
    "mean_items_used": float(np.mean([r["news_items_n"] for r in rows])),
    "items_used_last_30_days_median": float(np.median([r["news_items_n"] for r in rows if r["as_of"] >= since30])),
    "ai_call_latency": "not recorded per call; only the whole run's lag after the cutoff (below)",
    "run_lag_after_cutoff_seconds_last_30_days": (lambda v: {"median": float(np.median(v)), "p95": float(np.percentile(v, 95)), "max": float(max(v))})(
        [float((r["run_meta"] or {}).get("lag_seconds_after_cutoff")) for r in rows if r["as_of"] >= since30 and (r["run_meta"] or {}).get("lag_seconds_after_cutoff") is not None]),
}

# 3. how often news changes the stored signal (recombined without news, exactly as the parity check does)
with_news = [r for r in rows if any(cs["name"] == "news" and float(cs["weight"]) > 0 for cs in r["category_scores"])]
changes = Counter()
shift = []
for r in with_news:
    without = overall_without_news(r["category_scores"])
    shift.append(r["overall_score"] - without)
    sig_without = decide_signal(without)
    if sig_without != r["signal"]:
        changes[f"{sig_without}->{r['signal']}"] += 1
news_scores = [float(cs["score"]) for r in with_news for cs in r["category_scores"] if cs["name"] == "news"]
out["influence"] = {"hours_with_news_weight": len(with_news), "signals_changed_by_news": sum(changes.values()),
                    "share_changed": sum(changes.values()) / len(with_news), "changes": dict(changes),
                    "overall_score_shift": {"mean": float(np.mean(shift)), "mean_abs": float(np.mean(np.abs(shift))),
                                            "max_abs": float(np.max(np.abs(shift)))},
                    "news_score": {"mean": float(np.mean(news_scores)), "sd": float(np.std(news_scores, ddof=1)),
                                   "share_negative": float(np.mean(np.array(news_scores) < 0))},
                    "signal_mix_with_news": dict(Counter(r["signal"] for r in with_news)),
                    "signal_mix_without_news": dict(Counter(decide_signal(overall_without_news(r["category_scores"])) for r in with_news))}
print(json.dumps(out, indent=1, default=str))
