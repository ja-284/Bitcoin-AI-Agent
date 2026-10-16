"""The direction experiment's integrity check (agent/research/direction_integrity.py; addendum 2026-10-16, item 6).
Synthetic rows only. It must catch each integrity defect, and print counts only, never a probability or an outcome."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.direction_shadow.features import INPUTS
from agent.direction_shadow.model import load_model
from agent.research import direction_integrity as di
from agent.version import PIPELINE_VERSION

H = timedelta(hours=1)
T0 = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)
MODEL = load_model()
NOW = T0 + 30 * H


def _rows(n):
    feats = {k: 0.1 for k in INPUTS} | {"taker_buy_share_1h": 0.5, "taker_buy_share_6h": 0.5, "tr_mean_14_rel": 0.004, "trades_rel_168h": 1.0}
    pm, pf, pb = MODEL.predict(feats)
    out = []
    for i in range(n):
        a = T0 + i * H
        ref, close = 100.0 + i, 100.5 + i
        out.append({"as_of": a, "cutoff_at": a + H, "fetched_at": a + H + timedelta(minutes=12), "created_at": a + H + timedelta(minutes=12, seconds=3),
                    "model_version": "direction_1h_v1", "artefact_sha256": di.REGISTERED_SHA256, "pipeline_version": PIPELINE_VERSION,
                    "scoring_version": "0.2.0", "code_commit": "abc", "reference_close": ref, "status": "ok", "status_reason": None,
                    "features": dict(feats), "p_model": pm, "p_one_feature": pf, "p_base": pb, "horizon_hours": 1, "outcome_status": "ok",
                    "outcome_close": close, "outcome_return": (close - ref) / ref, "outcome_up": close > ref,
                    "outcome_checked_at": a + 2 * H + timedelta(minutes=12)})
    return out


def _state(rows, lost=(), errors=()):
    return {"rows": rows, "errors": list(errors), "lost": list(lost),
            "triggers": {"shadow_direction_guard_update": "O", "shadow_direction_forbid_delete": "O"}}


def _failed(results):
    return [name for name, ok, _ in results if not ok]


def test_a_clean_record_passes_every_check():
    assert _failed(di.check(_state(_rows(10)), MODEL, now=NOW)) == []


@pytest.mark.parametrize("field,value,check", [
    ("artefact_sha256", "0" * 64, "version"), ("scoring_version", "0.3.0", "version"),
    ("created_at", T0 + 2 * H + timedelta(minutes=1), "timestamps"),          # stored after the outcome candle closed
    ("fetched_at", T0 + timedelta(minutes=50), "timestamps"),                 # fetched before the reference candle closed
    ("outcome_checked_at", T0 + H + timedelta(minutes=30), "timestamps"),     # graded before the target candle closed
    ("p_model", 0.9, "preserved as predicted"),
    ("outcome_up", False, "graded correctly"), ("outcome_return", 0.5, "graded correctly"),
])
def test_each_defect_is_caught(field, value, check):
    rows = _rows(10)
    rows[0][field] = value
    assert check in _failed(di.check(_state(rows), MODEL, now=NOW))


def test_a_missing_hour_must_be_recorded_as_lost():
    rows = _rows(10)
    gap = rows.pop(4)["as_of"]
    assert "nothing skipped silently" in _failed(di.check(_state(rows), MODEL, now=NOW))
    assert "nothing skipped silently" not in _failed(di.check(_state(rows, lost=[gap]), MODEL, now=NOW))


def test_a_disabled_immutability_trigger_is_caught():
    s = _state(_rows(3))
    s["triggers"]["shadow_direction_guard_update"] = "D"
    assert "immutability" in _failed(di.check(s, MODEL, now=NOW))


def test_the_exchange_comparison_catches_a_wrong_close_and_a_wrong_input():
    rows = _rows(5)
    closes = {r["as_of"]: r["reference_close"] for r in rows} | {rows[-1]["as_of"] + H: rows[-1]["outcome_close"]}
    for r in rows[:-1]:
        closes[r["as_of"] + H] = r["outcome_close"]  # the next hour's candle closes where this row's outcome says
    inputs = {r["as_of"]: dict(r["features"]) for r in rows}
    ok = {"closes": dict(closes), "inputs": inputs}
    rows2 = [dict(r) for r in rows]
    for i, r in enumerate(rows2):
        r["reference_close"], r["outcome_close"] = closes[r["as_of"]], closes[r["as_of"] + H]
        r["outcome_return"] = (r["outcome_close"] - r["reference_close"]) / r["reference_close"]
        r["outcome_up"] = r["outcome_return"] > 0
    assert _failed(di.check(_state(rows2), MODEL, ok, now=NOW)) == []
    wrong_close = {"closes": dict(closes) | {rows2[1]["as_of"] + H: 1.0}, "inputs": inputs}
    assert "graded correctly" in _failed(di.check(_state(rows2), MODEL, wrong_close, now=NOW))
    wrong_input = {"closes": closes, "inputs": {**inputs, rows2[2]["as_of"]: {**inputs[rows2[2]["as_of"]], "trend_score": 0.7}}}
    assert "inputs reproduce" in _failed(di.check(_state(rows2), MODEL, wrong_input, now=NOW))


def test_it_prints_counts_only_and_reads_only():
    src = Path(di.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    printed = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print"]
    for p in printed:
        for word in ("p_model", "outcome_return", "outcome_up", "brier", "accuracy"):
            assert word not in p, (word, p)
    assert "conn.read_only = True" in src and "INSERT" not in src and "UPDATE " not in src and "DELETE FROM" not in src
