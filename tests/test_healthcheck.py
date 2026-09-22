"""
The health checks the workflows rely on.

- staleness: the newest prediction must be recent enough (self-check after each run, watchdog);
- shadow errors: one recorded failure is tolerated, a persistent one must turn the watchdog red
  (added after the 2026-09-21/22 incident, where the shadow step failed on ~half of all hours).
"""

from datetime import datetime, timedelta, timezone

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
