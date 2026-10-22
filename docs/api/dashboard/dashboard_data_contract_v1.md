> **Preserved document (added to the repository 2026-10-22).** This is dashboard data contract v1 exactly as
> delivered on 2026-10-22. It was derived from the backend reporting code at commit `a9abca0` (reporting contract
> version `"1"`). Nothing in it was rewritten. The only additions are this box and two notes marked
> **"Preservation note"** in §2.2 and §2.3.
>
> Where this document and **Supplement S1** (`dashboard_contract_v1_supplement_s1.md`) differ in precision, S1 and its
> generated files (`dashboard_contract_v1.ts`, `dashboard_fixtures_v1.json`) apply. No JSON field name and no
> definition differs between them. See `README.md` in this folder.

# Bitcoin AI Control Center: dashboard data contract v1

**What this is.** The complete read-only data contract for the private Bitcoin AI Control Center dashboard, written so it can be pasted into Lovable as it stands. Parts 1–9 are the contract and Part 10 is the summary, so the document is the standalone handoff that Part 10 asks for.

**Status.** Documentation only. Nothing was changed in the code, database, policies, workflows or repository while preparing it.

**Evidence labels used throughout:**
- **[LIVE]**: checked read-only against the production database on 2026-10-22 at about 14:20 UTC. This covers column metadata, constraints, policies, grants, every JSON key path and type across all 786 run rows and the snapshot, and timestamp and count cross-checks. Only types, labels and counts were printed.
- **[CODE]**: read from the repository at `a9abca0`.
- **[NOT VERIFIED]**: stated from documentation or expectation and not checked in this session.
- **[NOT AVAILABLE]**: the three tables do not contain it.

---

## Ground rules (they apply to every part)

1. The dashboard reads **three tables only**, with **SELECT only**:
   - `public.reporting_snapshot`
   - `public.reporting_runs`
   - `public.reporting_incidents`
2. It **renders and never recomputes**. It does not re-derive a statistic, re-label a number, compute a target, a probability or a verdict, or fetch market data from anywhere.
3. A JSON `null` means **"not available"**, never zero. An absent optional key means the same.
4. **Returns are fractions** (`0.0044` = +0.44 %). **`threshold_pct` is already a percentage** (`0.25` = 0.25 %).
5. Only a field with `is_probability: true` may be shown as a percentage chance. Today that is **only** the move-size probability.
6. **No trading language.** There are no trades, positions, P&L or "returns from following the signal".
7. Every statistic is descriptive (`descriptive_only: true`, `is_verdict: false`). No green/red "good/bad" colouring, and no "proven", "significant" or "validated".

---

## Part 1: Table structures [LIVE]

### 1.1 `public.reporting_snapshot` (exactly one row)

| column | type | null | key / constraint | meaning | display? |
|---|---|---|---|---|---|
| `id` | integer | NOT NULL, default 1 | PRIMARY KEY, `CHECK (id = 1)` | always 1 | no (use for `.eq('id', 1)`) |
| `reporting_contract_version` | text | NOT NULL | — | contract version of `document`; currently `"1"` | diagnostics only |
| `as_known_at` | timestamptz | NOT NULL | — | the moment the document describes | yes, as "data som kjent per" |
| `generated_at` | timestamptz | NOT NULL | — | when the publisher computed it. **Always equal to `as_known_at`** (the publisher passes the same instant) [LIVE + CODE] | yes: the freshness clock |
| `document` | jsonb | NOT NULL | — | the whole statistics document (Part 2) | rendered per contract |

- **Size [LIVE]:** about 134 KB as JSON text (28 KB stored compressed).
- **Updates:** the row is **replaced in place** (UPSERT on `id`) on every publish. Nothing else writes it.
- **Indexes:** primary key only.
- **Triggers:** none.

### 1.2 `public.reporting_runs` (one row per saved hourly run)

| column | type | null | key | meaning | display? |
|---|---|---|---|---|---|
| `hour` | timestamptz | NOT NULL | **PRIMARY KEY** (unique) | the run's reference hour: the candle that **opened** at `hour` and closed at `hour` + 1 h. Equal to `run.hour` in all 786 rows [LIVE]. | yes |
| `reporting_contract_version` | text | NOT NULL | — | `"1"` in every row [LIVE] | diagnostics only |
| `as_known_at` | timestamptz | NOT NULL | — | **the publish at which this row's content last changed** (an outcome recorded, or pending → overdue). Rows that have not changed keep an older value. 399 distinct values today [LIVE]. | optional ("sist endret") |
| `run` | jsonb | NOT NULL | — | the run view (Part 3) | rendered per contract |

- **Rows [LIVE]:** 786, from `2026-09-19T09:00:00+00:00` to `2026-10-22T13:00:00+00:00`.
- **Size [LIVE]:** on average 5.8 KB of JSON per row (max 6.2 KB), so a 24-row page is about 140 KB.
- **Writes:** UPSERT by `hour`, only when the content or version differs. **Rows are never deleted** by the publisher [CODE].
- **Missing hours have no row.** There are 11 missing hours [LIVE]; their list is in the snapshot (`body.health.missing_hours_all_time`).
- **Ordering and pagination:** `hour` is unique, so `ORDER BY hour DESC` is a total, stable order. Use **keyset pagination** (`hour < oldest shown`), not offsets: a new row arrives at the top every hour and would shift offset pages.

### 1.3 `public.reporting_incidents` (append-only operational incidents)

| column | type | null | constraint | meaning | display? |
|---|---|---|---|---|---|
| `incident_key` | text | NOT NULL | **PRIMARY KEY** | idempotency key: `github:<run id>:<attempt>` or `publisher:…`. **Opaque; do not parse.** | no |
| `kind` | text | NOT NULL | `CHECK` ∈ `hourly_run_failed`, `watchdog_failed`, `stats_publish_failed`, `stats_snapshot_was_stale` | what happened | yes |
| `source` | text | NOT NULL | `CHECK` ∈ `workflow_event`, `github_api_backfill`, `publisher` | how it was recorded | yes, small |
| `occurred_at` | timestamptz | NOT NULL | indexed (`idx_reporting_incidents_time`) | when it happened: the failed run's start, or the start of the stale period | yes |
| `recorded_at` | timestamptz | NOT NULL, default `now()` | — | when it was written here. Never earlier than `occurred_at` [LIVE]. | optional |
| `workflow` | text | NULL | — | GitHub workflow name (run incidents only) | yes |
| `conclusion` | text | NULL | — | GitHub's conclusion (run incidents only) | yes |
| `run_url` | text | NULL | — | public GitHub Actions run page. All present values point at the project's own Actions pages [LIVE]. | yes, as a link |
| `detail` | text | NOT NULL | — | one plain English sentence; by design never an exception text or a secret | yes, verbatim |

- **Append-only:** the trigger `reporting_incidents_append_only` refuses UPDATE and DELETE for every role [LIVE].
- **Contents [LIVE]:** 17 rows, all `hourly_run_failed`. 16 came from `github_api_backfill` and 1 from `workflow_event`. All have workflow `Hourly Bitcoin analysis` and conclusion `failure`. They occurred between 2026-09-21 and 2026-10-05.
- **Stable order:** `occurred_at DESC, incident_key DESC`. `occurred_at` is not unique, so the tiebreaker is needed.

### 1.4 Access, as it stands [LIVE, policy names and roles; the condition was verified 2026-10-21]

- **Policy:** each table has exactly one policy reachable through the API, `control_center_read`: PERMISSIVE, `FOR SELECT TO authenticated`.
  - Its condition: **the one dedicated dashboard account** AND a session at **`aal2`** (password plus authenticator code).
  - The other policies (`backend_*`) belong to the internal job role `bitcoin_agent` and cannot be reached through the API.
- **API grants:** `authenticated` has `SELECT`; `anon` has nothing.
- **Probe of 2026-10-21** (rolled back; counts only):
  - the dashboard account at aal2 read 1 / 764 / 17 rows;
  - at aal1, the old viewer account, and any other account: 0 rows;
  - anonymous: denied;
  - every other table: denied.
- All columns of all three tables are safe to show. None holds a secret by design. Show `incident_key` and `reporting_contract_version` only for diagnostics.

---

## Part 2: The snapshot JSON contract (`reporting_snapshot.document`)

### 2.1 Versioning and validation

| where | value today | meaning |
|---|---|---|
| `reporting_snapshot.reporting_contract_version` (column) | `"1"` | the dashboard contract version |
| `document.reporting_contract_version` | `"1"` | the same, inside the JSON |
| `reporting_runs.reporting_contract_version` (column, every row) | `"1"` | the version of each run row |
| `document.kind` | `"all"` | the only kind stored |

