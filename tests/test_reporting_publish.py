"""
The private stats publisher (agent/reporting/publish.py), without a database: it publishes exactly what the
reporting layer computes (nothing recalculated for the website), never an hour from the sealed holdout, only
through its two cache statements, and it is loud only when the snapshot has actually gone stale.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from agent.reporting import publish, views
from agent.reporting.source import Records
from agent.research.periods import HOLDOUT
from tests.test_reporting import AT, T0, pred, records, world

H = timedelta(hours=1)


def _with_details(rec: Records) -> Records:
    details = {p["as_of"]: {"explanation": f"why {p['id']}", "category_scores": [{"name": "trend", "score": 0.1, "weight": 0.25,
                                                                                  "is_independent": False}],
                            "created_at": p["created_at"]} for p in rec.predictions}
    return Records(rec.predictions, rec.outcomes, rec.shadow, rec.shadow_errors, rec.backend_state, rec.schema_version,
                   None, details)


def test_it_publishes_exactly_what_the_reporting_layer_computes():
    rec = _with_details(world())
    snapshot, runs = publish.build(rec, AT, AT, (0.003, 0.005), {})
    assert snapshot == views.document("all", views.report(rec, AT, (0.003, 0.005), {}), AT, AT)
    assert runs == {h: views.clean(r) for h, r in views.all_runs(rec, AT).items()}
    first = runs[T0]
    assert first["explanation"] == "why 1" and first["categories"][0]["name"] == "trend"
    assert list(runs) == sorted(runs) and len(runs) == len(views.known_at(rec, AT).predictions)
    json.dumps(snapshot, allow_nan=False), [json.dumps(r, allow_nan=False) for r in runs.values()]


def test_a_run_detail_saved_after_the_moment_is_not_published():
    rec = _with_details(world(hours=12))
    at = T0 + 5 * H
    runs = views.all_runs(rec, at)
    assert max(runs) == T0 + 3 * H  # hour 4 was saved at T0+5h12m
    assert all(r["explanation"] for r in runs.values())


def test_nothing_from_the_sealed_holdout_can_be_published():
    inside = HOLDOUT.start + timedelta(days=30)
    rec = records([pred(1, inside), pred(2, T0)])
    with pytest.raises(RuntimeError, match="sealed holdout"):
        publish.build(rec, AT, AT)
    publish.refuse_holdout([HOLDOUT.start - H, HOLDOUT.end])  # the edges are outside: no error


class _Cur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append(("execute", sql, params))

    def executemany(self, sql, rows):
        self.log.append(("executemany", sql, list(rows)))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self):
        self.log, self.commits = [], 0

    def cursor(self):
        return _Cur(self.log)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_store_sends_only_its_two_cache_statements_in_one_transaction(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(publish, "_cache_connection", lambda: conn)
    snapshot, runs = publish.build(world(hours=6), AT, AT)
    out = publish.store(snapshot, runs, AT, AT)
    assert [kind for kind, _, _ in conn.log] == ["execute", "executemany"] and conn.commits == 1
    assert conn.log[0][1] is publish.SNAPSHOT_SQL and conn.log[1][1] is publish.RUN_SQL
    assert len(conn.log[1][2]) == out["runs"] == 6
    assert json.loads(conn.log[0][2][3]) == snapshot


@pytest.mark.parametrize("age, code", [(timedelta(hours=1), 0), (timedelta(hours=4), 1), (None, 1)])
def test_a_failure_is_loud_only_once_the_snapshot_is_stale(monkeypatch, age, code):
    def boom(**kw):
        raise ConnectionError("database unreachable")

    recorded = []
    monkeypatch.setattr(publish, "load", boom)
    monkeypatch.setattr(publish, "snapshot_generated_at", lambda: None)
    monkeypatch.setattr(publish, "snapshot_age", lambda now: age)
    monkeypatch.setattr(publish.incidents, "record", recorded.append)
    assert publish.main([]) == code
    # the failure itself stays visible afterwards, whether or not the snapshot is stale yet
    assert [r["kind"] for r in recorded] == ["stats_publish_failed"] and "ConnectionError" in recorded[0]["detail"]


def test_a_dry_run_stores_nothing(monkeypatch, capsys):
    monkeypatch.setattr(publish, "load", lambda **kw: world(hours=3))
    monkeypatch.setattr(publish, "frozen_terciles", lambda: None)
    monkeypatch.setattr(publish, "computed_readings", lambda: {})

    def forbidden(*a, **kw):
        raise AssertionError("a dry run must not store")

    monkeypatch.setattr(publish, "store", forbidden)
    monkeypatch.setattr(publish, "snapshot_generated_at", lambda: datetime.now(timezone.utc) - timedelta(hours=9))
    monkeypatch.setattr(publish.incidents, "record", forbidden)  # a dry run records no incident either
    assert publish.main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["would_store"]["runs"] == 3


def test_a_stale_gap_is_recorded_before_the_new_snapshot_is_computed(monkeypatch):
    order = []
    monkeypatch.setattr(publish, "snapshot_generated_at", lambda: datetime.now(timezone.utc) - timedelta(hours=5))
    monkeypatch.setattr(publish.incidents, "record", lambda row: order.append(("incident", row["kind"])))
    monkeypatch.setattr(publish, "load", lambda **kw: order.append(("load", None)) or world(hours=3))
    monkeypatch.setattr(publish, "frozen_terciles", lambda: None)
    monkeypatch.setattr(publish, "computed_readings", lambda: {})
    monkeypatch.setattr(publish, "store", lambda *a, **kw: order.append(("store", None)) or {})
    assert publish.main([]) == 0
    assert order == [("incident", "stats_snapshot_was_stale"), ("load", None), ("store", None)]


def test_the_stale_rule_is_strictly_more_than_three_hours():
    now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    assert publish.stale_incident(None, now) is None
    assert publish.stale_incident(now - timedelta(hours=3), now) is None
    gap = publish.stale_incident(now - timedelta(hours=3, minutes=1), now)
    assert gap["kind"] == "stats_snapshot_was_stale" and gap["occurred_at"] == now - timedelta(hours=3, minutes=1)
    assert "08:59" in gap["detail"] and "12:00" in gap["detail"] and gap["incident_key"].startswith("publisher:stale:")


def test_the_stale_threshold_and_the_cache_tables_are_what_the_docs_say():
    assert publish.STALE_AFTER == timedelta(hours=3)
    assert publish.CACHE_TABLES == ("reporting_snapshot", "reporting_runs")
    assert datetime(2026, 9, 19, tzinfo=timezone.utc) >= HOLDOUT.end  # the live record begins after the holdout
