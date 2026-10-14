# E030 — news first look (roadmap 8.6)

Written 2026-10-14 13:55 UTC by `python -m agent.research.news_first_look`. Hours 2026-09-19T20:00 → 2026-10-11T13:00 UTC — exactly the first 500 usable news hours (571 available). Intervals: 48h circular block bootstrap, 500 resamples, seed 17.

**Registered (E025, 2026-09-24; execution details E030, `014cdef`, before any news-versus-outcome figure existed): a first look, descriptive, NO verdict.** The verdict point is 3,140 usable hours.

**What this size can see (E025):** only |ρ| ≥ 0.125 at 1h (0.27 at 6h, 0.42 at 24h) with 80% power. That is far above anything this programme has found (|ρ| 0.05–0.08). The interval is also liberal here: under no effect it excludes zero about 9% of the time instead of 5%. A null here is not evidence of no effect, and an interval that excludes zero is not evidence of one.

News score in these hours: mean +0.101, sd 0.145, range -0.247 to +0.552; 138 hours negative.

| horizon | role | n | Spearman ρ(news score, forward return) | 95% interval | excludes 0? | smallest ρ this size can detect (E025) |
|---|---|---|---|---|---|---|
| 1h | primary | 500 | +0.046 | [-0.052, +0.151] | no | 0.125 |
| 6h | descriptive only | 500 | +0.001 | [-0.200, +0.210] | no | 0.274 |
| 24h | descriptive only | 500 | -0.096 | [-0.380, +0.209] | no | 0.416 |

Hours left out for lack of an 'ok' outcome: none.

**No verdict, by registration.** No news weight, model parameter, feature, threshold, prompt or live signal changes because of this look.
