"""
The backend's outward-facing state, version 1 (master plan sections 39 and 52).

    python -m agent.api.state            # print the current state as JSON
    python -m agent.api.state --pretty

This is the single place that decides what the backend SAYS about itself. A frontend reads
this structure and nothing else; it never recomputes research logic, and it never has to know
which numbers are trustworthy, because every number carries that judgement with it.

The design rule, which is the entire point of the module:

    A number that is not a validated probability must not be able to look like one.

So each quantity arrives as an object with `value`, `kind`, `is_probability` and a `meaning`
sentence written for a reader, not for a developer. The signal carries its own evidence status,
which currently says in plain words that it has no demonstrated predictive value (E001, E017).
A UI that simply renders what it is given cannot overstate the evidence; a UI that ignores
these fields is choosing to, and that is visible in review.

Nothing here computes anything. It reads committed research conclusions and the database.
It never writes, so it cannot affect the live record.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.database.db import get_connection
from agent.news.rss_source import FEEDS
from agent.healthcheck import check as staleness_check
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1"
# Staleness is NOT defined here. agent/healthcheck.check owns that definition -- hours since the
# reference candle CLOSED, not since it opened -- and the self-check, the watchdog and this
# contract all call it, so they cannot drift into disagreeing about whether the system is healthy.
STALE_AFTER_HOURS = 2.0
news_sources_total = len(FEEDS)

# Research conclusions, quoted from the committed experiment records. Changing a conclusion
# here without an experiment to back it would be a silent methodology change, so each one
# names the experiments it comes from.
SIGNAL_EVIDENCE = {
    "status": "no_demonstrated_predictive_value",
    "headline": "This signal has not been shown to predict anything.",
    "detail": ("Tested over 68,619 historical hours at five time horizons against simple baselines, "
               "the BUY/HOLD/SELL signal showed no evidence of predictive information at any horizon, "
               "under both scoring 0.1.0 and the corrected scoring 0.2.0. It is recorded and measured "
               "so that it can be improved; it is not advice and must never be presented as a forecast."),
    "experiments": ["E001", "E002", "E011", "E017"],
}
CONFIDENCE_MEANING = ("A consistency and completeness estimate, not a probability. It rises when the "
                      "independent categories agree with each other and when all the data was available. "
                      "It has been checked against real outcomes and carries no information about whether "
                      "the signal turns out to be right (E001, E017).")
MOVE_SIZE_MEANING = ("The estimated chance that Bitcoin's price moves more than 0.25% in either direction "
                     "over the next hour. This says nothing about the DIRECTION of the move. It is "
                     "calibrated: across validation data, hours given about this chance did move that much "
                     "about this often (E012, E013).")
MOVE_SIZE_STATUS = {
    "status": "research_shadow_only",
    "detail": ("This probability runs alongside the live system in its own record and has never influenced "
               "the BUY/HOLD/SELL signal. Its calibration was measured on 2024-2025 validation data; its "
               "prospective record began on 2026-09-21 and is judged at 500, 2,000 and 5,000 hours. The "
               "final sealed holdout has not been opened."),
    "experiments": ["E012", "E013", "E018", "E019", "E020", "E021"],
}
LIMITATIONS = [
    "The BUY/HOLD/SELL signal has no demonstrated predictive value (E001, E017).",
    "The confidence number is a heuristic about agreement and completeness, not a probability.",
    "Only the move-size probability is calibrated, and only on validation data so far.",
    ("Most of the move-size model's skill is simply knowing how volatile the market is right now, which a "
     "plain average of recent hours also captures; its own added value is the smaller part (E019, E021)."),
    ("The question itself gets easier and harder with the market: across years, the share of hours with a "
     "move over 0.25% has ranged from 34% to 68% (E021)."),
    "Nothing here is a direction forecast: no directional edge was found in the free data (E011).",
    "This system does not trade, hold funds, or place orders of any kind, and is not investment advice.",
]


@dataclass(frozen=True)
class Quantity:
    """A number plus the honest description of what kind of number it is."""

    value: float | None
    kind: str           # "heuristic" | "calibrated_probability" | "score" | "price" | "return"
    is_probability: bool
    meaning: str

    def as_dict(self) -> dict:
        return {"value": self.value, "kind": self.kind, "is_probability": self.is_probability,
                "meaning": self.meaning}


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(timezone.utc).isoformat()


def _latest_prediction(cur) -> dict | None:
    cur.execute("""
        SELECT as_of, cutoff_at, fetched_at, close_price, price_source, price_is_synthetic,
               overall_score, signal, agreement_score, completeness_score, overall_confidence,
               pipeline_version, scoring_version, ai_model_news, ai_model_explanation,
               explanation, category_scores, news_items, run_meta
        FROM predictions ORDER BY as_of DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d.name for d in cur.description]
    return dict(zip(cols, row))


