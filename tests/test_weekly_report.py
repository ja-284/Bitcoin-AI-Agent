"""
The weekly report's computations are pure functions of rows; they are tested on synthetic rows.
No database, no network.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from agent.research.weekly_report import expected_hours, health, paper_record, signal_record, watch_list
from agent.version import PIPELINE_VERSION

T0 = datetime(2026, 9, 19, 9, tzinfo=timezone.utc)
H = timedelta(hours=1)


def _pred(as_of, signal="BUY", conf=0.8, delay_min=12.5, source="binance", synthetic=False, news=20, expl=True, meta=None, pv=PIPELINE_VERSION):
    return {"as_of": as_of, "fetched_at": as_of + H + timedelta(minutes=delay_min), "cutoff_at": as_of + H, "pipeline_version": pv,
            "price_source": source, "price_is_synthetic": synthetic, "run_meta": meta or {}, "news_items_n": news, "has_explanation": expl,
            "signal": signal, "overall_confidence": conf, "scoring_version": "0.2.0"}


def test_expected_hours_respects_the_run_minute():
    now = datetime(2026, 9, 21, 16, 5, tzinfo=timezone.utc)  # 16:05 -- the 16:12 run has not happened yet
    hours = expected_hours(T0, now)
    assert hours[-1] == datetime(2026, 9, 21, 14, tzinfo=timezone.utc)  # 15:00's row is written at 16:12, not yet due
    now = datetime(2026, 9, 21, 16, 30, tzinfo=timezone.utc)
    assert expected_hours(T0, now)[-1] == datetime(2026, 9, 21, 15, tzinfo=timezone.utc)


def test_health_finds_missing_hours_late_runs_and_errors():
    now = T0 + 30 * H + timedelta(minutes=40)
    rows = [_pred(T0 + i * H) for i in range(30) if i not in (5, 6)]  # two missing hours
    rows[3]["run_meta"] = {"news_error": "feed down"}
    rows[4]["price_source"] = "coingecko"
    rows[4]["price_is_synthetic"] = True
    outs = [{"prediction_as_of": r["as_of"], "horizon_hours": 1, "status": "ok"} for r in rows[:-3]]
    hlt = health(rows, outs, now, T0)
    assert hlt["expected_hours"] == 30 and hlt["predictions"] == 28
    assert [m[11:13] for m in hlt["missing_hours"]] == ["14", "15"]
    assert hlt["run_errors"] == {"news_error": 1}
    assert hlt["synthetic_rows"] == 1 and hlt["price_sources"] == {"binance": 27, "coingecko": 1}
    assert hlt["timestamp_rule_violations"] == []
    cov = hlt["outcome_coverage"]["1h"]
    assert cov["ok"] == 25 and cov["overdue"] == cov["due"] - 25  # the last rows are not due yet or overdue


def test_a_row_for_an_hour_not_yet_due_cannot_hide_a_missing_hour():
    """
    Found in the 2026-09-23 report: run at 16:17, it counted the 15:00 row (written at 16:12, not
    yet "expected" until 16:22) among 102 expected hours, and printed 94 of 102 with 9 missing.
    """
    from agent.research.weekly_report import render

    now = T0 + 10 * H + timedelta(minutes=17)  # this hour's run has written its row; allowance not over
    rows = [_pred(T0 + i * H) for i in range(10) if i != 4]  # hour 4 missing; hour 9 written early
    hlt = health(rows, [], now, T0)
    assert hlt["expected_hours"] == 9 and hlt["missing_hours"] == [(T0 + 4 * H).isoformat()]
    assert hlt["present_hours"] == 8 and hlt["rows_not_yet_due"] == 1
    assert hlt["present_hours"] + len(hlt["missing_hours"]) == hlt["expected_hours"]  # the line must add up
    rep = {"generated_at": now.isoformat(), "pipeline_version": "0.2.0", "scoring_version": "0.2.0",
           "schema_version": {"database": "4", "code": "4", "match": True}, "live_since": T0.isoformat(), "live_hours": 10,
           "health_last_7_days": hlt, "health_since_go_live": hlt,
           "signal_record": {"rows_pipeline_0_2_0": 0, "signal_mix": {}, "scoring_versions": {}, "by_horizon": {}},
           "watch_list": watch_list(rows, now), "drift": {"error": "not part of this test"}}
    text = render(rep)
    for line in ("- Last 7 days: ", "- Since go-live: "):  # each line on its own: one correct line must not cover the other
        assert line + "8 of 9 expected hours (+1 row for an hour not yet due)" in text, line


def test_health_flags_a_timestamp_rule_violation():
    now = T0 + 10 * H
    rows = [_pred(T0 + i * H) for i in range(5)]
    rows[2]["fetched_at"] = rows[2]["cutoff_at"] - timedelta(minutes=1)  # fetched before the candle closed
    assert health(rows, [], now, T0)["timestamp_rule_violations"] == [rows[2]["as_of"].isoformat()]


def test_signal_record_accuracy_edge_and_interval_gate():
    rng = np.random.default_rng(0)
    n = 200
    rows = [_pred(T0 + i * H, signal=rng.choice(["BUY", "SELL", "HOLD"])) for i in range(n)]
    rets = rng.normal(0, 0.005, size=n)  # stored as a FRACTION, like the outcome tracker writes it (0.005 = 0.5%)
    outs = [{"prediction_as_of": r["as_of"], "horizon_hours": 1, "status": "ok", "pct_change_from_prediction": float(x)} for r, x in zip(rows, rets)]
    outs += [{"prediction_as_of": rows[0]["as_of"], "horizon_hours": 24, "status": "ok", "pct_change_from_prediction": 1.0}]
    sr = signal_record(rows, outs)
    d1 = sr["by_horizon"]["1h"]
    assert d1["n"] == n and d1["edge"]["interval_available"] is True  # 200 >= 2 * 48
    sig = np.array([r["signal"] for r in rows])
    acted = sig != "HOLD"
    expect_acc = np.mean((sig[acted] == "BUY") == (rets[acted] > 0))
    assert d1["acted_accuracy"] == pytest.approx(expect_acc)
    assert d1["edge"]["point"] == pytest.approx(rets[sig == "BUY"].mean() - rets[sig == "SELL"].mean())  # no unit conversion: fraction in, fraction out
    assert d1["buy_and_hold_mean_return"] == pytest.approx(rets.mean())
    d24 = sr["by_horizon"]["24h"]
    assert d24["n"] == 1 and d24["edge"]["interval_available"] is False and d24["edge"]["hours_needed_for_interval"] == 96
    assert sr["by_horizon"]["168h"] == {"n": 0}


def test_signal_record_uses_only_the_corrected_pipeline_rows():
    rows = [_pred(T0, pv="0.1.0"), _pred(T0 + H)]
    outs = [{"prediction_as_of": r["as_of"], "horizon_hours": 1, "status": "ok", "pct_change_from_prediction": 0.3} for r in rows]
    assert signal_record(rows, outs)["rows_pipeline_0_2_0"] == 1


def test_paper_record_scores_probabilities():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.1, 0.9, size=400)
    y = (rng.uniform(size=400) < p).astype(float)  # perfectly calibrated by construction
    rec = paper_record(p, y, np.abs(rng.normal(size=400)) * p)
    assert rec["n"] == 400 and rec["ece"] < 0.08 and rec["brier"] < rec["brier_base_rate"]
    assert rec["rank_corr_p_vs_abs_return"] > 0.3
    assert paper_record(np.array([]), np.array([]), np.array([])) == {"n": 0}


def test_watch_list_thresholds():
    rows = [_pred(T0 + i * H, news=(20 if i % 2 else 0)) for i in range(100)]
    wl = watch_list(rows, T0 + 100 * H)
    assert wl["news_hours"]["have"] == 50 and wl["news_hours"]["ready"] is False
    assert wl["live_months"]["ready"] is False
    assert watch_list(rows, T0 + timedelta(days=200))["live_months"]["ready"] is True


def test_shadow_record_coverage_blanks_and_evaluation():
    from agent.research.weekly_report import shadow_record

    now = T0 + 12 * H + timedelta(minutes=40)
    rows = []
    for i in range(12):
        if i == 4:
            continue  # one missing hour
        r = {"as_of": T0 + i * H, "fetched_at": T0 + i * H + timedelta(hours=1, minutes=12), "horizon_hours": 1,
             "status": "ok", "status_reason": None, "live_close_match": True, "p_calibrated": 0.4 + 0.02 * i,
             "model_version": "move_size_1h_v1", "outcome_status": "ok" if i < 9 else None, "outcome_return": 0.004 if i % 2 else -0.001, "outcome_large": bool(i % 2)}
        rows.append(r)
    rows[2].update({"status": "unavailable", "status_reason": "missing inputs: rv_168", "p_calibrated": None, "outcome_status": None})
    rows[5]["live_close_match"] = False
    sh = shadow_record(rows, now)
    assert sh["n"] == 11 and sh["expected_hours"] == 12 and [m[11:13] for m in sh["missing_hours"]] == ["13"]
    assert sh["unavailable"] == 1 and sh["live_close_mismatch"] == 1
    assert sh["outcomes"]["ok_prospective"] == 7 and sh["outcomes"]["pending"] == 3  # rows 9,10,11 ok+pending; row 2 unavailable excluded
    assert sh["evaluation"]["n"] == 7 and "prospective" in sh["evaluation"]["note"]
    assert sh["not_prospective"] == []

    # a row written after its outcome candle had already closed is kept, shown, and NOT evaluated
    late = [dict(r) for r in rows]
    late[0]["fetched_at"] = late[0]["as_of"] + timedelta(hours=3)
    sh_late = shadow_record(late, now)
    assert sh_late["outcomes"]["ok_prospective"] == 6 and len(sh_late["not_prospective"]) == 1
    assert sh_late["evaluation"]["n"] == 6
    empty = shadow_record([], now)
    assert empty["n"] == 0 and empty["note"] == "no shadow rows yet" and empty["errors"]["n"] == 0


def test_paper_record_reports_intervals_only_with_enough_hours():
    rng = np.random.default_rng(5)
    p = rng.uniform(0.1, 0.9, size=300)
    y = (rng.uniform(size=300) < p).astype(float)
    rec = paper_record(p, y, np.abs(rng.normal(size=300)) * p)
    assert "brier_rel_gain_ci95" in rec and "ece_ci95" in rec and rec["brier_rel_gain_ci95"][0] <= rec["brier_rel_gain"] <= rec["brier_rel_gain_ci95"][1]
    small = paper_record(p[:100], y[:100], np.abs(rng.normal(size=100)))
    assert "brier_rel_gain_ci95" not in small and "no intervals yet" in small["interval_note"]


def test_shadow_record_reports_recorded_job_errors():
    """A shadow job that fails no longer turns the hourly workflow red, so the report must show it."""
    from agent.research.weekly_report import shadow_record

    now = T0 + 12 * H
    errors = [{"occurred_at": T0 + i * H, "expected_as_of": T0 + (i - 1) * H, "step": "load_model",
               "error_type": "ModelVersionError", "error_message": "feature definitions changed", "code_commit": None} for i in (1, 3, 5)]
    sh = shadow_record([], now, errors)
    assert sh["n"] == 0 and sh["errors"]["n"] == 3 and sh["errors"]["by_step"] == {"load_model": 3}
    assert sh["errors"]["latest"]["step"] == "load_model" and "ModelVersionError" in sh["errors"]["latest"]["error"]
    rows = [{"as_of": T0 + i * H, "status": "ok", "status_reason": None, "live_close_match": True, "p_calibrated": 0.5,
             "model_version": "move_size_1h_v1", "outcome_status": None, "outcome_return": None, "outcome_large": None} for i in range(3)]
    assert shadow_record(rows, now, [])["errors"]["n"] == 0
    assert shadow_record(rows, now)["errors"]["n"] == 0  # errors are optional


def test_signal_record_reports_the_scoring_version_mix():
    """Scoring 0.2.0 changed gap-affected hours, so the report must never blend versions silently."""
    rows = [_pred(T0), _pred(T0 + H)]
    rows[0]["scoring_version"] = "0.1.0"
    rows[1]["scoring_version"] = "0.2.0"
    outs = [{"prediction_as_of": r["as_of"], "horizon_hours": 1, "status": "ok", "pct_change_from_prediction": 0.004} for r in rows]
    sr = signal_record(rows, outs)
    assert sr["scoring_versions"] == {"0.1.0": 1, "0.2.0": 1}


def test_accuracy_always_carries_an_interval_so_small_samples_say_so():
    """
    Precision discipline: an accuracy printed to three decimals next to a naive rate invites the
    reader to believe a difference that 13 hours cannot support. Every accuracy now carries a
    Wilson interval, and the report states plainly whether it clears the naive rate.
    """
    rng = np.random.default_rng(3)
    small_p = rng.uniform(0.3, 0.7, size=13)
    small_y = (rng.uniform(size=13) < small_p).astype(float)
    small = paper_record(small_p, small_y, np.abs(rng.normal(size=13)))
    lo, hi = small["accuracy_ci95"]
    assert lo < small["accuracy"] < hi
    assert hi - lo > 0.3, "13 observations must produce an obviously wide interval"
    assert small["accuracy_beats_naive"] is False  # nothing can be established from 13 hours

    big_p = rng.uniform(0.05, 0.95, size=4000)
    big_y = (rng.uniform(size=4000) < big_p).astype(float)  # genuinely informative probabilities
    big = paper_record(big_p, big_y, np.abs(rng.normal(size=4000)) * big_p)
    blo, bhi = big["accuracy_ci95"]
    assert bhi - blo < 0.05, "4000 observations must produce a tight interval"
    assert big["accuracy_beats_naive"] is True


# ---------------------------------------------------------------- E019 reference, pre-committed
def _graded(n: int, start=None, threshold=0.0025):
    from datetime import datetime, timedelta, timezone
    start = start or datetime(2026, 9, 21, 17, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        t = start + timedelta(hours=i)
        rows.append({"as_of": t, "fetched_at": t + timedelta(minutes=12), "status": "ok",
                     "status_reason": None, "live_close_match": True, "p_calibrated": 0.4 + 0.01 * (i % 5),
                     "model_version": "move_size_1h_v1", "outcome_status": "ok",
                     "outcome_return": 0.003 if i % 2 else 0.001, "outcome_large": bool(i % 2),
                     "threshold": threshold, "horizon_hours": 1})
    return rows


def test_the_no_fitting_reference_is_scored_on_the_same_hours():
    """E019 made the EWMA rule the standing reference; the weekly report must actually use it."""
    import pandas as pd
    from datetime import datetime, timedelta, timezone
    from agent.research.weekly_report import shadow_record

    rows = _graded(12)
    idx = pd.DatetimeIndex([r["as_of"] for r in rows])
    ewma = pd.Series([0.45] * len(rows), index=idx)
    now = rows[-1]["as_of"] + timedelta(hours=3)
    sh = shadow_record(rows, now, [], ewma=ewma)
    ref = sh["evaluation_vs_ewma_reference"]
    assert ref["hours_compared"] == 12
    assert ref["model_brier"] == sh["evaluation"]["brier"]
    assert "2.47x" in ref["development_expectation"]


def test_the_reference_refuses_to_compare_a_different_event():
    """A shadow row scored at another threshold is not measuring the same thing as the reference."""
    import pandas as pd
    from datetime import timedelta
    from agent.research.weekly_report import shadow_record

    rows = _graded(12, threshold=0.01)
    ewma = pd.Series([0.45] * len(rows), index=pd.DatetimeIndex([r["as_of"] for r in rows]))
    sh = shadow_record(rows, rows[-1]["as_of"] + timedelta(hours=3), [], ewma=ewma)
    assert "unavailable" in sh["evaluation_vs_ewma_reference"]
    assert "same event" in sh["evaluation_vs_ewma_reference"]["unavailable"]


def test_a_missing_reference_never_costs_the_shadow_evaluation():
    from datetime import timedelta
    from agent.research.weekly_report import shadow_record

    rows = _graded(12)
    sh = shadow_record(rows, rows[-1]["as_of"] + timedelta(hours=3), [], ewma=None)
    assert sh["evaluation"]["n"] == 12
    assert "evaluation_vs_ewma_reference" not in sh


# ---------------------------------------------------------------- AI cost, from recorded token usage
def _usage_meta(news=(1753, 2188), expl=(509, 266)):
    u = {}
    if news:
        u["news"] = {"model": "claude-haiku-4-5", "input_tokens": news[0], "output_tokens": news[1]}
    if expl:
        u["explanation"] = {"model": "claude-sonnet-5", "input_tokens": expl[0], "output_tokens": expl[1]}
    return {"ai_usage": u}


def test_ai_cost_prices_the_recorded_tokens_exactly():
    from agent.research.weekly_report import ai_cost

    c = ai_cost([_pred(T0, meta=_usage_meta())], T0)
    # 1753 x $1 + 2188 x $5 (Haiku 4.5) + 509 x $2 + 266 x $10 (Sonnet 5), per million tokens
    expected = (1753 * 1 + 2188 * 5 + 509 * 2 + 266 * 10) / 1e6
    assert c["mean_cost_per_run_usd"] == pytest.approx(expected, rel=1e-12)
    assert c["projected_30_days_usd"] == pytest.approx(expected * 720, rel=1e-12)
    assert c["steps"]["news"]["mean_output_tokens"] == 2188


def test_ai_cost_never_counts_an_unknown_as_zero():
    """A run with a part lacking figures, or an unpriced model, has an unknown total: left out and counted."""
    from agent.research.weekly_report import ai_cost

    rows = [_pred(T0, meta=_usage_meta()),
            _pred(T0 + H, meta={"ai_usage": {"news": {"model": "claude-haiku-4-5", "usage_unavailable": True},
                                             "explanation": {"model": "claude-sonnet-5", "input_tokens": 1, "output_tokens": 1}}}),
            _pred(T0 + 2 * H, meta={"ai_usage": {"news": {"model": "some-new-model", "input_tokens": 9, "output_tokens": 9}}}),
            _pred(T0 + 3 * H)]  # before usage was recorded
    c = ai_cost(rows, T0)
    assert (c["rows"], c["rows_with_usage"], c["runs_priced"]) == (4, 3, 1)
    assert c["steps"]["news"]["usage_unavailable"] == 1 and c["unpriced_models"] == {"some-new-model": 1}
    assert c["mean_cost_per_run_usd"] == pytest.approx((1753 * 1 + 2188 * 5 + 509 * 2 + 266 * 10) / 1e6)


def test_a_run_whose_news_failed_is_priced_as_what_it_really_cost():
    """No news call means no news cost -- a real saving, not a gap."""
    from agent.research.weekly_report import ai_cost

    c = ai_cost([_pred(T0, meta=_usage_meta(news=None))], T0)
    assert c["runs_priced"] == 1 and c["mean_cost_per_run_usd"] == pytest.approx((509 * 2 + 266 * 10) / 1e6)


def test_ai_cost_renders_before_and_after_measurement_begins():
    from agent.research.weekly_report import _render_ai_cost, ai_cost

    assert "not measured yet" in _render_ai_cost(ai_cost([_pred(T0)], T0))
    line = _render_ai_cost(ai_cost([_pred(T0, meta=_usage_meta())], T0))
    assert "per run" in line and "2026-09-23" in line and "news" in line
