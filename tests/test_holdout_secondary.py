"""
The E023 secondary evaluation must not become a second route into the sealed holdout, and must not
be able to influence E014's verdict. No data, no database.
"""

from pathlib import Path

from agent.research import holdout_secondary as hs

import ast

SOURCE = Path("agent/research/holdout_secondary.py").read_text(encoding="utf-8")
EVAL = Path("agent/research/holdout_eval.py").read_text(encoding="utf-8")


def _names_used(source: str) -> set[str]:
    """Every name the CODE imports or calls -- parsed, so words in docstrings and comments do not count."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            names |= {a.name for a in node.names} | {node.module or ""}
        elif isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.Call):
            f = node.func
            names.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return names


def test_the_secondary_module_never_loads_data_itself():
    """Holdout candles enter only through holdout_eval's one guarded load_bars call."""
    used = _names_used(SOURCE)
    for forbidden in ("load_bars", "build_frame", "read_csv", "agent.research.history"):
        assert forbidden not in used, f"holdout_secondary must not use {forbidden}"


def test_holdout_eval_still_has_exactly_one_route_into_the_holdout():
    calls = [n for n in ast.walk(ast.parse(EVAL)) if isinstance(n, ast.Call)
             and any(k.arg == "allow_holdout" for k in n.keywords)]
    assert len(calls) == 1, "there must be exactly one load_bars(allow_holdout=...) call"


def test_the_guard_test_would_catch_a_new_route():
    """Perturbation: the parser must see a load_bars call added to the module."""
    assert "load_bars" in _names_used(SOURCE + "\nfrom agent.research.history import load_bars\nload_bars()\n")


def test_e014s_verdict_is_fixed_before_the_secondary_hypotheses_run():
    assert EVAL.index('results["verdicts"] = verdicts(results)') < EVAL.index("holdout_secondary.evaluate(")


def test_the_registered_constants_are_the_ones_in_e023():
    """A silent change here would turn a pre-registered test into a tuned one."""
    import json

    e023 = json.loads(Path("research/experiments/E023_holdout_secondary_hypotheses.json").read_text(encoding="utf-8"))
    text = json.dumps(e023["hypotheses"])
    assert (hs.H1_RATIO, hs.H3_MAX_SKILL, hs.H4_MAX_VOL_COST, hs.H5_MIN_SHARE) == (1.10, 0.01, 0.40, 0.95)
    for name in hs.E018_SIX:
        assert name in text
    assert "trades_rel_168h" in text


# ---------------------------------------------------------------- the pass rules, decided correctly
# evaluate() runs exactly once, on the holdout. Its pass rules are exercised here with a fake
# walk-forward whose forecast quality depends only on WHICH inputs it is given, so every outcome is
# known in advance -- including the case that separates H4's two clauses.
def _world(n_hours: int = 2400, seed: int = 0):
    from datetime import datetime, timedelta, timezone

    import numpy as np
    import pandas as pd

    from agent.research.feature_count import FULL
    from agent.shared.types import PriceBar

    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.004, size=n_hours + 1))
    bars = [PriceBar(start + timedelta(hours=i), c, c, c, c, 1.0, "test") for i, c in enumerate(closes)]
    idx = pd.DatetimeIndex([b.as_of for b in bars[:-1]])
    fwd = closes[1:] / closes[:-1] - 1
    df = pd.DataFrame({c: rng.normal(size=n_hours) for c in FULL}, index=idx)
    df["fwd_1h"] = fwd
    df["y"] = (np.abs(fwd) > 0.0025).astype(float)
    window = type("W", (), {"start": start + timedelta(hours=1200), "end": start + timedelta(hours=n_hours)})()
    return df, list(FULL), bars, window


def _fake_walk_forward(weights: dict):
    """Forecast quality q = min(0.8, sum of the weights of the inputs used); p = 0.5 + (y - 0.5) * q."""
    import pandas as pd

    def fit_and_score(frame, cols, horizon, window, calib_days, calibrator):
        rows = frame[frame[cols + ["y"]].notna().all(axis=1)]
        rows = rows[(rows.index >= pd.Timestamp(window.start)) & (rows.index < pd.Timestamp(window.end))]
        q = min(0.8, sum(weights.get(c, 0.0) for c in cols))
        return pd.DataFrame({"p": 0.5 + (rows["y"] - 0.5) * q, "y": rows["y"]}, index=rows.index), []
    return fit_and_score


def test_h4_passes_when_trade_intensity_leads_and_volatility_matters_little():
    df, cols, bars, window = _world()
    w = {c: 0.1 for c in cols} | {"trades_rel_168h": 0.5}
    e = hs.evaluate(df, cols, bars, window, _fake_walk_forward(w))
    assert e["H4"]["best_single_input"] == "trades_rel_168h"
    assert e["H4"]["volatility_group_cost"] < 0.40
    assert e["H4"]["pass"]


