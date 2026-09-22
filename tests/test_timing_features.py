"""
Tests for E022's comparison machinery.

The experiment reports "3 of 3 predictions held", and that sentence is only worth anything if
the checker can also say "failed". So each prediction is tested in BOTH directions on synthetic
inputs -- a checker that always agrees with itself is not evidence of anything.
"""

import json

import pytest

from agent.research import timing_features as tf
from agent.research.feature_count import FULL, GROUPS_UNDER_TEST


def _target(order: list[str], vol_cost: float) -> dict:
    return {"selection_order": order,
            "selection_k": {c: i + 1 for i, c in enumerate(order)},
            "group_ablation_skill_cost": {g: vol_cost if g == "volatility" else 0.2 for g in GROUPS_UNDER_TEST},
            "skill_by_k": {i + 1: 0.01 * (i + 1) for i in range(len(order))},
            "validation": {"n": 100, "base_rate": 0.5, "brier": 0.2, "skill": 0.07, "ece": 0.01,
                           "rho_p_vs_abs_return": 0.3},
            "exploration": {"n": 100, "base_rate": 0.5, "brier": 0.2, "skill": 0.1, "ece": 0.01},
            "coefficients_median": {c: 0.1 for c in FULL},
            "coefficient_sign_agreement": {c: 1.0 for c in FULL}}


def test_the_level_and_relative_groups_partition_the_inputs():
    assert sorted(tf.LEVEL_FEATURES + tf.RELATIVE_FEATURES) == sorted(FULL)
    assert not set(tf.LEVEL_FEATURES) & set(tf.RELATIVE_FEATURES)


def test_order_of_maps_each_feature_to_when_it_was_picked():
    steps = [{"k": 1, "added": "a"}, {"k": 2, "added": "b"}, {"k": 3, "added": "c"}]
    assert tf.order_of(steps) == {"a": 1, "b": 2, "c": 3}


def test_all_three_predictions_hold_when_they_should():
    fixed = _target(["tr_mean_14_rel", "trades_rel_24h", "rv_168", "hour_cos", "hour_sin",
                     "is_weekend", "trades_rel_168h", "rv_24", "vol_ratio_24_168"], vol_cost=0.61)
    scaled = _target(["trades_rel_168h", "tr_mean_14_rel", "rv_168", "is_weekend", "hour_sin",
                      "hour_cos", "vol_ratio_24_168", "rv_24", "trades_rel_24h"], vol_cost=0.14)
    p = tf.check_predictions(fixed, scaled)
    assert all(v["holds"] for v in p.values())
    assert p["P1_level_later_and_relative_earlier"]["level_features_selected_later"] == ["tr_mean_14_rel"]
    assert p["P3_first_pick_is_not_tr_mean_14_rel"]["first_against_scaled"] == "trades_rel_168h"


def test_p1_fails_when_nothing_moves():
    order = ["tr_mean_14_rel", "trades_rel_24h", "rv_168", "hour_cos", "hour_sin",
             "is_weekend", "trades_rel_168h", "rv_24", "vol_ratio_24_168"]
    p = tf.check_predictions(_target(order, 0.61), _target(order, 0.14))
    assert not p["P1_level_later_and_relative_earlier"]["holds"]
    assert p["P1_level_later_and_relative_earlier"]["level_features_selected_later"] == []


def test_p1_fails_when_only_one_half_moves():
    """
    A level feature moving later is not enough on its own -- the prediction had two clauses.
    Here two LEVEL features swap places, so a level feature is picked later while every
    relative feature stays exactly where it was.
    """
    fixed = _target(["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h",
                     "trades_rel_168h", "hour_sin", "hour_cos", "is_weekend"], 0.61)
    scaled = _target(["rv_24", "tr_mean_14_rel", "rv_168", "vol_ratio_24_168", "trades_rel_24h",
                      "trades_rel_168h", "hour_sin", "hour_cos", "is_weekend"], 0.14)
    p = tf.check_predictions(fixed, scaled)
    assert p["P1_level_later_and_relative_earlier"]["level_features_selected_later"] == ["tr_mean_14_rel"]
    assert p["P1_level_later_and_relative_earlier"]["relative_features_selected_earlier"] == []
    assert not p["P1_level_later_and_relative_earlier"]["holds"]


def test_p2_fails_when_volatility_still_dominates():
    order = list(FULL)
    p = tf.check_predictions(_target(order, 0.61), _target(order, 0.55))
    assert not p["P2_volatility_group_costs_less_than_40pct"]["holds"]


def test_p2_is_judged_at_the_declared_boundary():
    order = list(FULL)
    assert tf.check_predictions(_target(order, 0.6), _target(order, 0.3999))["P2_volatility_group_costs_less_than_40pct"]["holds"]
    assert not tf.check_predictions(_target(order, 0.6), _target(order, 0.40))["P2_volatility_group_costs_less_than_40pct"]["holds"]


def test_p3_fails_when_the_same_feature_is_picked_first():
    order = ["tr_mean_14_rel"] + [c for c in FULL if c != "tr_mean_14_rel"]
    p = tf.check_predictions(_target(order, 0.61), _target(order, 0.14))
    assert not p["P3_first_pick_is_not_tr_mean_14_rel"]["holds"]


def test_the_report_renders_after_a_json_round_trip():
    """The integer feature-count keys become strings in JSON; the report must survive that."""
    results = {
        "by_target": {"F_fixed": _target(list(FULL), 0.61), "V_vol_scaled": _target(list(FULL), 0.14)},
        "tripwire": {"e021_validation_skill": 0.07363, "this_run": 0.07363, "difference": 0.0,
                     "tolerance": 0.002, "fired": False},
        "predictions": tf.check_predictions(_target(list(FULL), 0.61), _target(list(FULL), 0.14)),
        "summary": {"n_held": 1, "statement": "x"},
        "generated_at": "now", "pipeline_version": "0.2.0", "folds": 27, "variants_evaluated": 96,
        "level_features": tf.LEVEL_FEATURES, "relative_features": tf.RELATIVE_FEATURES,
    }
    direct = tf.render(results)
    round_tripped = tf.render(json.loads(json.dumps(results)))
    assert direct == round_tripped
    assert "Skill by feature count" in direct
