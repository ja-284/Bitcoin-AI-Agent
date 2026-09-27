"""
The read-only reporting layer's views (agent/reporting/views.py), on synthetic records only: no database,
no network. What is pinned here: outcome matching, pending vs graded, horizons, missing data, calibration
figures identical to the registered checkpoint's code, sample-size labels, ordering, determinism -- and
above all that nothing recorded after a moment can change what a view of that moment shows.
"""

import json
from datetime import datetime, timedelta, timezone

import numpy as np

from agent.outcome_tracker import HORIZONS_HOURS
from agent.reporting import views
from agent.reporting.source import Records
from agent.research import live_checkpoint, weekly_report

H = timedelta(hours=1)
T0 = datetime(2026, 9, 21, 17, tzinfo=timezone.utc)
AT = T0 + 60 * H  # 1h/6h/24h outcomes of the early hours are known by then; 72h/168h ones are not


def pred(i, as_of, signal="BUY", **kw):
    row = dict(id=i, as_of=as_of, cutoff_at=as_of + H, fetched_at=as_of + H + timedelta(minutes=12),
               created_at=as_of + H + timedelta(minutes=12, seconds=20), pipeline_version="0.2.0", scoring_version="0.2.0",
               signal=signal, overall_score=0.1, overall_confidence=0.6, agreement_score=0.5, completeness_score=1.0,
               close_price=100.0, price_source="binance", price_is_synthetic=False, ai_model_news="claude-haiku-4-5",
               ai_model_explanation="claude-sonnet-5", has_explanation=True, news_items_n=10,
               run_meta={"db_role": "bitcoin_agent", "code_commit": "abc123", "news": {"sources_failed": []}})
    row.update(kw)
    return row


def outcome(pid, as_of, h, ret, status="ok", delay=timedelta(minutes=12)):
    return dict(prediction_id=pid, horizon_hours=h, status=status,
                price_at_horizon=100 * (1 + ret) if status == "ok" else None,
                pct_change_from_prediction=ret if status == "ok" else None,
                checked_at=as_of + timedelta(hours=h) + H + delay)


def shadow(as_of, p, large=False, ret=0.0, graded=True, **kw):
    fetched = as_of + H + timedelta(minutes=12)
    row = dict(as_of=as_of, cutoff_at=as_of + H, fetched_at=fetched, created_at=fetched + timedelta(seconds=5),
               model_version="move_size_1h_v1", pipeline_version="0.2.0", status="ok", status_reason=None,
               features={"rv_168": 0.004}, p_calibrated=p, threshold=0.0025, horizon_hours=1, live_close_match=True,
               outcome_status=None, outcome_return=None, outcome_large=None, outcome_checked_at=None)
    if graded:
        row.update(outcome_status="ok", outcome_return=ret, outcome_large=large, outcome_checked_at=as_of + 2 * H + timedelta(minutes=12))
    row.update(kw)
    return row


def records(preds=(), outs=(), shadows=(), errors=(), state=None, detail=None):
    return Records(list(preds), list(outs), list(shadows), list(errors), state, "4", detail)


def world(hours=48, seed=3):
    """A live-like record whose database already holds every outcome; `known_at` decides what a view may see."""
    rng = np.random.default_rng(seed)
    preds, outs, shadows = [], [], []
    for i in range(hours):
        a = T0 + i * H
        preds.append(pred(i + 1, a, signal=("BUY", "HOLD", "SELL")[i % 3]))
        outs += [outcome(i + 1, a, h, float(rng.normal(0, 0.01))) for h in HORIZONS_HOURS]
        r = float(rng.normal(0, 0.004))
        shadows.append(shadow(a, float(rng.uniform(0.2, 0.7)), large=abs(r) > 0.0025, ret=r))
    return records(preds, outs, shadows)


def _dump(doc) -> str:
    return json.dumps(doc, sort_keys=True, allow_nan=False)


# ------------------------------------------------------------------ the leakage boundary
def test_known_at_hides_everything_recorded_later():
    rec = world()
    at = T0 + 10 * H
    k = views.known_at(rec, at)
    assert [p["as_of"] for p in k.predictions] == [T0 + i * H for i in range(9)]  # hour 9 was saved at T0+10h12m
    assert all(o["checked_at"] <= at for o in k.outcomes)
    assert {(o["prediction_id"], o["horizon_hours"]) for o in k.outcomes} >= {(1, 1), (1, 6)}
    assert (1, 24) not in {(o["prediction_id"], o["horizon_hours"]) for o in k.outcomes}
    last = k.shadow[-1]
    assert last["as_of"] == T0 + 8 * H and last["outcome_status"] is None and last["outcome_large"] is None  # checked 10:12


