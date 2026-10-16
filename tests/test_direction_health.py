"""
The direction track's own monitor (agent/direction_shadow/health.py; addendum 2026-10-16, item 5): failure and overdue
detection, a late-but-recoverable hour told apart from a lost one, one alert per incident, recovery, and separation
from the main model's health. Synthetic rows only; no database, no network.
"""

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agent.direction_shadow.health as dh

H = timedelta(hours=1)
T0 = datetime(2026, 10, 16, 0, tzinfo=timezone.utc)


def _rows(hours, status="ok", reason=None):
    return [{"as_of": T0 + i * H, "status": status, "status_reason": reason} for i in hours]


def _at(hour_index, minute=12):
    """A run at :minute of the hour after hour_index's candle closed scores hour_index."""
    return T0 + (hour_index + 1) * H + timedelta(minutes=minute)


def test_healthy_when_the_latest_closed_hour_is_recorded():
    a = dh.assess(_rows(range(10)), [], _at(9))
    assert a.state == "healthy" and a.send == ["success"] and a.new_lost == [] and not a.record_recovered


def test_a_missing_latest_hour_before_its_deadline_is_late_not_failed():
    a = dh.assess(_rows(range(9)), [], _at(9, minute=40))  # hour 9 not recorded yet; its deadline is hour 11:00
    assert a.state == "late but recoverable" and a.send == [] and a.new_lost == []


def test_an_hour_past_its_deadline_without_an_observation_is_lost_and_alerts_once():
    rows = _rows([0, 1, 2, 4, 5])  # hour 3 never recorded
    a = dh.assess(rows, [], _at(5))
    assert a.new_lost == [T0 + 3 * H] and a.send == ["fail", "success"] and a.record_recovered
    again = dh.assess(rows, [{"kind": "hour_lost", "hour": T0 + 3 * H}, {"kind": "recovered", "hour": T0 + 5 * H}], _at(5))
    assert again.new_lost == [] and again.send == ["success"], "a recorded hour must never alert twice"


def test_a_persisting_failure_records_each_new_lost_hour_but_alerts_only_once():
    rows = _rows([0, 1, 2])
    first = dh.assess(rows, [], _at(4))  # hours 3 and 4 missing; hour 3 past its deadline (5:00 < 5:12)
    assert first.new_lost == [T0 + 3 * H] and first.send == ["fail"] and first.state == "failing"
    events = [{"kind": "hour_lost", "hour": T0 + 3 * H}]
    later = dh.assess(rows, events, _at(6))  # still failing: hours 4 and 5 are now lost too
    assert later.new_lost == [T0 + 4 * H, T0 + 5 * H] and later.send == [] and later.state == "failing"


def test_recovery_is_recorded_and_restores_health():
    rows = _rows([0, 1, 2, 6])
    events = [{"kind": "hour_lost", "hour": T0 + h * H} for h in (3, 4, 5)]
    a = dh.assess(rows, events, _at(6))
    assert a.state == "healthy" and a.record_recovered and a.send == ["success"] and a.new_lost == []
    after = dh.assess(rows + _rows([7]), events + [{"kind": "recovered", "hour": T0 + 6 * H}], _at(7))
    assert after.state == "healthy" and not after.record_recovered and after.send == ["success"]


def test_a_new_incident_after_a_recovery_alerts_again():
    rows = _rows([0, 1, 2, 4, 5, 6, 8, 9])
    events = [{"kind": "hour_lost", "hour": T0 + 3 * H}, {"kind": "recovered", "hour": T0 + 5 * H}]
    a = dh.assess(rows, events, _at(9))
    assert a.new_lost == [T0 + 7 * H] and a.send[0] == "fail"


def test_an_honest_blank_is_an_observation_but_a_broken_track_is_not():
    data_gap = _rows([3], "unavailable", "missing inputs at 2026-10-16T03:00:00+00:00: taker_buy_share_1h")
    assert dh.assess(_rows([0, 1, 2]) + data_gap, [], _at(3)).state == "healthy"
    broken = _rows([3], "unavailable", "scoring 0.3.0 is running; direction_1h_v1 needs 0.2.0")
    a = dh.assess(_rows([0, 1, 2]) + broken, [], _at(4, minute=30))
    assert a.state == "failing" and a.new_lost == [T0 + 3 * H] and a.send == ["fail"]


def test_no_rows_at_all_never_pings_so_the_silence_alarm_fires():
    a = dh.assess([], [], _at(3))
    assert a.send == [] and a.lost == [], "with nothing recorded no success ping may be sent"


