# E024 -- how many live hours before the shadow record can say anything?

Generated 2026-09-23T14:45:08.906114+00:00  |  pipeline 0.2.0  |  13127 validation hours, windows laid every 24h

**Descriptive planning. Fits nothing, selects nothing, changes nothing.** Assumes the live advantage is
the size seen on validation; if it is smaller, every figure below is an UNDER-estimate of the hours needed.

Whole validation period: model ahead of the free EWMA reference by 0.01459 Brier.

| live hours | windows | model ahead of free rule | Brier lead: 5th / median / 95th pct | passes E012 skill bar | ECE within 0.03 | large-move share range |
|---|---|---|---|---|---|---|
| 18 | 547 | 75% | -0.0240 / +0.0137 / +0.0646 | 13% | 2% | 11%-78% |
| 48 | 545 | 82% | -0.0105 / +0.0139 / +0.0460 | 23% | 1% | 21%-72% |
| 100 | 543 | 92% | -0.0027 / +0.0145 / +0.0333 | 39% | 1% | 28%-68% |
| 200 | 539 | 97% | +0.0024 / +0.0142 / +0.0281 | 54% | 4% | 32%-64% |
| 500 | 527 | 100% | +0.0068 / +0.0149 / +0.0232 | 78% | 10% | 34%-59% |
| 1000 | 506 | 100% | +0.0090 / +0.0144 / +0.0207 | 93% | 28% | 37%-59% |
| 2000 | 464 | 100% | +0.0109 / +0.0144 / +0.0200 | 100% | 62% | 42%-55% |
| 5000 | 339 | 100% | +0.0123 / +0.0144 / +0.0171 | 100% | 100% | 46%-50% |

## The verdict rules as written (research/LIVE_EVALUATION.md), window by window

E012 (verdict at 2,000 hours): Brier >= 5% below base AND accuracy >= naive + 5 points AND rho >= 0.10
with its interval excluding zero. E013 (verdict at 5,000 hours): ECE <= 0.03 AND every bucket with
>= 100 rows within 0.05. The **perfectly calibrated** columns use outcomes simulated from the model's own
probabilities: whatever share of windows fails there is the rule's failure rate from **noise alone**.

| live hours | E012 Brier | E012 accuracy | E012 rho point | E012 rho interval | E013 ECE | E013 buckets | E013 both | perfect: ECE | perfect: buckets | perfect: both |
|---|---|---|---|---|---|---|---|---|---|---|
| 18 | 13% | 19% | 52% | -- | 2% | 100% | 2% | 1% | 100% | 1% |
| 48 | 23% | 20% | 72% | -- | 1% | 100% | 1% | 1% | 100% | 1% |
| 100 | 39% | 31% | 89% | -- | 1% | 100% | 1% | 1% | 100% | 1% |
| 200 | 54% | 41% | 98% | -- | 4% | 100% | 4% | 3% | 100% | 3% |
| 500 | 78% | 59% | 100% | 100% (76 windows) | 10% | 46% | 8% | 17% | 54% | 16% |
| 1000 | 93% | 76% | 100% | -- | 28% | 29% | 21% | 50% | 44% | 38% |
| 2000 | 100% | 98% | 100% | 100% (67 windows) | 62% | 37% | 36% | 78% | 31% | 30% |
| 5000 | 100% | 100% | 100% | -- | 100% | 73% | 73% | 100% | 92% | 92% |

Percentages are the share of N-hour windows in which the rule PASSES.