- **Supported version: `"1"` only.** For any other value, **refuse to render that data**: show "Ukjent dataformat – oppdater dashbordet". No fallback, and no demo data.
- **Observed evolution policy [CODE/history]:** fields were added on 2026-10-05 (`overview`, `trends`, `latest_matured_run`, incidents) **without** a version change.
  - Treat `"1"` as "at least these fields".
  - **Ignore unknown keys**, and tolerate the optional keys marked below.
- **`reporting_incidents` has no version column.** Validate `kind` and `source` against Part 1's enums; show an unknown value as "Ukjent hendelsestype" rather than failing.
- **Do not confuse these with the contract version:**
  - `body.health.schema_version` (`"4"`) is the **database schema** version.
  - `body.health.published_state.contract_version` (`"1"`) is a **different cache** (`backend_state`, written by the hourly job), not this snapshot.
  - `versions.pipeline` / `versions.scoring` are the analysis versions.

### 2.2 Formal schema (TypeScript)

> **Preservation note (2026-10-22).** The TypeScript below was written by hand for v1. It is superseded by
> `dashboard_contract_v1.ts` in this folder, which is generated from the schema that validated the live tables and the
> fixtures (Supplement S1). The two differ only in strictness, never in a JSON field name or meaning:
> - S1 types `run.news.sources_failed` as `string[]` (here `unknown[]`), verified from the code;
> - S1 uses enums where this version uses `string`: `Category.name`, `run.price_source`, `IncidentItem.kind`,
>   `IncidentItem.how_known`, the incident row's `workflow` and `conclusion`;
> - S1 splits `Health` into `HealthFull | HealthNoData`;
> - S1 makes `explanation` and `categories` required in `reporting_runs` rows (`RunDetailView`); here they are optional;
> - some TypeScript type names differ (`Iso` → `IsoTimestamp`, `Interval` → `Interval95`, `IncidentRow` →
>   `ReportingIncidentRow`, the generic `Quantity` → named quantity interfaces).

Every key path below was observed live, unless it is marked as appearing only in states not present today. Optional keys (`?`) can be absent.

```ts
// ---------- shared ----------
/** ISO 8601, always UTC with offset, e.g. "2030-01-07T09:00:00+00:00"; may carry microseconds
 *  ("2030-01-07T10:14:05.123456+00:00"). Compare as instants, never as strings. */
type Iso = string;
type Horizon = "1h" | "6h" | "24h" | "72h" | "168h";
type Signal = "BUY" | "HOLD" | "SELL";
type Direction = "UP" | "DOWN";
type Interval = [number | null, number | null];          // a 95 % interval

interface Quantity<K extends string, P extends boolean> {
  value: number | null;          // null = not available, never 0
  kind: K;                       // "score" | "heuristic" | "price" | "calibrated_probability"
  is_probability: P;             // true ONLY for the move-size probability
  meaning: string;               // finished English sentence: show verbatim
}

interface Sample {               // attached to every statistic
  n: number;
  level: "too_few_to_conclude" | "early_intervals_optimistic" | "enough_for_nominal_intervals";
  intervals: "not_computed" | "shown_but_too_narrow" | "nominal";
  is_verdict: false;             // always false
  headline: string;              // show next to the figure
}

// ---------- outcomes ----------
// NOTE the key names: a recorded outcome has `matured_at`; a waiting one has `matures_at`.
type SignalOutcome =
  | { state: "graded"; matured_at: Iso; checked_at: Iso; return: number /* fraction */; direction: Direction;
      signal_stated_direction: Direction | null;                        // BUY→UP, SELL→DOWN, HOLD→null
      signal_vs_actual: "matched" | "not_matched" | "no_direction_stated" }
  | { state: "unavailable"; matured_at: Iso; checked_at: Iso; reason: string }   // not present live today
  | { state: "pending" | "overdue"; matures_at: Iso };                            // "overdue": not present live today

type MoveSizeOutcome =
  | { state: "graded"; matured_at: Iso; checked_at: Iso; return: number; direction: Direction;
      large_move: boolean; absolute_move: number /* fraction: compare with threshold_pct / 100 */ }
  | { state: "unavailable"; matured_at: Iso; checked_at: Iso; reason: string }
  | { state: "pending" | "overdue"; matures_at: Iso };

type MoveSize =
  | { available: false; reason: string }       // live: "no shadow row for this hour" (54 rows)
  | { available: true;
      separate_from_signal: string;
      status: "research_shadow_only";
      model_version: string;                   // live: "move_size_1h_v1"
      horizon_hours: number;                   // 1
      threshold_pct: number;                   // 0.25  (already PERCENT)
      probability: Quantity<"calibrated_probability", true>;   // value 0..1
      prospective: boolean;                    // stored before its outcome candle closed
      outcome: MoveSizeOutcome };

// ---------- one run (Part 3 describes every field) ----------
interface Category { name: string; score: number | null; weight: number | null;
                     is_independent: boolean | null; available: boolean }
interface RunView {
  hour: Iso; information_cutoff: Iso; data_fetched_at: Iso; saved_at: Iso;
  timing: { start_lag_seconds: number; analysis_seconds: number; job_wall_time_seconds: null; note: string };
  signal: { value: Signal; evidence_status: "no_demonstrated_predictive_value"; evidence: string };
  overall_score: Quantity<"score", false>;                  // -1..+1
  confidence: Quantity<"heuristic", false> & { components: { agreement: number | null; completeness: number | null } };
  price: Quantity<"price", false>;                          // USD
  versions: { pipeline: string; scoring: string; ai_news: string | null;
              ai_explanation: string | null; code_commit: string | null };
  run: { status: "ok" | "degraded"; problems: string[]; price_source: string; fallback_used: boolean;
         price_is_estimated: boolean; completeness: number | null;
         news: { available: boolean; items_used: number; error_type: string | null; sources_failed: unknown[] };
         explanation_available: boolean; database_role: string | null };
  outcomes: Record<Horizon, SignalOutcome>;
  outcomes_note: string;
  move_size: MoveSize;
  explanation?: string | null;    // ONLY in reporting_runs (not in latest_run / latest_matured_run)
  categories?: Category[];        // ONLY in reporting_runs
}

// ---------- the document ----------
interface SnapshotDocument {
  reporting_contract_version: "1"; kind: "all"; as_known_at: Iso; generated_at: Iso;
  read_only: true; descriptive_only: true;
  never_use_for: string[];        // 4 sentences: show on About
  limitations: string[];          // 7 sentences: show on About
  body: {
    overview: Overview;
    latest_run: RunView | null;
    latest_matured_run: RunView | null;     // newest run whose 1h outcome is recorded
    signal_statistics: SignalStatistics;
    move_size_statistics: MoveSizeStatistics;
    move_size_breakdowns: MoveSizeBreakdowns;
    trends: Trends;
    health: Health;
  };
}

interface Overview {
  latest_hour: Iso | null;
  latest_signal: RunView["signal"] | null;
  latest_confidence: RunView["confidence"] | null;
  latest_move_size: MoveSize | null;
  latest_matured_hour: Iso | null;
  latest_matured_1h_outcome: SignalOutcome | null;
  latest_matured_move_size: MoveSize | null;
  health: "healthy" | "degraded" | "attention_required" | "no_data";
  current_warning: string | null;
  prospective_progress: CheckpointProgress | null;
}

// ---------- direction-signal statistics ----------
interface ReturnGroup {
  graded: number; pending: number; overdue: number; unavailable: number;
  sample: Sample;
  share_followed_by_a_rise: number | null;   // null when graded = 0
  share_ci95?: Interval | null;              // ABSENT when graded = 0; null below 192 graded
  mean_return?: number;                      // ABSENT when graded = 0 (fraction)
  median_return?: number;                    // ABSENT when graded = 0 (fraction)
}
interface ActedAgreement {
  acted_graded: number; sample: Sample; note: string;
  majority_direction_share_all_hours?: number;  // ABSENT when no graded hour at this horizon
  matched_share?: number;                       // ABSENT when acted_graded = 0
  matched_ci95?: Interval | null;               // ABSENT when acted_graded = 0; null below 192
}
type HorizonTable = Record<Horizon,
  Record<Signal | "ALL", ReturnGroup> & { acted_direction_agreement: ActedAgreement }>;

interface SignalStatistics {
  evidence: { status: "no_demonstrated_predictive_value"; headline: string; detail: string; experiments: string[] };
  what_this_is: string;
  population: { runs: number; pipeline_version: string; excluded_older_pipeline_runs: number;
                scoring_versions: Record<string, number> };   // keys contain dots ("0.1.0"): use obj["0.1.0"]
  signal_counts: Record<Signal, number>;
  confidence: { kind: "heuristic"; is_probability: false; meaning: string; mean: number | null; note: string };
  by_horizon: HorizonTable;
}

// ---------- move-size (research shadow) statistics ----------
interface CheckpointProgress {
  prospective_graded_hours: number;
  selection_rule: string;
  next_checkpoint_hours: number | null;      // null after 5,000
  hours_remaining: number | null;
  expected_around: Iso | null;               // ESTIMATE, recomputed at every publish
  eta_assumption: string;
  reached: number[];                         // live: [500]
  computed_readings: Record<string, string>; // live: {"500": "research/monitoring/checkpoint_500h.md"} (a repo path)
  what_each_gives: { "500": string; "2000": string; "5000": string };
  rule: string;
}
interface CalibrationBin { from: number; to: number; n: number; stated: number; observed: number;
                           observed_ci95: Interval; enough_rows: boolean }  // only non-empty 0.1-wide bins
interface RunningFigures {
  n: number; large_move_share: number; mean_stated_p: number;
  brier: number; brier_of_the_observed_rate: number;
  brier_rel_gain: number | null;   brier_rel_gain_ci95?: Interval;   // ci present only from 192 graded
  accuracy: number; accuracy_ci95: Interval | null; naive_rate: number;
  rho: number | null;              rho_ci95?: Interval;
  ece: number;                     ece_ci95?: Interval;
  calibration_bins: CalibrationBin[];
  note: string;
}
interface MoveSizeStatistics {
  what_this_is: string;
  status: { status: "research_shadow_only"; detail: string; experiments: string[] };
  probability_meaning: string;
  rows: number;
  row_states: { graded: number; pending: number; overdue: number; outcome_unavailable: number; no_probability: number };
  not_prospective: number;
  model_versions: Record<string, number>;
  sample: Sample;
  checkpoint_progress: CheckpointProgress;
  running_figures?: RunningFigures;          // ABSENT when no graded hour exists
}

interface SliceGroup { n: number; large_move_share: number | null; mean_stated_p: number | null;
                       brier_rel_gain: number | null; ece: number | null; sample: Sample }
// Slices NEVER carry intervals, even when their sample.intervals says "shown_but_too_narrow".
// A group key appears only if it has at least one graded hour.
type MoveSizeBreakdowns =
  | { sample: Sample }                       // no graded hour yet
  | { slices: {
        hour_block_utc: Partial<Record<"00-06" | "06-12" | "12-18" | "18-24", SliceGroup>>;
        weekday_weekend: Partial<Record<"weekday" | "weekend", SliceGroup>>;
        recent_vs_earlier: Partial<Record<"last_168_graded_hours" | "earlier", SliceGroup>>;
        volatility_regime_168h?: Partial<Record<"low" | "mid" | "high" | "unknown", SliceGroup>>; // live: only "low"
      };
      definitions: Record<"hour_block_utc" | "weekday_weekend" | "volatility_regime_168h" | "recent_vs_earlier", string>;
      reading_note: string };

// ---------- trends ----------
interface MoveSizeWeek { week_starting: Iso; complete: boolean; sample: Sample; brier: number;
  n: number /* JSON number, integer-valued */; large_move_share: number | null; mean_stated_p: number | null;
  brier_rel_gain: number | null; ece: number | null }
interface NeutralChange { latest: number | null; previous: number | null; difference?: number;
                          wording: string; is_a_conclusion: false }
interface Trends {
  what_this_is: string;
  important: string;                         // show on the page
  move_size_by_week: MoveSizeWeek[];
  move_size_latest_vs_previous_complete_week:
    | { latest_week: Iso; previous_week: Iso;
        samples: [number, number];           // ORDER: [previous week's n, latest week's n]
        brier: NeutralChange; ece: NeutralChange; large_move_share: NeutralChange; mean_stated_p: NeutralChange }
    | { wording: "not enough complete weeks to compare" };
  signal_by_week: { week_starting: Iso; complete: boolean; runs: number;
                    signal_counts: Record<Signal, number>; by_horizon: HorizonTable }[];
}

// ---------- health ----------
interface WindowCounts {
  runs: number;                              // SAVED HOURS in the window (not GitHub runs)
  missing_hours: number; fallback_price_runs: number; news_unavailable_runs: number;
  news_partial_runs: number; explanation_unavailable_runs: number;
  start_lag_seconds: { median: number | null; max: number | null };
  analysis_seconds: { median: number | null; max: number | null };
}
interface IncidentItem { at: Iso; kind: string; how_known: string; summary: string; link: string | null }
interface Health {
  status: "ok" | "degraded" | "stale" | "no_data";
  problems: string[];
  external: { heartbeat: { observable_here: false; where: string };
              watchdog: { observable_here: "failed runs only"; where: string };   // NB: a string, not boolean
              job_wall_time: { observable_here: false; where: string } };
  // All keys below are ABSENT when status = "no_data":
  headline_status?: "healthy" | "degraded" | "attention_required";
  headline_rule?: string;
  current_warning?: string | null;
  last_run?: { hour: Iso; saved_at: Iso; freshness: string; database_role: string | null; code_commit: string | null };
  windows?: { last_24h: WindowCounts; last_7d: WindowCounts; all_time: WindowCounts };
  missing_hours_all_time?: Iso[];
  missing_note?: string;
  outcomes?: { overdue_by_horizon: Partial<Record<Horizon, number>>;   // {} when none overdue
               graded_before_their_candle_closed: number; rows_for_unregistered_horizons: number;
               registered_horizons_hours: number[] };
  shadow?: { rows: number; hours_without_a_shadow_row: number; errors_total: number; errors_last_24h: number;
             latest_error: { occurred_at: Iso; step: string; error_type: string } | null; note: string };
  published_state?: { contract_version: string; generated_at: Iso; age_hours: number }
                  | { available: false; reason: string };   // the hourly job's backend_state cache, NOT this snapshot
  schema_version?: string | null;            // database schema version, live "4"
  checkpoint_progress?: CheckpointProgress;
  incidents?: { recorded_total: number; recorded_last_24h: number; recorded_by_kind: Record<string, number>;
                capture: { recorded: string[]; derived_from_the_record: string[]; not_captured: string[];
                           recorded_since: string /* date "2026-10-05" */; note: string } };
  incident_history?: IncidentItem[];         // newest first, unbounded (53 items today)
}

// ---------- reporting_incidents row ----------
interface IncidentRow {
  incident_key: string;
  kind: "hourly_run_failed" | "watchdog_failed" | "stats_publish_failed" | "stats_snapshot_was_stale";
  source: "workflow_event" | "github_api_backfill" | "publisher";
  occurred_at: Iso; recorded_at: Iso;
  workflow: string | null; conclusion: string | null; run_url: string | null; detail: string;
}
```

