"""
Tests for the E020 model-family comparison. The comparison is only meaningful if the extra
columns are exactly what was declared, if adding them cannot change which rows are available,
and if the tree model is deterministic -- otherwise "the same experiment" would not reproduce.
"""

import itertools

import numpy as np
import pandas as pd
import pytest

from agent.research import model_family as mf


def _frame(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({c: rng.normal(size=n) for c in mf.FULL}, index=idx)


def test_interactions_are_exactly_the_declared_set():
    df, added = mf.interaction_columns(_frame())
    squares = ["sq_%s" % c for c in mf.CONTINUOUS]
    products = ["x_%s__%s" % (a, b) for a, b in itertools.combinations(mf.CONTINUOUS, 2)]
    assert added == squares + products
    assert len(added) == len(mf.CONTINUOUS) + len(mf.CONTINUOUS) * (len(mf.CONTINUOUS) - 1) // 2 == 21
    assert len(set(added)) == len(added)
    assert not set(added) & set(mf.FULL), "an interaction column must not shadow an input"


def test_interaction_values_are_the_products_they_claim_to_be():
    df, _ = mf.interaction_columns(_frame())
    a, b = mf.CONTINUOUS[0], mf.CONTINUOUS[1]
    assert np.allclose(df["sq_%s" % a].to_numpy(), df[a].to_numpy() ** 2)
    assert np.allclose(df["x_%s__%s" % (a, b)].to_numpy(), df[a].to_numpy() * df[b].to_numpy())


def test_adding_interactions_cannot_change_which_rows_are_available():
    """
    A product is missing exactly when one of its parents is. If that were not true, the
    interaction model would train and be scored on a different set of hours, and the
    comparison with the incumbent would be meaningless.
    """
    base = _frame()
    base.loc[base.index[5], mf.CONTINUOUS[0]] = np.nan
    df, added = mf.interaction_columns(base)
    parents_ok = base[mf.FULL].notna().all(axis=1)
    all_ok = df[mf.FULL + added].notna().all(axis=1)
    assert parents_ok.equals(all_ok)


def test_tree_settings_are_fixed_and_deterministic():
    assert mf.TREE_PARAMS["early_stopping"] is False, "early stopping would split off a random slice"
    assert mf.TREE_PARAMS["random_state"] == 0, "an unset seed would make the experiment unreproducible"


def test_tree_model_gives_the_same_answer_twice():
    rng = np.random.default_rng(2)
    X = pd.DataFrame(rng.normal(size=(800, 4)), columns=list("abcd"))
    y = (X["a"] + rng.normal(scale=0.5, size=800) > 0).astype(float).to_numpy()
    a, b = mf.TreeModel(), mf.TreeModel()
    a.fit(X, y)
    b.fit(X, y)
    assert np.array_equal(a.predict_proba(X), b.predict_proba(X))


def test_tree_model_returns_probabilities():
    rng = np.random.default_rng(3)
    X = pd.DataFrame(rng.normal(size=(600, 3)), columns=list("abc"))
    y = (rng.uniform(size=600) < 0.4).astype(float)
    m = mf.TreeModel()
    m.fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (600,)
    assert p.min() >= 0.0 and p.max() <= 1.0
    assert p.mean() == pytest.approx(y.mean(), abs=0.15)
