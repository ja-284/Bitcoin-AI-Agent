# E009 — AI component tests

news: claude-haiku-4-5 · explainer: claude-sonnet-5

## News scorer

- S1 schema: 6/6 calls returned one assessment per headline → PASS
- S2 stability: aggregate score mean +0.254, std 0.013; mean per-headline sentiment std 0.029 → PASS
- S3 relevance: Bitcoin headlines 0.93, non-Bitcoin 0.04 → PASS
- S4 sentiment sign on unambiguous headlines, every repeat → PASS
- S5 order: shuffled aggregate +0.208 vs mean +0.254 (shift 0.046) → FAIL

Per-headline (mean relevance / mean sentiment / sentiment std):

- Bitcoin climbs above $80,000 as spot ETF inflows hit a record: 1.00 / +0.94 / 0.05
- US regulator approves new rules for Bitcoin custody at banks: 0.95 / +0.74 / 0.05
- Bitcoin miners sell reserves as hashrate reaches all-time high: 0.88 / -0.28 / 0.04
- MicroStrategy adds another 5,000 BTC to its treasury: 0.87 / +0.72 / 0.07
- Manchester United appoint new manager after poor start to the season: 0.00 / +0.00 / 0.00
- New study links coffee consumption to longer sleep duration: 0.00 / +0.00 / 0.00
- Ethereum developers delay the next network upgrade by two months: 0.15 / +0.00 / 0.00
- Apple unveils thinner laptop with a new chip: 0.00 / +0.00 / 0.00
- Bitcoin ETF sees record $2 billion of inflows in a single day: 1.00 / +0.87 / 0.02
- Major pension fund announces first Bitcoin allocation: 0.93 / +0.79 / 0.04
- Bitcoin falls 15% after large exchange halts withdrawals following hac: 0.99 / -0.86 / 0.04
- Regulators propose ban on Bitcoin trading for retail investors: 0.96 / -0.85 / 0.03

## Explainer

- X1 signal named, never another: 9/9 named, 0 mentioned another signal → PASS
- X2 forbidden content: 0/9 → PASS
- X3 adversarial cases (read by hand):

### adversarial_buy_with_negative_news (signal BUY; stray percentages: none)

At $81,000, the system landed on a BUY signal with a modest overall score of +0.200. This comes from a mix of strongly positive readings in trend and chart_pattern, moderately positive momentum and volume, and a sharply negative news score pulling the total back down. The 30% agreement figure only looks at the independent categories—momentum, volume, and news—and since those three are pulling in different directions (two positive, one strongly negative), they don't agree with each other much, which keeps that number low. Completeness is 100%, meaning every category had usable data this run, so nothing was missing from the calculation. Overall, the modest score and low agreement reflect a case where some indicators lean bullish while news leans strongly bearish, producing a net positive but not a strongly unified result.

### adversarial_hold_all_missing_but_trend (signal HOLD; stray percentages: none)

At $81,000, the system landed on a HOLD with a fairly weak overall score of +0.10, which sits close to neutral rather than leaning strongly bullish or bearish. Only one category actually had usable data this run: trend, scoring +0.10 — and since it's flagged as not independent (it shares underlying math with another category), it was excluded from the agreement calculation, leaving nothing to actually compare for agreement, which is why that figure defaults to 50%. The bigger issue here is completeness, at just 25%, since momentum, volume, chart_pattern, and news all came back with no data — meaning most of the system's intended inputs weren't available to inform this score. In short, the modest score and HOLD signal are being driven by a single, non-independent category, with most of the analysis framework sitting empty this run.

### adversarial_sell_low_confidence (signal SELL; stray percentages: none)

At $81,000, the system landed on a SELL with an overall score of -0.160, a fairly mild reading near the center of the -1 to +1 range. That weak score reflects a real split in the data: volume is strongly negative (-0.90) and trend is modestly negative (-0.20) and chart_pattern is fully negative (-1.00), but momentum is strongly positive (+0.80) and news is neutral (0.00), pulling the overall number back toward zero. The 10% agreement figure is low because it only compares the independent categories — momentum, volume, and news — and these three are pulling in very different directions (strongly up, strongly down, and flat), so they don't corroborate each other. Completeness sits at 60%, meaning a good chunk of the weighted scoring inputs either had usable data or didn't — some was missing this run, capping how much of the full picture was formed. Overall, this is a case where the headline signal is SELL, but the underlying components disagree noticeably and part of the data was incomplete.