**States that exist in code but not in today's data** need fixture tests:
- outcome `unavailable` and `overdue`;
- health `stale` and `no_data`;
- volatility groups `mid`, `high` and `unknown`;
- `running_figures` absent;
- a non-empty `news.sources_failed` (its element type has never been seen live; render items with `String()`).

### 2.3 Fictional example (real field names and types; **every value is invented**)

> **Preservation note (2026-10-22).** This example is an abbreviated illustration. Strings in parentheses such as
> `"(SliceGroup)"`, `"(WindowCounts)"` or `"(…)"` stand for whole objects or shortened sentences, so it is **not** a
> valid fixture and must not be used for tests. The complete, machine-valid fixtures are in
> `dashboard_fixtures_v1.json` (generated by the real reporting code and validated; Supplement S1, S2).

The dates are in 2030 on purpose. Long backend sentences are shortened with "(…)". Only `1h` is shown inside `by_horizon`; `6h`, `24h`, `72h` and `168h` have the identical shape and are always present.

```json
{
  "reporting_contract_version": "1",
  "kind": "all",
  "as_known_at": "2030-01-09T10:14:05.123456+00:00",
  "generated_at": "2030-01-09T10:14:05.123456+00:00",
  "read_only": true,
  "descriptive_only": true,
  "never_use_for": ["tuning, refitting or recalibrating any model", "(…3 more)"],
  "limitations": ["The BUY/HOLD/SELL signal has no demonstrated predictive value (E001, E017).", "(…6 more)"],
  "body": {
    "overview": {
      "latest_hour": "2030-01-09T09:00:00+00:00",
      "latest_signal": { "value": "SELL", "evidence_status": "no_demonstrated_predictive_value",
                         "evidence": "This signal has not been shown to predict anything." },
      "latest_confidence": { "value": 0.61, "kind": "heuristic", "is_probability": false,
                             "meaning": "A consistency and completeness estimate, not a probability. (…)",
                             "components": { "agreement": 0.52, "completeness": 1.0 } },
      "latest_move_size": { "available": true, "separate_from_signal": "research shadow model; (…)",
        "status": "research_shadow_only", "model_version": "move_size_1h_v1", "horizon_hours": 1,
        "threshold_pct": 0.25,
        "probability": { "value": 0.31, "kind": "calibrated_probability", "is_probability": true,
                         "meaning": "The estimated chance that Bitcoin's price moves more than 0.25% (…)" },
        "prospective": true,
        "outcome": { "state": "pending", "matures_at": "2030-01-09T11:00:00+00:00" } },
      "latest_matured_hour": "2030-01-09T08:00:00+00:00",
      "latest_matured_1h_outcome": { "state": "graded", "matured_at": "2030-01-09T10:00:00+00:00",
        "checked_at": "2030-01-09T10:13:02.000001+00:00", "return": -0.0012, "direction": "DOWN",
        "signal_stated_direction": null, "signal_vs_actual": "no_direction_stated" },
      "latest_matured_move_size": { "available": false, "reason": "no shadow row for this hour" },
      "health": "healthy",
      "current_warning": null,
      "prospective_progress": { "prospective_graded_hours": 1234, "selection_rule": "(…)",
        "next_checkpoint_hours": 2000, "hours_remaining": 766,
        "expected_around": "2030-02-10T08:14:05.123456+00:00", "eta_assumption": "(…)",
        "reached": [500], "computed_readings": { "500": "research/monitoring/checkpoint_500h.md" },
        "what_each_gives": { "500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict" },
        "rule": "(…)" }
    },
    "latest_run": "(a RunView without explanation/categories; see the reporting_runs example below)",
    "latest_matured_run": "(a RunView, or null)",
    "signal_statistics": {
      "evidence": { "status": "no_demonstrated_predictive_value",
                    "headline": "This signal has not been shown to predict anything.",
                    "detail": "(…)", "experiments": ["E001", "E002", "E011", "E017"] },
      "what_this_is": "(…)",
      "population": { "runs": 1200, "pipeline_version": "0.2.0", "excluded_older_pipeline_runs": 4,
                      "scoring_versions": { "0.1.0": 65, "0.2.0": 1135 } },
      "signal_counts": { "BUY": 300, "HOLD": 500, "SELL": 400 },
      "confidence": { "kind": "heuristic", "is_probability": false, "meaning": "(…)", "mean": 0.58, "note": "(…)" },
      "by_horizon": {
        "1h": {
          "BUY":  { "graded": 299, "pending": 1, "overdue": 0, "unavailable": 0,
                    "sample": { "n": 299, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow",
                                "is_verdict": false, "headline": "(…)" },
                    "share_followed_by_a_rise": 0.5, "share_ci95": [0.44, 0.56],
                    "mean_return": 0.0001, "median_return": 0.00005 },
          "HOLD": { "graded": 500, "pending": 0, "overdue": 0, "unavailable": 0, "sample": { "n": 500, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow", "is_verdict": false, "headline": "(…)" }, "share_followed_by_a_rise": 0.49, "share_ci95": [0.45, 0.53], "mean_return": 0.0, "median_return": -0.00002 },
          "SELL": { "graded": 0, "pending": 0, "overdue": 0, "unavailable": 0, "sample": { "n": 0, "level": "too_few_to_conclude", "intervals": "not_computed", "is_verdict": false, "headline": "(…)" }, "share_followed_by_a_rise": null },
          "ALL":  { "graded": 799, "pending": 1, "overdue": 0, "unavailable": 0, "sample": { "n": 799, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow", "is_verdict": false, "headline": "(…)" }, "share_followed_by_a_rise": 0.5, "share_ci95": [0.46, 0.53], "mean_return": 0.00004, "median_return": 0.0 },
          "acted_direction_agreement": { "acted_graded": 299, "sample": { "n": 299, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow", "is_verdict": false, "headline": "(…)" }, "note": "(…)",
                                         "majority_direction_share_all_hours": 0.5, "matched_share": 0.5, "matched_ci95": [0.44, 0.56] }
        }
      }
    },
    "move_size_statistics": {
      "what_this_is": "(…)",
      "status": { "status": "research_shadow_only", "detail": "(…)", "experiments": ["E012", "E013", "E018", "E019", "E020", "E021"] },
      "probability_meaning": "(…)", "rows": 1235,
      "row_states": { "graded": 1234, "pending": 1, "overdue": 0, "outcome_unavailable": 0, "no_probability": 0 },
      "not_prospective": 0, "model_versions": { "move_size_1h_v1": 1235 },
      "sample": { "n": 1234, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow", "is_verdict": false, "headline": "(…)" },
      "checkpoint_progress": "(same shape as overview.prospective_progress)",
      "running_figures": { "n": 1234, "large_move_share": 0.3, "mean_stated_p": 0.32,
        "brier": 0.2, "brier_of_the_observed_rate": 0.21, "brier_rel_gain": 0.05, "brier_rel_gain_ci95": [0.01, 0.09],
        "accuracy": 0.7, "accuracy_ci95": [0.67, 0.73], "naive_rate": 0.7,
        "rho": 0.3, "rho_ci95": [0.24, 0.36], "ece": 0.04, "ece_ci95": [0.02, 0.07],
        "calibration_bins": [ { "from": 0.2, "to": 0.3, "n": 150, "stated": 0.25, "observed": 0.24,
                                "observed_ci95": [0.18, 0.31], "enough_rows": true } ],
        "note": "(…)" }
    },
    "move_size_breakdowns": {
      "slices": {
        "hour_block_utc": { "00-06": { "n": 300, "large_move_share": 0.25, "mean_stated_p": 0.29, "brier_rel_gain": 0.03, "ece": 0.05,
                                       "sample": { "n": 300, "level": "early_intervals_optimistic", "intervals": "shown_but_too_narrow", "is_verdict": false, "headline": "(…)" } } },
        "weekday_weekend": { "weekday": "(SliceGroup)", "weekend": "(SliceGroup)" },
        "recent_vs_earlier": { "last_168_graded_hours": "(SliceGroup)", "earlier": "(SliceGroup)" },
        "volatility_regime_168h": { "low": "(SliceGroup)" }
      },
      "definitions": { "hour_block_utc": "(…)", "weekday_weekend": "(…)", "volatility_regime_168h": "(…)", "recent_vs_earlier": "(…)" },
      "reading_note": "(…)"
    },
    "trends": {
      "what_this_is": "(…)", "important": "(…)",
      "move_size_by_week": [ { "week_starting": "2030-01-07T00:00:00+00:00", "complete": false,
        "sample": { "n": 50, "level": "too_few_to_conclude", "intervals": "not_computed", "is_verdict": false, "headline": "(…)" },
        "brier": 0.19, "n": 50, "large_move_share": 0.28, "mean_stated_p": 0.3, "brier_rel_gain": 0.04, "ece": 0.08 } ],
      "move_size_latest_vs_previous_complete_week": { "latest_week": "2029-12-31T00:00:00+00:00", "previous_week": "2029-12-24T00:00:00+00:00",
        "samples": [167, 168],
        "brier": { "latest": 0.2, "previous": 0.21, "difference": -0.01, "wording": "lower than the previous week", "is_a_conclusion": false },
        "ece": "(NeutralChange)", "large_move_share": "(NeutralChange)", "mean_stated_p": "(NeutralChange)" },
      "signal_by_week": [ { "week_starting": "2030-01-07T00:00:00+00:00", "complete": false, "runs": 50,
        "signal_counts": { "BUY": 10, "HOLD": 25, "SELL": 15 }, "by_horizon": "(HorizonTable)" } ]
    },
    "health": {
      "status": "ok", "headline_status": "healthy", "headline_rule": "(…)", "problems": [], "current_warning": null,
      "last_run": { "hour": "2030-01-09T09:00:00+00:00", "saved_at": "2030-01-09T10:13:01.5+00:00",
                    "freshness": "newest prediction is for 2030-01-09T09:00:00+00:00 (0.2h since its candle closed)",
                    "database_role": "bitcoin_agent", "code_commit": "0000000000000000000000000000000000000000" },
      "windows": { "last_24h": { "runs": 24, "missing_hours": 0, "fallback_price_runs": 0, "news_unavailable_runs": 0,
                                 "news_partial_runs": 0, "explanation_unavailable_runs": 0,
                                 "start_lag_seconds": { "median": 750.0, "max": 770.0 },
                                 "analysis_seconds": { "median": 25.0, "max": 37.0 } },
                   "last_7d": "(WindowCounts)", "all_time": "(WindowCounts)" },
      "missing_hours_all_time": ["2029-12-30T14:00:00+00:00"], "missing_note": "(…)",
      "outcomes": { "overdue_by_horizon": {}, "graded_before_their_candle_closed": 0,
                    "rows_for_unregistered_horizons": 0, "registered_horizons_hours": [1, 6, 24, 72, 168] },
      "shadow": { "rows": 1235, "hours_without_a_shadow_row": 7, "errors_total": 0, "errors_last_24h": 0,
                  "latest_error": null, "note": "(…)" },
      "published_state": { "contract_version": "1", "generated_at": "2030-01-09T10:13:03+00:00", "age_hours": 0.02 },
      "schema_version": "4",
      "external": { "heartbeat": { "observable_here": false, "where": "(…)" },
                    "watchdog": { "observable_here": "failed runs only", "where": "(…)" },
                    "job_wall_time": { "observable_here": false, "where": "(…)" } },
      "checkpoint_progress": "(same shape as overview.prospective_progress)",
      "incidents": { "recorded_total": 1, "recorded_last_24h": 0, "recorded_by_kind": { "hourly_run_failed": 1 },
                     "capture": { "recorded": ["(…)"], "derived_from_the_record": ["(…)"], "not_captured": ["(…)"],
                                  "recorded_since": "2026-10-05", "note": "(…)" } },
      "incident_history": [ { "at": "2029-12-30T14:00:00+00:00", "kind": "missing_hour", "how_known": "derived from the record",
                              "summary": "No prediction was recorded for the 2029-12-30 14:00 UTC hour.", "link": null } ]
    }
  }
}
```

