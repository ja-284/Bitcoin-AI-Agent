# Observability review — can every failure be told apart from a normal run?

Reviewed 2026-09-22 by reading every failure handler in the live path (`agent/`, excluding
`agent/research/`) and checking each against one standard:

> **A failure must never be indistinguishable from a real observation.**
> "No data", "could not be computed", "deliberately excluded" and "genuinely neutral" are four
> different things, and collapsing them is how a broken system comes to look like a working one.

## Every failure path, and what it leaves behind

| what fails | what happens | how you can tell |
|---|---|---|
| Binance responds with a bad shape | `KlineSchemaError`, no retry on a malformed body | job fails loudly |
| Binance unreachable | one bounded retry, then fall through to CoinGecko | `price_source`, `run_meta.price_data` |
| both price sources fail | the run **aborts** — price is the one input nothing can proceed without | job fails; next hour's self-check also fails |
| CoinGecko used instead | prices stored with `price_is_synthetic = true`; volume unavailable, not guessed | `price_is_estimated` in the contract; excluded from parity |
| impossible candle (high < low, etc.) | raises; nothing is repaired | job fails loudly |
| a gap in the candle history | indicators run on the longest unbroken run ending at the reference candle; anything whose warm-up does not fit becomes **unavailable** | `run_meta.price_data`, category weight 0, `window_hours` vs `consecutive_hours` |
| data older than the staleness rule | raises rather than being scored | job fails loudly |
| **one news feed down** | the other feeds are still collected and scored | `run_meta.news.sources_failed`; **contract `news.sources_failed` / `sources_used` / `sources_total`; weekly report §1** |
| all news feeds down | zero items → news category **weight 0** | `news.available = false`, `completeness_score` drops |
| the news AI call fails or is truncated | news left out entirely, never guessed at | `run_meta.news_error` + `news_error_type`, `ai_model_news` NULL, weight 0 |
| the explanation fails or is truncated | the analysis is saved without it; the decision never depended on it | `run_meta.explanation_error`, `explanation_status` |
| a database write fails | the run fails; the next hour recomputes from scratch | job fails; writes are idempotent so a retry cannot duplicate |
| the same hour runs twice | early exit **before** the AI calls | no duplicate row (`ON CONFLICT DO NOTHING`, proven on real Postgres) |
| the research shadow step fails | recorded in `shadow_run_errors`; the hourly job stays green because the live record is unaffected | weekly report §3; watchdog alarms only if it persists (> 2 in 6h) |
| an outcome candle does not exist | status `unavailable`; price and return stay NULL | `prediction_outcomes.status`, never a fabricated price |
| an hourly run is skipped | the next run's self-check fails on staleness | GitHub emails the failure; watchdog every 3h; weekly report lists the missing hours |
| a table becomes reachable through Supabase's public API (RLS switched off by hand, a privilege re-granted, or a new table made outside the schema files, which Supabase's defaults expose at once) | nothing in the hourly job changes — this is invisible from the record itself | `python -m agent.database.security` in the watchdog, every 3 hours: the job fails and GitHub emails you (added 2026-09-23) |
| the database is on an older schema than the code (a restore, or a rebuild from old files) | the run stops before writing anything | `assert_schema_current`; the job fails loudly naming both versions |
| **GitHub itself stops running anything** | **nothing happens, and nothing complains** | **NOT DETECTABLE — see below** |

## The one real gap

Every alarm above lives inside GitHub. If GitHub stops running the workflow — which it already
did in the first days, firing 2 of 8 scheduled slots — then no job runs, so no job fails, so
nothing is reported. **Silence is indistinguishable from success.**

The fix is written and inert: the hourly workflow's last step pings `$HEARTBEAT_URL` if that
secret exists, placed after every other step so a ping means the whole hour genuinely succeeded.
It needs a free healthchecks.io account and one repository secret — a user action, five minutes,
written up in [`open_user_actions.md`](open_user_actions.md).

Until then the mitigations are: the Supabase `pg_cron` trigger (independent of GitHub's own
scheduler), the self-check, the 3-hourly watchdog, and the weekly report's missing-hours list.
All of them still require GitHub to run *something*.

## Two things found during this review

**1. A partial news failure was invisible.** A feed going down is the quiet case: unlike a total
outage it still produces a number, and nothing downstream distinguished "three feeds, all
healthy" from "one feed, two down". The fact was recorded in `run_meta.news.sources_failed` but
never surfaced or tested. It has never happened in 69 live runs, which is exactly why it needed
a test rather than a watch. Now: shown in the backend contract (`sources_used` / `sources_total`),
counted in the weekly report, and covered by four tests.

**2. A decision deliberately NOT taken.** It would be defensible to reduce the news category's
weight in proportion to how many sources answered — `completeness_score` claims full
completeness today even if two of three feeds were down. It is not done, for three reasons: it
changes live scoring, which is the thing currently under test and would need a new version and a
re-run of the baseline; the effect has never once occurred in production; and the honesty goal is
met by making the shortfall visible instead. If feeds start failing regularly, this is the first
thing to revisit, and it is written here so that revisit starts from a decision rather than an
oversight.

## Data quality, measured rather than assumed (2026-09-22)

Across the 69 live runs with a news block: **95.2** items fetched per hour on average, **34.7**
used. Every exclusion is one of the intended rules — **59.8** outside the 24-hour window, **0.4**
published after the information cutoff, **0.2** duplicates across feeds, **0.0** undated. Nothing
is dropped for an unexplained reason, and nothing undated is ever admitted.

`used` has since risen to about 50 per hour, which is what overran the news scorer's old
2,048-token limit on 2026-09-21. The limit is now 16,384, so there is roughly a 5× margin.

## What is deliberately *not* logged

Secrets, in any form — checked by scanning both tracked files and every stored row. Raw exception
text never reaches the outward-facing contract either: it stays in the database, where it is
needed for diagnosis and where it identified the 2026-09-21 truncation, and the contract reports
a plain sentence plus the exception type.
