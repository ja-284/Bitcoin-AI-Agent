"""
Property tests: instead of checking hand-picked cases, hit the core logic with thousands of
random inputs and assert the things that must ALWAYS hold. Hand-written examples prove that a
function works where the author looked; these look where nobody did.

Every property here is a claim the rest of the project relies on:
  labels        a forward return is the candle opening at as_of+H, or nothing -- never a neighbour
  candles       impossible data always raises; clean data never does; gaps are counted exactly
  scoring       the overall score stays in range, respects weights, and ignores unavailable ones
  confidence    stays in [0,1] and never uses categories that are not independent
  signals       monotone in the score: a higher score can never produce a more bearish call
  walk-forward  folds never overlap, always keep the purge gap, always train on enough data
  shadow model  monotone in each input according to its coefficient's sign
  metrics       Brier/reliability stay in their mathematical ranges
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from agent.data_providers.quality import BarValidationError, validate_bars
from agent.decision.decision import compute_confidence, decide_signal
from agent.research.labels import LabelSpec, make_labels
from agent.research.metrics import brier_score, reliability_table
from agent.research.walkforward import WalkForwardSpec, make_folds
from agent.scoring.scorer import combine_scores
from agent.shadow.model import DEFAULT_VERSION, load_model
from agent.shared.types import CategoryScore, PriceBar

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
TRIALS = 200


def _series(rng, n: int, drop: float = 0.0) -> list[PriceBar]:
    """A random candle series, optionally with random hours missing."""
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.005, size=n)))
    bars = []
    for i in range(n):
        if drop and rng.uniform() < drop:
            continue
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        hi = max(o, c) * (1 + abs(float(rng.normal(0, 0.002))))
        lo = min(o, c) * (1 - abs(float(rng.normal(0, 0.002))))
        bars.append(PriceBar(START + i * HOUR, o, hi, lo, c, float(abs(rng.normal(50, 10))), "binance"))
    return bars


def test_forward_return_is_always_the_candle_at_as_of_plus_h_or_nothing():
    rng = np.random.default_rng(0)
    for trial in range(50):
        bars = _series(rng, 300, drop=0.05)
        by_time = {b.as_of: b for b in bars}
        h = int(rng.choice([1, 6, 24]))
        lab = make_labels(bars, LabelSpec(h, "binary")).set_index("as_of")
        for b in bars:
            target = b.as_of + h * HOUR
            ret = lab.loc[b.as_of, "ret"]
            if target in by_time:
                expected = (by_time[target].close - b.close) / b.close
                assert ret == pytest.approx(expected, rel=1e-12), (trial, h, b.as_of)
            else:
                assert np.isnan(ret), f"trial {trial}: {b.as_of} has no candle at +{h}h but got {ret}"


def test_impossible_candles_always_raise_and_clean_ones_never_do():
    rng = np.random.default_rng(1)
    for _ in range(TRIALS):
        bars = _series(rng, 60)
        now = bars[-1].as_of + 2 * HOUR
        report = validate_bars(bars, now=now)  # clean data must pass
        assert report.count == len(bars) and report.missing_hours == 0
        i = int(rng.integers(0, len(bars)))
        b = bars[i]
        broken = rng.choice(["dup", "order", "nan", "negative", "ohlc", "unclosed", "offhour"])
        if broken == "dup":
            bars.insert(i, b)
        elif broken == "order":
            bars[i], bars[(i + 1) % len(bars)] = bars[(i + 1) % len(bars)], bars[i]
            if i + 1 >= len(bars):
                continue
        elif broken == "nan":
            bars[i] = PriceBar(b.as_of, b.open, float("nan"), b.low, b.close, b.volume, b.source)
        elif broken == "negative":
            bars[i] = PriceBar(b.as_of, b.open, b.high, b.low, b.close, -1.0, b.source)
        elif broken == "ohlc":
            bars[i] = PriceBar(b.as_of, b.open, b.low - 1, b.high + 1, b.close, b.volume, b.source)
        elif broken == "unclosed":
            now = bars[-1].as_of  # the last candle has not closed yet
        else:
            bars[i] = PriceBar(b.as_of + timedelta(minutes=7), b.open, b.high, b.low, b.close, b.volume, b.source)
        with pytest.raises(BarValidationError):
            validate_bars(bars, now=now)


def test_gaps_are_counted_exactly():
    rng = np.random.default_rng(2)
    for _ in range(TRIALS):
        full = _series(rng, 80)
        keep = sorted(rng.choice(len(full), size=int(rng.integers(20, len(full))), replace=False))
        bars = [full[i] for i in keep]
        report = validate_bars(bars, now=full[-1].as_of + 2 * HOUR)
        span = int((bars[-1].as_of - bars[0].as_of) / HOUR) + 1
        assert report.missing_hours == span - len(bars)
        assert sum(missing for _, missing in report.gaps) == report.missing_hours


def test_overall_score_respects_range_weights_and_availability():
    rng = np.random.default_rng(3)
    names = ["trend", "momentum", "volume", "chart_pattern", "news"]
    for _ in range(TRIALS):
        cats = [CategoryScore(n, float(rng.uniform(-1, 1)), float(rng.choice([0.0, 0.15, 0.2, 0.25])), bool(rng.integers(0, 2)), {}) for n in names]
        if all(c.weight == 0 for c in cats):
            cats[0] = CategoryScore("trend", 0.5, 0.25, False, {})
        result = combine_scores(cats)
        assert -1.0 - 1e-12 <= result.overall_score <= 1.0 + 1e-12
        assert 0.0 <= result.completeness <= 1.0 + 1e-12
        # a zero-weight category must not move the result, whatever its score says
        flipped = [CategoryScore(c.name, -c.score if c.weight == 0 else c.score, c.weight, c.is_independent, {}) for c in cats]
        assert combine_scores(flipped).overall_score == pytest.approx(result.overall_score, abs=1e-12)
        # scaling every weight by the same factor cannot change the weighted average
        scaled = [CategoryScore(c.name, c.score, c.weight * 2, c.is_independent, {}) for c in cats]
        assert combine_scores(scaled).overall_score == pytest.approx(result.overall_score, abs=1e-9)


def test_confidence_stays_in_range_and_ignores_non_independent_categories():
    rng = np.random.default_rng(4)
    for _ in range(TRIALS):
        cats = [CategoryScore(f"c{i}", float(rng.uniform(-1, 1)), 0.2, bool(rng.integers(0, 2)), {}) for i in range(5)]
        if not any(c.is_independent for c in cats):
            cats[0] = CategoryScore("c0", cats[0].score, 0.2, True, {})
        result = combine_scores(cats)
        conf = compute_confidence(result)
        assert 0.0 <= conf.overall_confidence <= 1.0 and 0.0 <= conf.agreement_score <= 1.0
        # changing a NON-independent category's score must not move agreement
        moved = [CategoryScore(c.name, (0.9 if c.score < 0 else -0.9) if not c.is_independent else c.score, c.weight, c.is_independent, {}) for c in cats]
        assert compute_confidence(combine_scores(moved)).agreement_score == pytest.approx(conf.agreement_score, abs=1e-12)


def test_signal_is_monotone_in_the_score():
    order = {"SELL": 0, "HOLD": 1, "BUY": 2}
    scores = np.linspace(-1, 1, 4001)
    ranks = [order[decide_signal(float(s))] for s in scores]
    assert ranks == sorted(ranks), "a higher score produced a more bearish signal somewhere"
    assert ranks[0] == 0 and ranks[-1] == 2


def test_walk_forward_folds_never_overlap_and_always_keep_the_purge():
    rng = np.random.default_rng(5)
    for _ in range(60):
        days = int(rng.integers(500, 1500))
        times = __import__("pandas").date_range(START, periods=days * 24, freq="h", tz="UTC")
        spec = WalkForwardSpec(
            horizon_hours=int(rng.choice([1, 6, 24, 168])),
            scheme=str(rng.choice(["expanding", "rolling"])),
            min_train_days=int(rng.integers(100, 300)),
            test_block_days=int(rng.integers(30, 120)),
            embargo_hours=int(rng.choice([0, 12, 24, 48])),
            calib_days=int(rng.choice([0, 30, 90])),
        )
        try:
            folds = make_folds(times, spec)
        except ValueError:
            continue  # not enough data for this random spec: refusing is correct
        for a, b in zip(folds, folds[1:]):
            assert a.test_end == b.test_start  # contiguous, never overlapping
        for f in folds:
            last_fit = f.calib_end if f.calib_start is not None else f.train_end
            assert last_fit + spec.purge <= f.test_start, "a fold reached into the purge gap"
            assert f.train_end - f.train_start >= timedelta(days=spec.min_train_days)
            if f.calib_start is not None:
                assert f.train_end + spec.purge == f.calib_start


def test_shadow_model_is_monotone_in_every_input():
    m = load_model(DEFAULT_VERSION)
    rng = np.random.default_rng(6)
    for _ in range(100):
        base = {f: float(rng.uniform(0.2, 2.0)) if f in m.log_features else float(rng.uniform(-1, 1)) for f in m.features}
        p0 = m.predict(base)[1]
        for i, f in enumerate(m.features):
            higher = dict(base)
            higher[f] = base[f] * 1.5 if f in m.log_features else base[f] + 0.5
            p1 = m.predict(higher)[1]
            if m.coef[i] > 1e-9:
                assert p1 >= p0 - 1e-12, f"raising {f} (positive coefficient) lowered the probability"
            elif m.coef[i] < -1e-9:
                assert p1 <= p0 + 1e-12, f"raising {f} (negative coefficient) raised the probability"


def test_metrics_stay_in_their_mathematical_ranges():
    rng = np.random.default_rng(7)
    for _ in range(TRIALS):
        n = int(rng.integers(2, 500))
        p = rng.uniform(0, 1, size=n)
        y = (rng.uniform(size=n) < p).astype(float)
        b = brier_score(p, y)
        assert 0.0 <= b <= 1.0
        buckets, ece, mce = reliability_table(p, y)
        assert 0.0 <= ece <= 1.0 and 0.0 <= mce <= 1.0 and ece <= mce + 1e-12
        assert sum(bk.n for bk in buckets) == n
        for bk in buckets:
            assert 0.0 <= bk.observed <= 1.0 and bk.ci_low <= bk.observed <= bk.ci_high