The strings in parentheses, such as `"(SliceGroup)"`, stand for an object of that type. They are placeholders in this example only; the real document always contains the full objects.

---

## Part 3: `reporting_runs.run` field reference

**Classes:**
- **P** = fixed at prediction time. It comes from append-only records and never changes after the run is saved.
- **O** = outcome-time. It starts as `pending` and changes once (to `graded` or `unavailable`). It can also show `overdue` in between.
- **C** = a constant sentence of contract `"1"`, the same in every row.

| path | type | class | meaning / display rule |
|---|---|---|---|
| `hour` | Iso | P | Reference hour (UTC). The candle opened at `hour` and closed at `hour` + 1 h. |
| `information_cutoff` | Iso | P | = `hour` + 1 h in all 786 rows [LIVE]: nothing after this moment was used (news included). |
| `data_fetched_at` | Iso | P | When the run fetched its data. |
| `saved_at` | Iso | P | When the row was saved. Never before `data_fetched_at` [LIVE]. |
| `timing.start_lag_seconds` | number | P | Candle close → data fetched. About 750 s normally, because the run starts at about :12. |
| `timing.analysis_seconds` | number | P | Data fetched → row saved. |
| `timing.job_wall_time_seconds` | null | C | Always null (not stored). Show `timing.note`. |
| `signal.value` | `BUY`/`HOLD`/`SELL` | P | The rule-based signal. **Always show `signal.evidence` next to it.** |
| `signal.evidence_status`, `signal.evidence` | string | C | `no_demonstrated_predictive_value` / "This signal has not been shown to predict anything." |
| `overall_score.value` | number −1…+1 or null | P | Weighted category score. "Score, not a probability, not an expected return" (`meaning`). |
| `confidence.value` | number 0…1 or null | P | **Consistency/completeness heuristic. Never a probability, never shown with "%" or "sjanse".** Example: "0,61 (konsistensscore)". |
| `confidence.components.agreement` / `.completeness` | number or null | P | The two inputs, each 0…1. |
| `price.value` | number | P | BTC close at the information cutoff, USD. |
| `versions.pipeline` | string | P | Live: `"0.1.0"` (the 4 earliest rows, before the correctness fixes) or `"0.2.0"` (from 2026-09-19 20:00). |
| `versions.scoring` | string | P | `"0.1.0"` (before 2026-09-22 16:00) or `"0.2.0"`. |
| `versions.ai_news` / `ai_explanation` | string or null | P | AI model ids. Live: `claude-haiku-4-5` / `claude-sonnet-5`; null when that AI step failed. |
| `versions.code_commit` | string or null | P | Public git commit; null on early rows. |
| `run.status` | `ok`/`degraded` | P | `degraded` if `problems` is non-empty (18 rows live). |
| `run.problems[]` | string[] | P | Finished English sentences, shown verbatim. Possible values: fallback price data; news step failed (news left out, weight 0, **not neutral**); N news sources failed; no explanation written; some categories unavailable. |
| `run.price_source`, `fallback_used`, `price_is_estimated` | string, bool, bool | P | Live: always `binance`, false, false. |
| `run.completeness` | number or null | P | Share of analysis inputs available. |
| `run.news.available`, `items_used`, `error_type`, `sources_failed` | bool, int, string or null, array | P | `available` = items > 0 and no error. `error_type` seen live: `InternalServerError`. |
| `run.explanation_available` | bool | P | |
| `run.database_role` | string or null | P | Live: `bitcoin_agent`, `postgres` (early), null (before it was recorded). Health/detail page only. |
| `explanation` | string or null | P | **AI-written narration, produced after the signal was decided.** Label it: "Skrevet av KI etter at signalet var bestemt – forklarer, beviser ikke." When null: "Ingen forklaring ble skrevet." |
| `categories[]` | 5 items live | P | `name` ∈ `trend`, `momentum`, `volume`, `chart_pattern`, `news`. `score`, `weight`, `is_independent`. `available` = weight > 0, so news with weight 0 means unavailable, not neutral. |
| `outcomes["1h"…"168h"]` | SignalOutcome | O | See below. **All five horizons are always present.** |
| `outcomes_note` | string | C | Show once on the page. |
| `move_size.available` | bool | P | false + `reason` for 54 rows live: the 47 hours before the shadow record began on 2026-09-21 17:00, plus 7 hours with no shadow row. |
| `move_size.probability.value` | number 0…1 | P | **The only probability.** Show it as "31 % sjanse for en bevegelse over 0,25 % (opp eller ned) neste time". It says nothing about direction. |
| `move_size.model_version`, `horizon_hours`, `threshold_pct`, `prospective`, `status`, `separate_from_signal` | — | P | Show `status`: "forskningsmodell i skyggedrift – påvirker aldri signalet". |
| `move_size.outcome` | MoveSizeOutcome | O | `large_move` (bool) and `absolute_move` (a **fraction**; compare with `threshold_pct`/100). |