def test_the_fail_report_names_the_track_says_the_main_model_is_unaffected_and_holds_no_secret():
    a = dh.assess(_rows([0, 1, 2, 4]), [], _at(4))
    msg = dh.fail_message(a)
    assert msg.startswith("Bitcoin-AI-Agent DIRECTION TRACK") and "main hourly prediction" in msg and "unaffected" in msg
    assert "2026-10-16 03:00" in msg and "http" not in msg.lower() and len(msg) < 1500


def test_the_delivery_test_text_says_it_is_a_test():
    msg = dh.delivery_test_message(datetime(2026, 10, 16, 15, tzinfo=timezone.utc))
    assert msg.startswith("Bitcoin-AI-Agent DELIVERY TEST of the DIRECTION TRACK") and "NO direction hour is lost" in msg


def test_the_step_sends_no_second_alert_when_a_concurrent_run_recorded_the_hours_first(monkeypatch, tmp_path):
    monkeypatch.setattr(dh, "read_state", lambda: (_rows([0, 1, 2, 4]), []))
    monkeypatch.setattr(dh, "record", lambda a: (0, False))  # every INSERT hit ON CONFLICT: already recorded
    acts, body = tmp_path / "a.txt", tmp_path / "b.txt"
    dh.step(_at(4), acts, body)
    assert acts.read_text(encoding="utf-8").split() == ["success"] and body.read_text(encoding="utf-8") == ""


def test_the_step_writes_the_alert_when_it_recorded_a_new_incident(monkeypatch, tmp_path):
    monkeypatch.setattr(dh, "read_state", lambda: (_rows([0, 1, 2, 4]), []))
    monkeypatch.setattr(dh, "record", lambda a: (len(a.new_lost), a.record_recovered))
    acts, body = tmp_path / "a.txt", tmp_path / "b.txt"
    dh.step(_at(4), acts, body)
    assert acts.read_text(encoding="utf-8").split() == ["fail", "success"]
    assert body.read_text(encoding="utf-8").startswith("Bitcoin-AI-Agent DIRECTION TRACK")


def test_it_is_separate_from_the_main_model_and_changes_no_direction_row():
    src = Path(dh.__file__).read_text(encoding="utf-8")
    mods = {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom) and n.module}
    assert "agent.healthcheck" not in mods and not any(m.startswith(("agent.shadow", "agent.reporting", "agent.orchestrator")) for m in mods)
    sql = " ".join(re.findall(r'"""(.*?)"""', src, re.S) + re.findall(r'"(SELECT[^"]*)"', src))
    assert "predictions" not in sql and "shadow_move_size" not in sql, "it reads only the direction track's own tables"
    assert re.findall(r"INSERT INTO (\w+)", src) == ["shadow_direction_health", "shadow_direction_health"]
    assert "UPDATE" not in src and "DELETE" not in src


def test_the_workflow_step_is_its_own_check_and_can_never_change_the_jobs_result():
    wf = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")
    body = wf[wf.index("    steps:"):]
    blocks = re.split(r"\n(?=      - )", body)[1:]
    names = [re.search(r"name:\s*(.+)", b).group(1).strip() for b in blocks if re.search(r"name:\s*(.+)", b)]
    step = next(b for b in blocks if "Heartbeat direction track" in b)
    assert "continue-on-error: true" in step and "!cancelled()" in step
    assert "DIRECTION_HEARTBEAT_URL" in step and "${HEARTBEAT_URL" not in step and '"$HEARTBEAT_URL"' not in step
    assert names.index("Heartbeat direction track (its own check)") < names.index("Heartbeat ping")
    assert names.index("Heartbeat direction track (its own check)") > names.index("Grade direction shadow rows")
    assert "DIRECTION_HEARTBEAT_URL: ${{ secrets.DIRECTION_HEARTBEAT_URL }}" in wf


@pytest.mark.parametrize("hour_index", [0, 5, 23])
def test_the_expected_hour_is_the_one_the_direction_step_scores(hour_index):
    from agent.data_providers.market_data import expected_last_closed

    now = _at(hour_index, minute=37)
    assert dh.expected_hour(now) == expected_last_closed(now) == T0 + hour_index * H


def test_the_health_record_is_append_only_and_records_each_event_once_as_written():
    """Text-level; the behaviour is proven on real Postgres in tests/integration."""
    sql = " ".join(Path("agent/direction_shadow/schema.sql").read_text(encoding="utf-8").split())
    assert "CREATE TRIGGER shadow_direction_health_append_only BEFORE UPDATE OR DELETE ON shadow_direction_health" in sql
    assert "UNIQUE (kind, hour)" in sql and "CHECK (kind IN ('hour_lost', 'recovered'))" in sql
    assert "ARRAY['shadow_direction', 'shadow_direction_errors', 'shadow_direction_health']" in sql
