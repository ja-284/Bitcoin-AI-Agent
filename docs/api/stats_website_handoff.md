# Private statistics website: frontend handoff (for the Lovable build)

> **A SIDE PROJECT. A PRIVATE, READ-ONLY STATISTICS WEBSITE. NOT THE FUTURE AUTOMATED-TRADING APPLICATION.**
> It shows one person what the Bitcoin analysis system predicted, what actually happened, how the figures
> change over time, and whether the system is healthy. It cannot influence the system it observes. If anything
> in a UI requirement seems to need more access than described here, the requirement loses, not the security.

Everything the website needs is already computed by the backend's reporting layer and stored, read-only for
you, in three tables. **The website renders. It never recomputes a statistic, re-labels a number, invents a
target, or calls anything else.** The backend side is finished and live (since 2026-09-27; incidents and the
fields marked *2026-10-05* since 2026-10-05). Full field reference: `docs/api/reporting_v1.md`. Security
boundary and its proofs: `docs/api/stats_access.md`.

## 1. Connection and sign-in

| what | value |
|---|---|
| backend | the project's Supabase database, through Supabase's normal client (`supabase-js`) |
| the website receives | the Supabase **project URL** and the **publishable (anon) key**. Both are designed to be public, and on their own they read nothing here. |
| never give the website | the `service_role` key, the database URL / password, the `bitcoin_agent` password, the Anthropic key, any GitHub token |
| sign-in | Supabase Auth, email + password (`signInWithPassword`). One account, created by the owner; sign-ups switched off. |
| what makes the account a viewer | the owner-set flag `app_metadata.reporting_viewer = true` (`docs/api/stats_access.md` §2). Without it a signed-in account sees **zero rows**; that is correct, not a bug. |
| what the account can do | `SELECT` on three tables. Nothing else: no writes, no functions, no other table. |

## 2. The three tables