def test_h4_fails_when_a_volatility_input_is_the_best_single_input():
    """
    The case that separates H4's two clauses: removing the volatility group costs nothing here, but
    the best single input is a volatility one -- so the registered rule must FAIL. A rule that had
    quietly lost its first clause would pass it.
    """
    df, cols, bars, window = _world()
    w = {c: 0.1 for c in cols} | {"trades_rel_168h": 0.5, "tr_mean_14_rel": 0.6}
    e = hs.evaluate(df, cols, bars, window, _fake_walk_forward(w))
    assert e["H4"]["best_single_input"] == "tr_mean_14_rel"
    assert e["H4"]["volatility_group_cost"] < 0.40
    assert not e["H4"]["pass"]


def test_h5_follows_the_share_of_skill_kept_by_the_six_inputs():
    df, cols, bars, window = _world()
    weak_six = hs.evaluate(df, cols, bars, window, _fake_walk_forward({c: 0.1 for c in cols} | {"trades_rel_168h": 0.5}))
    assert weak_six["H5"]["share"] < 0.95 and not weak_six["H5"]["pass"]
    strong_six = hs.evaluate(df, cols, bars, window, _fake_walk_forward({c: 0.1 for c in cols} | {"tr_mean_14_rel": 0.6}))
    assert strong_six["H5"]["share"] >= 0.95 and strong_six["H5"]["pass"]


def test_the_fixed_and_scaled_models_are_trained_on_identical_rows():
    """
    Found by mutation testing: aligning only the SCORED rows is not enough. H2 compares a model on
    the fixed target with one on the volatility-scaled target; if hours where the scaled label does
    not exist (the first ~240 hours, or around a data gap) stayed in the fixed model's training data,
    the two would be trained on different rows and H2 would compare unlike with unlike.
    """
    import pandas as pd

    df, cols, bars, window = _world()
    seen = []
    inner = _fake_walk_forward({c: 0.1 for c in cols})

    def recording(frame, use_cols, *a):
        seen.append((tuple(use_cols), frame[frame[use_cols + ["y"]].notna().all(axis=1)].index))
        return inner(frame, use_cols, *a)

    hs.evaluate(df, cols, bars, window, recording)
    nine = [idx for used, idx in seen if len(used) == len(cols)]
    assert len(nine) == 2, "expected one nine-input fit per target"
    assert nine[0].equals(nine[1]), "the fixed- and scaled-target models were trained on different rows"
    assert len(nine[0]) < len(df), "the world must contain hours without a scaled label, or this proves nothing"


def test_every_comparison_uses_only_rows_inside_the_window():
    import pandas as pd

    df, cols, bars, window = _world()
    e = hs.evaluate(df, cols, bars, window, _fake_walk_forward({c: 0.1 for c in cols}))
    in_window = ((df.index >= pd.Timestamp(window.start)) & (df.index < pd.Timestamp(window.end))).sum()
    assert 0 < e["rows"] <= in_window


# ---------------------------------------------------------------- what E014 tests is pinned
def test_the_evaluation_refuses_to_run_on_an_unregistered_scoring_version(monkeypatch):
    """
    E014 once named scoring 0.1.0 while the code had moved to 0.2.0 -- nobody would have noticed
    until after the one-time run. Now a mismatch stops the run before any candle is loaded.
    """
    import pytest

    from agent.research import holdout_eval

    loads = []
    monkeypatch.setattr(holdout_eval, "load_bars", lambda *a, **k: loads.append(1))
    monkeypatch.setattr(holdout_eval, "SCORING_VERSION", "9.9.9")
    with pytest.raises(RuntimeError, match="registers"):
        holdout_eval.run("E014", unseal=False, dry_run=True)
    assert loads == [], "the version check must happen before any data is loaded"


def test_the_registered_version_is_the_one_e014_names():
    import json

    from agent.research import holdout_eval
    from agent.scoring.scorer import SCORING_VERSION

    e014 = json.loads(Path("research/experiments/E014_holdout_evaluation.json").read_text(encoding="utf-8"))
    assert holdout_eval.REGISTERED_SCORING_VERSION in e014["scoring_version"]
    assert holdout_eval.REGISTERED_SCORING_VERSION == SCORING_VERSION


def test_the_skill_measure_is_the_usual_one():
    import numpy as np

    y = np.array([0, 1, 0, 1, 1, 0, 1, 0], float)
    assert hs._skill(np.full(8, y.mean()), y) == 0.0            # the base rate itself has no skill
    assert hs._skill(y * 0.8 + 0.1, y) > 0.5                    # a nearly perfect forecast has a lot
