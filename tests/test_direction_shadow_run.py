"""The direction track's hourly step and grading (E034): pure parts and failure recording. No network, no database."""

from datetime import datetime, timedelta, timezone

import pytest

import agent.direction_shadow.db as ddb
from agent.data_providers import binance
from agent.direction_shadow import features as df_
from agent.direction_shadow import outcomes, run
from agent.direction_shadow.model import load_model
from agent.shadow.features import reference_series

HOUR = timedelta(hours=1)
MODEL = load_model()


def _window():
    bars, extras = reference_series()
    return bars[-df_.WINDOW_HOURS:], df_.extras_rows_from_frame(extras)[-df_.WINDOW_HOURS:]


def _compute(**kw):
    bars, extras = _window()
    cutoff = bars[-1].as_of + HOUR
    args = dict(model=MODEL, bars=bars, extras_rows=extras, open_candles=[(cutoff, 123.4)],
                fetched_at=cutoff + timedelta(minutes=12), scoring_version="0.2.0")
    args.update(kw)
    return run.compute(**args)


def test_a_full_window_gives_all_three_probabilities_and_everything_needed_to_recompute_them():
    row = _compute()
    assert row["status"] == "ok" and row["status_reason"] is None
    assert row["p_model"] == MODEL.predict(row["features"])[0] and row["p_base"] == MODEL.base_rate
    assert set(row["features"]) == set(df_.INPUTS) and row["regime_rv_168"] > 0
    assert row["artefact_sha256"] == MODEL.sha256 and row["model_version"] == "direction_1h_v1"
    assert row["cutoff_at"] == row["as_of"] + HOUR and row["price_at_prediction"] == 123.4


def test_the_price_at_prediction_is_never_an_input():
    a, b = _compute(), _compute(open_candles=[(_window()[0][-1].as_of + HOUR, 999999.0)])
    assert a["features"] == b["features"] and (a["p_model"], a["p_one_feature"]) == (b["p_model"], b["p_one_feature"])
    assert "price_at_prediction" not in df_.INPUTS


def test_the_price_at_prediction_comes_only_from_the_target_candle():
    later = _window()[0][-1].as_of + 2 * HOUR
    assert _compute(open_candles=[(later, 1.0)])["price_at_prediction"] is None
    assert _compute(open_candles=[])["price_at_prediction"] is None


def test_a_fetch_before_the_reference_candle_closed_is_refused():
    bars, _ = _window()
    with pytest.raises(RuntimeError, match="before the reference candle closed"):
        _compute(fetched_at=bars[-1].as_of + timedelta(minutes=59))


def test_a_gap_makes_the_hour_unavailable_with_no_probability():
    all_bars, all_extras = reference_series()
    rows = df_.extras_rows_from_frame(all_extras)
    n = df_.WINDOW_HOURS + 1  # one hour more than a window, then one hour in the middle taken out
    bars, extras = all_bars[-n:], rows[-n:]
    row = _compute(bars=bars[:100] + bars[101:], extras_rows=extras[:100] + extras[101:])
    assert row["status"] == "unavailable" and "gap" in row["status_reason"]
    assert row["p_model"] is None and row["p_one_feature"] is None and row["p_base"] is None


def test_another_scoring_version_makes_the_hour_unavailable():
    row = _compute(scoring_version="0.3.0")
    assert row["status"] == "unavailable" and "needs 0.2.0" in row["status_reason"] and row["p_model"] is None


def test_the_fetch_builds_closed_candles_exactly_as_the_move_size_shadow_does(monkeypatch):
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    ms = lambda t: int(t.timestamp() * 1000)  # noqa: E731
    payload = []
    for i in range(252, -1, -1):  # 252 closed hours, then the open one
        o = now - i * HOUR
        payload.append([ms(o), "1", "2", "0.5", str(100 + i), "10", ms(o + HOUR) - 1, "x", 50 + i, str(4 + i / 1000), "0", "0"])
    monkeypatch.setattr(binance, "_get_klines", lambda params, **kw: [list(k) for k in payload])
    bars, extras, still_open, _ = run.fetch(df_.WINDOW_HOURS)
    ref_bars, ref_extras = binance.BinanceProvider().get_hourly_klines_with_extras(df_.WINDOW_HOURS)
    assert bars == ref_bars and extras == ref_extras and len(bars) == df_.WINDOW_HOURS
    assert still_open == [(now, 100.0)] and bars[-1].as_of + HOUR == now  # set aside, never in the window