def test_a_later_outcome_can_never_change_an_earlier_view():
    rec = world()
    before = _dump(views.document("all", views.report(rec, AT, (0.003, 0.005)), AT, AT))
    # rewrite every outcome that was recorded after AT: a view of AT must not move by a single character
    outs = [o if o["checked_at"] <= AT else {**o, "pct_change_from_prediction": 0.5, "status": "ok"} for o in rec.outcomes]
    shadows = [s if s["outcome_checked_at"] <= AT else {**s, "outcome_large": not s["outcome_large"], "outcome_return": 0.9}
               for s in rec.shadow]
    later_runs = [pred(900 + i, T0 + (60 + i) * H) for i in range(5)]  # saved after AT
    after = _dump(views.document("all", views.report(records(rec.predictions + later_runs, outs, shadows), AT, (0.003, 0.005)), AT, AT))
    assert before == after


def test_published_state_is_not_reconstructed_for_the_past():
    rec = records([pred(1, T0)], state={"contract_version": "1", "generated_at": T0 + 5 * H})
    assert views.health(rec, T0 + 3 * H)["published_state"]["available"] is False
    assert views.health(rec, T0 + 6 * H)["published_state"]["age_hours"] == 1.0


# ------------------------------------------------------------------ outcomes, horizons, runs
def test_outcome_states_and_the_registered_direction_rule():
    a = T0
    state = views._outcome_state
    assert state(a, 1, None, a + 2 * H - timedelta(seconds=1), "r")["state"] == "pending"   # candle closes a+2h, due a+3h
    assert state(a, 1, None, a + 3 * H - timedelta(seconds=1), "r")["state"] == "pending"
    assert state(a, 1, None, a + 3 * H, "r")["state"] == "overdue"
    up = state(a, 1, {"status": "ok", "r": 0.001, "checked_at": a + 2 * H}, a + 9 * H, "r")
    assert (up["state"], up["direction"], up["return"]) == ("graded", "UP", 0.001)
    assert state(a, 1, {"status": "ok", "r": 0.0, "checked_at": a + 2 * H}, a + 9 * H, "r")["direction"] == "DOWN"  # labels.py: UP only if > 0
    assert state(a, 1, {"status": "unavailable", "r": None, "checked_at": a + 9 * H}, a + 9 * H, "r")["state"] == "unavailable"


def test_each_run_gets_its_own_outcomes_and_its_own_shadow_row():
    a, b = T0, T0 + H
    rec = records([pred(1, a), pred(2, b)], [outcome(1, a, 1, 0.01), outcome(2, b, 1, -0.02)], [shadow(b, 0.4, True, -0.02)])
    runs = {r["hour"]: r for r in views.recent_runs(rec, T0 + 10 * H)["runs"]}
    assert runs[a.isoformat()]["outcomes"]["1h"]["return"] == 0.01
    assert runs[b.isoformat()]["outcomes"]["1h"]["return"] == -0.02
    assert runs[a.isoformat()]["move_size"]["available"] is False
    assert runs[b.isoformat()]["move_size"]["probability"]["value"] == 0.4
    assert runs[b.isoformat()]["move_size"]["outcome"]["large_move"] is True


def test_every_registered_horizon_and_only_those():
    assert HORIZONS_HOURS == weekly_report.HORIZONS
    rec = records([pred(1, T0)], [outcome(1, T0, 1, 0.01), outcome(1, T0, 12, 0.02)])
    run = views.latest_run(rec, T0 + 30 * H)
    assert list(run["outcomes"]) == [f"{h}h" for h in HORIZONS_HOURS]
    assert views.health(rec, T0 + 30 * H)["outcomes"]["rows_for_unregistered_horizons"] == 1
    assert views.signal_statistics(rec, T0 + 30 * H)["by_horizon"].keys() == {f"{h}h" for h in HORIZONS_HOURS}


def test_history_is_newest_first_pages_without_overlap_and_finds_one_hour():
    rec = world(hours=12)
    at = T0 + 20 * H
    page1 = views.recent_runs(rec, at, limit=5)
    hours1 = [r["hour"] for r in page1["runs"]]
    assert hours1 == sorted(hours1, reverse=True) and len(hours1) == 5 and page1["total_runs"] == 12
    page2 = views.recent_runs(rec, at, limit=5, before=datetime.fromisoformat(page1["next_before"]))
    assert set(hours1).isdisjoint(r["hour"] for r in page2["runs"]) and page2["runs"][0]["hour"] < hours1[-1]
    last = views.recent_runs(rec, at, limit=5, before=datetime.fromisoformat(page2["next_before"]))
    assert last["returned"] == 2 and last["next_before"] is None
    assert views.run_at(rec, at, T0 + 3 * H)["hour"] == (T0 + 3 * H).isoformat()
    assert views.run_at(rec, at, T0 + 99 * H) is None
    assert views.run_at(rec, T0 + 3 * H, T0 + 3 * H) is None  # not saved yet at that moment


