"""
Turns the overall score into BUY/HOLD/SELL, and calculates confidence.

Confidence here is a computed stand-in, not a real probability (see CLAUDE.md rule 6
and the plan). It has two ingredients, both measurable today without any history of
past outcomes:

- agreement: do the *independent* category scores (momentum, volume, news -- not
  trend/chart_pattern, which share the same underlying moving averages and would
  agree with each other almost by construction) actually point the same way? Low
  spread among genuinely separate signals is more meaningful than low spread among
  categories that were never independent to begin with.
- completeness: how much of the full toolkit actually had data this run.

Both are stored individually (see ConfidenceBreakdown), not just the blended number,
so a later phase can check which of these -- if either -- actually correlates with
real outcomes, instead of trusting the blend on faith.
"""

import statistics

from agent.scoring.scorer import ScoringResult
from agent.shared.types import CategoryScore, ConfidenceBreakdown

BUY_THRESHOLD = 0.15
SELL_THRESHOLD = -0.15
MAX_PLAUSIBLE_STDEV = 1.0  # the largest spread possible for scores confined to [-1, 1]
DEFAULT_AGREEMENT_WHEN_UNMEASURABLE = 0.5  # fewer than 2 independent signals: agreement can't be measured


def decide_signal(overall_score: float) -> str:
    if overall_score >= BUY_THRESHOLD:
        return "BUY"
    if overall_score <= SELL_THRESHOLD:
        return "SELL"
    return "HOLD"


def _independent_active_scores(category_scores: list[CategoryScore]) -> list[float]:
    return [c.score for c in category_scores if c.is_independent and c.weight > 0]


def compute_confidence(scoring_result: ScoringResult) -> ConfidenceBreakdown:
    independent_scores = _independent_active_scores(scoring_result.category_scores)

    if len(independent_scores) >= 2:
        spread = statistics.pstdev(independent_scores)
        agreement_score = max(0.0, min(1.0, 1 - (spread / MAX_PLAUSIBLE_STDEV)))
    else:
        agreement_score = DEFAULT_AGREEMENT_WHEN_UNMEASURABLE

    completeness_score = max(0.0, min(1.0, scoring_result.completeness))
    overall_confidence = (agreement_score + completeness_score) / 2

    return ConfidenceBreakdown(
        agreement_score=agreement_score,
        completeness_score=completeness_score,
        overall_confidence=overall_confidence,
    )