def test_the_cross_check_compares_the_close_and_the_four_category_scores():
    row = _compute()
    scores = {k: row["features"][k] for k in df_.CATEGORY_INPUTS}
    run.cross_check(row, (row["reference_close"], scores))
    assert row["live_close_match"] is True and row["live_scores_match"] is True
    run.cross_check(row, (row["reference_close"] + 1, scores | {"trend_score": scores["trend_score"] + 0.1}))
    assert row["live_close_match"] is False and row["live_scores_match"] is False
    fresh = _compute()
    run.cross_check(fresh, None)
    assert fresh["live_close_match"] is None and fresh["live_scores_match"] is None


def test_a_failure_is_recorded_and_the_step_exits_0(monkeypatch):
    recorded = []
    monkeypatch.setattr(run, "load_model", lambda version: (_ for _ in ()).throw(ValueError("artefact broken")))
    monkeypatch.setattr(ddb, "save_run_error", lambda row: recorded.append(row) or 1)
    assert run.run_and_record() == 0
    assert recorded[0]["step"] == "load_model" and recorded[0]["error_type"] == "ValueError"


def test_if_even_recording_fails_the_step_fails_so_it_is_seen(monkeypatch):
    monkeypatch.setattr(run, "load_model", lambda version: (_ for _ in ()).throw(ValueError("artefact broken")))
    monkeypatch.setattr(ddb, "save_run_error", lambda row: (_ for _ in ()).throw(RuntimeError("database down")))
    assert run.run_and_record() == 1


def test_grading_stores_a_fraction_and_a_tie_is_not_up():
    ret, up = outcomes.grade(100.0, 100.5)
    assert ret == pytest.approx(0.005) and up is True
    assert outcomes.grade(100.0, 99.0)[1] is False and outcomes.grade(100.0, 100.0) == (0.0, False)


def test_grading_finds_the_target_candle_by_timestamp_and_marks_a_missing_one_unavailable(monkeypatch):
    as_of = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    saved = []
    monkeypatch.setattr(ddb, "rows_awaiting_outcome", lambda now: [(7, as_of, 100.0, 1)])
    monkeypatch.setattr(ddb, "save_outcome", lambda *a: saved.append(a))

    class Provider:
        def __init__(self, bar):
            self.bar, self.asked = bar, []

        def get_bar_at(self, t):
            self.asked.append(t)
            return self.bar

    from agent.shared.types import PriceBar

    p = Provider(PriceBar(as_of + HOUR, 1, 1, 1, 101.0, 1, "binance"))
    assert outcomes.track(now=as_of + 3 * HOUR, provider=p)["graded"] == 1
    assert p.asked == [as_of + HOUR] and saved[-1][:5] == (7, 101.0, pytest.approx(0.01), True, "ok")
    assert outcomes.track(now=as_of + 3 * HOUR, provider=Provider(None))["deferred"] == 1
    assert outcomes.track(now=as_of + 9 * HOUR, provider=Provider(None))["unavailable"] == 1 and saved[-1][4] == "unavailable"


def test_a_grading_failure_is_recorded_and_exits_0(monkeypatch):
    recorded = []
    monkeypatch.setattr(ddb, "rows_awaiting_outcome", lambda now: (_ for _ in ()).throw(RuntimeError("database down")))
    monkeypatch.setattr(ddb, "save_run_error", lambda row: recorded.append(row) or 1)
    assert outcomes.track_and_record() == 0 and recorded[0]["step"] == "outcomes"


def test_the_schema_makes_rows_immutable_and_errors_append_only():
    """Text-level (the triggers are proven on real Postgres in tests/integration): the guards are present as written."""
    from pathlib import Path

    code = chr(10).join(line.split("--", 1)[0] for line in Path("agent/direction_shadow/schema.sql").read_text(encoding="utf-8").splitlines())
    sql = " ".join(code.split())  # comments removed, so a phrase in a comment can never stand in for the code
    assert "CREATE TRIGGER shadow_direction_guard_update BEFORE UPDATE ON shadow_direction" in sql
    assert "IF (to_jsonb(NEW) - outcome) IS DISTINCT FROM (to_jsonb(OLD) - outcome) THEN" in sql
    assert "IF OLD.outcome_status IS NOT NULL THEN" in sql
    assert "CREATE TRIGGER shadow_direction_forbid_delete BEFORE DELETE ON shadow_direction" in sql
    assert "CREATE TRIGGER shadow_direction_errors_append_only BEFORE UPDATE OR DELETE ON shadow_direction_errors" in sql
    assert "CHECK (fetched_at >= cutoff_at)" in sql and "CHECK (cutoff_at = as_of + interval '1 hour')" in sql
