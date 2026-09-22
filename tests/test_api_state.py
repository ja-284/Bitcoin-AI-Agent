"""
Tests for the backend's outward-facing contract (agent/api/state.py).

The contract's job is to stop a frontend from overstating the evidence. These tests are
therefore mostly about the honesty labels, not about plumbing: if someone later removes the
"this is not a probability" flag from the confidence number, or lets the signal be published
without its evidence status, a test here fails. No database is needed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent.api import state as api

NOW = datetime(2026, 9, 22, 19, 5, tzinfo=timezone.utc)


def _pred(**over) -> dict:
    base = {
        "as_of": NOW - timedelta(hours=2), "cutoff_at": NOW - timedelta(hours=1),
        "fetched_at": NOW - timedelta(minutes=53), "close_price": 86570.24,
        "price_source": "binance", "price_is_synthetic": False,
        "overall_score": 0.46, "signal": "BUY", "agreement_score": 0.94,
        "completeness_score": 1.0, "overall_confidence": 0.97,
        "pipeline_version": "0.2.0", "scoring_version": "0.2.0",
        "ai_model_news": "claude-haiku-4-5", "ai_model_explanation": "claude-sonnet-5",
        "explanation": "Trend is strongly positive while momentum is neutral.",
        "category_scores": [{"name": "trend", "score": 0.85, "weight": 0.25, "is_independent": False},
                            {"name": "volume", "score": 0.0, "weight": 0.0, "is_independent": True}],
        "news_items": [{"headline": "something happened"}],
        "run_meta": {},
    }
    base.update(over)
    return base


def _shadow(**over) -> dict:
    base = {"as_of": NOW - timedelta(hours=2), "cutoff_at": NOW - timedelta(hours=1),
            "model_version": "move_size_1h_v1", "pipeline_version": "0.2.0",
            "p_calibrated": 0.4836, "threshold": 0.0025, "horizon_hours": 1,
            "status": "ok", "status_reason": None}
    base.update(over)
    return base


def _counts(**over) -> dict:
    base = {"predictions": 72, "first_prediction": "2026-09-19T09:00:00+00:00",
            "latest_prediction": "2026-09-22T17:00:00+00:00", "missing_hours_last_48h": 0,
            "shadow_rows": 18, "shadow_errors_last_24h": 0}
    base.update(over)
    return base


def _state(pred=None, shadow=None, counts=None, now=NOW) -> dict:
    return api.assemble(pred if pred is not None else _pred(),
                        shadow if shadow is not None else _shadow(),
                        counts or _counts(), {"by_horizon": [], "latest_1h": [], "note": ""}, now)


# ---------------------------------------------------------------- the honesty labels
def test_confidence_can_never_be_mistaken_for_a_probability():
    c = _state()["latest"]["confidence"]
    assert c["is_probability"] is False
    assert c["kind"] == "heuristic"
    assert "not a probability" in c["meaning"]


def test_the_signal_always_carries_its_evidence_status():
    latest = _state()["latest"]
    assert latest["signal"] in ("BUY", "HOLD", "SELL")
    assert latest["signal_evidence"]["status"] == "no_demonstrated_predictive_value"
    assert "E001" in latest["signal_evidence"]["experiments"]


def test_the_only_thing_flagged_as_a_probability_is_the_calibrated_one():
    s = _state()
    flagged = []
    def walk(node, path=""):
        if isinstance(node, dict):
            if node.get("is_probability") is True:
                flagged.append(path)
            for k, v in node.items():
                walk(v, path + "/" + k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))
    walk(s)
    assert flagged == ["/move_size/probability"], flagged


def test_the_overall_score_is_not_presented_as_an_expected_return():
    q = _state()["latest"]["overall_score"]
    assert q["is_probability"] is False
    assert "not a probability" in q["meaning"]


def test_the_explanation_is_labelled_as_coming_after_the_decision():
    latest = _state()["latest"]
    assert "after the decision" in latest["explanation_role"]
    assert "never changes it" in latest["explanation_role"]


def test_trading_boundary_is_stated_in_the_contract_itself():
    s = _state()
    assert s["trading"]["places_orders"] is False
    assert s["trading"]["holds_funds"] is False
    assert s["not_financial_advice"] is True
    assert any("does not trade" in line for line in s["limitations"])


# ---------------------------------------------------------------- degraded states
def test_missing_news_is_reported_rather_than_hidden():
    s = _state(pred=_pred(news_items=[], run_meta={"news_error": "the scorer timed out",
                                                   "news_error_type": "TimeoutError"}))
    news = s["latest"]["news"]
    assert news["available"] is False
    assert "failed this hour" in news["reason_if_absent"]
    assert news["error_type"] == "TimeoutError"


def test_the_raw_exception_text_never_reaches_the_contract():
    """
    A stringified exception is verbose, exposes internal structure and is not something anyone
    should promise is safe to publish. It stays in the database, where it is needed for
    diagnosis -- it is what identified the 2026-09-21 truncation -- and stops there.
    """
    import json
    secret_looking = "Connection failed: postgresql://user:hunter2@db.example/postgres"
    s = _state(pred=_pred(news_items=[], run_meta={"news_error": secret_looking,
                                                   "news_error_type": "OperationalError"}))
    assert secret_looking not in json.dumps(s, default=str)
    assert s["latest"]["news"]["error_type"] == "OperationalError"


def test_an_unavailable_category_is_visible_as_unavailable():
    cats = _state()["latest"]["categories"]
    volume = next(c for c in cats if c["name"] == "volume")
    assert volume["available"] is False, "a category with weight 0 was not computed; it is not a neutral opinion"


def test_a_failed_shadow_row_does_not_produce_a_probability():
    s = _state(shadow=_shadow(status="skipped", status_reason="features unavailable", p_calibrated=None))
    assert s["move_size"]["available"] is False
    assert s["move_size"]["reason"] == "features unavailable"
    assert "probability" not in s["move_size"]


def test_no_predictions_at_all_is_reported_honestly():
    s = api.assemble(None, None, _counts(predictions=0), {"by_horizon": [], "latest_1h": [], "note": ""}, NOW)
    assert s["latest"] is None
    assert s["health"]["status"] == "no_data"
    assert s["move_size"]["available"] is False


def test_fallback_price_is_flagged():
    s = _state(pred=_pred(price_is_synthetic=True, price_source="coingecko"))
    assert s["latest"]["price_is_estimated"] is True
    assert any("fallback" in p for p in s["health"]["problems"])


def test_missing_hours_and_shadow_errors_show_up_in_health():
    s = _state(counts=_counts(missing_hours_last_48h=3, shadow_errors_last_24h=5))
    assert s["health"]["status"] == "degraded"
    assert any("3 hour(s) missing" in p for p in s["health"]["problems"])
    assert any("shadow error" in p for p in s["health"]["problems"])


# ---------------------------------------------------------------- staleness
def test_staleness_uses_the_same_rule_as_the_watchdog():
    """
    The reference candle closes an hour after as_of, and the job runs at :12, so just before a
    run the newest prediction is legitimately about 2h10m old by as_of. It must not be called
    stale for that: the contract and the watchdog must agree, because they call one function.
    """
    just_before_the_run = _state(pred=_pred(as_of=NOW - timedelta(hours=2, minutes=11),
                                            cutoff_at=NOW - timedelta(hours=1, minutes=11)))
    assert just_before_the_run["health"]["status"] == "ok"

    genuinely_late = _state(pred=_pred(as_of=NOW - timedelta(hours=5), cutoff_at=NOW - timedelta(hours=4)))
    assert genuinely_late["health"]["status"] == "stale"
    assert genuinely_late["health"]["problems"]


def test_contract_version_is_stated_in_two_places_and_agrees():
    s = _state()
    assert s["contract_version"] == api.CONTRACT_VERSION
    assert s["latest"]["versions"]["contract"] == api.CONTRACT_VERSION


def test_the_state_is_json_serialisable():
    import json
    json.dumps(_state(), default=str)


def test_timestamps_are_utc_iso_strings():
    latest = _state()["latest"]
    for field in ("as_of", "information_cutoff", "data_fetched_at"):
        assert latest[field].endswith("+00:00"), field


@pytest.mark.parametrize("signal", ["BUY", "HOLD", "SELL"])
def test_every_signal_value_carries_the_same_warning(signal):
    s = _state(pred=_pred(signal=signal))
    assert s["latest"]["signal_evidence"]["status"] == "no_demonstrated_predictive_value"
