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
            "signal": signal, "overall_confidence": conf}


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
        r = {"as_of": T0 + i * H, "status": "ok", "status_reason": None, "live_close_match": True, "p_calibrated": 0.4 + 0.02 * i,
             "model_version": "move_size_1h_v1", "outcome_status": "ok" if i < 9 else None, "outcome_return": 0.004 if i % 2 else -0.001, "outcome_large": bool(i % 2)}
        rows.append(r)
    rows[2].update({"status": "unavailable", "status_reason": "missing inputs: rv_168", "p_calibrated": None, "outcome_status": None})
    rows[5]["live_close_match"] = False
    sh = shadow_record(rows, now)
    assert sh["n"] == 11 and sh["expected_hours"] == 12 and [m[11:13] for m in sh["missing_hours"]] == ["13"]
    assert sh["unavailable"] == 1 and sh["live_close_mismatch"] == 1
    assert sh["outcomes"]["ok"] == 7 and sh["outcomes"]["pending"] == 3  # rows 9,10,11 ok+pending; row 2 unavailable excluded
    assert sh["evaluation"]["n"] == 7 and "LIVE" in sh["evaluation"]["note"]
    assert shadow_record([], now) == {"n": 0, "note": "no shadow rows yet"}


def test_paper_record_reports_intervals_only_with_enough_hours():
    rng = np.random.default_rng(5)
    p = rng.uniform(0.1, 0.9, size=300)
    y = (rng.uniform(size=300) < p).astype(float)
    rec = paper_record(p, y, np.abs(rng.normal(size=300)) * p)
    assert "brier_rel_gain_ci95" in rec and "ece_ci95" in rec and rec["brier_rel_gain_ci95"][0] <= rec["brier_rel_gain"] <= rec["brier_rel_gain_ci95"][1]
    small = paper_record(p[:100], y[:100], np.abs(rng.normal(size=100)))
    assert "brier_rel_gain_ci95" not in small and "no intervals yet" in small["interval_note"]