**Outcome timing [LIVE + CODE]:**
- A horizon `h` outcome measures the close of the candle opening at `hour` + h, against the close at the cutoff.
- That candle closes at **`hour` + h + 1 h**, which is `matured_at` / `matures_at`. For example, the 1h outcome matures at `hour` + 2 h. This was verified for every row.
- It is recorded (`checked_at`) at or after that moment, never before [LIVE].
- `pending` turns into `overdue` one hour after `matures_at`.
- `direction` is `UP` if `return` > 0, otherwise `DOWN`, so a return of exactly 0 counts as DOWN.

| `state` | show (suggested Norwegian) |
|---|---|
| `pending` | "Venter – klart etter {matures_at}". 168h stays pending for a week, which is normal. |
| `graded` | the return in %, the direction, and `signal_vs_actual`: `matched` → "Samsvarte", `not_matched` → "Samsvarte ikke", `no_direction_stated` → "Ingen retning oppgitt (HOLD)" |
| `overdue` | a warning: "Forsinket – burde vært registrert". It is also counted in `health.outcomes.overdue_by_horizon`. |
| `unavailable` | "Ikke tilgjengelig" plus `reason`. Never retried. |

**Live state counts [LIVE]:**
- Graded rows per horizon: 785 at 1h, 780 at 6h, 762 at 24h, 714 at 72h, 618 at 168h. The rest are pending.
- Today there are no `unavailable` and no `overdue` outcomes.

---

## Part 4: Published statistics

**General points for every statistic:**
- Every number below is **preliminary and descriptive**. The only **official** results are the registered checkpoint readings (Part 5), and none of them is published as figures in these tables.
- **No "AI accuracy score" exists, and none may be built.**
- **Pipeline 0.1.0 runs are excluded** from the signal statistics: 4 rows (`population.excluded_older_pipeline_runs`).
- **Scoring 0.1.0 and 0.2.0 are pooled** (`population.scoring_versions`). That is a limitation to show.
- **Overlapping windows:**
  - Hourly runs with a horizon above 1 h overlap: two consecutive 24h outcomes share 23 hours.
  - So `graded` at 6h, 24h, 72h and 168h is **not** a count of independent observations. Roughly `graded ÷ horizon in hours` windows are independent; at 168h that is about 618 ÷ 168 ≈ 3.7 weeks today.
  - The Wilson intervals assume independence, so at these horizons they are **far too narrow**. The `sample.headline` does not say this, so the dashboard must.