| table | rows | columns |
|---|---|---|
| `reporting_snapshot` | exactly 1 | `reporting_contract_version` (text), `as_known_at`, `generated_at` (timestamps), `document` (JSON) |
| `reporting_runs` | one per hourly run since 2026-09-19 | `hour` (timestamp, the primary key), `reporting_contract_version`, `as_known_at` (when this row's content last changed), `run` (JSON) |
| `reporting_incidents` *(2026-10-05)* | one per recorded operational incident, append-only | `incident_key`, `kind`, `source`, `occurred_at`, `recorded_at`, `workflow`, `conclusion`, `run_url`, `detail` |

`document` is an envelope:
- `reporting_contract_version`, `kind` = `"all"`, `as_known_at`, `generated_at`;
- `read_only`, `descriptive_only`, `never_use_for`, `limitations`;
- `body`, which has:
  - `overview` *(2026-10-05)*;
  - `latest_run` and `latest_matured_run` *(2026-10-05)*;
  - `signal_statistics`, `move_size_statistics` and `move_size_breakdowns`;
  - `trends` *(2026-10-05)*;
  - `health`.

Every `run` (in `reporting_runs`, and in `latest_run` / `latest_matured_run`) has:
- `hour`, `information_cutoff`, `data_fetched_at`, `saved_at`, `timing`;
- `signal` (`value` BUY/HOLD/SELL + `evidence_status` + `evidence` sentence);
- `overall_score`, `confidence` and `price`, each as `{value, kind, is_probability, meaning}`;
- `versions`, `run` (`status` ok/degraded, `problems`, fallback, news, explanation, database role);
- `outcomes` (one per registered horizon `1h 6h 24h 72h 168h`), `outcomes_note`;
- `move_size` (the shadow model);
- in `reporting_runs` also `explanation` and `categories`.

Times are UTC ISO strings. A JSON `null` means "not available", never zero. Returns are fractions: 0.0044 =
+0.44%.

## 3. Example reads

```js
// sign in
const { error } = await supabase.auth.signInWithPassword({ email, password })

// the statistics document (overview, statistics, trends, health)
const { data: snap } = await supabase.from('reporting_snapshot')
  .select('reporting_contract_version, generated_at, as_known_at, document').single()

// run history, newest first, 24 per page (page n: range(24*n, 24*n + 23))
const { data: runs } = await supabase.from('reporting_runs')
  .select('hour, run').order('hour', { ascending: false }).range(0, 23)

// a stable "older" page: everything before the oldest hour already shown
const { data: older } = await supabase.from('reporting_runs')
  .select('hour, run').lt('hour', oldestShownHour).order('hour', { ascending: false }).limit(24)

// one hour in full
const { data: one } = await supabase.from('reporting_runs')
  .select('hour, run').eq('hour', '2026-10-05T16:00:00+00:00').maybeSingle()

// incident history, newest first (the full, merged history is also in document.body.health.incident_history)
const { data: incidents } = await supabase.from('reporting_incidents')
  .select('occurred_at, kind, source, detail, run_url').order('occurred_at', { ascending: false }).limit(50)
```

## 4. Pages (the intended information architecture)

| page | read from |
|---|---|
| **1. Overview** | `body.overview`: latest hour, signal and confidence, the shadow probability, the latest matured hour with its 1h outcome, `health` (healthy / degraded / attention_required), `current_warning`, `prospective_progress` (graded hours, next checkpoint, ETA). Plus the snapshot's age (§5). |
| **2. Run history** | `reporting_runs`, newest first, paged. Each row: `hour`, `signal.value`, `confidence.value` (labelled per §7), `run.status`, and the 1h outcome state. Tap a row for `run` in full. **Insert a placeholder row for every hour in `body.health.missing_hours_all_time`**: a missing hour has no run row, and must not silently disappear from the list. |
| **3. Prediction vs actual** | Per run, per horizon (`run.outcomes`): `state`, and once graded, `return`, `direction`, `signal_stated_direction`, `signal_vs_actual` (matched / not_matched / no_direction_stated). Shadow model: `run.move_size.probability.value` against `move_size.outcome.large_move` and `absolute_move` (threshold in `threshold_pct`). Aggregate: `signal_statistics.by_horizon[h]` (BUY/HOLD/SELL/ALL shares followed by a rise, and `acted_direction_agreement`). |
| **4. Performance / statistics** | `signal_statistics` (counts, outcomes by signal, acted-hour comparison, all with `sample`), `move_size_statistics` (`running_figures`: Brier, Brier of the observed rate, skill, ECE, `calibration_bins`, accuracy, ρ; `checkpoint_progress`), `move_size_breakdowns` (UTC hour blocks, weekday/weekend, volatility regime, recent vs earlier). |
| **5. Trends** | `trends.move_size_by_week`, `trends.signal_by_week` (per calendar week, Monday 00:00 UTC; `complete` false for the current week), `trends.move_size_latest_vs_previous_complete_week` (neutral `wording`; `is_a_conclusion` always false). Show `trends.important` on the page. |
| **6. System health** | `health`: `headline_status` + `headline_rule`, `problems`, `last_run`, `windows` (last 24 h / 7 days / all time: runs, missing hours, fallback, news unavailable, partial news, no explanation, timings), `outcomes` (overdue, rule breaks), `shadow`, `published_state`, `incidents` (counts and the capture limits), **`incident_history`** (every incident, recorded or derived, newest first), `external` (what is not observable here). |

## 5. Freshness and outages (never show old data as current)

- **Snapshot age** = now − `generated_at`. It is refreshed a few minutes after every completed hourly run, so
  normally it is under about 75 minutes.

  | age | show |
  |---|---|
  | ≤ 90 min | normal |
  | 90 min – 3 h | "data may be behind" |
  | > 3 h | a clear **"Reporting is not updating. The data shown is from <generated_at>."** banner |

  The publisher records a `stats_snapshot_was_stale` incident when it resumes after more than 3 h.
- `body.health` was computed at `generated_at`. Its statuses describe that moment, so always show it with the
  age.
- **Missing hours** are in `health.missing_hours_all_time` and in `incident_history` (`kind = missing_hour`).
- **Failed runs** are in `reporting_incidents` and `incident_history` (`hourly_run_failed`, `watchdog_failed`).
  A failed run whose hour a later backup run filled is still listed, so the history is not "all fine" just
  because every hour has a row.
- **What is NOT captured:**
  - heartbeat (healthchecks.io) alarms;
  - a reporting-workflow run that failed before it could write anything;
  - anything while the database is unreachable.

  Show `health.incidents.capture.not_captured` on the health page, so its silence is not read as "nothing
  happened".

## 6. Errors and empty states

| situation | what it means | show |
|---|---|---|
| sign-in fails | wrong credentials or no account | the sign-in error |
| signed in, but every table returns 0 rows | the account lacks the viewer flag (`docs/api/stats_access.md` §2) | "This account is not set up as a viewer", not "no data" |
| a request errors or times out | network or Supabase issue | "Could not load", with a retry; never an empty chart |
| unknown `reporting_contract_version` | the backend's shape changed | refuse to render that data and say so |
| a field is `null` | not available (e.g. no shadow row that hour) | "not available", never 0 |
| `run.move_size.available` is false | no shadow probability that hour | the `reason` |

## 7. Labelling rules (non-negotiable)

- **Probability vs heuristic.** Only a field with `is_probability: true` may be shown as a percentage chance;
  today that is only the shadow model's move-size probability. The direction **confidence** has
  `kind: "heuristic"` and must be labelled as a consistency score, not a probability (its `meaning`
  sentence says so). The overall score is a score.
- **The signal has no demonstrated predictive value.** Show `signal.evidence` (or `signal_statistics.evidence`)
  wherever the signal appears.
- **No trading language.** There are no trades, positions or profits. Never show P&L, "returns from following
  the signal", "win rate" or "accuracy" as performance. Use the field words: "followed by a rise", "matched",
  "not matched", "no direction stated".
- **Small samples look small.** Every statistic carries `sample` (`n`, `level`, `intervals`, `is_verdict`,
  `headline`). Always show `n` and the headline next to the figure.
  - Below 192 hours (`too_few_to_conclude`): no confidence bands, a muted style, the headline visible.
  - Below 2,000 (`early_intervals_optimistic`): bands may be drawn, but labelled too narrow.
  - `is_verdict` is always false. Never write "proven", "significant" or "validated".
- **Change is not improvement.** Week-on-week figures use the backend's neutral `wording` ("higher than the
  previous week"). Never "better", "worse", "improved", "declined" or "success".
- **Calibration bins** carry `enough_rows` (≥ 100). Draw small bins faintly.
- **Show `never_use_for` and `limitations`** somewhere reachable (an "About these numbers" page).

## 8. Pending, overdue and unavailable outcomes

| `outcomes[h].state` | meaning | show |
|---|---|---|
| `pending` | the target candle has not closed yet (or within the hour after) | "pending until `matures_at`" |
| `graded` | recorded | the return, the direction and the `signal_vs_actual` check |
| `overdue` | due for over an hour but not recorded | a warning; it is also counted in `health.outcomes.overdue_by_horizon` |
| `unavailable` | the exchange has no candle for that hour; never retried | "not available" and the `reason` |

The 168 h outcome of a run is pending for a week; that is normal.

## 9. What the website must never do

- Write anything, call a database function, or read any table other than the three above.
- Use a secret beyond the publishable key and the signed-in session.
- Recompute, re-label or "fix" a statistic, or compute its own targets, horizons, probabilities or verdicts.
- Present the BUY/HOLD/SELL record or anything else as trading performance or as a recommendation.
- Feed anything back into the analysis system. It is an observer, not an optimizer. Its numbers are never a
  tuning set (`never_use_for`).
- Become the trading application. That is a separate, NOT ACTIVE design (`docs/FUTURE_EXECUTION_ARCHITECTURE.md`)
  and must never be built here.

## 10. What only the owner can do (needed before the website can show data)

The steps are in `docs/api/stats_access.md` §2 and `docs/ops/open_user_actions.md` item 6:
1. Create the one Supabase Auth user.
2. Turn off sign-ups.
3. Run the one SQL statement that sets `app_metadata.reporting_viewer = true`.
4. Give Lovable only the project URL and the publishable key.

No password, key or token belongs in a chat, in Lovable's prompts, or in the repository.
