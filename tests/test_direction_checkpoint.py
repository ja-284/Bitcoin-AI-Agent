"""The direction track's registered readings (E034, research/DIRECTION_TRACK.md v1.1). Synthetic rows only: no
database and no real outcome. The real rows are read only by the command, and only when a reading is due."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from agent.direction_shadow.features import INPUTS
from agent.direction_shadow.model import load_model
from agent.research import direction_checkpoint as dc

HOUR = timedelta(hours=1)
MODEL = load_model()
START = datetime(2026, 10, 16, tzinfo=timezone.utc)


def _rows(n: int, seed: int = 1, skill: bool = True) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        as_of = START + i * HOUR
        feats = {k: float(v) for k, v in zip(INPUTS, rng.normal(0, 1, len(INPUTS)) * 0.2)}
        feats["taker_buy_share_1h"] = float(rng.uniform(0.3, 0.7))
        feats["taker_buy_share_6h"] = float(rng.uniform(0.4, 0.6))
        feats["tr_mean_14_rel"] = float(rng.uniform(0.002, 0.01))
        feats["trades_rel_168h"] = float(rng.uniform(0.5, 2.0))
        pm, pf, pb = MODEL.predict(feats)
        up = bool(rng.uniform() < (pm if skill else pb))
        ref = 100000.0
        ret = float(rng.uniform(0.0001, 0.01)) * (1 if up else -1)
        out.append({"id": i + 1, "as_of": as_of, "cutoff_at": as_of + HOUR, "fetched_at": as_of + HOUR + timedelta(minutes=12),
                    "created_at": as_of + HOUR + timedelta(minutes=12, seconds=5), "model_version": "direction_1h_v1",
                    "artefact_sha256": MODEL.sha256, "status": "ok", "features": feats, "regime_rv_168": 0.004,
                    "p_model": pm, "p_one_feature": pf, "p_base": pb, "horizon_hours": 1, "reference_close": ref,
                    "price_at_prediction": ref * (1 + float(rng.normal(0, 0.0005))), "live_close_match": True,
                    "live_scores_match": True, "outcome_status": "ok", "outcome_close": ref * (1 + ret),
                    "outcome_return": ret, "outcome_up": up})
    return out


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(dc, "N_BOOT", 60)  # the registered 2,000 make a reading slow; the logic is the same


def test_only_prospective_graded_ok_rows_of_this_model_are_eligible_in_time_order():
    rows = _rows(10)
    rows[2]["created_at"] = rows[2]["as_of"] + 2 * HOUR          # stored after its outcome candle closed
    rows[3]["status"] = "unavailable"
    rows[4]["outcome_status"] = None                             # not graded yet
    rows[5]["model_version"] = "direction_1h_v2"
    rows[6]["fetched_at"] = rows[6]["as_of"] + 2 * HOUR + timedelta(seconds=1)
    ok, late = dc.eligible(list(reversed(rows)))
    assert [r["id"] for r in ok] == [1, 2, 8, 9, 10]
    assert sorted(r["id"] for r in late) == [3, 7]


def test_the_operational_view_carries_no_outcome_based_figure():
    """Amendment 1.1: before a reading, only counts. Nothing that could reveal how the model is doing."""
    op = dc.operational(_rows(30), START + 40 * HOUR)
    assert set(op) == {"rows", "first_hour", "expected_hours_since_first", "status_counts", "eligible_graded", "not_prospective",
                       "pending_outcome", "outcome_unavailable", "live_close_mismatches", "live_scores_mismatches", "next_reading"}
    assert op["eligible_graded"] == 30 and op["next_reading"] == 1000 and op["expected_hours_since_first"] == 40  # START .. START + 39h


def test_a_reading_is_refused_before_its_size_and_reads_exactly_the_first_n():
    rows = _rows(1010)
    with pytest.raises(RuntimeError, match="not due"):
        dc.reading(rows[:999], 1000, START)
    doc = dc.reading(rows, 1000, START + 2000 * HOUR)
    assert doc["first_hour"] == rows[0]["as_of"].isoformat() and doc["last_hour"] == rows[999]["as_of"].isoformat()
    assert doc["verdict"] is None and "OPTIMISTIC" in doc["intervals"]
    assert doc["stats"]["integrity"]["probabilities_recompute_from_stored_inputs_max_abs_diff"] < 1e-12


def test_a_reading_is_written_once_and_never_rewritten(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "OUT_DIR", tmp_path)
    doc = dc.reading(_rows(1000), 1000, START + 2000 * HOUR)
    path = dc.write_once(doc)
    assert path.exists() and (tmp_path / "direction_checkpoint_1000h.json").exists()
    with pytest.raises(FileExistsError):
        dc.write_once(doc)


def test_the_verdict_rules_are_section_7():
    good = {"stated_minus_observed": {"point": 0.01}, "ece": 0.01}
    bad = {"stated_minus_observed": {"point": 0.05}, "ece": 0.01}
    assert dc.rule({"ci95": [0.0001, 0.002]}, good) == "IMPROVEMENT"
    assert dc.rule({"ci95": [0.0001, 0.002]}, bad) == "SKILL, BUT MISCALIBRATED"
    assert dc.rule({"ci95": [-0.001, 0.0004]}, good) == "NO IMPROVEMENT"
    assert dc.rule({"ci95": [-0.002, -0.0001]}, good) == "NO IMPROVEMENT (worse than the reference)"
    assert dc.rule({"ci95": [-0.0002, 0.0009]}, good) == "INSUFFICIENT EVIDENCE"


def test_only_the_6500_hour_reading_has_a_verdict():
    assert [n for n, r in dc.READINGS.items() if r["verdict"]] == [6500]
    assert list(dc.READINGS) == [1000, 3000, 6500]


def test_the_economics_charge_a_full_round_trip_per_traded_hour():
    p = np.array([0.6, 0.4, 0.6])
    entry = np.array([100.0, 100.0, np.nan])
    close = np.array([101.0, 99.0, 101.0])
    e = dc.economics(p, entry, close)
    assert e["hours_with_an_entry_price"] == 2 and e["hours_without"] == 1
    lf = e["rules"]["long_flat"]
    assert lf["traded_hours"] == 1
    assert lf["by_cost"]["standard"]["net_mean_per_traded_hour"]["point"] == pytest.approx(0.01 - 0.0022)
    sign = e["rules"]["sign"]
    assert sign["traded_hours"] == 2 and sign["gross_mean_per_traded_hour"]["point"] == pytest.approx(0.01)


def test_auc_is_the_mann_whitney_area():
    assert dc.auc(np.array([0.1, 0.2, 0.8, 0.9]), np.array([0, 0, 1, 1.0])) == 1.0
    assert dc.auc(np.array([0.5, 0.5, 0.5, 0.5]), np.array([0, 1, 0, 1.0])) == 0.5
    assert np.isnan(dc.auc(np.array([0.1, 0.2]), np.array([1.0, 1.0])))


def test_the_readings_read_only_and_never_touch_the_reporting_layer_or_the_holdout():
    src = Path(dc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith("agent.reporting") for m in mods)
    assert "conn.read_only = True" in src and dc.SQL.strip().upper().startswith("SELECT")
    keywords = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
    assert "allow_holdout" not in keywords
