"""
Evaluation metrics, implemented plainly so every number can be checked by hand.

Classification (signal vs. label): accuracy, balanced accuracy, per-class precision /
recall / F1, confusion matrix, prediction distribution.

Probability quality (a stated probability of UP vs. what happened): Brier score (mean
squared error of the probability -- 0 is perfect, 0.25 is "always say 50%"), log loss,
and a reliability table: bucket predictions by stated probability, compare the stated
average to the observed frequency, with a Wilson interval so small buckets show their
own uncertainty. ECE/MCE summarise the table.

Uncertainty: hourly predictions with multi-hour outcomes overlap heavily, so n rows are
far fewer than n independent observations. Intervals therefore come from a circular
block bootstrap: resample whole blocks of consecutive hours (block length >= the longest
horizon) so the dependence inside a block is preserved.
"""

import math
from dataclasses import dataclass, field

import numpy as np

CLASSES_3 = ["UP", "NEUTRAL", "DOWN"]
CLASSES_2 = ["UP", "DOWN"]


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    # A Wilson interval always contains its own point estimate; floating point can put the bound
    # a whisker on the wrong side of it (observed 0.0 with a lower bound of 7e-18, found by
    # fuzzing), which reads as a contradiction in a reliability table. Clamp to the estimate.
    return (min(p, max(0.0, centre - half)), max(p, min(1.0, centre + half)))


@dataclass
class ClassificationReport:
    n: int
    accuracy: float
    balanced_accuracy: float
    per_class: dict = field(default_factory=dict)  # class -> {precision, recall, f1, support, predicted}
    confusion: dict = field(default_factory=dict)  # true -> {pred: count}
    prediction_distribution: dict = field(default_factory=dict)  # pred -> share

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "per_class": self.per_class,
            "confusion": self.confusion,
            "prediction_distribution": self.prediction_distribution,
        }


def classification_report(y_true: list[str], y_pred: list[str], classes: list[str]) -> ClassificationReport:
    if len(y_true) != len(y_pred):
        raise ValueError("length mismatch")
    n = len(y_true)
    confusion = {t: {p: 0 for p in classes} for t in classes}
    for t, p in zip(y_true, y_pred):
        confusion[t][p] += 1

    per_class = {}
    recalls = []
    for c in classes:
        tp = confusion[c][c]
        support = sum(confusion[c].values())
        predicted = sum(confusion[t][c] for t in classes)
        precision = tp / predicted if predicted else float("nan")
        recall = tp / support if support else float("nan")
        f1 = (2 * precision * recall / (precision + recall)) if predicted and support and (precision + recall) else float("nan")
        per_class[c] = {"precision": precision, "recall": recall, "f1": f1, "support": support, "predicted": predicted}
        if support:
            recalls.append(recall)

    correct = sum(confusion[c][c] for c in classes)
    return ClassificationReport(
        n=n,
        accuracy=correct / n if n else float("nan"),
        balanced_accuracy=float(np.mean(recalls)) if recalls else float("nan"),
        per_class=per_class,
        confusion=confusion,
        prediction_distribution={c: per_class[c]["predicted"] / n if n else float("nan") for c in classes},
    )


def brier_score(p_up: np.ndarray, y_up: np.ndarray) -> float:
    p_up, y_up = np.asarray(p_up, float), np.asarray(y_up, float)
    return float(np.mean((p_up - y_up) ** 2)) if len(p_up) else float("nan")


def log_loss(p_up: np.ndarray, y_up: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(np.asarray(p_up, float), eps, 1 - eps)
    y = np.asarray(y_up, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(p) else float("nan")


@dataclass
class ReliabilityBucket:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed: float
    ci_low: float
    ci_high: float

    @property
    def reliable(self) -> bool:
        # "Enough rows to measure" (n >= 100) -- NOT a statement that the bucket is calibrated.
        return self.n >= 100


def reliability_table(p_up: np.ndarray, y_up: np.ndarray, edges: list[float] | None = None) -> tuple[list[ReliabilityBucket], float, float]:
    """Buckets by stated probability. Returns (buckets, ECE, MCE) where ECE is weighted by bucket size."""
    p, y = np.asarray(p_up, float), np.asarray(y_up, float)
    edges = edges or [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 + 1e-9]
    buckets, ece, mce = [], 0.0, 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        mean_p = float(p[mask].mean())
        obs = float(y[mask].mean())
        ci = wilson_interval(int(y[mask].sum()), n)
        buckets.append(ReliabilityBucket(lo, min(hi, 1.0), n, mean_p, obs, ci[0], ci[1]))
        gap = abs(mean_p - obs)
        ece += gap * n / len(p)
        mce = max(mce, gap)
    return buckets, ece, mce


def block_bootstrap_estimates(values: np.ndarray, stat, block: int, n_boot: int = 1000, seed: int = 0) -> tuple[float, np.ndarray]:
    """
    Circular block bootstrap of `stat(values)` over a time-ordered array (or 2-D array of
    rows). Returns (point estimate, the n_boot resampled estimates). `block` = hours per hour-block.

    Callers that only want an interval use `block_bootstrap`; this variant exists because a
    PAIRED comparison of two models needs the spread of the resampled differences, not a
    percentile of one of them. The resampling itself is identical, so the two agree exactly.
    """
    values = np.asarray(values)
    n = len(values)
    point = float(stat(values))
    if n < block * 2:
        return point, np.empty(0)
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    estimates = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel() % n
        estimates[b] = stat(values[idx[:n]])
    return point, estimates


def block_bootstrap(values: np.ndarray, stat, block: int, n_boot: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    """
    Circular block bootstrap of `stat(values)`. Returns (point estimate, 2.5th pct, 97.5th pct).
    """
    point, estimates = block_bootstrap_estimates(values, stat, block, n_boot, seed)
    if len(estimates) == 0:
        return point, float("nan"), float("nan")
    return point, float(np.percentile(estimates, 2.5)), float(np.percentile(estimates, 97.5))


def signal_edge(signals: np.ndarray, returns: np.ndarray) -> float:
    """Mean return after BUY minus mean return after SELL; NaN if either side is empty."""
    signals, returns = np.asarray(signals), np.asarray(returns, float)
    buy, sell = returns[signals == "BUY"], returns[signals == "SELL"]
    if len(buy) == 0 or len(sell) == 0:
        return float("nan")
    return float(buy.mean() - sell.mean())
