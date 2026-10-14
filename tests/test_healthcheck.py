"""
The health checks the workflows rely on.

- staleness: the newest prediction must be recent enough (self-check after each run, watchdog);
- shadow errors: one recorded failure is tolerated, a persistent one must turn the watchdog red
  (added after the 2026-09-21/22 incident, where the shadow step failed on ~half of all hours);
- a single missed hour: reported once, by the run that saved the next hour, and never for a late run
  (added 2026-10-14 after 2026-10-07, when one hour went missing and nothing alarmed).
"""

from datetime import datetime, timedelta, timezone

import pytest

import agent.healthcheck as hc

NOW = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def test_staleness_uses_the_candle_close_not_the_reference_hour(monkeypatch):
    monkeypatch.setattr(hc, "latest_prediction_as_of", lambda: NOW - 2 * HOUR)  # candle closed at NOW - 1h
    ok, msg = hc.check(max_age_hours=2, now=NOW)
    assert ok and "1.0h since its candle closed" in msg
    monkeypatch.setattr(hc, "latest_prediction_as_of", lambda: NOW - 4 * HOUR)
    ok, _ = hc.check(max_age_hours=2, now=NOW)
    assert not ok
    monkeypatch.setattr(hc, "latest_prediction_as_of", lambda: None)
    ok, msg = hc.check(max_age_hours=2, now=NOW)
    assert not ok and "no predictions" in msg


def _errors(n: int) -> list[dict]:
    return [{"occurred_at": NOW - i * HOUR, "expected_as_of": NOW - (i + 1) * HOUR, "step": "fetch",
             "error_type": "RuntimeError", "error_message": "all Binance endpoints failed", "code_commit": None} for i in range(n)]


def test_shadow_error_check_tolerates_a_blip_but_not_a_pattern(monkeypatch):
    import agent.shadow.db as sdb

    monkeypatch.setattr(sdb, "run_errors_since", lambda since: [])
    ok, msg = hc.check_shadow_errors(max_errors=2, hours=6, now=NOW)
    assert ok and "no shadow-job errors" in msg

    monkeypatch.setattr(sdb, "run_errors_since", lambda since: _errors(2))
    ok, msg = hc.check_shadow_errors(max_errors=2, hours=6, now=NOW)
    assert ok and "2 shadow-job error(s)" in msg  # recorded and reported, but not an alarm yet

    monkeypatch.setattr(sdb, "run_errors_since", lambda since: _errors(3))
    ok, msg = hc.check_shadow_errors(max_errors=2, hours=6, now=NOW)
    assert not ok and "RuntimeError" in msg and "Binance" in msg


def test_shadow_error_check_asks_for_the_right_window(monkeypatch):
    import agent.shadow.db as sdb

    seen = {}

    def record(since):
        seen["since"] = since
        return []

    monkeypatch.setattr(sdb, "run_errors_since", record)
    hc.check_shadow_errors(max_errors=1, hours=6, now=NOW)
    assert seen["since"] == NOW - 6 * HOUR


# ---- the single-missed-hour signal (2026-10-14) ------------------------------------------------------------
# Clock times are the runs' (job start = START); as_of is the hour each run analysed. A run at hh:12 analyses
# the hour that closed at hh:00, i.e. as_of = hh:00 - 1h.
T = datetime(2026, 10, 7, 0, tzinfo=timezone.utc)  # hours of 2026-10-07: T + 14 * HOUR is 14:00


def _rows(*pairs):
    """[(as_of hour, created minutes after the job start)], newest first, as newest_predictions() returns them."""
    return [(T + h * HOUR, START + timedelta(minutes=m)) for h, m in pairs]


START = T + 16 * HOUR + timedelta(minutes=12)  # a job that started 16:12


def test_a_normal_hour_reports_nothing():
    missing, saved = hc.new_gap(START, _rows((15, 1), (14, -60)))  # saved 15:00 a minute in; 14:00 an hour ago
    assert (missing, saved) == ([], T + 15 * HOUR)


def test_a_late_run_is_not_a_missed_hour():
    """Queued 28 minutes, the run still analyses the hour that is due: nothing is missing."""
    late = T + 15 * HOUR + timedelta(minutes=40)
    missing, saved = hc.new_gap(late, [(T + 14 * HOUR, late + timedelta(minutes=1)), (T + 13 * HOUR, late - timedelta(minutes=88))])
    assert (missing, saved) == ([], T + 14 * HOUR)