| # | statistic | path | definition / method | n, horizon, missing data | better is… | beginner reading (NO) |
|---|---|---|---|---|---|---|
| S1 | Signal counts | `signal_statistics.signal_counts` | Pipeline-0.2.0 runs per signal | n = `population.runs`. Missing hours have no row. | none | "Hvor ofte systemet sa BUY, HOLD eller SELL." |
| S2 | Outcome counts | `by_horizon[h][g].graded/pending/overdue/unavailable` | Runs per outcome state, per signal group g ∈ BUY/HOLD/SELL/ALL | per horizon | none (overdue > 0 is an operational warning) | "Hvor mange utfall som er registrert, venter eller mangler." |
| S3 | Share followed by a rise | `…share_followed_by_a_rise`, `share_ci95` | Graded runs with return > 0, divided by graded. 95 % **Wilson** interval: null below 192; key absent when graded = 0. | n = `graded` (overlapping above 1h) | **none.** Compare a signal group with `ALL`; a difference is not evidence. | "Hvor ofte prisen var høyere etter h timer, etter dette signalet, sammenlignet med alle timer." |
| S4 | Mean / median return | `…mean_return`, `median_return` | Arithmetic mean and median of the raw price change (fractions). Absent when graded = 0. | as S3 | none. **Not profit.** Bitcoin drifts on its own. | "Gjennomsnittlig prisendring etter signalet, ikke gevinst." |
| S5 | Acted-hour agreement (E001 comparison) | `…acted_direction_agreement.matched_share`, `matched_ci95`, `majority_direction_share_all_hours` | BUY then rise, or SELL then fall, as a share of graded BUY+SELL runs (Wilson). Shown next to the share a hindsight guess of the more common direction gets over all graded hours. Absent keys as in §2.2. | n = `acted_graded` | A matched share above the majority share would be in the signal's favour, **but over 68,619 historical hours there was no edge (E001/E017).** Don't colour it. | "Hvor ofte BUY/SELL pekte riktig vei, mot hvor ofte det å alltid gjette den vanligste retningen ville truffet." |
| S6 | Confidence mean | `signal_statistics.confidence.mean` | Mean of the heuristic | `population.runs` | none. **No calibration is computed** (it is not a probability). | "Gjennomsnittlig konsistensscore." |
| M1 | Shadow row states | `move_size_statistics.rows`, `row_states`, `not_prospective`, `model_versions` | Counts | — | `overdue`, `outcome_unavailable`, `no_probability` and `not_prospective` should stay 0 | "Hvor mange timer forskningsmodellen har vurdert." |
| M2 | Large-move share | `running_figures.large_move_share` | Graded hours with \|move\| > 0.25 %, divided by graded | n = `running_figures.n` = prospective graded hours | none (a property of the market) | "Hvor ofte prisen faktisk beveget seg mer enn 0,25 % på en time." |
| M3 | Mean stated probability | `running_figures.mean_stated_p` | Mean of the stated probabilities | same | **closeness to M2** (calibration-in-the-large); neither side is "better" | "Hva modellen i snitt sa, mot hva som skjedde (M2)." |
| M4 | Brier score | `running_figures.brier`, `brier_of_the_observed_rate` | Mean of (p − y)². The reference is the Brier of a constant equal to the observed share of the same hours, which is only known in hindsight. | same | **lower** | "Gjennomsnittlig feil i sannsynlighetene; lavere er bedre." |
| M5 | Relative Brier gain (skill) | `running_figures.brier_rel_gain`, `brier_rel_gain_ci95` | 1 − Brier ÷ reference Brier. Interval: circular **block bootstrap** (48 h blocks, 500 resamples, seed 17), present only from 192 graded hours, **too narrow below 2,000** (E025). | same | **higher**; above 0 means better than the hindsight constant | "Hvor mye bedre modellen var enn å si samme tall hver time." |
| M6 | Accuracy vs naive rate | `running_figures.accuracy`, `accuracy_ci95`, `naive_rate` | The share of hours where "p > 0.5" agrees with large/not large (Wilson; null below 192). `naive_rate` is always guessing the more common outcome. | same | Nominally higher, **but with about 30 % large-move hours a calibrated model rarely says > 0.5, so accuracy ≈ naive rate by construction.** Show it as secondary only, never as "KI-treffsikkerhet". | "Ikke et godt mål her; se Brier." |
| M7 | Ranking (Spearman ρ) | `running_figures.rho`, `rho_ci95` | Rank correlation of the stated p with the absolute move. Block-bootstrap interval as M5. | same | **higher** | "Om høyere oppgitt sjanse faktisk fulgte med større bevegelser." |
| M8 | ECE (calibration error) | `running_figures.ece`, `ece_ci95` | Size-weighted mean of \|stated − observed\| over 0.1-wide bins | same | **lower**, but at a few hundred to a couple of thousand hours, values of several hundredths are expected even from a perfectly calibrated model (E024). It cannot be read as miscalibration. | "Gjennomsnittlig avvik mellom oppgitt og faktisk andel." |
| M9 | Calibration bins | `running_figures.calibration_bins[]` | Per non-empty 0.1-wide bin: `n`, `stated` (mean p), `observed` share, Wilson `observed_ci95`, `enough_rows` (n ≥ 100) | per bin | points near the diagonal; draw bins under 100 faintly | reliability diagram: x = stated, y = observed |
| B1 | Breakdowns | `move_size_breakdowns.slices.*` | M2, M3, M5 and M8 per group. **No intervals.** Hour blocks are UTC; read them **against E027's known offsets** (nights over-stated, 12–18 UTC under-stated), not against zero. All hours so far fall in the `low` volatility regime, so `mid`/`high` are absent. | per group `n` | as M5/M8; each group carries its own `sample` | "Samme mål, fordelt på tid på døgnet, ukedag/helg, volatilitet, siste uke mot tidligere." |
| T1 | Weekly trends | `trends.*` | Per calendar week from Monday 00:00 UTC. `complete: false` for the current week. Neutral `wording` only, and `is_a_conclusion` is always false. | weekly n < 192, so no intervals | **none.** "Higher/lower", never "better/worse". Show `trends.important`. | "Ukens tall varierer mye av tilfeldigheter." |
| H1 | Health windows | `health.windows.{last_24h,last_7d,all_time}` | Counts. `runs` = **saved hours** (not GitHub runs). Lags are in seconds. | — | 0 is good for every problem count | see Part 6 |

**Never draw the registered pass bars** (E012/E013 thresholds) as pass/fail lines. The checkpoint's own pass flags are deliberately left out of the published data.

---

## Part 5: Checkpoints and research protection

**Published counts** (`body.overview.prospective_progress`; the same object appears in `move_size_statistics.checkpoint_progress` and `health.checkpoint_progress`):
- `prospective_graded_hours`: 731 at 14:18 UTC today [LIVE].
- `next_checkpoint_hours`: 2,000. `hours_remaining`: 1,269.
- `expected_around`: currently ≈ 2026-12-14.
- `reached`: `[500]`.
- `computed_readings`: `{"500": "research/monitoring/checkpoint_500h.md"}`.
- `what_each_gives`, `rule`, `selection_rule`, `eta_assumption`.

**Counting rule.** An hour counts when:
- its shadow row has status ok;
- its outcome is ok; and
- its probability was stored **before** its outcome candle closed.

Missing hours, hours without a shadow row and unavailable outcomes never count. A checkpoint reads exactly the **first N** such hours.

**Progress bar: safe, with conditions.**
- **Allowed:** `prospective_graded_hours` against the markers 500 / 2,000 / 5,000. It is a count of collected hours, not an outcome value.
- **Neutral colour.** Label it "Innsamlede timer", not "fremgang mot suksess".
- **`expected_around` is an estimate.** It is recomputed every hour and assumes no lost hours. The 2,000-hour reading is taken at the first working session after the count is reached, not automatically.
  - Show "tidligst rundt {dato} (anslag)".
  - Never show it as the date of a result.

**Dates:**

| item | date | status |
|---|---|---|
| First stored run hour | 2026-09-19 09:00 UTC | confirmed [LIVE] |
| Shadow (move-size) record begins | 2026-09-21 17:00 UTC | confirmed [LIVE] |
| Incident recording begins | 2026-10-05 | confirmed [CODE] |
| 500-hour first look | taken 2026-10-13 | confirmed; **no verdict, by registration** |
| 2,000-hour reading (E012 verdict) | ≈ 2026-12-14 | **estimated**; published in `expected_around` |
| 5,000-hour reading (E013 verdict) | ≈ 2027-04-18/20 | estimated; **[NOT AVAILABLE] in the tables** |
| Direction-track readings, 1,000 / 3,000 / 6,500 eligible hours | ≈ 2026-11-26 / 2027-02-17 / 2027-07-13 | estimated; **[NOT AVAILABLE]** |
| News verdict | ≈ 2027-01-29 to 02-03 | estimated; **[NOT AVAILABLE]** |

