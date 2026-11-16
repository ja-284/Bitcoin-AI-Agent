"""
E043 (agent/research/fall_sources.py) på syntetiske data, uten de ekte øyeblikksbildene: egenskapene ved t ser aldri
en verdi stemplet etter t, målene er framtiden, et hull fylles aldri, målet skiller «varsler fall» fra «varsler bare
størrelse», og dom-reglene er de registrerte.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research import fall_sources as F

UTC = timezone.utc


def _series(n=24 * 40, seed=1, start=datetime(2022, 1, 1, tzinfo=UTC)):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="h", tz=UTC)
    closes = pd.Series(30000 * np.exp(np.cumsum(rng.normal(0, 0.005, n))), index=idx)
    dvol = pd.Series(50 + np.cumsum(rng.normal(0, 0.3, n)), index=idx)
    oi = pd.Series(1e5 * np.exp(np.cumsum(rng.normal(0, 0.002, n))), index=idx)
    longs = pd.Series(9e4 * np.exp(np.cumsum(rng.normal(0, 0.001, n))), index=idx)
    shorts = pd.Series(2e3 * np.exp(np.cumsum(rng.normal(0, 0.003, n))), index=idx)
    return closes, dvol, oi, longs, shorts


def test_features_at_t_never_see_a_value_stamped_after_t():
    a = _series()
    cut = a[0].index[500]
    changed = []
    for s in a:
        s2 = s.copy()
        s2[s2.index > cut] *= 1.7
        changed.append(s2)
    fa, fb = F.build_frame(*a), F.build_frame(*changed)
    cols = [*F.FEATURES, F.CONTROL]
    x, y = fa.loc[:cut, cols], fb.loc[:cut, cols]
    assert ((x == y) | (x.isna() & y.isna())).all().all()
    assert not np.isclose(fa.loc[cut, "r1"], fb.loc[cut, "r1"])  # the target IS the future


def test_the_targets_and_features_are_the_registered_formulas():
    closes, dvol, oi, longs, shorts = _series()
    f = F.build_frame(closes, dvol, oi, longs, shorts)
    t = closes.index[300]
    h = pd.Timedelta(hours=1)
    assert f.loc[t, "r1"] == pytest.approx(np.log(closes[t + h] / closes[t]))
    assert f.loc[t, "r24"] == pytest.approx(np.log(closes[t + 24 * h] / closes[t]))
    assert f.loc[t, "F1_dvol_chg24"] == pytest.approx(np.log(dvol[t] / dvol[t - 24 * h]))
    assert f.loc[t, "F3_oi_chg24"] == pytest.approx(np.log(oi[t] / oi[t - 24 * h]))
    assert f.loc[t, "F4_oi_x_ret"] == pytest.approx(np.log(oi[t] / oi[t - 24 * h]) * np.log(closes[t] / closes[t - 24 * h]))
    ls = np.log(longs / shorts)
    assert f.loc[t, "F5_margin_ls_chg24"] == pytest.approx(ls[t] - ls[t - 24 * h])
    r = np.log(closes / closes.shift(1))
    rv = np.sqrt((r.loc[t - 23 * h:t] ** 2).mean() * 24 * 365)
    assert f.loc[t, "F2_iv_rv"] == pytest.approx(np.log(dvol[t] / 100 / rv))


def test_a_gap_is_never_filled():
    closes, dvol, oi, longs, shorts = _series()
    t = closes.index[400]
    h = pd.Timedelta(hours=1)
    f = F.build_frame(closes, dvol.drop(t - 24 * h), oi.drop(t), longs, shorts)
    assert np.isnan(f.loc[t, "F1_dvol_chg24"]) and np.isnan(f.loc[t, "F3_oi_chg24"])
    g = F.build_frame(closes.drop(t - 5 * h), dvol, oi, longs, shorts)
    assert np.isnan(g.loc[t, "F2_iv_rv"]) and np.isnan(g.loc[t - 6 * h, "r1"])  # no 24 consecutive hours; no next candle


def test_the_statistic_rewards_warning_of_falls_and_not_mere_size():
    rng = np.random.default_rng(5)
    n = 200_000  # enough points that sampling noise (SD ≈ 0.007 for the contrast) cannot pass for an effect
    x = rng.normal(size=n)
    y_fall = rng.normal(size=n) - 0.8 * (x > 1.28)              # high x: more falls
    y_size = rng.normal(size=n) * np.where(np.abs(x) > 1.28, 2.5, 1.0)  # extreme x: bigger moves both ways
    c_fall = F.contrast(np.column_stack([x, y_fall]))
    c_size = F.contrast(np.column_stack([x, y_size]))
    assert c_fall > 0.15 and abs(c_size) < 0.03
    assert F.contrast(np.column_stack([-x, y_fall])) == pytest.approx(-c_fall)  # the sign follows the feature


def _result(ce, cv, years):
    return {"exploration": {"C": ce}, "validation": {"C": cv}, "years": dict(zip("abcde", years))}


@pytest.mark.parametrize("ce,cv,years,p,want", [
    (0.06, 0.07, [0.1, 0.1, 0.1, 0.1, -0.1], 0.01, "SUPPORTED"),
    (0.06, 0.04, [0.1, 0.1, 0.1, 0.1, 0.1], 0.01, "INCONCLUSIVE"),     # below the practical bar
    (0.06, 0.07, [0.1, 0.1, 0.1, 0.1, 0.1], 0.20, "INCONCLUSIVE"),     # not significant after Holm
    (-0.06, 0.07, [0.1, 0.1, 0.1, 0.1, 0.1], 0.01, "NOT_SUPPORTED"),   # the sign flips between the periods
    (0.06, 0.07, [0.1, 0.1, 0.1, -0.1, -0.1], 0.01, "NOT_SUPPORTED"),  # only 3 of 5 years
])
def test_the_verdicts_are_the_registered_rules(ce, cv, years, p, want):
    assert F.verdict(_result(ce, cv, years), p) == want


def test_the_periods_and_settings_are_the_registered_ones():
    assert F.EXPLORATION == (datetime(2021, 4, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC))
    assert F.VALIDATION == (datetime(2024, 1, 1, tzinfo=UTC), F.HOLDOUT.start)
    assert (F.N_BOOT, F.SEED, F.ALPHA, F.PRACTICAL) == (2000, 43, 0.05, 0.05)
    assert F.HORIZONS == {"1h": ("r1", 48), "24h": ("r24", 7)} and len(F.FEATURES) == 5
