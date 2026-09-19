"""
A8: outcomes attach only after the target candle has actually closed; the target is
found by exact timestamp; a missing candle becomes 'unavailable' (after a grace
period), never a neighbouring candle. Database and exchange are replaced by stand-ins.
"""

from datetime import datetime, timedelta, timezone

import agent.outcome_tracker as tracker
from agent.shared.types import PriceBar

AS_OF = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)  # reference candle 09:00-10:00, cutoff 10:00
REF_PRICE = 100.0


class FakeExchange:
    """Knows candles at the given hours; refuses to return one that hasn't closed by `now`."""

    def __init__(self, closes_by_hour: dict[datetime, float], now: datetime):
        self.closes = closes_by_hour
        self.now = now
        self.requests: list[datetime] = []

    def get_bar_at(self, as_of):
        self.requests.append(as_of)
        if as_of not in self.closes or as_of + timedelta(hours=1) > self.now:
            return None
        c = self.closes[as_of]
        return PriceBar(as_of, c, c, c, c, 1.0, "fake")


class FakeDb:
    def __init__(self, pending):
        self.pending = pending  # {horizon: [(id, as_of, close)]}
        self.saved = []
        self.unavailable = []

    def awaiting(self, horizon, now):
        return list(self.pending.get(horizon, []))

    def save(self, prediction_id, horizon, price, pct):
        self.saved.append((prediction_id, horizon, price, round(pct, 6)))

    def save_unavailable(self, prediction_id, horizon):
        self.unavailable.append((prediction_id, horizon))


def _wire(monkeypatch, db: FakeDb, horizons):
    monkeypatch.setattr(tracker, "HORIZONS_HOURS", horizons)
    monkeypatch.setattr(tracker, "predictions_awaiting_outcome", db.awaiting)
    monkeypatch.setattr(tracker, "save_outcome", db.save)
    monkeypatch.setattr(tracker, "save_outcome_unavailable", db.save_unavailable)


def test_is_gradeable_requires_target_candle_to_have_closed():
    assert not tracker.is_gradeable(AS_OF, 1, AS_OF + timedelta(hours=1, minutes=59))  # 10:59: 10:00 candle still open
    assert tracker.is_gradeable(AS_OF, 1, AS_OF + timedelta(hours=2))  # 11:00: 10:00-11:00 candle closed
    assert not tracker.is_gradeable(AS_OF, 24, AS_OF + timedelta(hours=24, minutes=30))
    assert tracker.is_gradeable(AS_OF, 24, AS_OF + timedelta(hours=25))


def test_grades_with_the_exact_target_candle(monkeypatch):
    now = AS_OF + timedelta(hours=26)
    closes = {AS_OF + timedelta(hours=h): 100.0 + h for h in range(0, 30)}
    exchange = FakeExchange(closes, now)
    db = FakeDb({1: [(7, AS_OF, REF_PRICE)], 24: [(7, AS_OF, REF_PRICE)]})
    _wire(monkeypatch, db, [1, 24])

    counts = tracker.track_outcomes(now=now, provider=exchange)

    assert counts["graded"] == 2
    assert (7, 1, 101.0, 0.01) in db.saved  # candle opening at 10:00 (as_of + 1h), close 101
    assert (7, 24, 124.0, 0.24) in db.saved  # candle opening at 09:00 next day
    assert exchange.requests == [AS_OF + timedelta(hours=1), AS_OF + timedelta(hours=24)]


def test_never_grades_before_the_target_candle_closes(monkeypatch):
    now = AS_OF + timedelta(hours=1, minutes=30)  # 10:30 -- the 10:00 candle is still forming
    exchange = FakeExchange({AS_OF + timedelta(hours=1): 101.0}, now)
    db = FakeDb({1: [(7, AS_OF, REF_PRICE)]})
    _wire(monkeypatch, db, [1])

    counts = tracker.track_outcomes(now=now, provider=exchange)

    assert db.saved == [] and db.unavailable == []
    assert counts["deferred"] == 1
    assert exchange.requests == []  # the guard stops it before even asking the exchange


def test_missing_candle_is_unavailable_after_grace_never_a_neighbour(monkeypatch):
    now = AS_OF + timedelta(hours=40)
    closes = {AS_OF + timedelta(hours=h): 100.0 + h for h in range(0, 30) if h != 24}  # 24h candle missing
    exchange = FakeExchange(closes, now)
    db = FakeDb({24: [(7, AS_OF, REF_PRICE)]})
    _wire(monkeypatch, db, [24])

    counts = tracker.track_outcomes(now=now, provider=exchange)

    assert db.saved == []
    assert db.unavailable == [(7, 24)]
    assert counts["unavailable"] == 1


def test_missing_candle_inside_grace_is_retried_later(monkeypatch):
    now = AS_OF + timedelta(hours=25, minutes=30)  # closed 30 min ago; could be an API hiccup
    exchange = FakeExchange({}, now)
    db = FakeDb({24: [(7, AS_OF, REF_PRICE)]})
    _wire(monkeypatch, db, [24])

    counts = tracker.track_outcomes(now=now, provider=exchange)

    assert db.saved == [] and db.unavailable == []
    assert counts["deferred"] == 1


def test_exchange_error_leaves_prediction_ungraded(monkeypatch):
    class Broken:
        def get_bar_at(self, as_of):
            raise ConnectionError("down")

    db = FakeDb({1: [(7, AS_OF, REF_PRICE)]})
    _wire(monkeypatch, db, [1])
    counts = tracker.track_outcomes(now=AS_OF + timedelta(hours=3), provider=Broken())
    assert counts["errors"] == 1 and db.saved == [] and db.unavailable == []
