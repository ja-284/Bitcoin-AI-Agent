"""
Backend Phase G: scoring 0.1.0 is pinned end to end. Three windows of a fixed synthetic
series produce fixed indicator values, category scores, weights, patterns, confidence and
signal (tests/golden_scoring_0_1_0.json). Any change to a formula, weight, threshold or
window length fails this test -- which is the point: such a change must come with a new
SCORING_VERSION (or PIPELINE_VERSION) and a deliberate, reviewable update of the pin.
"""

import json
from pathlib import Path

import pytest

from agent.indicators.engine import HISTORY_HOURS
from agent.research.replay import analyze_window_detailed
from agent.scoring.scorer import SCORING_VERSION
from agent.shadow.features import reference_series
from agent.version import PIPELINE_VERSION

GOLDEN = json.loads(Path(__file__).with_name("golden_scoring_0_1_0.json").read_text(encoding="utf-8"))


def test_versions_are_the_pinned_ones():
    assert SCORING_VERSION == "0.1.0" and PIPELINE_VERSION == "0.2.0"  # bump deliberately, together with the golden file


def test_scoring_0_1_0_reproduces_the_golden_values():
    bars, _ = reference_series(600)
    for expected, i in zip(GOLDEN, (299, 449, 599)):
        row = analyze_window_detailed(bars[i + 1 - HISTORY_HOURS : i + 1])
        for k, v in expected.items():
            if isinstance(v, float):
                assert row[k] == pytest.approx(v, rel=1e-9, abs=1e-12), k
            else:
                assert row[k] == v, k


def test_schema_version_constant_matches_the_sql():
    import re

    from agent.database.db import SCHEMA_PATH, SCHEMA_VERSION

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    m = re.search(r"VALUES \('schema_version', '(\d+)'\)", sql)
    assert m and m.group(1) == SCHEMA_VERSION