def test_run_status_labels_and_the_one_probability():
    a = T0
    degraded = pred(1, a, price_source="coingecko", price_is_synthetic=True, has_explanation=False, news_items_n=0,
                    run_meta={"news_error": "boom", "news_error_type": "APIError"})
    rec = records([degraded], shadows=[shadow(a, 0.45, graded=False)])
    run = views.latest_run(rec, a + 2 * H)
    assert run["run"]["status"] == "degraded" and run["run"]["fallback_used"] is True
    assert run["run"]["news"] == {"available": False, "items_used": 0, "error_type": "APIError", "sources_failed": []}
    assert "boom" not in _dump(run)  # the stored exception text is never published
    assert run["confidence"]["is_probability"] is False and run["confidence"]["kind"] == "heuristic"
    assert run["move_size"]["outcome"]["state"] == "pending"

    def probabilities(x, path=""):
        if isinstance(x, dict):
            if x.get("is_probability") is True:
                yield path
            for k, v in x.items():
                yield from probabilities(v, f"{path}/{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from probabilities(v, f"{path}/{i}")

    doc = views.document("all", views.report(world(), AT), AT, AT)
    assert set(probabilities(doc)) == {"/body/latest_run/move_size/probability"}


# ------------------------------------------------------------------ statistics
def test_signal_statistics_match_a_hand_count_and_exclude_older_pipelines():
    rec = world()
    old = pred(500, T0 - 5 * H, pipeline_version="0.1.0")
    rec = records([old] + rec.predictions, rec.outcomes, rec.shadow)
    s = views.signal_statistics(rec, AT)
    assert s["population"]["excluded_older_pipeline_runs"] == 1 and s["evidence"]["status"] == "no_demonstrated_predictive_value"
    k = views.known_at(rec, AT)
    graded = {o["prediction_id"]: o["pct_change_from_prediction"] for o in k.outcomes if o["horizon_hours"] == 1}
    for signal in ("BUY", "HOLD", "SELL"):
        rets = [graded[p["id"]] for p in k.predictions if p["signal"] == signal and p["pipeline_version"] == "0.2.0" and p["id"] in graded]
        g = s["by_horizon"]["1h"][signal]
        assert g["graded"] == len(rets) == g["sample"]["n"]
        assert g["share_followed_by_a_rise"] == sum(r > 0 for r in rets) / len(rets)
        assert abs(g["mean_return"] - float(np.mean(rets))) < 1e-15
    all_ = s["by_horizon"]["1h"]["ALL"]
    assert all_["graded"] == sum(s["by_horizon"]["1h"][x]["graded"] for x in ("BUY", "HOLD", "SELL"))
    assert s["by_horizon"]["168h"]["ALL"]["graded"] == 0 and s["by_horizon"]["168h"]["ALL"]["pending"] == 48


def test_move_size_figures_are_the_registered_checkpoint_code_on_the_registered_selection():
    rec = world(hours=60)
    late = shadow(T0 + 70 * H, 0.9, True, 0.01, fetched_at=T0 + 73 * H, created_at=T0 + 73 * H)  # stored after its outcome closed
    rec = records(rec.predictions, rec.outcomes, rec.shadow + [late])
    at = T0 + 80 * H
    m = views.move_size_statistics(rec, at)
    graded = live_checkpoint.prospective_graded(views.known_at(rec, at).shadow)
    assert m["sample"]["n"] == len(graded) == m["checkpoint_progress"]["prospective_graded_hours"] == 60
    assert m["not_prospective"] == 1
    p = np.array([r["p_calibrated"] for r in graded])
    y = np.array([1.0 if r["outcome_large"] else 0.0 for r in graded])
    size = np.abs(np.array([r["outcome_return"] for r in graded]))
    ref = live_checkpoint.core(p, y, size)
    for key in ("brier_rel_gain", "ece", "rho", "large_move_share", "mean_stated_p"):
        assert m["running_figures"][key] == ref[key]
    assert m["running_figures"]["brier"] == float(np.mean((p - y) ** 2))
    assert sum(b["n"] for b in m["running_figures"]["calibration_bins"]) == 60
    text = _dump(views.clean(m))
    for verdict_like in ("e013_ece_ok", "e013_buckets_ok", "within_0_05", "counts_for_e013", '"pass"'):
        assert verdict_like not in text


def test_small_samples_can_never_look_like_evidence():
    ev = views.sample_evidence
    assert ev(191)["level"] == "too_few_to_conclude" and ev(191)["intervals"] == "not_computed"
    assert ev(192)["level"] == "early_intervals_optimistic" and ev(1999)["level"] == "early_intervals_optimistic"
    assert ev(2000)["level"] == "enough_for_nominal_intervals"
    assert not any(ev(n)["is_verdict"] for n in (0, 1, 191, 192, 1999, 2000, 10**6))
    small = views.move_size_statistics(world(hours=48), AT)["running_figures"]
    assert not any(k.endswith("_ci95") and k != "accuracy_ci95" for k in small)  # no bootstrap interval below 192 hours
    big = views.move_size_statistics(world(hours=200), T0 + 220 * H)["running_figures"]
    assert "brier_rel_gain_ci95" in big and "ece_ci95" in big


def test_breakdowns_partition_the_graded_hours():
    rec = world(hours=48)
    shadows = [{**s, "features": {"rv_168": (0.002, 0.006, 0.009)[i % 3]}} for i, s in enumerate(rec.shadow)]
    rec = records(rec.predictions, rec.outcomes, shadows)
    b = views.move_size_breakdowns(rec, AT, (0.004759, 0.006966))
    n = views.move_size_statistics(rec, AT)["sample"]["n"]
    for name, groups in b["slices"].items():
        assert sum(g["n"] for g in groups.values()) == n, name
        assert all(g["sample"]["n"] == g["n"] for g in groups.values())
    assert set(b["slices"]["volatility_regime_168h"]) == {"low", "mid", "high"}
    assert set(b["slices"]["hour_block_utc"]) <= {"00-06", "06-12", "12-18", "18-24"}
    assert "volatility_regime_168h" not in views.move_size_breakdowns(rec, AT, None)["slices"]


# ------------------------------------------------------------------ health
def test_health_sees_missing_hours_overdue_outcomes_and_anomalies_but_never_error_text():
    rec = world(hours=24)
    preds = [p for p in rec.predictions if p["as_of"] not in (T0 + 5 * H, T0 + 6 * H)]
    outs = [o for o in rec.outcomes if not (o["prediction_id"] == 1 and o["horizon_hours"] == 1)]  # never graded -> overdue
    outs.append({**outcome(3, T0 + 2 * H, 6, 0.01), "checked_at": T0 + 3 * H})  # graded before its candle closed
    outs = [o for o in outs if not (o["prediction_id"] == 3 and o["horizon_hours"] == 6 and o["checked_at"] != T0 + 3 * H)]
    errors = [{"occurred_at": T0 + 20 * H, "expected_as_of": T0 + 19 * H, "step": "fetch", "error_type": "HTTPError",
               "error_message": "SECRET-TOKEN-should-never-appear"}]
    at = T0 + 25 * H + timedelta(minutes=10)  # the T0+24h run is not due until :22 (weekly_report.expected_hours)
    h = views.health(records(preds, outs, rec.shadow, errors), at)
    assert h["missing_hours_all_time"] == [(T0 + 5 * H).isoformat(), (T0 + 6 * H).isoformat()]
    assert h["windows"]["all_time"]["missing_hours"] == 2
    assert h["outcomes"]["overdue_by_horizon"]["1h"] == 1
    assert h["outcomes"]["graded_before_their_candle_closed"] == 1
    assert h["shadow"]["latest_error"] == {"occurred_at": (T0 + 20 * H).isoformat(), "step": "fetch", "error_type": "HTTPError"}
    assert h["status"] == "degraded" and h["shadow"]["hours_without_a_shadow_row"] == 0
    assert "SECRET-TOKEN" not in _dump(views.clean(h))
    assert h["external"]["heartbeat"]["observable_here"] is False and h["external"]["watchdog"]["observable_here"] is False
    assert views.health(rec, T0 + 40 * H)["status"] == "stale"
    assert views.health(records(), AT)["status"] == "no_data"


def test_checkpoint_progress_counts_but_never_evaluates():
    cp = views.checkpoint_progress(126, AT, {500: "research/monitoring/checkpoint_500h.md"})
    assert (cp["next_checkpoint_hours"], cp["hours_remaining"], cp["reached"]) == (500, 374, [])
    assert cp["expected_around"] == (AT + 374 * H).isoformat()
    assert views.checkpoint_progress(500, AT)["reached"] == [500] and views.checkpoint_progress(500, AT)["next_checkpoint_hours"] == 2000
    assert views.checkpoint_progress(5000, AT)["next_checkpoint_hours"] is None
    assert cp["computed_readings"] == {"500": "research/monitoring/checkpoint_500h.md"}


# ------------------------------------------------------------------ the document
def test_documents_are_deterministic_json_safe_and_carry_their_warnings():
    rec = world()
    a = _dump(views.document("all", views.report(rec, AT, (0.003, 0.005)), AT, AT))
    b = _dump(views.document("all", views.report(rec, AT, (0.003, 0.005)), AT, AT))
    assert a == b
    doc = json.loads(a)
    assert doc["read_only"] is True and doc["descriptive_only"] is True and doc["never_use_for"]
    assert views.clean({"x": float("nan"), "y": np.float64(np.inf), "z": np.int64(3)}) == {"x": None, "y": None, "z": 3}