def test_one_missed_hour_is_reported_by_the_run_that_saved_the_next_hour():
    """2026-10-07 exactly: no run for the 14:00 hour; the 16:12 run saved 15:00."""
    missing, saved = hc.new_gap(START, _rows((15, 1), (13, -100)))
    assert (missing, saved) == ([T + 14 * HOUR], T + 15 * HOUR)


def test_several_missed_hours_are_all_reported():
    missing, _ = hc.new_gap(START, _rows((15, 1), (10, -330)))
    assert missing == [T + h * HOUR for h in (11, 12, 13, 14)]


def test_a_gap_is_reported_once_later_runs_see_nothing_new():
    """The backup runs later in the hour (and re-runs) started after the row was created: no second report."""
    rows = _rows((15, 1), (13, -100))
    assert hc.new_gap(START, rows)[0] == [T + 14 * HOUR]
    for later in (START + timedelta(minutes=10), START + timedelta(minutes=25), START + timedelta(minutes=40)):
        assert hc.new_gap(later, rows) == ([], None)


def test_recovery_the_next_hour_after_a_gap_reports_nothing():
    nxt = START + HOUR
    rows = [(T + 16 * HOUR, nxt + timedelta(minutes=1)), (T + 15 * HOUR, START + timedelta(minutes=1))]
    assert hc.new_gap(nxt, rows) == ([], T + 16 * HOUR)


def test_a_row_created_at_the_very_second_the_job_started_counts_as_this_runs():
    assert hc.new_gap(START, [(T + 15 * HOUR, START), (T + 13 * HOUR, START - HOUR)])[0] == [T + 14 * HOUR]


def test_no_predictions_or_only_the_first_one_reports_nothing():
    assert hc.new_gap(START, []) == ([], None)
    assert hc.new_gap(START, _rows((15, 1))) == ([], T + 15 * HOUR)


def test_it_reads_the_two_newest_predictions_when_not_given(monkeypatch):
    seen = {}

    def newest(n):
        seen["n"] = n
        return _rows((15, 1), (13, -100))

    monkeypatch.setattr(hc, "newest_predictions", newest)
    assert hc.new_gap(START)[0] == [T + 14 * HOUR] and seen["n"] == 2


def test_the_report_names_the_hours_in_plain_words_and_nothing_else():
    msg = hc.gap_message([T + 14 * HOUR], T + 15 * HOUR)
    assert "1 hourly prediction(s) permanently missing" in msg and "2026-10-07 14:00" in msg and "2026-10-07 15:00" in msg
    assert "http" not in msg.lower() and "never backfilled" in msg
    long = hc.gap_message([T + h * HOUR for h in range(40)], T + 40 * HOUR)
    assert "16 more not listed" in long and len(long) < 1500  # a long outage is summarised, not listed


def test_the_cli_writes_the_report_only_when_an_hour_is_missing_and_never_fails(monkeypatch, tmp_path, capsys):
    body = tmp_path / "missed-hours.txt"
    stamp = START.strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(hc, "newest_predictions", lambda n: _rows((15, 1), (13, -100)))
    assert hc.main(["--new-gap-since", stamp, "--gap-body-file", str(body)]) == 0
    assert "2026-10-07 14:00" in body.read_text(encoding="utf-8") and capsys.readouterr().out.startswith("MISSED: ")

    body.write_text("left over from somewhere", encoding="utf-8")  # a stale file can never trigger a signal
    monkeypatch.setattr(hc, "newest_predictions", lambda n: _rows((15, 1), (14, -60)))
    assert hc.main(["--new-gap-since", stamp, "--gap-body-file", str(body)]) == 0
    assert body.read_text(encoding="utf-8") == "" and "OK: no hour is missing" in capsys.readouterr().out

    monkeypatch.setattr(hc, "newest_predictions", lambda n: _rows((15, -5), (13, -100)))  # saved by an earlier run
    assert hc.main(["--new-gap-since", stamp, "--gap-body-file", str(body)]) == 0
    assert body.read_text(encoding="utf-8") == "" and "saved no new hour" in capsys.readouterr().out


def test_the_cli_refuses_a_start_time_without_a_time_zone():
    with pytest.raises(SystemExit):
        hc.main(["--new-gap-since", "2026-10-14T13:12:05"])
