"""
Tests for publishing the backend state.

The property that matters most is negative: publishing must never be able to fail the hourly
job. That is the lesson of the 2026-09-21 incident, where a research add-on turned the job red
every other hour while the live record was perfectly healthy. No database needed here.
"""

import json

import pytest

from agent.api import publish as pub


def test_a_publish_failure_never_fails_the_job(monkeypatch, caplog):
    """Anything at all going wrong must still exit 0: the previous snapshot simply stays."""
    def boom():
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(pub, "backend_state", boom)
    monkeypatch.setattr("sys.argv", ["publish"])
    assert pub.main() == 0
    assert "Could not publish" in caplog.text
    assert "database is on fire" in caplog.text


def test_a_dry_run_stores_nothing(monkeypatch, capsys):
    stored = []
    monkeypatch.setattr(pub, "backend_state", lambda: {"contract_version": "1", "generated_at": "t", "x": 1})
    monkeypatch.setattr(pub, "publish", lambda state=None: stored.append(state))
    monkeypatch.setattr("sys.argv", ["publish", "--dry-run"])
    assert pub.main() == 0
    assert stored == [], "a dry run must not write"
    assert json.loads(capsys.readouterr().out)["contract_version"] == "1"


def test_the_published_state_is_serialisable_and_carries_its_version():
    """A reader has to be able to refuse a shape it does not understand."""
    from datetime import datetime, timedelta, timezone

    from agent.api import state as api

    now = datetime(2026, 9, 22, 19, 5, tzinfo=timezone.utc)
    counts = {"predictions": 0, "first_prediction": None, "latest_prediction": None,
              "missing_hours_last_48h": 0, "shadow_rows": 0, "shadow_errors_last_24h": 0}
    s = api.assemble(None, None, counts, {"by_horizon": [], "latest_1h": [], "note": ""}, now)
    text = json.dumps(s, default=str)
    assert json.loads(text)["contract_version"] == api.CONTRACT_VERSION
    assert "generated_at" in s


def test_the_hourly_job_publishes_after_the_record_and_before_the_heartbeat():
    """
    Order is the whole point. After the prediction, the self-check and the shadow steps, so the
    snapshot describes the hour's finished work; before the heartbeat, which must mean "every
    step ran". A publish placed before the self-check could describe an hour that then failed it.
    """
    from pathlib import Path

    wf = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")
    order = [wf.index(s) for s in ("python run.py", "python -m agent.healthcheck", "python -m agent.shadow.outcomes",
                                   "python -m agent.api.publish", "HEARTBEAT_URL\" >")]
    assert order == sorted(order), "the publish step is out of place in the hourly workflow"


def test_the_schema_declares_a_single_row_and_says_why_it_may_be_overwritten():
    """
    Every other table in this project is append-only. This one is not, and the exception has to
    be justified in the schema itself -- otherwise a future reader could take it as a precedent.
    """
    sql = pub.SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CHECK (id = 1)" in sql
    assert "not a record" in sql.lower() or "no history" in sql.lower()
    assert "contract_version" in sql