def _latest_shadow(cur) -> dict | None:
    cur.execute("""
        SELECT as_of, cutoff_at, model_version, pipeline_version, p_calibrated, threshold,
               horizon_hours, status, status_reason
        FROM shadow_move_size ORDER BY as_of DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d.name for d in cur.description], row))


def _counts(cur, now: datetime) -> dict:
    cur.execute("SELECT count(*), min(as_of), max(as_of) FROM predictions")
    n, first, last = cur.fetchone()
    cur.execute("""
        SELECT count(*) FROM generate_series(
            date_trunc('hour', %s::timestamptz) - interval '48 hours',
            date_trunc('hour', %s::timestamptz) - interval '2 hours',
            interval '1 hour') g(h)
        WHERE NOT EXISTS (SELECT 1 FROM predictions p WHERE p.as_of = g.h)
    """, (now, now))
    missing = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM shadow_move_size")
    shadow_rows = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM shadow_run_errors WHERE occurred_at > %s", (now - timedelta(hours=24),))
    shadow_errors = cur.fetchone()[0]
    return {"predictions": n, "first_prediction": _iso(first), "latest_prediction": _iso(last),
            "missing_hours_last_48h": missing, "shadow_rows": shadow_rows,
            "shadow_errors_last_24h": shadow_errors}


def _recent_outcomes(cur, limit: int = 24) -> dict:
    """Raw realised returns only. Whether a signal was 'right' is an analysis question."""
    cur.execute("""
        SELECT o.horizon_hours, count(*) FILTER (WHERE o.status = 'ok'),
               count(*) FILTER (WHERE o.status = 'unavailable')
        FROM prediction_outcomes o GROUP BY 1 ORDER BY 1
    """)
    by_horizon = [{"horizon_hours": h, "graded": ok, "unavailable": un} for h, ok, un in cur.fetchall()]
    cur.execute("""
        SELECT p.as_of, p.signal, o.pct_change_from_prediction
        FROM predictions p JOIN prediction_outcomes o ON o.prediction_id = p.id
        WHERE o.horizon_hours = 1 AND o.status = 'ok'
        ORDER BY p.as_of DESC LIMIT %s
    """, (limit,))
    recent = [{"as_of": _iso(a), "signal": s, "return_1h": r} for a, s, r in cur.fetchall()]
    return {"by_horizon": by_horizon, "latest_1h": recent,
            "note": ("Returns are fractions: 0.0044 means +0.44%. A return after a BUY is not evidence the "
                     "signal worked -- Bitcoin drifts on its own, and the comparison that matters is against "
                     "buy-and-hold over the same window.")}


def backend_state(now: datetime | None = None) -> dict:
    """The whole contract. Read-only; safe to call as often as a frontend likes."""
    now = now or datetime.now(timezone.utc)
    with get_connection() as conn, conn.cursor() as cur:
        pred = _latest_prediction(cur)
        shadow = _latest_shadow(cur)
        counts = _counts(cur, now)
        outcomes = _recent_outcomes(cur)
    return assemble(pred, shadow, counts, outcomes, now)


def assemble(pred: dict | None, shadow: dict | None, counts: dict, outcomes: dict, now: datetime) -> dict:
    """
    Turn what the database holds into what the backend says. Separated from the reading so it
    can be tested without a database -- the honesty labels are the part worth testing, and a
    test that needs Postgres to check a sentence would never be run.
    """
    state: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "generated_at": _iso(now),
        "pipeline_version": PIPELINE_VERSION,
        "limitations": LIMITATIONS,
        "not_financial_advice": True,
        "trading": {"places_orders": False, "holds_funds": False,
                    "detail": "This backend is analysis only. It has no exchange connection and no wallet."},
    }

    if pred is None:
        state["latest"] = None
        state["health"] = {"status": "no_data", "detail": "No prediction has ever been stored."}
        state["move_size"] = {"available": False, "reason": "no predictions yet"}
        state["recent_outcomes"] = outcomes
        return state

    age_hours = (now - pred["as_of"]).total_seconds() / 3600.0
    fresh, staleness_detail = staleness_check(STALE_AFTER_HOURS, now=now, latest=pred["as_of"])
    run_meta = pred["run_meta"] or {}
    news_items = pred["news_items"] or []
    news_error = run_meta.get("news_error")
    news_meta = run_meta.get("news") or {}
    categories = pred["category_scores"] or []

    state["latest"] = {
        "as_of": _iso(pred["as_of"]),
        "information_cutoff": _iso(pred["cutoff_at"]),
        "data_fetched_at": _iso(pred["fetched_at"]),
        "age_hours": round(age_hours, 3),
        "hours_since_candle_closed": round((now - pred["cutoff_at"]).total_seconds() / 3600.0, 3),
        "price": Quantity(pred["close_price"], "price", False,
                          "Bitcoin's closing price at the information cutoff, in US dollars.").as_dict(),
        "price_source": pred["price_source"],
        "price_is_estimated": bool(pred["price_is_synthetic"]),
        "signal": pred["signal"],
        "signal_evidence": SIGNAL_EVIDENCE,
        "overall_score": Quantity(pred["overall_score"], "score", False,
                                  "The weighted combination of the category scores, from -1 to +1. "
                                  "A score, not a probability and not an expected return.").as_dict(),
        "confidence": Quantity(pred["overall_confidence"], "heuristic", False, CONFIDENCE_MEANING).as_dict()
        | {"components": {"agreement": pred["agreement_score"], "completeness": pred["completeness_score"]}},
        "categories": [{"name": c.get("name"), "score": c.get("score"), "weight": c.get("weight"),
                        "is_independent": c.get("is_independent"),
                        "available": bool(c.get("weight"))} for c in categories],
        # The raw exception text stays in the database, where it is needed for diagnosis, and
        # never reaches this contract: it is verbose, it exposes internal structure, and a
        # stringified exception is not something anyone should promise is safe to publish.
        "news": {"available": bool(news_items) and not news_error,
                 "items_used": len(news_items),
                 "reason_if_absent": ("the news step failed this hour, so news was left out rather than "
                                      "counted as neutral" if news_error else
                                      (None if news_items else "no stories were published before the cutoff")),
                 "error_type": run_meta.get("news_error_type") if news_error else None,
                 # A PARTIAL failure is the quiet one: two of three feeds down still produces a
                 # number, and without this a reader could not tell it from a complete fetch.
                 "sources_failed": news_meta.get("sources_failed") or [],
                 "sources_used": news_sources_total - len(news_meta.get("sources_failed") or []),
                 "sources_total": news_sources_total,
                 "detail": ("Only stories that were published and retrievable before the information cutoff "
                            "are used. An hour with no usable news is scored on the other categories and "
                            "says so here.")},
        "explanation": pred["explanation"],
        "explanation_status": ("unavailable" if not pred["explanation"] else "ok"),
        "explanation_role": ("Written after the decision was already made by the scoring formulas. It "
                             "describes the result; it never changes it, and it never states a confidence "
                             "of its own."),
        "versions": {"pipeline": pred["pipeline_version"], "scoring": pred["scoring_version"],
                     "ai_news": pred["ai_model_news"], "ai_explanation": pred["ai_model_explanation"],
                     "contract": CONTRACT_VERSION},
    }

    if shadow is None or shadow["status"] != "ok" or shadow["p_calibrated"] is None:
        state["move_size"] = {"available": False,
                              "reason": (shadow or {}).get("status_reason") or "no shadow row yet"}
    else:
        state["move_size"] = {
            "available": True,
            "as_of": _iso(shadow["as_of"]),
            "information_cutoff": _iso(shadow["cutoff_at"]),
            "horizon_hours": shadow["horizon_hours"],
            "threshold_pct": round(shadow["threshold"] * 100, 4),
            "probability": Quantity(shadow["p_calibrated"], "calibrated_probability", True,
                                    MOVE_SIZE_MEANING).as_dict(),
            "model_version": shadow["model_version"],
            "status": MOVE_SIZE_STATUS,
            "prospective_rows": counts["shadow_rows"],
        }

    stale = not fresh
    problems = []
    if stale:
        problems.append(staleness_detail)
    if counts["missing_hours_last_48h"]:
        problems.append("%d hour(s) missing in the last 48" % counts["missing_hours_last_48h"])
    if counts["shadow_errors_last_24h"]:
        problems.append("%d research shadow error(s) in the last 24 hours (the live record is unaffected)"
                        % counts["shadow_errors_last_24h"])
    if pred["price_is_synthetic"]:
        problems.append("the latest price came from the fallback source and is partly estimated")
    state["health"] = {
        "status": "ok" if not problems else ("degraded" if not stale else "stale"),
        "problems": problems,
        "counts": counts,
    }
    state["recent_outcomes"] = outcomes
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the backend's outward-facing state as JSON.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(backend_state(), indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