Show only the published progress. Anything else is "Data ikke tilgjengelig ennå" unless you approve static copy.

**Official results that exist:**
- The **500-hour first look** of the move-size model (2026-10-13). It deliberately carries no verdict.
- Its figures are **not** in the tables; only its existence is (`computed_readings`).
- Recommended display: "Første gjennomgang ved 500 timer er tatt 13.10.2026. Ingen konklusjon – slik var den registrert." No numbers.
- No verdict exists yet for anything.

**Must NEVER be exposed:**
1. **The blind direction track.** That means `direction_1h_v1`, the tables `shadow_direction*`, its probabilities, gradings and counts. None of it is in the three tables; the dashboard must not get it any other way.
   - At most, optional static text, your call: "Et blindt retningsforsøk pågår; ingen tall vises før de registrerte avlesningene."
2. **The sealed holdout** (1 July 2025 – 19 August 2026): no data and no evaluation from that period.
   - The tables contain no hour from it; the publisher refuses to publish one.
   - The dashboard fetches **no market data from anywhere**.
3. Any other table, such as raw predictions, outcomes, news headlines, AI usage and cost, dispatch logs or `backend_state`.
4. The shadow error messages (deliberately unpublished; only `step` and `error_type` are shown).
5. Checkpoint pass/fail flags, development-period research data, and experiment records.
6. Secrets of any kind: keys, tokens, database URLs, passwords, TOTP secrets, session tokens. **Never log them**, and do not add analytics or error-reporting scripts that capture responses or headers.

---

## Part 6: Incidents, health and freshness

**Two lists:**
- **`body.health.incident_history`** is the complete merged list, newest first. **Use it.** It holds:
  - the recorded kinds (Part 1);
  - kinds derived from the record: `missing_hour`, `run_degraded`, `shadow_error`, `shadow_row_missing`.
  - `how_known` is `recorded (workflow_event)`, `recorded (github_api_backfill)`, `recorded (publisher)` or `derived from the record`.
  - Show `summary` verbatim and `link` as a link.
- **`reporting_incidents`** is the raw recorded subset. It is live, while the snapshot list is as of `generated_at`, so the two can differ for a few minutes. Prefer the snapshot list.

**Display rules:**
- **Failed runs:** `hourly_run_failed` / `watchdog_failed`. A failure whose hour a backup run filled is still listed, so "every hour has a row" does not mean "nothing failed".
- **Missing hours:** insert a placeholder row in the run list for every entry of `health.missing_hours_all_time`: "Ingen analyse for denne timen – mangler permanent, fylles aldri inn". Never skip the hour silently.
  - Check: rows + missing = hours from first to latest. Today 786 + 11 = 797 = 797 [LIVE].
- **Degraded runs:** `run.status = degraded` plus `problems`.
- **Severity:** don't invent one. `headline_status` is the only summary:
  - `attention_required`: no fresh prediction, or a failed hourly/watchdog run in the last 24 h;
  - `degraded`: any other problem in the last 24 h;
  - `healthy`: none.
  - It looks back 24 h, so always show `current_warning` and `headline_rule` with it.
- **What is not captured:** show `health.incidents.capture.not_captured` (heartbeat alarms; a reporting run that failed before writing, under 3 h; a database outage), so silence is not read as "nothing happened".

**Freshness. Two clocks, both computed with the device clock:**

| clock | formula | normal | warning | alarm |
|---|---|---|---|---|
| Snapshot age | now − `generated_at` | ≤ 90 min | 90 min – 3 h: "Dataene kan ligge etter" | > 3 h: banner "Rapporteringen oppdateres ikke. Viser data fra {generated_at}." |
| Record age | now − (`overview.latest_hour` + 1 h) | about 12–75 min | — | > 2 h: "Ingen ny analyse lagret siden {latest_hour + 1 h}" |

Why these thresholds:
- The hourly run is dispatched at :12, with GitHub backup slots at :07 / :22 / :37 / :52. The snapshot is republished after every completed hourly or watchdog run, so its normal age is under about an hour.
- **90 min** equals the heartbeat's own allowance (1 h period + 30 min grace).
- **3 h** is the publisher's `STALE_AFTER`: there it fails loudly and records `stats_snapshot_was_stale`.
- **2 h** after the candle closed is the backend's own staleness rule (`agent/healthcheck`). At that point `health.status` becomes `stale`, judged at `generated_at`.
- If the computed age is negative (device clock ahead), show 0 and no alarm.

---

## Part 7: Page mapping

Support levels: **FULL** = everything comes from the tables; **PARTIAL** = some of it; **NONE** = show "Data ikke tilgjengelig ennå".

| page | source and paths | support | required labels | unavailable state |
|---|---|---|---|---|
| **Overview** | `body.overview.*` and the snapshot `generated_at` | FULL | signal + `evidence`; confidence = heuristic; move-size = probability + `status`; both freshness clocks; `health` + `current_warning` | `latest_*` null → "Ingen data ennå"; 0 rows → access message (Part 8) |
| **Performance** | `signal_statistics`, `move_size_statistics`, `move_size_breakdowns`, `trends` | FULL (descriptive) | `sample.n` + `headline` beside every figure; the overlap warning above 1h; "beskrivende, ikke en konklusjon"; no green/red; `trends.important` | `running_figures` absent → "Ingen graderte timer ennå" |
| **Runs** | `reporting_runs`, keyset pages of 24, plus missing-hour placeholders | FULL | per row: hour, `signal.value`, `confidence.value` (heuristic), `run.status`, 1h `state` | access or error states |
| **Run details** | one `reporting_runs` row | FULL | the explanation label; categories (`available` false = "ikke brukt", not neutral); all 5 horizons; move-size and its unit note; pipeline-0.1.0 rows labelled "før korrigeringene" | missing hour → the placeholder text |
| **Models** | `versions.*` per run; `population.scoring_versions`; `move_size_statistics.model_versions`, `.status`, `.probability_meaning`; `signal_statistics.evidence` | PARTIAL | the move-size model is a research shadow model | weights, artefacts, prompts, the direction model and AI cost: "Data ikke tilgjengelig ennå" |
| **Tests & CI** | none | NONE | — | "Data ikke tilgjengelig ennå". A static link to the public GitHub Actions page is optional, your decision. |
| **Experiments** | none; only cited ids (`evidence.experiments`, `status.experiments`) | NONE | — | "Data ikke tilgjengelig ennå" (the cited ids may be listed as "referert i beskrivelsene") |
| **System Health** | `body.health.*` and `reporting_incidents` | FULL | `headline_rule`; `capture.not_captured`; `external` (what cannot be seen here); `published_state` labelled "backend-state-cache", not this snapshot | — |
| **Roadmap** | `checkpoint_progress` only | PARTIAL | dates as estimates; no verdict implied | everything else: "Data ikke tilgjengelig ennå" |
| **About** | `never_use_for`, `limitations`, `evidence.detail`, the `meaning` sentences, `capture`, the contract version | FULL | — | — |
| **Simulert resultat** | **nothing from the tables** | NONE by design | permanent banner: "FIKTIVE TALL – ingen ekte handel, ingen ekte gevinst eller tap. Ikke beregnet fra systemets signaler." | It must never read the tables, never compute "what if you had followed the signal", and never appear as a fallback for a live page. |

**Language.** Backend sentences (`meaning`, `headline`, `summary`, `problems`, notes) are shown **verbatim in English** and never paraphrased. Enum values get fixed Norwegian labels; suggested ones are in Parts 3 and 6. Keep `BUY`/`HOLD`/`SELL` untranslated as system labels.

---

## Part 8: Safe read-only integration

**Configuration:**
- `createClient(PROJECT_URL, PUBLISHABLE_KEY)` from `@supabase/supabase-js` v2. **Nothing else.**
- Do **not** use Lovable's built-in Supabase integration, a `service_role` key, a database URL or any admin credential.
- Do not use Realtime, Storage, Edge Functions or `.rpc`.
- Optional: `auth.storage = window.sessionStorage`, so closing the tab ends the session.

**Sign-in (aal2 is required before any data query):**
```ts
await supabase.auth.signInWithPassword({ email, password })
const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel()
if (aal?.currentLevel !== 'aal2') {
  const { data: f } = await supabase.auth.mfa.listFactors()
  const factorId = f!.totp[0].id
  const { data: ch } = await supabase.auth.mfa.challenge({ factorId })
  await supabase.auth.mfa.verify({ factorId, challengeId: ch!.id, code })   // → aal2
}
```

