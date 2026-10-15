"""The prospective direction shadow track (E034, research/DIRECTION_TRACK.md): inputs, frozen model, isolation."""

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from agent.direction_shadow import features as df_
from agent.direction_shadow.model import DirectionModel
from agent.research.direction_probability import INPUTS as E032_INPUTS
from agent.research.direction_probability import ONE_FEATURE as E032_ONE
from agent.shadow.features import reference_series


def _window():
    bars, extras = reference_series()
    return bars[-df_.WINDOW_HOURS:], df_.extras_rows_from_frame(extras)[-df_.WINDOW_HOURS:]


def test_the_inputs_are_exactly_e032s():
    assert df_.INPUTS == tuple(E032_INPUTS)
    assert [df_.ONE_FEATURE] == list(E032_ONE)
    assert df_.REGIME_FEATURE not in df_.INPUTS  # descriptive only


def test_input_row_computes_every_input_on_a_full_window():
    bars, extras = _window()
    values, rv, reason = df_.input_row(bars, extras)
    assert reason is None and set(values) == set(df_.INPUTS)
    assert all(isinstance(v, float) and not math.isnan(v) for v in values.values())
    assert rv is not None and rv > 0


def test_input_row_refuses_a_window_of_the_wrong_length():
    bars, extras = _window()
    values, rv, reason = df_.input_row(bars[1:], extras[1:])
    assert values == {} and "expected exactly 250" in reason


def test_a_missing_trade_record_makes_the_hour_unavailable_not_filled():
    bars, extras = _window()
    values, _, reason = df_.input_row(bars, extras[:-1])  # the reference hour's taker volume is missing
    assert reason is not None and "taker_buy_share_1h" in reason and values["taker_buy_share_1h"] is None


def test_the_reference_values_identify_every_input_and_are_deterministic():
    a, b = df_.reference_values(), df_.reference_values()
    assert set(a) == set(df_.INPUTS) and a == b
    assert all(len(v) == 5 and not any(math.isnan(x) for x in v) for v in a.values())


def _model(**kw):
    n = len(df_.INPUTS)
    base = dict(version="t", horizon_hours=1, features=df_.INPUTS, scaler_mean=np.zeros(n), scaler_scale=np.ones(n),
                coef=np.zeros(n), intercept=0.0, one_feature=df_.ONE_FEATURE, one_mean=0.5, one_scale=0.1, one_coef=-1.0,
                one_intercept=0.0, base_rate=0.51, scoring_version="0.2.0", sha256="x", training={}, provenance={})
    base.update(kw)
    return DirectionModel(**base)


def test_predict_is_the_logistic_on_standardised_inputs():
    row = {k: 1.0 for k in df_.INPUTS} | {"taker_buy_share_1h": 0.6}
    coef = np.arange(len(df_.INPUTS), dtype=float) / 10
    m = _model(coef=coef, intercept=-0.2)
    p_model, p_one, p_base = m.predict(row)
    x = np.array([row[k] for k in df_.INPUTS])
    assert p_model == pytest.approx(1 / (1 + math.exp(-(coef @ x - 0.2))), abs=1e-15)
    assert p_one == pytest.approx(1 / (1 + math.exp(-(-1.0 * (0.6 - 0.5) / 0.1))), abs=1e-15)
    assert p_base == 0.51


def test_predict_refuses_a_missing_input():
    row = {k: 1.0 for k in df_.INPUTS} | {"volume_score": None}
    assert _model().predict(row) is None
    assert _model().predict({k: 1.0 for k in df_.INPUTS} | {"trend_score": float("nan")}) is None


def test_the_export_never_opens_the_holdout():
    tree = ast.parse(Path("agent/research/export_direction_model.py").read_text(encoding="utf-8"))
    keywords = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
    assert "allow_holdout" not in keywords and "data" not in keywords  # build_frame's default stops at the holdout


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


def test_nothing_in_the_live_path_or_the_move_size_track_imports_the_direction_track():
    live = [Path("run.py"), Path("agent/orchestrator.py"), Path("agent/outcome_tracker.py"), Path("agent/healthcheck.py"),
            *Path("agent/scoring").glob("*.py"), *Path("agent/decision").glob("*.py"), *Path("agent/shadow").glob("*.py"),
            *Path("agent/api").glob("*.py"), *Path("agent/indicators").glob("*.py"), *Path("agent/patterns").glob("*.py"),
            Path("agent/research/live_checkpoint.py")]
    for path in live:
        assert not any(m.startswith("agent.direction_shadow") for m in _imports(path)), path


def test_the_direction_track_never_imports_the_reporting_layer_or_any_trading_code():
    for path in Path("agent/direction_shadow").glob("*.py"):
        mods = _imports(path)
        assert not any(m.startswith("agent.reporting") for m in mods), path
        assert not any(w in m for m in mods for w in ("order", "trade", "exchange", "broker")), path