**Queries** (`.maybeSingle()`, because `.single()` turns the 0-row access case into an error):
```ts
const snap = await supabase.from('reporting_snapshot')
  .select('reporting_contract_version, as_known_at, generated_at, document').eq('id', 1).maybeSingle()

const firstPage = await supabase.from('reporting_runs')
  .select('hour, reporting_contract_version, as_known_at, run')
  .order('hour', { ascending: false }).limit(24)
const olderPage = await supabase.from('reporting_runs')
  .select('hour, reporting_contract_version, as_known_at, run')
  .lt('hour', oldestHourShown).order('hour', { ascending: false }).limit(24)
const oneRun = await supabase.from('reporting_runs')
  .select('hour, reporting_contract_version, as_known_at, run').eq('hour', hourIso).maybeSingle()

const incidents = await supabase.from('reporting_incidents')
  .select('incident_key, kind, source, occurred_at, recorded_at, workflow, conclusion, run_url, detail')
  .order('occurred_at', { ascending: false }).order('incident_key', { ascending: false }).limit(50)
```
Never fetch `reporting_runs` without a limit.

**Validation, before rendering:**
1. Every version field is `"1"` (both snapshot fields and every run row), `document.kind === "all"`, and `read_only` and `descriptive_only` are true. Otherwise refuse.
2. `document.generated_at` equals the column `generated_at`, and every `run.hour` equals its row's `hour`.
3. **Same-publish consistency.** If any fetched run row has `as_known_at` later than the snapshot's `generated_at`, or the newest `hour` is later than `overview.latest_hour`, a publish happened between the reads. Refetch the snapshot once, then render.
   - Rows with an older `as_known_at` are already consistent with it, because only changed rows are rewritten.
   - The publisher writes the snapshot and the runs in one transaction.
4. Unknown enum values: show "ukjent", never crash. Absent optional keys and nulls: "ikke tilgjengelig".

**Errors and empty states:**

| case | expected response | show |
|---|---|---|
| not signed in (anon) | an error: permission denied (42501). The exact HTTP code is [NOT VERIFIED] and should be confirmed in the browser test. | the sign-in page |
| signed in at aal1, or another account | 0 rows, no error | first ask for the authenticator code; if it is still 0 rows at aal2, "Denne kontoen har ikke tilgang". Never "ingen data", never demo data. |
| expired or invalid session (401 / JWT error) | error | refresh the session; if that fails, sign in again |
| network or timeout | error | "Kunne ikke laste" plus a retry. Never an empty chart or demo data. |
| unknown version | — | refuse that data (§2.1) |

**Caching:**
- Keep data **in memory only**. No localStorage copy of the data.
- Refetch on load and on tab focus if older than 5 min. Never poll more often than every 5 minutes, because the data changes about hourly.
- When `generated_at` changes, invalidate the cached run pages.
- On sign-out, clear all caches.

**Demo data:**
- In live mode, demo fixtures must be unreachable from every live page.
- They may exist only in tests and on "Simulert resultat".
- If a demo mode exists, it needs a visible "DEMO" watermark.

**Time zones.** Show Europe/Oslo with a UTC indicator. Hour blocks and weeks are UTC by definition, so label them that way.

**Parsing.** Parse microsecond timestamps with a tolerant ISO parser (for example `date-fns/parseISO`). Read keys that contain dots (`"0.1.0"`) or start with digits (`"1h"`) with bracket access.

**Unchanged by any of this:** no new permissions, no RLS change, no new API.

---

## Part 9: Verification checklist

None of these browser tests has been performed. Only you can perform them; until then nothing is claimed.

| # | test | expected |
|---|---|---|
| 1 | Dashboard account, password + code (aal2) | snapshot 1 row; runs paged; incidents visible. (The SQL-level probe on 2026-10-21 gave 1/764/17 rows.) |
| 2 | Not signed in | permission-denied error on all 3 tables; the app shows sign-in |
| 3 | Password only (aal1) | 0 rows on all 3; the app asks for the code; no data, no demo |
| 4 | Any other account, including the old viewer account | 0 rows even at aal2; "ingen tilgang" |
| 5 | Read-only: insert / update / delete / `.rpc` from the dev console (optional) | refused (permission denied) |
| 6 | Protected tables, e.g. `predictions`, `shadow_direction` | refused |
| 7 | No demo fallback: go offline, at aal1, and with an error | error or access states only; no demo values anywhere |
| 8 | Version check | fixture test with version `"2"` → refused |
| 9 | Missing, pending and incomplete outcomes against real rows | latest run: all horizons pending; 168h pending on the last 168 rows; the 18 degraded rows (17 news failed; 1 also with no explanation, 2026-09-29 13:00); the 54 rows with `move_size.available: false`; the 4 pipeline-0.1.0 rows; missing-hour placeholders (e.g. 2026-10-05 19:00, 2026-10-07 14:00) |
| 10 | States not present live | fixture tests: `unavailable`, `overdue`, `no_data`, `stale`, absent `running_figures`, null/absent intervals, volatility `mid`/`high`/`unknown` |
| 11 | Matching values | on screen equals JSON. Also: `overview.latest_hour` = newest `hour`; `health.windows.all_time.runs` = row count (786 = 786 [LIVE]); rows + missing = hours span (797 [LIVE]); `population.runs` + `excluded_older_pipeline_runs` = row count (782 + 4 [LIVE]); `move_size_statistics.rows` = runs with `move_size.available` (732 [LIVE]). With your approval I can also show that the stored snapshot is identical to a recomputation as of its own `generated_at`. |
| 12 | Stale warnings | fixture with `generated_at` 2 h and 4 h old, and `latest_hour` 3 h old → the right banners |
| 13 | Sign-out | data gone; back button and a new tab show no data |
| 14 | Session expiry: leave it open more than 1 h | tokens refresh; still aal2; data loads. (Keeping aal2 after refresh is expected but [NOT VERIFIED].) |
| 15 | Labels | probability only on move-size; confidence never "%"; evidence beside every signal; no trading words; sample n beside every statistic |

---

## Part 10: References and evidence summary

**Repository files:**
- `agent/reporting/schema.sql`: tables, trigger, policy.
- `agent/reporting/views.py`: every field.
- `agent/reporting/publish.py`: writes, `STALE_AFTER`, the holdout refusal.
- `agent/reporting/__init__.py`: version, `NEVER_USE_FOR`.
- `agent/api/state.py`: `Quantity` and the evidence and meaning texts.
- `agent/research/live_checkpoint.py`: selection, metrics, slices.
- `agent/research/metrics.py`: Brier, Wilson, bins.
- Docs: `docs/api/reporting_v1.md`, `docs/api/stats_website_handoff.md`, `docs/api/stats_access.md`, `research/LIVE_EVALUATION.md`.

**Verified [LIVE, 2026-10-22 ≈ 14:20 UTC, read-only]:**
- column types, nullability, keys, CHECKs, indexes, the trigger, policy names and roles, API grants;
- every JSON key path and type in the snapshot and in all 786 run rows;
- the timestamp relations (cutoff = hour + 1 h; maturity = hour + h + 1 h; never graded early);
- the count cross-checks;
- version `"1"` everywhere.

**From code and earlier sessions:**
- the policy condition and the 2026-10-21 probe;
- state transitions not present live.

**Assumptions [NOT VERIFIED]:**
- the exact HTTP status codes in the browser;
- aal2 surviving a token refresh;
- response compression;
- sign-ups being off (set by you on 2026-10-21, not re-checked here).

**Not available in the tables:**
- tests and CI, experiments, AI cost, news evaluation;
- the direction track (must stay hidden);
- readiness status;
- the 5,000-hour, direction and news dates;
- the 500-hour figures.

### Kort oppsummering (bokmål)

- Dashbordet leser bare tre tabeller med SELECT: ett sammendragsdokument (`reporting_snapshot`), én rad per time (`reporting_runs`) og en logg over hendelser som aldri kan endres (`reporting_incidents`).
- Det er dashbordkontoen som leser, og bare med tofaktorinnlogging (aal2). Alt annet gir 0 rader eller avvisning.
- Alt er beskrivende. BUY/HOLD/SELL har ingen påvist treffsikkerhet. Konsistensscoren er ikke en sannsynlighet. Bare bevegelsesmodellens sannsynlighet er en sannsynlighet.
- Ingen tall er en konklusjon før de registrerte sjekkpunktene. Ved 500 timer ble det bevisst ikke trukket noen konklusjon. 2 000 timer nås tidligst rundt 14.12.2026, og det er et anslag.
- Blinde retningsresultater og holdout-data skal aldri vises.
- Sider uten kilde (Tester & CI, Eksperimenter, deler av Modeller og Veikart) viser «Data ikke tilgjengelig ennå».
- «Simulert resultat» er bare fiktive tall.
- Nettlesertesten er ikke gjort. Den er ditt steg.
