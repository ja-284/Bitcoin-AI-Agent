> **Preserved document (added to the repository 2026-10-22).** This is Supplement S1 to dashboard data contract v1
> as delivered on 2026-10-22, for reporting contract version `"1"`, derived from backend commit `a9abca0`.
>
> Two things were adapted for the repository, and nothing else:
> 1. the paragraph about where the files are (they were in a temporary folder; they are now in this folder);
> 2. every code and JSON block is inserted byte-for-byte from the files in this folder, so the document and the files
>    cannot disagree. The edge-case block (S2.5) is therefore laid out slightly differently from the chat copy; its
>    data is identical.
>
> The JavaScript module's header was strengthened on 2026-10-22 to say "UNTESTED REFERENCE MATERIAL. NOT
> PRODUCTION-READY"; its code is unchanged. See `README.md` in this folder.

# Supplement S1 to dashboard data contract v1: technical definitions

**Reporting contract version:** `"1"` (unchanged).
**Date:** 2026-10-22.
**Status:** documentation handoff only. This is not authorisation to connect, deploy or change anything.

**How this supplement was made.**
- The schema was written once. The TypeScript below was **generated from it mechanically**.
- The same schema was used to validate the live tables **read-only**. Only error paths and counts were printed.
- The JSON fixtures were **produced by running the real reporting code** (`agent.reporting.publish.build` / `agent.reporting.views` at `a9abca0`) on **invented records dated 2030**.
- Nothing in the repository or the database was changed. No commit was made and nothing was published.

**The files** (in this folder, `docs/api/dashboard/`):

| file | content |
|---|---|
| `dashboard_contract_v1.ts` | Part S1, the complete TypeScript |
| `dashboard_reporting_client.js` | Part S3, the read-only access module (UNTESTED reference material) |
| `dashboard_fixtures_v1.json` | `main` (4 rows), `edge_cases` (E01–E19), `no_data_document` |

---

## S1. The complete TypeScript contract

**How to read it:**
- **Required:** no `?`.
- **Optional:** `?` means the key may be absent.
- **Nullable:** `| null` means the key is present and the value is null ("not available", never 0).
- **State-dependent:** discriminated unions (on `state`, `available`, `status`, or `"slices" in x`).
- **Code-only:** commented `NOT OBSERVED LIVE`. These are produced by the code and covered by fixtures, but were not in the live tables on 2026-10-22.

There are no `any` types. Runtime JSON must pass the validation in S3/S4 before it is treated as these types.

```typescript
// Bitcoin AI Control Center: dashboard data contract v1 (reporting_contract_version "1").
// GENERATED from the same schema that validated the live tables on 2026-10-22 and the fixtures produced by the
// real reporting code. Conventions: `?` = OPTIONAL (key may be absent); `| null` = NULLABLE (key present, value
// null = not available, never 0); unions = STATE-DEPENDENT shapes; "NOT OBSERVED LIVE" = in the code, not in
// the live tables on 2026-10-22. Runtime JSON must be validated before it is treated as these types.
// NOT YET COMPILED: no TypeScript compiler was available on 2026-10-22. Run `tsc --noEmit` before relying on it.
// Source: backend reporting code at commit a9abca0 (agent/reporting). Reporting contract version "1".

/** ISO 8601 with offset, always UTC ("+00:00"), e.g. "2030-01-07T09:00:00+00:00"; may carry microseconds ("2030-01-15T08:14:05.123456+00:00"). Compare as instants, never as strings. */
export type IsoTimestamp = string;

/** The five registered outcome horizons; every outcome table has all five. */
export type Horizon = "1h" | "6h" | "24h" | "72h" | "168h";

/** HOLD states no direction. */
export type SignalValue = "BUY" | "HOLD" | "SELL";

/** UP if the return > 0, otherwise DOWN (a return of exactly 0 is DOWN). */
export type Direction = "UP" | "DOWN";

/** [low, high] 95 % interval. An element is null only if it could not be computed. */
export type Interval95 = [number | null, number | null];

/** n < 192 / 192 <= n < 2000 / n >= 2000. */
/** NOT OBSERVED LIVE: "enough_for_nominal_intervals" */
export type SampleLevel = "too_few_to_conclude" | "early_intervals_optimistic" | "enough_for_nominal_intervals";

/** NOT OBSERVED LIVE: "nominal" */
export type SampleIntervals = "not_computed" | "shown_but_too_narrow" | "nominal";

export type SignalVsActual = "matched" | "not_matched" | "no_direction_stated";

/** NOT OBSERVED LIVE: "degraded", "attention_required" */
export type HeadlineStatus = "healthy" | "degraded" | "attention_required";

/** NOT OBSERVED LIVE: "watchdog_failed", "stats_publish_failed", "stats_snapshot_was_stale" */
export type RecordedIncidentKind = "hourly_run_failed" | "watchdog_failed" | "stats_publish_failed" | "stats_snapshot_was_stale";

/** Recorded kinds (first four) plus kinds derived from the record (last four). */
/** NOT OBSERVED LIVE: "watchdog_failed", "stats_publish_failed", "stats_snapshot_was_stale", "shadow_error" */
export type IncidentKind = "hourly_run_failed" | "watchdog_failed" | "stats_publish_failed" | "stats_snapshot_was_stale" | "missing_hour" | "run_degraded" | "shadow_error" | "shadow_row_missing";

/** NOT OBSERVED LIVE: "publisher" */
export type IncidentSource = "workflow_event" | "github_api_backfill" | "publisher";

/** NOT OBSERVED LIVE: "recorded (publisher)" */
export type HowKnown = "recorded (workflow_event)" | "recorded (github_api_backfill)" | "recorded (publisher)" | "derived from the record";

/** NOT OBSERVED LIVE: "Watchdog" */
export type WorkflowName = "Hourly Bitcoin analysis" | "Watchdog";

/** NOT OBSERVED LIVE: "timed_out", "startup_failure", "action_required" */
export type WorkflowConclusion = "failure" | "timed_out" | "startup_failure" | "action_required";

/** binance = primary; coingecko = fallback (fallback_used is true then). */
/** NOT OBSERVED LIVE: "coingecko" */
export type PriceSource = "binance" | "coingecko";

export type CategoryName = "trend" | "momentum" | "volume" | "chart_pattern" | "news";

export type HourBlockUtc = "00-06" | "06-12" | "12-18" | "18-24";

/** NOT OBSERVED LIVE: "mid", "high", "unknown" */
export type VolatilityRegime = "low" | "mid" | "high" | "unknown";

/** Attached to every statistic: how much a figure computed on n hours can say. */
export interface Sample {
  n: number;
  level: SampleLevel;
  intervals: SampleIntervals;
  is_verdict: false;  // Always false: no running figure is a verdict.
  headline: string;  // Show next to the figure, verbatim.
}

export interface ScoreQuantity {
  value: number | null;  // -1..+1
  kind: "score";
  is_probability: false;
  meaning: string;
}

export interface ConfidenceComponents {
  agreement: number | null;  // 0..1
  completeness: number | null;  // 0..1
}

export interface ConfidenceQuantity {
  value: number | null;  // 0..1. A consistency/completeness HEURISTIC, never a probability.
  kind: "heuristic";
  is_probability: false;
  meaning: string;
  components: ConfidenceComponents;
}

export interface PriceQuantity {
  value: number | null;  // USD close at the information cutoff.
  kind: "price";
  is_probability: false;
  meaning: string;
}

export interface ProbabilityQuantity {
  value: number | null;  // 0..1. The ONLY probability in the contract.
  kind: "calibrated_probability";
  is_probability: true;
  meaning: string;
}

export interface SignalOutcomeGraded {
  state: "graded";
  matured_at: IsoTimestamp;  // Close of the target candle = hour + h + 1 h.
  checked_at: IsoTimestamp;  // When it was recorded; never before matured_at.
  return: number;  // FRACTION: 0.0044 = +0.44 %.
  direction: Direction;
  signal_stated_direction: Direction | null;  // BUY -> UP, SELL -> DOWN, HOLD -> null.
  signal_vs_actual: SignalVsActual;
}

/** The exchange had no candle for the target hour. */
/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface OutcomeUnavailable {
  state: "unavailable";
  matured_at: IsoTimestamp;
  checked_at: IsoTimestamp;
  reason: string;  // Shown verbatim. Never retried.
}

export interface OutcomeWaiting {
  state: "pending" | "overdue";  // pending until one hour after matures_at; overdue after that if still not recorded. values NOT OBSERVED LIVE: "overdue"
  matures_at: IsoTimestamp;  // NOTE the key name: matures_at (waiting) vs matured_at (recorded).
}

/** Discriminate on `state`. */
export type SignalOutcome = SignalOutcomeGraded | OutcomeUnavailable | OutcomeWaiting;

export interface MoveSizeOutcomeGraded {
  state: "graded";
  matured_at: IsoTimestamp;
  checked_at: IsoTimestamp;
  return: number;  // FRACTION.
  direction: Direction;
  large_move: boolean;  // |return| > threshold_pct / 100.
  absolute_move: number;  // FRACTION; compare with threshold_pct / 100.
}

export type MoveSizeOutcome = MoveSizeOutcomeGraded | OutcomeUnavailable | OutcomeWaiting;

export interface MoveSizeAvailable {
  available: true;
  separate_from_signal: string;
  status: "research_shadow_only";
  model_version: string;
  horizon_hours: number;
  threshold_pct: number;  // ALREADY a percentage: 0.25 = 0.25 %.
  probability: ProbabilityQuantity;
  prospective: boolean;  // Stored before its outcome candle closed.
  outcome: MoveSizeOutcome;
}

export interface MoveSizeUnavailable {
  available: false;
  reason: string;  // Shown verbatim.
}

/** Discriminate on `available`. */
export type MoveSize = MoveSizeAvailable | MoveSizeUnavailable;

export interface RunTiming {
  start_lag_seconds: number;
  analysis_seconds: number;
  job_wall_time_seconds: null;  // Always null (not stored).
  note: string;
}

export interface RunSignal {
  value: SignalValue;
  evidence_status: "no_demonstrated_predictive_value";
  evidence: string;  // Always show next to the signal.
}

export interface RunVersions {
  pipeline: string;
  scoring: string;
  ai_news: string | null;
  ai_explanation: string | null;
  code_commit: string | null;
}

export interface RunNews {
  available: boolean;
  items_used: number;
  error_type: string | null;
  sources_failed: string[];  // Feed names (agent/news).
}

export interface RunHealth {
  status: "ok" | "degraded";
  problems: string[];  // Finished sentences; show verbatim.
  price_source: PriceSource;
  fallback_used: boolean;
  price_is_estimated: boolean;
  completeness: number | null;
  news: RunNews;
  explanation_available: boolean;
  database_role: string | null;
}

/** All five horizons are always present. */
export interface Outcomes {
  "1h": SignalOutcome;
  "6h": SignalOutcome;
  "24h": SignalOutcome;
  "72h": SignalOutcome;
  "168h": SignalOutcome;
}

/** One hourly run, as in snapshot.body.latest_run / latest_matured_run (no explanation, no categories). */
export interface RunView {
  hour: IsoTimestamp;  // Reference hour: the candle that opened at `hour`.
  information_cutoff: IsoTimestamp;  // = hour + 1 h.
  data_fetched_at: IsoTimestamp;
  saved_at: IsoTimestamp;
  timing: RunTiming;
  signal: RunSignal;
  overall_score: ScoreQuantity;
  confidence: ConfidenceQuantity;
  price: PriceQuantity;
  versions: RunVersions;
  run: RunHealth;
  outcomes: Outcomes;
  outcomes_note: string;
  move_size: MoveSize;
}

export interface Category {
  name: CategoryName;
  score: number | null;
  weight: number | null;
  is_independent: boolean | null;
  available: boolean;  // weight > 0. false = left out (e.g. failed news), NOT neutral.
}

/** One hourly run as stored in reporting_runs.run: RunView plus explanation and categories (always present there). */
export interface RunDetailView extends RunView {
  explanation: string | null;  // AI narration written AFTER the decision; null = none written.
  categories: Category[];
}

export interface Overview {
  latest_hour: IsoTimestamp | null;
  latest_signal: RunSignal | null;
  latest_confidence: ConfidenceQuantity | null;
  latest_move_size: MoveSize | null;
  latest_matured_hour: IsoTimestamp | null;
  latest_matured_1h_outcome: SignalOutcome | null;  // Always state graded when not null (that is what 'matured' means).
  latest_matured_move_size: MoveSize | null;
  health: "healthy" | "degraded" | "attention_required" | "no_data";  // values NOT OBSERVED LIVE: "degraded", "attention_required", "no_data"
  current_warning: string | null;
  prospective_progress: CheckpointProgress | null;
}

export interface SignalEvidence {
  status: "no_demonstrated_predictive_value";
  headline: string;
  detail: string;
  experiments: string[];
}

export interface SignalPopulation {
  runs: number;  // Pipeline-0.2.0 runs only.
  pipeline_version: string;
  excluded_older_pipeline_runs: number;
  scoring_versions: Record<string, number>;  // Keys contain dots ("0.1.0"): use bracket access.
}

export interface SignalCounts {
  BUY: number;
  HOLD: number;
  SELL: number;
}

export interface SignalConfidenceSummary {
  kind: "heuristic";
  is_probability: false;
  meaning: string;
  mean: number | null;
  note: string;
}

export interface ReturnGroup {
  graded: number;
  pending: number;
  overdue: number;
  unavailable: number;
  sample: Sample;
  share_followed_by_a_rise: number | null;  // null when graded = 0.
  share_ci95?: Interval95 | null;  // ABSENT when graded = 0; null when graded < 192. Wilson.
  mean_return?: number;  // ABSENT when graded = 0. FRACTION.
  median_return?: number;  // ABSENT when graded = 0. FRACTION.
}

export interface ActedDirectionAgreement {
  acted_graded: number;
  sample: Sample;
  note: string;
  majority_direction_share_all_hours?: number;  // ABSENT when no hour at this horizon is graded.
  matched_share?: number;  // ABSENT when acted_graded = 0.
  matched_ci95?: Interval95 | null;  // ABSENT when acted_graded = 0; null when < 192.
}

export interface HorizonEntry {
  BUY: ReturnGroup;
  HOLD: ReturnGroup;
  SELL: ReturnGroup;
  ALL: ReturnGroup;
  acted_direction_agreement: ActedDirectionAgreement;
}

/** All five horizons always present. */
export interface HorizonTable {
  "1h": HorizonEntry;
  "6h": HorizonEntry;
  "24h": HorizonEntry;
  "72h": HorizonEntry;
  "168h": HorizonEntry;
}

export interface SignalStatistics {
  evidence: SignalEvidence;
  what_this_is: string;
  population: SignalPopulation;
  signal_counts: SignalCounts;
  confidence: SignalConfidenceSummary;
  by_horizon: HorizonTable;
}

export interface CheckpointMilestones {
  "500": string;
  "2000": string;
  "5000": string;
}

export interface CheckpointProgress {
  prospective_graded_hours: number;  // Collected eligible hours; NOT a measure of skill.
  selection_rule: string;
  next_checkpoint_hours: number | null;  // null after 5,000.
  hours_remaining: number | null;
  expected_around: IsoTimestamp | null;  // ESTIMATE, recomputed at every publish.
  eta_assumption: string;
  reached: number[];
  computed_readings: Record<string, string>;  // Checkpoint -> repository path of the reading file; figures are NOT published.
  what_each_gives: CheckpointMilestones;
  rule: string;
}

/** One non-empty 0.1-wide bin of stated probability. */
export interface CalibrationBin {
  from: number;
  to: number;
  n: number;
  stated: number;
  observed: number;
  observed_ci95: Interval95;  // Wilson.
  enough_rows: boolean;  // n >= 100.
}

export interface RunningFigures {
  n: number;
  large_move_share: number;
  mean_stated_p: number;
  brier_rel_gain: number | null;
  brier_rel_gain_ci95?: Interval95;  // Present only when n >= 192 (block bootstrap).
  accuracy: number;
  accuracy_ci95: Interval95 | null;  // null when n < 192 (Wilson otherwise).
  naive_rate: number;
  rho: number | null;
  rho_ci95?: Interval95;  // Present only when n >= 192.
  ece: number;
  ece_ci95?: Interval95;  // Present only when n >= 192.
  brier: number;
  brier_of_the_observed_rate: number;
  calibration_bins: CalibrationBin[];
  note: string;
}

export interface MoveSizeStatus {
  status: "research_shadow_only";
  detail: string;
  experiments: string[];
}

export interface MoveSizeRowStates {
  graded: number;
  pending: number;
  overdue: number;
  outcome_unavailable: number;
  no_probability: number;
}

export interface MoveSizeStatistics {
  what_this_is: string;
  status: MoveSizeStatus;
  probability_meaning: string;
  rows: number;
  row_states: MoveSizeRowStates;
  not_prospective: number;
  model_versions: Record<string, number>;
  sample: Sample;
  checkpoint_progress: CheckpointProgress;
  running_figures?: RunningFigures;  // ABSENT when no prospective graded hour exists.
}

/** No intervals, ever (even when sample.intervals says shown_but_too_narrow). */
export interface SliceGroup {
  n: number;
  large_move_share: number | null;
  mean_stated_p: number | null;
  brier_rel_gain: number | null;
  ece: number | null;
  sample: Sample;
}

/** A group key appears only if that group has at least one graded hour. */
export interface BreakdownSlices {
  hour_block_utc: Partial<Record<HourBlockUtc, SliceGroup>>;
  weekday_weekend: Partial<Record<"weekday" | "weekend", SliceGroup>>;
  recent_vs_earlier: Partial<Record<"last_168_graded_hours" | "earlier", SliceGroup>>;
  volatility_regime_168h?: Partial<Record<VolatilityRegime, SliceGroup>>;  // ABSENT if the frozen terciles are unavailable.
}

export interface BreakdownDefinitions {
  hour_block_utc: string;
  weekday_weekend: string;
  volatility_regime_168h: string;
  recent_vs_earlier: string;
}

export interface MoveSizeBreakdownsAvailable {
  slices: BreakdownSlices;
  definitions: BreakdownDefinitions;
  reading_note: string;
}

/** No prospective graded hour yet. */
/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface MoveSizeBreakdownsEmpty {
  sample: Sample;
}

/** Discriminate on `"slices" in x`. */
export type MoveSizeBreakdowns = MoveSizeBreakdownsAvailable | MoveSizeBreakdownsEmpty;

export interface MoveSizeWeek {
  week_starting: IsoTimestamp;  // Monday 00:00 UTC.
  complete: boolean;
  sample: Sample;
  brier: number;
  n: number;  // JSON number, integer-valued (may be written 168.0).
  large_move_share: number | null;
  mean_stated_p: number | null;
  brier_rel_gain: number | null;
  ece: number | null;
}

export interface NeutralChange {
  latest: number | null;
  previous: number | null;
  difference?: number;  // ABSENT when latest or previous is null.
  wording: string;  // Neutral wording; show verbatim.
  is_a_conclusion: false;
}

export interface WeekComparison {
  latest_week: IsoTimestamp;
  previous_week: IsoTimestamp;
  samples: [number, number];  // ORDER: [previous week n, latest week n].
  brier: NeutralChange;
  ece: NeutralChange;
  large_move_share: NeutralChange;
  mean_stated_p: NeutralChange;
}

/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface WeekComparisonUnavailable {
  wording: "not enough complete weeks to compare";
}

export interface SignalWeek {
  week_starting: IsoTimestamp;
  complete: boolean;
  runs: number;
  signal_counts: SignalCounts;
  by_horizon: HorizonTable;
}

export interface Trends {
  what_this_is: string;
  important: string;  // Show on the page.
  move_size_by_week: MoveSizeWeek[];
  move_size_latest_vs_previous_complete_week: WeekComparison | WeekComparisonUnavailable;
  signal_by_week: SignalWeek[];
}

export interface LastRun {
  hour: IsoTimestamp;
  saved_at: IsoTimestamp;
  freshness: string;
  database_role: string | null;
  code_commit: string | null;
}

export interface MedianMax {
  median: number | null;
  max: number | null;
}

export interface WindowCounts {
  runs: number;  // SAVED HOURS in the window (not GitHub runs).
  missing_hours: number;
  fallback_price_runs: number;
  news_unavailable_runs: number;
  news_partial_runs: number;
  explanation_unavailable_runs: number;
  start_lag_seconds: MedianMax;
  analysis_seconds: MedianMax;
}

export interface HealthWindows {
  last_24h: WindowCounts;
  last_7d: WindowCounts;
  all_time: WindowCounts;
}

export interface HealthOutcomes {
  overdue_by_horizon: Partial<Record<Horizon, number>>;  // {} when nothing is overdue.
  graded_before_their_candle_closed: number;
  rows_for_unregistered_horizons: number;
  registered_horizons_hours: number[];
}

/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface ShadowErrorSummary {
  occurred_at: IsoTimestamp;
  step: string;
  error_type: string;
}

export interface HealthShadow {
  rows: number;
  hours_without_a_shadow_row: number;
  errors_total: number;
  errors_last_24h: number;
  latest_error: ShadowErrorSummary | null;
  note: string;
}

/** The hourly job's backend_state cache. NOT the reporting snapshot. */
export interface PublishedState {
  contract_version: string;
  generated_at: IsoTimestamp;
  age_hours: number;
}

/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface PublishedStateUnavailable {
  available: false;
  reason: string;
}

export interface ExternalNotObservable {
  observable_here: false;
  where: string;
}

export interface ExternalWatchdog {
  observable_here: "failed runs only";
  where: string;
}

export interface HealthExternal {
  heartbeat: ExternalNotObservable;
  watchdog: ExternalWatchdog;
  job_wall_time: ExternalNotObservable;
}

export interface IncidentCapture {
  recorded: string[];
  derived_from_the_record: string[];
  not_captured: string[];
  recorded_since: string;  // A date, "2026-10-05".
  note: string;
}

export interface HealthIncidents {
  recorded_total: number;
  recorded_last_24h: number;
  recorded_by_kind: Partial<Record<RecordedIncidentKind, number>>;
  capture: IncidentCapture;
}

export interface IncidentItem {
  at: IsoTimestamp;
  kind: IncidentKind;
  how_known: HowKnown;
  summary: string;  // Finished sentence; show verbatim.
  link: string | null;  // Public GitHub run page or null.
}

/** Health when at least one prediction exists. Judged at generated_at. */
export interface HealthFull {
  status: "ok" | "degraded" | "stale";  // values NOT OBSERVED LIVE: "degraded", "stale"
  headline_status: HeadlineStatus;
  headline_rule: string;
  problems: string[];
  current_warning: string | null;
  last_run: LastRun;
  windows: HealthWindows;
  missing_hours_all_time: IsoTimestamp[];  // The ONLY source for missing-hour placeholders.
  missing_note: string;
  outcomes: HealthOutcomes;
  shadow: HealthShadow;
  published_state: PublishedState | PublishedStateUnavailable;
  schema_version: string | null;  // DATABASE schema version ("4"), not the contract version.
  external: HealthExternal;
  checkpoint_progress: CheckpointProgress;
  incidents: HealthIncidents;
  incident_history: IncidentItem[];  // Complete merged list, newest first. Preferred display source.
}

/** Health when no prediction exists at all. */
/** NOT OBSERVED LIVE (2026-10-22): produced by the code, covered by the fixtures. */
export interface HealthNoData {
  status: "no_data";
  problems: string[];
  external: HealthExternal;
}

/** Discriminate on `status === "no_data"`. */
export type Health = HealthFull | HealthNoData;

export interface ReportBody {
  overview: Overview;
  latest_run: RunView | null;
  latest_matured_run: RunView | null;
  signal_statistics: SignalStatistics;
  move_size_statistics: MoveSizeStatistics;
  move_size_breakdowns: MoveSizeBreakdowns;
  trends: Trends;
  health: Health;
}

export interface SnapshotDocument {
  reporting_contract_version: "1";
  kind: "all";
  as_known_at: IsoTimestamp;
  generated_at: IsoTimestamp;  // Equals the row's generated_at and as_known_at.
  read_only: true;  // Applies to the whole document.
  descriptive_only: true;  // Applies to the whole document.
  never_use_for: string[];
  limitations: string[];
  body: ReportBody;
}

/** public.reporting_snapshot (exactly one row). */
export interface ReportingSnapshotRow {
  id: 1;
  reporting_contract_version: "1";
  as_known_at: IsoTimestamp;
  generated_at: IsoTimestamp;
  document: SnapshotDocument;
}

/** public.reporting_runs (one row per saved hour). */
export interface ReportingRunRow {
  hour: IsoTimestamp;  // PRIMARY KEY; equals run.hour.
  reporting_contract_version: "1";
  as_known_at: IsoTimestamp;  // The publish at which this row's content last changed.
  run: RunDetailView;
}

/** public.reporting_incidents (append-only). */
export interface ReportingIncidentRow {
  incident_key: string;  // Opaque, unique. Do not parse.
  kind: RecordedIncidentKind;
  source: IncidentSource;
  occurred_at: IsoTimestamp;
  recorded_at: IsoTimestamp;
  workflow: WorkflowName | null;  // null for publisher incidents.
  conclusion: WorkflowConclusion | null;  // null for publisher incidents.
  run_url: string | null;  // null for publisher incidents.
  detail: string;
}
```

---

## S2. Fictional fixtures (machine-valid JSON)

All values are invented: dates in 2030, prices around 10,000 USD, random fictional scores. The backend sentences (`meaning`, `headline`, `note` and so on) are the real constant texts, because the code emits them unchanged.

### S2.1 Which fixture for which test

| fixture (in `dashboard_fixtures_v1.json`) | use it for |
|---|---|
| `main.reporting_snapshot_row` (98 KB, **file only**, too large for this document) | **The contract-validation test** for the snapshot and the rendering tests for all pages. |
| `main.reporting_runs_row_pending` (S2.3) | the run list and run details with every outcome pending; the same publish as the snapshot |
| `main.reporting_runs_row_graded` (S2.4) | all five horizons graded; `as_known_at` earlier than the snapshot (the normal case) |
| `main.reporting_incidents_row` (S2.2) | a recorded GitHub run failure |
| `edge_cases[]` E01–E19 (S2.5) | states not seen live: overdue, unavailable, stale, no data, absent `running_figures`, null/absent intervals, publisher incident, ≥ 5,000 hours |
| `no_data_document` (file only) | a complete document with no prediction at all |

**What the main snapshot fixture contains** (all values fictional):
- `generated_at` = `as_known_at` = `2030-01-15T08:14:05.123456+00:00`.
- `overview.latest_hour` = `2030-01-15T07:00:00+00:00`, the pending run row.
- 200 hours from `2030-01-07T00:00` and 199 saved, with one missing hour, `2030-01-09T02:00`, listed in `missing_hours_all_time`.
- One hour without a shadow row (`2030-01-10T08:00`).
- One degraded run: news failed at `2030-01-12T00:00`.
- One recorded failed run at `2030-01-12T20:12`. Its hour (`19:00`) was filled by the :22 backup slot.
- 197 graded move-size hours, so the `running_figures` intervals are present.
- All three volatility regimes, both sample levels, and groups with `graded = 0` (absent keys) inside `trends.signal_by_week`.
- `health` is `ok` / `healthy`, because every incident is more than 24 h old.

**Tests to derive from the main fixtures** (one mutation each; expected result in S4):
- version `"2"` → refused;
- `document.kind` removed → refused;
- `body.trends` removed → only Trends disabled;
- an extra unknown key → ignored;
- `state: "exploded"` → "Ukjent tilstand";
- a run row with `as_known_at` later than `generated_at` → refetch the snapshot;
- `information_cutoff` ≠ `hour` + 1 h → that row rejected;
- `now` = `generated_at` + 89 / 91 / 181 minutes, or − 10 minutes → normal / warning / serious / clock-suspect.

### S2.2 One `reporting_incidents` row

```json
{
  "incident_key": "github:9000000001:1",
  "kind": "hourly_run_failed",
  "source": "workflow_event",
  "occurred_at": "2030-01-12T20:12:03+00:00",
  "workflow": "Hourly Bitcoin analysis",
  "conclusion": "failure",
  "run_url": "https://github.com/ja-284/Bitcoin-AI-Agent/actions/runs/9000000001",
  "detail": "The 'Hourly Bitcoin analysis' run started at 2030-01-12 20:12 UTC (workflow_dispatch, attempt 1) ended: failure.",
  "recorded_at": "2030-01-12T20:15:44+00:00"
}
```

### S2.3 One `reporting_runs` row with every outcome pending (the newest hour; same publish as the snapshot)

```json
{
  "hour": "2030-01-15T07:00:00+00:00",
  "reporting_contract_version": "1",
  "as_known_at": "2030-01-15T08:14:05.123456+00:00",
  "run": {
    "hour": "2030-01-15T07:00:00+00:00",
    "information_cutoff": "2030-01-15T08:00:00+00:00",
    "data_fetched_at": "2030-01-15T08:12:31+00:00",
    "saved_at": "2030-01-15T08:12:56+00:00",
    "timing": {
      "start_lag_seconds": 751.0,
      "analysis_seconds": 25.0,
      "job_wall_time_seconds": null,
      "note": "start lag = candle close -> data fetched; analysis = data fetched -> row saved. The whole GitHub job's duration is not stored in the database (see the Actions run)."
    },
    "signal": {"value": "SELL", "evidence_status": "no_demonstrated_predictive_value", "evidence": "This signal has not been shown to predict anything."},
    "overall_score": {
      "value": -0.3064,
      "kind": "score",
      "is_probability": false,
      "meaning": "The weighted combination of the category scores, from -1 to +1. A score, not a probability and not an expected return."
    },
    "confidence": {
      "value": 0.6634,
      "kind": "heuristic",
      "is_probability": false,
      "meaning": "A consistency and completeness estimate, not a probability. It rises when the independent categories agree with each other and when all the data was available. It has been checked against real outcomes and carries no information about whether the signal turns out to be right (E001, E017).",
      "components": {"agreement": 0.3268, "completeness": 1.0}
    },
    "price": {"value": 9438.6, "kind": "price", "is_probability": false, "meaning": "Bitcoin's closing price at the information cutoff, in US dollars."},
    "versions": {
      "pipeline": "0.2.0",
      "scoring": "0.2.0",
      "ai_news": "claude-haiku-4-5",
      "ai_explanation": "claude-sonnet-5",
      "code_commit": "0000000000000000000000000000000000000000"
    },
    "run": {
      "status": "ok",
      "problems": [],
      "price_source": "binance",
      "fallback_used": false,
      "price_is_estimated": false,
      "completeness": 1.0,
      "news": {"available": true, "items_used": 44, "error_type": null, "sources_failed": []},
      "explanation_available": true,
      "database_role": "bitcoin_agent"
    },
    "outcomes": {
      "1h": {"state": "pending", "matures_at": "2030-01-15T09:00:00+00:00"},
      "6h": {"state": "pending", "matures_at": "2030-01-15T14:00:00+00:00"},
      "24h": {"state": "pending", "matures_at": "2030-01-16T08:00:00+00:00"},
      "72h": {"state": "pending", "matures_at": "2030-01-18T08:00:00+00:00"},
      "168h": {"state": "pending", "matures_at": "2030-01-22T08:00:00+00:00"}
    },
    "outcomes_note": "Raw price change after the reference close, as a fraction (0.0044 = +0.44%), and its direction by the registered binary rule (UP if > 0). `signal_vs_actual` compares that with the direction the signal stated (BUY = UP, SELL = DOWN; HOLD states none). Bitcoin drifts on its own: a rise after a BUY is not evidence the signal worked, and no profit is implied.",
    "move_size": {
      "available": true,
      "separate_from_signal": "research shadow model; it has never influenced the BUY/HOLD/SELL signal",
      "status": "research_shadow_only",
      "model_version": "move_size_1h_v1",
      "horizon_hours": 1,
      "threshold_pct": 0.25,
      "probability": {
        "value": 0.0997,
        "kind": "calibrated_probability",
        "is_probability": true,
        "meaning": "The estimated chance that Bitcoin's price moves more than 0.25% in either direction over the next hour. This says nothing about the DIRECTION of the move. It is calibrated: across validation data, hours given about this chance did move that much about this often (E012, E013)."
      },
      "prospective": true,
      "outcome": {"state": "pending", "matures_at": "2030-01-15T09:00:00+00:00"}
    },
    "explanation": "FICTIONAL FIXTURE TEXT, not a real analysis. In the real system this field holds the AI's plain-language narration, written after the signal was decided; it explains the decision and is not evidence for it.",
    "categories": [
      {"name": "trend", "score": 0.199, "weight": 0.3, "is_independent": true, "available": true},
      {"name": "momentum", "score": 0.562, "weight": 0.25, "is_independent": true, "available": true},
      {"name": "volume", "score": -0.4925, "weight": 0.15, "is_independent": true, "available": true},
      {"name": "chart_pattern", "score": -0.357, "weight": 0.1, "is_independent": false, "available": true},
      {"name": "news", "score": -0.1443, "weight": 0.2, "is_independent": true, "available": true}
    ]
  }
}
```

### S2.4 One `reporting_runs` row with all five outcomes graded

This is the oldest hour. Its row last changed at the publish right after its 168h outcome was recorded; the generator checked that its content is identical at that moment and at the snapshot's moment.

```json
{
  "hour": "2030-01-07T00:00:00+00:00",
  "reporting_contract_version": "1",
  "as_known_at": "2030-01-14T01:14:05.123456+00:00",
  "run": {
    "hour": "2030-01-07T00:00:00+00:00",
    "information_cutoff": "2030-01-07T01:00:00+00:00",
    "data_fetched_at": "2030-01-07T01:12:31+00:00",
    "saved_at": "2030-01-07T01:12:56+00:00",
    "timing": {
      "start_lag_seconds": 751.0,
      "analysis_seconds": 25.0,
      "job_wall_time_seconds": null,
      "note": "start lag = candle close -> data fetched; analysis = data fetched -> row saved. The whole GitHub job's duration is not stored in the database (see the Actions run)."
    },
    "signal": {"value": "BUY", "evidence_status": "no_demonstrated_predictive_value", "evidence": "This signal has not been shown to predict anything."},
    "overall_score": {
      "value": 0.1513,
      "kind": "score",
      "is_probability": false,
      "meaning": "The weighted combination of the category scores, from -1 to +1. A score, not a probability and not an expected return."
    },
    "confidence": {
      "value": 0.8737,
      "kind": "heuristic",
      "is_probability": false,
      "meaning": "A consistency and completeness estimate, not a probability. It rises when the independent categories agree with each other and when all the data was available. It has been checked against real outcomes and carries no information about whether the signal turns out to be right (E001, E017).",
      "components": {"agreement": 0.7474, "completeness": 1.0}
    },
    "price": {"value": 10000.0, "kind": "price", "is_probability": false, "meaning": "Bitcoin's closing price at the information cutoff, in US dollars."},
    "versions": {
      "pipeline": "0.2.0",
      "scoring": "0.2.0",
      "ai_news": "claude-haiku-4-5",
      "ai_explanation": "claude-sonnet-5",
      "code_commit": "0000000000000000000000000000000000000000"
    },
    "run": {
      "status": "ok",
      "problems": [],
      "price_source": "binance",
      "fallback_used": false,
      "price_is_estimated": false,
      "completeness": 1.0,
      "news": {"available": true, "items_used": 49, "error_type": null, "sources_failed": []},
      "explanation_available": true,
      "database_role": "bitcoin_agent"
    },
    "outcomes": {
      "1h": {
        "state": "graded",
        "matured_at": "2030-01-07T02:00:00+00:00",
        "checked_at": "2030-01-07T02:12:40+00:00",
        "return": -0.0006229999999999292,
        "direction": "DOWN",
        "signal_stated_direction": "UP",
        "signal_vs_actual": "not_matched"
      },
      "6h": {
        "state": "graded",
        "matured_at": "2030-01-07T07:00:00+00:00",
        "checked_at": "2030-01-07T07:12:40+00:00",
        "return": 0.0019240000000000368,
        "direction": "UP",
        "signal_stated_direction": "UP",
        "signal_vs_actual": "matched"
      },
      "24h": {
        "state": "graded",
        "matured_at": "2030-01-08T01:00:00+00:00",
        "checked_at": "2030-01-08T01:12:40+00:00",
        "return": 0.022342000000000084,
        "direction": "UP",
        "signal_stated_direction": "UP",
        "signal_vs_actual": "matched"
      },
      "72h": {
        "state": "graded",
        "matured_at": "2030-01-10T01:00:00+00:00",
        "checked_at": "2030-01-10T01:12:40+00:00",
        "return": 0.0016439999999999788,
        "direction": "UP",
        "signal_stated_direction": "UP",
        "signal_vs_actual": "matched"
      },
      "168h": {
        "state": "graded",
        "matured_at": "2030-01-14T01:00:00+00:00",
        "checked_at": "2030-01-14T01:12:40+00:00",
        "return": -0.06061700000000003,
        "direction": "DOWN",
        "signal_stated_direction": "UP",
        "signal_vs_actual": "not_matched"
      }
    },
    "outcomes_note": "Raw price change after the reference close, as a fraction (0.0044 = +0.44%), and its direction by the registered binary rule (UP if > 0). `signal_vs_actual` compares that with the direction the signal stated (BUY = UP, SELL = DOWN; HOLD states none). Bitcoin drifts on its own: a rise after a BUY is not evidence the signal worked, and no profit is implied.",
    "move_size": {
      "available": true,
      "separate_from_signal": "research shadow model; it has never influenced the BUY/HOLD/SELL signal",
      "status": "research_shadow_only",
      "model_version": "move_size_1h_v1",
      "horizon_hours": 1,
      "threshold_pct": 0.25,
      "probability": {
        "value": 0.2919,
        "kind": "calibrated_probability",
        "is_probability": true,
        "meaning": "The estimated chance that Bitcoin's price moves more than 0.25% in either direction over the next hour. This says nothing about the DIRECTION of the move. It is calibrated: across validation data, hours given about this chance did move that much about this often (E012, E013)."
      },
      "prospective": true,
      "outcome": {
        "state": "graded",
        "matured_at": "2030-01-07T02:00:00+00:00",
        "checked_at": "2030-01-07T02:13:10+00:00",
        "return": -0.0006229999999999292,
        "direction": "DOWN",
        "large_move": false,
        "absolute_move": 0.0006229999999999292
      }
    },
    "explanation": "FICTIONAL FIXTURE TEXT, not a real analysis. In the real system this field holds the AI's plain-language narration, written after the signal was decided; it explains the decision and is not evidence for it.",
    "categories": [
      {"name": "trend", "score": 0.297, "weight": 0.3, "is_independent": true, "available": true},
      {"name": "momentum", "score": -0.5178, "weight": 0.25, "is_independent": true, "available": true},
      {"name": "volume", "score": -0.5726, "weight": 0.15, "is_independent": true, "available": true},
      {"name": "chart_pattern", "score": 0.0348, "weight": 0.1, "is_independent": false, "available": true},
      {"name": "news", "score": 0.1715, "weight": 0.2, "is_independent": true, "available": true}
    ]
  }
}
```

### S2.5 Edge cases: states that exist in code but not in live data

Each `value` is a complete object of the named `type`, produced by the real code and validated against S1.

```json
[
  {
    "id": "E01",
    "type": "SignalOutcome",
    "where": "run.outcomes[h]",
    "description": "OVERDUE: due more than an hour ago, not recorded.",
    "value": {"state": "overdue", "matures_at": "2030-03-04T02:00:00+00:00"}
  },
  {
    "id": "E02",
    "type": "MoveSizeOutcome",
    "where": "run.move_size.outcome",
    "description": "OVERDUE move-size outcome.",
    "value": {"state": "overdue", "matures_at": "2030-03-04T02:00:00+00:00"}
  },
  {
    "id": "E03",
    "type": "Health",
    "where": "document.body.health",
    "description": "STALE health: no fresh prediction (status stale -> headline attention_required), outcomes overdue, a shadow error, a recorded publisher incident, and no backend_state (published_state unavailable).",
    "value": {
      "status": "stale",
      "headline_status": "attention_required",
      "headline_rule": "attention_required: no fresh prediction, or a failed hourly/watchdog run in the last 24 h; degraded: any other problem in the last 24 h; healthy: none. Judged when this was computed.",
      "problems": [
        "newest prediction is for 2030-03-04T09:00:00+00:00 (4.5h since its candle closed)",
        "4 hour(s) missing in the last 24 hours",
        "1 research shadow error(s) in the last 24 hours (the live record is unaffected)",
        "17 outcome(s) overdue",
        "1 recorded incident(s) in the last 24 hours: stats snapshot was stale"
      ],
      "current_warning": "newest prediction is for 2030-03-04T09:00:00+00:00 (4.5h since its candle closed)",
      "last_run": {
        "hour": "2030-03-04T09:00:00+00:00",
        "saved_at": "2030-03-04T10:12:56+00:00",
        "freshness": "newest prediction is for 2030-03-04T09:00:00+00:00 (4.5h since its candle closed)",
        "database_role": "bitcoin_agent",
        "code_commit": "0000000000000000000000000000000000000000"
      },
      "windows": {
        "last_24h": {
          "runs": 10,
          "missing_hours": 4,
          "fallback_price_runs": 0,
          "news_unavailable_runs": 0,
          "news_partial_runs": 0,
          "explanation_unavailable_runs": 0,
          "start_lag_seconds": {"median": 751.0, "max": 751.0},
          "analysis_seconds": {"median": 25.0, "max": 25.0}
        },
        "last_7d": {
          "runs": 10,
          "missing_hours": 4,
          "fallback_price_runs": 0,
          "news_unavailable_runs": 0,
          "news_partial_runs": 0,
          "explanation_unavailable_runs": 0,
          "start_lag_seconds": {"median": 751.0, "max": 751.0},
          "analysis_seconds": {"median": 25.0, "max": 25.0}
        },
        "all_time": {
          "runs": 10,
          "missing_hours": 4,
          "fallback_price_runs": 0,
          "news_unavailable_runs": 0,
          "news_partial_runs": 0,
          "explanation_unavailable_runs": 0,
          "start_lag_seconds": {"median": 751.0, "max": 751.0},
          "analysis_seconds": {"median": 25.0, "max": 25.0}
        }
      },
      "missing_hours_all_time": ["2030-03-04T10:00:00+00:00", "2030-03-04T11:00:00+00:00", "2030-03-04T12:00:00+00:00", "2030-03-04T13:00:00+00:00"],
      "missing_note": "Missing hours are never backfilled; the ones on go-live weekend (2026-09-19/20) are documented and permanent.",
      "outcomes": {
        "overdue_by_horizon": {"1h": 10, "6h": 7},
        "graded_before_their_candle_closed": 0,
        "rows_for_unregistered_horizons": 0,
        "registered_horizons_hours": [1, 6, 24, 72, 168]
      },
      "shadow": {
        "rows": 10,
        "hours_without_a_shadow_row": 0,
        "errors_total": 1,
        "errors_last_24h": 1,
        "latest_error": {"occurred_at": "2030-03-04T09:12:50+00:00", "step": "fetch", "error_type": "ConnectionError"},
        "note": "Error messages are kept in the database for diagnosis and deliberately not published here."
      },
      "published_state": {"available": false, "reason": "no published snapshot known at this time"},
      "schema_version": "4",
      "external": {
        "heartbeat": {"observable_here": false, "where": "the healthchecks.io dashboard (it emails when pings stop)"},
        "watchdog": {
          "observable_here": "failed runs only",
          "where": "failed runs are recorded as incidents since 2026-10-05; successful runs are not stored (GitHub -> Actions -> Watchdog)"
        },
        "job_wall_time": {"observable_here": false, "where": "GitHub -> Actions -> the hourly run"}
      },
      "checkpoint_progress": {
        "prospective_graded_hours": 0,
        "selection_rule": "the registered checkpoint's own selection (agent/research/live_checkpoint.prospective_graded): status ok, outcome ok, probability stored before the outcome candle closed",
        "next_checkpoint_hours": 500,
        "hours_remaining": 500,
        "expected_around": "2030-03-25T10:30:00+00:00",
        "eta_assumption": "one graded hour per hour from now, none lost; the newest hour is graded about an hour after it closes",
        "reached": [],
        "computed_readings": {},
        "what_each_gives": {"500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict"},
        "rule": "A checkpoint reads exactly the first N prospective graded hours (research/LIVE_EVALUATION.md rule 8). The running figures in this report cover every graded hour known at the time and are never a checkpoint."
      },
      "incidents": {
        "recorded_total": 1,
        "recorded_last_24h": 1,
        "recorded_by_kind": {"stats_snapshot_was_stale": 1},
        "capture": {
          "recorded": [
            "a failed hourly run (also when a later backup run filled its hour)",
            "a failed watchdog run",
            "a failed stats publish (when the database could still be reached)",
            "a stats snapshot that was not refreshed for more than 3 hours"
          ],
          "derived_from_the_record": [
            "a missing hour",
            "a run with news unavailable, fallback price data, no explanation or an unavailable category",
            "a research shadow error",
            "an hour without a shadow row"
          ],
          "not_captured": [
            "a heartbeat alarm (it lives on healthchecks.io, outside this database)",
            "a reporting-workflow run that failed before it could write anything, e.g. no GitHub runner (when publishing resumes after more than 3 hours the gap is recorded; a shorter gap leaves no record, and nothing is lost, because every publish recomputes everything from the record)",
            "anything while the database itself is unreachable"
          ],
          "recorded_since": "2026-10-05",
          "note": "Failed runs from before 2026-10-05 were backfilled from GitHub's own run history (source 'github_api_backfill'); GitHub keeps that history for a limited time only."
        }
      },
      "incident_history": [
        {
          "at": "2030-03-04T13:00:00+00:00",
          "kind": "missing_hour",
          "how_known": "derived from the record",
          "summary": "No prediction was recorded for the 2030-03-04 13:00 UTC hour.",
          "link": null
        },
        {
          "at": "2030-03-04T12:00:00+00:00",
          "kind": "missing_hour",
          "how_known": "derived from the record",
          "summary": "No prediction was recorded for the 2030-03-04 12:00 UTC hour.",
          "link": null
        },
        {
          "at": "2030-03-04T11:00:00+00:00",
          "kind": "missing_hour",
          "how_known": "derived from the record",
          "summary": "No prediction was recorded for the 2030-03-04 11:00 UTC hour.",
          "link": null
        },
        {
          "at": "2030-03-04T10:00:00+00:00",
          "kind": "missing_hour",
          "how_known": "derived from the record",
          "summary": "No prediction was recorded for the 2030-03-04 10:00 UTC hour.",
          "link": null
        },
        {
          "at": "2030-03-04T09:14:00+00:00",
          "kind": "stats_snapshot_was_stale",
          "how_known": "recorded (publisher)",
          "summary": "The stats snapshot was not refreshed between 2030-03-04 09:14 and 2030-03-04 13:02 UTC (3.8 hours).",
          "link": null
        },
        {
          "at": "2030-03-04T09:12:50+00:00",
          "kind": "shadow_error",
          "how_known": "derived from the record",
          "summary": "The research shadow step failed at 'fetch' (ConnectionError); the live record is unaffected.",
          "link": null
        }
      ]
    }
  },
  {
    "id": "E04",
    "type": "SignalOutcome",
    "where": "run.outcomes[h]",
    "description": "UNAVAILABLE: the exchange had no candle for the target hour.",
    "value": {
      "state": "unavailable",
      "matured_at": "2030-05-06T02:00:00+00:00",
      "checked_at": "2030-05-06T02:12:40+00:00",
      "reason": "the target candle is missing from the exchange's history"
    }
  },
  {
    "id": "E05",
    "type": "MoveSizeOutcome",
    "where": "run.move_size.outcome",
    "description": "UNAVAILABLE move-size outcome.",
    "value": {
      "state": "unavailable",
      "matured_at": "2030-05-06T02:00:00+00:00",
      "checked_at": "2030-05-06T02:13:10+00:00",
      "reason": "the target candle is missing from the exchange's history"
    }
  },
  {
    "id": "E06",
    "type": "MoveSize",
    "where": "run.move_size",
    "description": "No probability: the shadow row exists but has no probability.",
    "value": {"available": false, "reason": "model refused an input (non-positive value for a log-transformed feature)"}
  },
  {
    "id": "E07",
    "type": "MoveSize",
    "where": "run.move_size",
    "description": "No shadow row for this hour.",
    "value": {"available": false, "reason": "no shadow row for this hour"}
  },
  {
    "id": "E08",
    "type": "SignalOutcome",
    "where": "run.outcomes[h]",
    "description": "PENDING outcome.",
    "value": {"state": "pending", "matures_at": "2030-05-06T06:00:00+00:00"}
  },
  {
    "id": "E09",
    "type": "Health",
    "where": "document.body.health",
    "description": "NO_DATA: no prediction exists at all.",
    "value": {
      "status": "no_data",
      "problems": ["no prediction has been stored"],
      "external": {
        "heartbeat": {"observable_here": false, "where": "the healthchecks.io dashboard (it emails when pings stop)"},
        "watchdog": {
          "observable_here": "failed runs only",
          "where": "failed runs are recorded as incidents since 2026-10-05; successful runs are not stored (GitHub -> Actions -> Watchdog)"
        },
        "job_wall_time": {"observable_here": false, "where": "GitHub -> Actions -> the hourly run"}
      }
    }
  },
  {
    "id": "E10",
    "type": "Overview",
    "where": "document.body.overview",
    "description": "NO_DATA overview.",
    "value": {
      "latest_hour": null,
      "latest_signal": null,
      "latest_confidence": null,
      "latest_move_size": null,
      "latest_matured_hour": null,
      "latest_matured_1h_outcome": null,
      "latest_matured_move_size": null,
      "health": "no_data",
      "current_warning": null,
      "prospective_progress": null
    }
  },
  {
    "id": "E11",
    "type": "MoveSizeStatistics",
    "where": "document.body.move_size_statistics",
    "description": "running_figures ABSENT (no graded hour).",
    "value": {
      "what_this_is": "The research shadow model's stated chance of a move larger than the threshold in the next hour, against what happened. Separate from the BUY/HOLD/SELL signal, which it never influences.",
      "status": {
        "status": "research_shadow_only",
        "detail": "This probability runs alongside the live system in its own record and has never influenced the BUY/HOLD/SELL signal. Its calibration was measured on 2024-2025 validation data; its prospective record began on 2026-09-21 and is judged at 500, 2,000 and 5,000 hours. The final sealed holdout has not been opened.",
        "experiments": ["E012", "E013", "E018", "E019", "E020", "E021"]
      },
      "probability_meaning": "The estimated chance that Bitcoin's price moves more than 0.25% in either direction over the next hour. This says nothing about the DIRECTION of the move. It is calibrated: across validation data, hours given about this chance did move that much about this often (E012, E013).",
      "rows": 0,
      "row_states": {"graded": 0, "pending": 0, "overdue": 0, "outcome_unavailable": 0, "no_probability": 0},
      "not_prospective": 0,
      "model_versions": {},
      "sample": {
        "n": 0,
        "level": "too_few_to_conclude",
        "intervals": "not_computed",
        "is_verdict": false,
        "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
      },
      "checkpoint_progress": {
        "prospective_graded_hours": 0,
        "selection_rule": "the registered checkpoint's own selection (agent/research/live_checkpoint.prospective_graded): status ok, outcome ok, probability stored before the outcome candle closed",
        "next_checkpoint_hours": 500,
        "hours_remaining": 500,
        "expected_around": "2030-07-22T08:14:05+00:00",
        "eta_assumption": "one graded hour per hour from now, none lost; the newest hour is graded about an hour after it closes",
        "reached": [],
        "computed_readings": {},
        "what_each_gives": {"500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict"},
        "rule": "A checkpoint reads exactly the first N prospective graded hours (research/LIVE_EVALUATION.md rule 8). The running figures in this report cover every graded hour known at the time and are never a checkpoint."
      }
    }
  },
  {
    "id": "E12",
    "type": "MoveSizeBreakdowns",
    "where": "document.body.move_size_breakdowns",
    "description": "No graded hour: only `sample`.",
    "value": {
      "sample": {
        "n": 0,
        "level": "too_few_to_conclude",
        "intervals": "not_computed",
        "is_verdict": false,
        "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
      }
    }
  },
  {
    "id": "E13",
    "type": "HorizonEntry",
    "where": "document.body.signal_statistics.by_horizon[h]",
    "description": "graded = 0 everywhere: share_ci95 / mean_return / median_return / matched_* / majority_* ABSENT.",
    "value": {
      "BUY": {
        "graded": 0,
        "pending": 0,
        "overdue": 0,
        "unavailable": 0,
        "sample": {
          "n": 0,
          "level": "too_few_to_conclude",
          "intervals": "not_computed",
          "is_verdict": false,
          "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
        },
        "share_followed_by_a_rise": null
      },
      "HOLD": {
        "graded": 0,
        "pending": 0,
        "overdue": 0,
        "unavailable": 0,
        "sample": {
          "n": 0,
          "level": "too_few_to_conclude",
          "intervals": "not_computed",
          "is_verdict": false,
          "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
        },
        "share_followed_by_a_rise": null
      },
      "SELL": {
        "graded": 0,
        "pending": 0,
        "overdue": 0,
        "unavailable": 0,
        "sample": {
          "n": 0,
          "level": "too_few_to_conclude",
          "intervals": "not_computed",
          "is_verdict": false,
          "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
        },
        "share_followed_by_a_rise": null
      },
      "ALL": {
        "graded": 0,
        "pending": 0,
        "overdue": 0,
        "unavailable": 0,
        "sample": {
          "n": 0,
          "level": "too_few_to_conclude",
          "intervals": "not_computed",
          "is_verdict": false,
          "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
        },
        "share_followed_by_a_rise": null
      },
      "acted_direction_agreement": {
        "acted_graded": 0,
        "sample": {
          "n": 0,
          "level": "too_few_to_conclude",
          "intervals": "not_computed",
          "is_verdict": false,
          "headline": "0 hours: far too few to conclude anything. A description of what happened, not evidence of how the system behaves."
        },
        "note": "How often a BUY was followed by a rise or a SELL by a fall, next to how often guessing the more common direction of all these hours would have been right. A higher first number on a small sample is not evidence; over 68,619 historical hours there was no edge (E001, E017). Not a profit figure."
      }
    }
  },
  {
    "id": "E14",
    "type": "RunningFigures",
    "where": "document.body.move_size_statistics.running_figures",
    "description": "n < 192: accuracy_ci95 null; brier_rel_gain_ci95 / rho_ci95 / ece_ci95 ABSENT.",
    "value": {
      "n": 39,
      "large_move_share": 0.358974358974359,
      "mean_stated_p": 0.21068461538461541,
      "brier_rel_gain": -0.14720099334285708,
      "accuracy": 0.6666666666666666,
      "accuracy_ci95": null,
      "naive_rate": 0.641025641025641,
      "rho": -0.0896761133603239,
      "ece": 0.15404871794871794,
      "brier": 0.2639844494871795,
      "brier_of_the_observed_rate": 0.23011176857330704,
      "calibration_bins": [
        {
          "from": 0.0,
          "to": 0.1,
          "n": 3,
          "stated": 0.06846666666666666,
          "observed": 0.6666666666666666,
          "observed_ci95": [0.2076549551264879, 0.9385096847238394],
          "enough_rows": false
        },
        {
          "from": 0.1,
          "to": 0.2,
          "n": 17,
          "stated": 0.15141764705882355,
          "observed": 0.35294117647058826,
          "observed_ci95": [0.17309486143904904, 0.5870003327878818],
          "enough_rows": false
        },
        {
          "from": 0.2,
          "to": 0.3,
          "n": 13,
          "stated": 0.2394076923076923,
          "observed": 0.23076923076923078,
          "observed_ci95": [0.08179379092465713, 0.5025687399512693],
          "enough_rows": false
        },
        {
          "from": 0.3,
          "to": 0.4,
          "n": 5,
          "stated": 0.34931999999999996,
          "observed": 0.4,
          "observed_ci95": [0.1176182311592533, 0.769280067791163],
          "enough_rows": false
        },
        {"from": 0.5, "to": 0.6, "n": 1, "stated": 0.5783, "observed": 1.0, "observed_ci95": [0.20654329147389294, 1.0], "enough_rows": false}
      ],
      "note": "Every prospective graded hour known at this moment. Descriptive; the registered readings are the checkpoint files, and the only verdicts are at 2,000 (E012) and 5,000 (E013) hours."
    }
  },
  {
    "id": "E15",
    "type": "WeekComparison",
    "where": "document.body.trends.move_size_latest_vs_previous_complete_week",
    "description": "Two complete weeks exist: neutral comparison object.",
    "value": {
      "latest_week": "2030-11-18T00:00:00+00:00",
      "previous_week": "2030-11-11T00:00:00+00:00",
      "samples": [168.0, 168.0],
      "brier": {
        "latest": 0.28131225404761906,
        "previous": 0.2976863444047619,
        "difference": -0.016374090357142823,
        "wording": "lower than the previous week",
        "is_a_conclusion": false
      },
      "ece": {
        "latest": 0.2113476190476191,
        "previous": 0.2180345238095238,
        "difference": -0.0066869047619046995,
        "wording": "lower than the previous week",
        "is_a_conclusion": false
      },
      "large_move_share": {
        "latest": 0.3869047619047619,
        "previous": 0.44047619047619047,
        "difference": -0.05357142857142855,
        "wording": "lower than the previous week",
        "is_a_conclusion": false
      },
      "mean_stated_p": {
        "latest": 0.21975595238095236,
        "previous": 0.22244166666666665,
        "difference": -0.0026857142857142913,
        "wording": "lower than the previous week",
        "is_a_conclusion": false
      }
    }
  },
  {
    "id": "E16",
    "type": "NeutralChange",
    "where": "WeekComparison.<metric>",
    "description": "A side is null: `difference` ABSENT.",
    "value": {"latest": null, "previous": 0.21, "wording": "not enough data to compare", "is_a_conclusion": false}
  },
  {
    "id": "E17",
    "type": "CheckpointProgress",
    "where": "document.body.overview.prospective_progress",
    "description": "After the 500-hour reading: computed_readings has its repository path.",
    "value": {
      "prospective_graded_hours": 1234,
      "selection_rule": "the registered checkpoint's own selection (agent/research/live_checkpoint.prospective_graded): status ok, outcome ok, probability stored before the outcome candle closed",
      "next_checkpoint_hours": 2000,
      "hours_remaining": 766,
      "expected_around": "2030-02-16T06:14:05.123456+00:00",
      "eta_assumption": "one graded hour per hour from now, none lost; the newest hour is graded about an hour after it closes",
      "reached": [500],
      "computed_readings": {"500": "research/monitoring/checkpoint_500h.md"},
      "what_each_gives": {"500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict"},
      "rule": "A checkpoint reads exactly the first N prospective graded hours (research/LIVE_EVALUATION.md rule 8). The running figures in this report cover every graded hour known at the time and are never a checkpoint."
    }
  },
  {
    "id": "E18",
    "type": "CheckpointProgress",
    "where": "document.body.overview.prospective_progress",
    "description": "FICTIONAL FUTURE STATE after 5,000 hours: no next checkpoint (nulls). The 2,000/5,000 reading files do not exist today.",
    "value": {
      "prospective_graded_hours": 5000,
      "selection_rule": "the registered checkpoint's own selection (agent/research/live_checkpoint.prospective_graded): status ok, outcome ok, probability stored before the outcome candle closed",
      "next_checkpoint_hours": null,
      "hours_remaining": null,
      "expected_around": null,
      "eta_assumption": "one graded hour per hour from now, none lost; the newest hour is graded about an hour after it closes",
      "reached": [500, 2000, 5000],
      "computed_readings": {
        "500": "research/monitoring/checkpoint_500h.md",
        "2000": "research/monitoring/checkpoint_2000h.md",
        "5000": "research/monitoring/checkpoint_5000h.md"
      },
      "what_each_gives": {"500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict"},
      "rule": "A checkpoint reads exactly the first N prospective graded hours (research/LIVE_EVALUATION.md rule 8). The running figures in this report cover every graded hour known at the time and are never a checkpoint."
    }
  },
  {
    "id": "E19",
    "type": "ReportingIncidentRow",
    "where": "public.reporting_incidents",
    "description": "A PUBLISHER incident: workflow / conclusion / run_url are null.",
    "value": {
      "incident_key": "publisher:stale:2030-03-04T09:14:00",
      "kind": "stats_snapshot_was_stale",
      "source": "publisher",
      "occurred_at": "2030-03-04T09:14:00+00:00",
      "workflow": null,
      "conclusion": null,
      "run_url": null,
      "detail": "The stats snapshot was not refreshed between 2030-03-04 09:14 and 2030-03-04 13:02 UTC (3.8 hours).",
      "recorded_at": "2030-03-04T13:02:08+00:00"
    }
  }
]
```

---

## S3. Read-only Supabase access (supabase-js v2, reusing the existing client)

The module reuses the frontend's existing authenticated client. It does not use the built-in Lovable Supabase integration, a `service_role` key, `.rpc()`, any write or any other table.

**Configuration:** `expectedUserId` is the dashboard account's id, the one named in the `control_center_read` policy (`agent/reporting/schema.sql`). Comparing it is only a convenience for the UI; RLS is what actually enforces access.

**UNTESTED REFERENCE MATERIAL, NOT PRODUCTION-READY.** No JavaScript runtime was available, so this module has never been executed or type-checked. Adapt it, then compile, execute and test it against the fixtures in the frontend's own test suite before any use.

```javascript
// Bitcoin AI Control Center: read-only access to dashboard data contract v1 (reporting_contract_version "1").
//
// UNTESTED REFERENCE MATERIAL. NOT PRODUCTION-READY.
// This module has never been executed or type-checked: no JavaScript runtime or TypeScript compiler was available
// where it was written (2026-10-22). Adapt it, then compile, execute and test it against dashboard_fixtures_v1.json
// in the frontend's own test suite before any use. Do not copy it into production unchanged and untested.
//
// - Reuses the frontend's EXISTING authenticated supabase-js v2 client (passed in as `supabase`). It creates no
//   client, stores no credential, token or session, and logs none.
// - Reads exactly three tables with SELECT: reporting_snapshot, reporting_runs, reporting_incidents.
//   No insert/update/upsert/delete, no .rpc(), no other table, no Realtime, no Storage.
// - Types: see dashboard_contract_v1.ts. Test data: dashboard_fixtures_v1.json (fictional).

/** @typedef {import('./dashboard_contract_v1').ReportingSnapshotRow} ReportingSnapshotRow */
/** @typedef {import('./dashboard_contract_v1').ReportingRunRow} ReportingRunRow */
/** @typedef {import('./dashboard_contract_v1').ReportingIncidentRow} ReportingIncidentRow */

export const SUPPORTED_CONTRACT_VERSION = '1';
export const RUNS_PAGE_SIZE = 24;
const REQUEST_TIMEOUT_MS = 15000;
const HOUR_MS = 3600000;
const MINUTE_MS = 60000;
const HORIZON_HOURS = { '1h': 1, '6h': 6, '24h': 24, '72h': 72, '168h': 168 };
const SNAPSHOT_COLUMNS = 'id, reporting_contract_version, as_known_at, generated_at, document';
const RUN_COLUMNS = 'hour, reporting_contract_version, as_known_at, run';
const INCIDENT_COLUMNS = 'incident_key, kind, source, occurred_at, recorded_at, workflow, conclusion, run_url, detail';

// kind: 'not_signed_in' | 'needs_aal2' | 'wrong_account' | 'no_row' | 'auth' | 'network' | 'timeout' | 'server'
//       | 'unsupported_version' | 'invalid_contract'
export class ReportingError extends Error {
  constructor(kind, message, details = {}) {
    super(message);
    this.name = 'ReportingError';
    this.kind = kind;
    this.details = details; // status / code only; never tokens, never response bodies
  }
}

// ------------------------------------------------------------------ time
/** Milliseconds since epoch, or NaN. Trims fractional seconds to 3 digits (the API may send 6). */
export function parseInstant(value) {
  if (typeof value !== 'string') return NaN;
  return Date.parse(value.replace(/(\.\d{3})\d+/, '$1'));
}
function isInstant(value) {
  return typeof value === 'string' && /(Z|[+-]\d{2}:\d{2})$/.test(value) && !Number.isNaN(parseInstant(value));
}
/** A canonical UTC ISO string for filters ("...Z": no '+' that a route or URL could mangle). */
export function toUtcIso(value) {
  const ms = value instanceof Date ? value.getTime() : parseInstant(value);
  if (Number.isNaN(ms)) throw new ReportingError('invalid_contract', 'not a timestamp');
  return new Date(ms).toISOString();
}
const isObj = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);

// ------------------------------------------------------------------ access (a UX check; RLS is the real control)
/**
 * @param supabase the existing authenticated client
 * @param expectedUserId the dashboard account's id (the one named in the read policy), from the app's config
 */
export async function checkAccess(supabase, expectedUserId) {
  const { data: userData, error: userError } = await supabase.auth.getUser(); // asks the Auth server, not local storage
  if (userError || !userData?.user) return { ok: false, reason: 'not_signed_in' };
  const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (aalError) return { ok: false, reason: 'auth' };
  if (aal?.currentLevel !== 'aal2') return { ok: false, reason: 'needs_aal2' };
  if (expectedUserId && userData.user.id !== expectedUserId) return { ok: false, reason: 'wrong_account' };
  return { ok: true };
}

// ------------------------------------------------------------------ one request, with timeout and error classes
async function run(buildQuery, label) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await buildQuery(controller.signal);
    if (res.error) throw classify(res.error, res.status, label, controller.signal.aborted);
    return res;
  } catch (e) {
    if (e instanceof ReportingError) throw e;
    if (controller.signal.aborted) throw new ReportingError('timeout', `${label}: no answer within ${REQUEST_TIMEOUT_MS / 1000} s`);
    throw new ReportingError('network', `${label}: network failure`);
  } finally {
    clearTimeout(timer);
  }
}

function classify(error, status, label, aborted) {
  const msg = String(error?.message ?? '');
  if (aborted || /abort/i.test(msg)) return new ReportingError('timeout', `${label}: request timed out`);
  if (!status || /failed to fetch|networkerror|load failed/i.test(msg)) return new ReportingError('network', `${label}: network failure`);
  if (status === 401 || status === 403 || error?.code === '42501' || /jwt/i.test(msg)) {
    return new ReportingError('auth', `${label}: not authorised`, { status, code: error?.code });
  }
  return new ReportingError('server', `${label}: request failed`, { status, code: error?.code });
}

// ------------------------------------------------------------------ the three reads
/** The one snapshot row (id = 1). Throws ReportingError; 'no_row' = 0 rows (aal1, another account, or nothing published). */
export async function fetchSnapshot(supabase) {
  const { data } = await run(
    (signal) => supabase.from('reporting_snapshot').select(SNAPSHOT_COLUMNS).eq('id', 1).abortSignal(signal).maybeSingle(),
    'reporting_snapshot');
  if (data === null) throw new ReportingError('no_row', 'reporting_snapshot returned no row');
  const v = validateSnapshotRow(data);
  if (!v.ok) throw new ReportingError(v.kind, v.problems.join('; '));
  return { row: /** @type {ReportingSnapshotRow} */ (data), sectionProblems: v.sectionProblems };
}

/**
 * Newest first, at most 24 rows, stable keyset pagination on the primary key `hour`.
 * @param options.before the `hour` of the oldest row already shown (omit for the first page)
 */
export async function fetchRunsPage(supabase, { before = null, limit = RUNS_PAGE_SIZE } = {}) {
  const size = Math.min(Math.max(1, Math.trunc(limit) || RUNS_PAGE_SIZE), RUNS_PAGE_SIZE);
  const { data } = await run((signal) => {
    let q = supabase.from('reporting_runs').select(RUN_COLUMNS);
    if (before) q = q.lt('hour', toUtcIso(before));
    return q.order('hour', { ascending: false }).limit(size).abortSignal(signal);
  }, 'reporting_runs');
  const rows = [];
  const rejected = []; // shown as "could not display this hour", never silently dropped
  for (const row of data ?? []) {
    const v = validateRunRow(row);
    if (v.ok) rows.push(/** @type {ReportingRunRow} */ (row));
    else rejected.push({ hour: isObj(row) ? row.hour ?? null : null, kind: v.kind, problems: v.problems });
  }
  const last = (data ?? [])[(data ?? []).length - 1];
  return { rows, rejected, firstPage: !before, nextBefore: (data ?? []).length === size && last ? last.hour : null };
}

/** One hour. { row: null } = no row: a missing hour, not saved yet, or no access (decide with the snapshot). */
export async function fetchRun(supabase, hour) {
  const { data } = await run(
    (signal) => supabase.from('reporting_runs').select(RUN_COLUMNS).eq('hour', toUtcIso(hour)).abortSignal(signal).maybeSingle(),
    'reporting_runs');
  if (data === null) return { row: null };
  const v = validateRunRow(data);
  if (!v.ok) throw new ReportingError(v.kind, v.problems.join('; '));
  return { row: /** @type {ReportingRunRow} */ (data) };
}

/** The RECORDED incidents only (a subset of snapshot.document.body.health.incident_history), newest first. */
export async function fetchIncidents(supabase, { limit = 50 } = {}) {
  const size = Math.min(Math.max(1, Math.trunc(limit) || 50), 200);
  const { data } = await run(
    (signal) => supabase.from('reporting_incidents').select(INCIDENT_COLUMNS)
      .order('occurred_at', { ascending: false }).order('incident_key', { ascending: false })
      .limit(size).abortSignal(signal),
    'reporting_incidents');
  return /** @type {ReportingIncidentRow[]} */ (data ?? []);
}

// ------------------------------------------------------------------ validation (contract v1)
const SECTION_REQUIRED = {
  overview: ['latest_hour', 'latest_signal', 'latest_confidence', 'latest_move_size', 'latest_matured_hour',
    'latest_matured_1h_outcome', 'latest_matured_move_size', 'health', 'current_warning', 'prospective_progress'],
  signal_statistics: ['evidence', 'what_this_is', 'population', 'signal_counts', 'confidence', 'by_horizon'],
  move_size_statistics: ['what_this_is', 'status', 'probability_meaning', 'rows', 'row_states', 'not_prospective',
    'model_versions', 'sample', 'checkpoint_progress'],
  trends: ['what_this_is', 'important', 'move_size_by_week', 'move_size_latest_vs_previous_complete_week', 'signal_by_week'],
};
const HEALTH_REQUIRED = ['status', 'headline_status', 'headline_rule', 'problems', 'current_warning', 'last_run', 'windows',
  'missing_hours_all_time', 'missing_note', 'outcomes', 'shadow', 'published_state', 'schema_version', 'external',
  'checkpoint_progress', 'incidents', 'incident_history'];
const RUN_REQUIRED = ['hour', 'information_cutoff', 'data_fetched_at', 'saved_at', 'timing', 'signal', 'overall_score',
  'confidence', 'price', 'versions', 'run', 'outcomes', 'outcomes_note', 'move_size'];

const missingKeys = (obj, keys) => keys.filter((k) => !(k in obj)); // present-with-null is fine; absent is not

/** Envelope problems reject the whole snapshot; section problems disable only that section. */
export function validateSnapshotRow(row) {
  if (!isObj(row)) return { ok: false, kind: 'invalid_contract', problems: ['no snapshot row'] };
  const d = row.document;
  if (row.reporting_contract_version !== SUPPORTED_CONTRACT_VERSION || (isObj(d) && d.reporting_contract_version !== SUPPORTED_CONTRACT_VERSION)) {
    return { ok: false, kind: 'unsupported_version', problems: ['unsupported reporting_contract_version'] };
  }
  const fatal = [];
  if (!isObj(d)) fatal.push('document missing');
  else {
    if (d.kind !== 'all') fatal.push('document.kind is not "all"');
    if (d.read_only !== true) fatal.push('document.read_only is not true');
    if (d.descriptive_only !== true) fatal.push('document.descriptive_only is not true');
    if (!Array.isArray(d.never_use_for) || !Array.isArray(d.limitations)) fatal.push('never_use_for / limitations missing');
    if (!isObj(d.body)) fatal.push('document.body missing');
    if (!isInstant(d.as_known_at) || !isInstant(d.generated_at)) fatal.push('document timestamps invalid');
  }
  if (!isInstant(row.as_known_at) || !isInstant(row.generated_at)) fatal.push('row timestamps invalid');
  if (!fatal.length) {
    const g = parseInstant(row.generated_at);
    if ([row.as_known_at, d.generated_at, d.as_known_at].some((t) => parseInstant(t) !== g)) {
      fatal.push('generated_at / as_known_at disagree (they are equal in every v1 snapshot)');
    }
  }
  if (fatal.length) return { ok: false, kind: 'invalid_contract', problems: fatal };
  return { ok: true, sectionProblems: validateBody(d.body) };
}

function validateBody(body) {
  const problems = {};
  const note = (section, list) => { if (list.length) problems[section] = list; };
  for (const [section, keys] of Object.entries(SECTION_REQUIRED)) {
    note(section, isObj(body[section]) ? missingKeys(body[section], keys).map((k) => `${k} missing`) : ['section missing']);
  }
  for (const section of ['latest_run', 'latest_matured_run']) {
    if (!(section in body)) note(section, ['section missing']);
    else if (body[section] !== null) note(section, isObj(body[section]) ? runViewProblems(body[section], false) : ['not an object']);
  }
  const b = body.move_size_breakdowns;
  note('move_size_breakdowns', !isObj(b) ? ['section missing']
    : 'slices' in b ? missingKeys(b, ['slices', 'definitions', 'reading_note']).map((k) => `${k} missing`)
      : ('sample' in b ? [] : ['neither slices nor sample']));
  const h = body.health;
  note('health', !isObj(h) ? ['section missing']
    : h.status === 'no_data' ? missingKeys(h, ['status', 'problems', 'external']).map((k) => `${k} missing`)
      : missingKeys(h, HEALTH_REQUIRED).map((k) => `${k} missing`));
  return problems; // {} when every section can be rendered
}

/** Row-level checks of a reporting_runs row. A failing row is shown as "could not display", never dropped. */
export function validateRunRow(row) {
  if (!isObj(row)) return { ok: false, kind: 'invalid_contract', problems: ['not a row'] };
  if (row.reporting_contract_version !== SUPPORTED_CONTRACT_VERSION) {
    return { ok: false, kind: 'unsupported_version', problems: ['unsupported reporting_contract_version'] };
  }
  const problems = [];
  if (!isInstant(row.hour) || !isInstant(row.as_known_at)) problems.push('hour / as_known_at invalid');
  if (!isObj(row.run)) problems.push('run missing');
  else {
    problems.push(...runViewProblems(row.run, true));
    if (!problems.length && parseInstant(row.run.hour) !== parseInstant(row.hour)) problems.push('run.hour differs from hour');
  }
  return { ok: problems.length === 0, kind: problems.length ? 'invalid_contract' : null, problems };
}

/** The timestamp invariants every v1 run satisfies (checked on all live rows on 2026-10-22). */
export function runViewProblems(r, isStoredRow) {
  const required = isStoredRow ? [...RUN_REQUIRED, 'explanation', 'categories'] : RUN_REQUIRED;
  const p = missingKeys(r, required).map((k) => `run.${k} missing`);
  if (p.length) return p;
  const h = parseInstant(r.hour);
  if (Number.isNaN(h)) return ['run.hour invalid'];
  if (parseInstant(r.information_cutoff) !== h + HOUR_MS) p.push('information_cutoff is not hour + 1 h');
  if (parseInstant(r.saved_at) < parseInstant(r.data_fetched_at)) p.push('saved_at before data_fetched_at');
  const checkOutcome = (o, hours, name) => {
    if (!isObj(o)) { p.push(`${name} missing`); return; }
    const due = h + (hours + 1) * HOUR_MS; // the target candle's close
    if (o.state === 'graded' || o.state === 'unavailable') {
      if (parseInstant(o.matured_at) !== due) p.push(`${name}.matured_at inconsistent`);
      if (!(parseInstant(o.checked_at) >= due)) p.push(`${name} recorded before its candle closed`);
    } else if (o.state === 'pending' || o.state === 'overdue') {
      if (parseInstant(o.matures_at) !== due) p.push(`${name}.matures_at inconsistent`);
    } // an unknown state is rendered as "Ukjent tilstand", it does not invalidate the row
  };
  for (const [key, hours] of Object.entries(HORIZON_HOURS)) checkOutcome(r.outcomes?.[key], hours, `outcomes.${key}`);
  if (isObj(r.move_size) && r.move_size.available === true) checkOutcome(r.move_size.outcome, r.move_size.horizon_hours, 'move_size.outcome');
  return p;
}

// ------------------------------------------------------------------ same publication?
/**
 * The snapshot and the runs come from separate requests and can straddle an hourly publish.
 * Rows only change when their content changes, so any row with as_known_at <= generated_at is consistent.
 */
export function comparePublication(snapshotRow, runRows, { firstPage }) {
  const g = parseInstant(snapshotRow.generated_at);
  const latest = snapshotRow.document.body.overview?.latest_hour ?? null;
  const newestRun = runRows.length ? runRows[0].hour : null;
  const rowNewer = runRows.some((row) => parseInstant(row.as_known_at) > g);
  const runsAhead = Boolean(firstPage && latest && newestRun && parseInstant(newestRun) > parseInstant(latest));
  const snapshotAhead = Boolean(firstPage && latest && newestRun && parseInstant(latest) > parseInstant(newestRun));
  return { consistent: !rowNewer && !runsAhead && !snapshotAhead, refetch: rowNewer || runsAhead ? 'snapshot' : snapshotAhead ? 'runs' : null };
}

/** First screen: access, snapshot, first page; one retry if a publish happened between the reads. */
export async function loadFirstScreen(supabase, expectedUserId) {
  const access = await checkAccess(supabase, expectedUserId);
  if (!access.ok) return { state: access.reason };
  let snapshot = await fetchSnapshot(supabase);
  let page = await fetchRunsPage(supabase);
  let pub = comparePublication(snapshot.row, page.rows, { firstPage: true });
  if (pub.refetch === 'snapshot') snapshot = await fetchSnapshot(supabase);
  if (pub.refetch === 'runs') page = await fetchRunsPage(supabase);
  if (pub.refetch) pub = comparePublication(snapshot.row, page.rows, { firstPage: true });
  return { state: 'ok', snapshot, page, publicationChangedDuringLoad: !pub.consistent };
}

// ------------------------------------------------------------------ freshness (two independent clocks)
export function freshness(snapshotRow, now = Date.now()) {
  const g = parseInstant(snapshotRow.generated_at);
  const body = snapshotRow.document.body;
  const latest = body.overview?.latest_hour ?? null;
  const snapshotAge = (now - g) / MINUTE_MS;
  const recordAge = latest ? (now - (parseInstant(latest) + HOUR_MS)) / MINUTE_MS : null;
  const clockSuspect = snapshotAge < -5; // the device clock is behind the server by more than 5 minutes
  return {
    snapshotAgeMinutes: Math.max(0, snapshotAge),
    snapshotLevel: clockSuspect ? 'clock_suspect' : snapshotAge > 180 ? 'serious' : snapshotAge > 90 ? 'warning' : 'normal',
    analysisAgeMinutes: recordAge === null ? null : Math.max(0, recordAge),
    analysisLevel: recordAge === null ? 'no_data' : clockSuspect ? 'clock_suspect' : recordAge > 120 ? 'warning' : 'normal',
    serverHealthStatus: body.health?.status ?? null, // judged by the backend at generated_at; independent of the device clock
    generatedAt: snapshotRow.generated_at, // always show the absolute time too
  };
}

// ------------------------------------------------------------------ missing-hour placeholders (from the snapshot only)
/**
 * @param upperBound the `hour` of the oldest row on the previous (newer) page; null for the first page
 */
export function withMissingHourPlaceholders(snapshotRow, pageRows, upperBound) {
  const health = snapshotRow.document.body.health;
  if (!pageRows.length || !health || health.status === 'no_data') return pageRows.map((row) => ({ type: 'run', row }));
  const lower = parseInstant(pageRows[pageRows.length - 1].hour);
  const upper = upperBound ? parseInstant(upperBound) : Infinity;
  const items = pageRows.map((row) => ({ type: 'run', t: parseInstant(row.hour), row }));
  for (const hour of health.missing_hours_all_time) {
    const t = parseInstant(hour);
    if (t > lower && t < upper) items.push({ type: 'missing_hour', t, hour });
  }
  return items.sort((a, b) => b.t - a.t).map(({ t, ...item }) => item);
}

// ------------------------------------------------------------------ display formatting (no statistics computed)
const nb = (digits) => new Intl.NumberFormat('nb-NO', { maximumFractionDigits: digits, minimumFractionDigits: digits });
/** A return stored as a FRACTION (0.0044) shown as a percentage ("+0,44 %"). */
export function returnText(fraction) {
  if (typeof fraction !== 'number') return 'Ikke tilgjengelig';
  const s = nb(2).format(fraction * 100);
  return `${fraction > 0 ? '+' : ''}${s} %`;
}
/** threshold_pct is ALREADY a percentage (0.25 -> "0,25 %"). */
export function thresholdText(pct) {
  return typeof pct === 'number' ? `${nb(2).format(pct)} %` : 'Ikke tilgjengelig';
}
/** Only a quantity with is_probability === true may be shown as a chance. */
export function probabilityText(q) {
  if (!isObj(q) || q.is_probability !== true || typeof q.value !== 'number') return 'Ikke tilgjengelig';
  return `${nb(0).format(q.value * 100)} % sjanse`;
}
/** The confidence heuristic: a score, never a percentage. */
export function heuristicText(q) {
  if (!isObj(q) || q.kind !== 'heuristic' || typeof q.value !== 'number') return 'Ikke tilgjengelig';
  return `${nb(2).format(q.value)} (konsistensscore, ikke sannsynlighet)`;
}
```

**Expected behaviour of the client calls.** Each is either established by how RLS works or still to be confirmed in the browser test:

| case | expected | status |
|---|---|---|
| Signed in, aal2, dashboard account | rows returned | verified at SQL level 2026-10-21 (1 / 764 / 17 rows) |
| Signed in at aal1, or another account | `data` = `[]` / `null`, no error → `no_row` | verified at SQL level; browser NOT VERIFIED |
| Not signed in | error, permission denied (42501). HTTP 401 expected → `auth`. | the HTTP code is NOT VERIFIED |
| Network down | supabase-js returns `status` 0 or throws → `network` | NOT VERIFIED |
| Expired or invalid session | 401 with a JWT message → `auth`. Refresh the session or ask to sign in. | NOT VERIFIED |
| aal2 kept after an automatic token refresh | expected | NOT VERIFIED |

---

## S4. Contract validation rules

### S4.1 Where the flags live

| field | exact location | scope |
|---|---|---|
| `reporting_contract_version` | column `reporting_snapshot.reporting_contract_version`; `document.reporting_contract_version`; column `reporting_runs.reporting_contract_version` (every row) | snapshot: the whole document; runs: that row. Not inside `run` JSON; not in `reporting_incidents`. |
| `document.kind` | document root | the whole document (always `"all"`) |
| `read_only` | document root only | the whole document. Run rows do not carry it. |
| `descriptive_only` | document root only | the whole document |
| `is_verdict` | every `Sample` object (`….sample.is_verdict`) | that one statistic. Always `false`. |
| `is_probability` | every `Quantity` (`overall_score`, `confidence`, `price`, `move_size.probability`) and `signal_statistics.confidence` | that one metric. `true` only on `move_size.probability`. |
| `is_a_conclusion` | every `NeutralChange` in `trends` | that one comparison. Always `false`. |
| `generated_at` | column `reporting_snapshot.generated_at` and `document.generated_at` (equal) | freshness of the whole snapshot. **Not** `health.published_state.generated_at`, which belongs to another cache. |
| `overview.latest_hour` | `document.body.overview.latest_hour` | the newest saved hour as of `generated_at` |

### S4.2 What each problem leads to

| problem | detection | action |
|---|---|---|
| **Unsupported contract version** | any of the three version fields ≠ `"1"` | refuse the snapshot, or that run row: "Ukjent dataformat – oppdater dashbordet". No fallback, no demo data. |
| **Missing required envelope field** (version, `kind`, `read_only`, `descriptive_only`, timestamps, `never_use_for`, `limitations`, `body`) | `validateSnapshotRow` | refuse the whole snapshot |
| **Missing required section or a required key in a section** | `validateBody` | disable **only that section**: "Kunne ikke vise denne delen". Everything else renders. |
| **Missing required run field** | `runViewProblems` | that row shows as "Kunne ikke vise denne timen". It is never silently dropped. |
| **Missing optional field** (`share_ci95`, `mean_return`, `median_return`, `majority_direction_share_all_hours`, `matched_*`, `running_figures`, `*_ci95` in `running_figures`, `volatility_regime_168h`, `difference`) | `!(key in obj)` | normal state: "Ikke tilgjengelig" or "ikke beregnet". **Never a rejection.** |
| **Explicit null** | `value === null` | "Ikke tilgjengelig". Never 0, never an empty bar. |
| **Unknown additional field** | key not in S1 | ignore (forward-compatible); optionally log it in development |
| **Unknown enum value** | value not in S1 | neutral label "Ukjent (verdi)", no colour. For a discriminator (`state`, `available`, `status`): "Ukjent tilstand" for that cell only. |
| **Inconsistent timestamps** | the snapshot's `generated_at` ≠ its `as_known_at` (in the row or in the document); `run.hour` ≠ row `hour`; `information_cutoff` ≠ `hour` + 1 h; `saved_at` < `data_fetched_at`; `matured_at` / `matures_at` ≠ `hour` + h + 1 h; `checked_at` < `matured_at` | snapshot: refuse. Run: reject that row. These are v1 invariants that hold in every live row (S8). |
| **Data fetched during a publication change** | a run row's `as_known_at` > the snapshot's `generated_at`; or on the first page the newest `hour` ≠ `overview.latest_hour` | refetch the older side once (`comparePublication`). If it is still inconsistent: render with "Dataene ble oppdatert mens siden lastet – last inn på nytt". |

---

## S5. Metric presentation rules (reconfirmed)

1. **Returns are fractions** (`0.0044` = +0.44 %). Convert only for display (`returnText`).
2. **`threshold_pct` is already a percentage** (`0.25` = 0.25 %). Compare `absolute_move` (a fraction) with `threshold_pct / 100`.
3. **Confidence is a consistency heuristic, not a probability.** Show it as a score (`0,66`), never with "%" or "sjanse".
4. **Only `move_size.probability`** (`is_probability: true`) may be shown as a probability.
5. **Pending, overdue, unavailable and missing outcomes are never counted as graded.** The counts come from the publisher (`graded`, `pending`, `overdue`, `unavailable`). The frontend does not count them itself.
6. **HOLD means no directional claim**: `signal_stated_direction` is null and `signal_vs_actual` is `no_direction_stated`.
7. **Signal statistics exclude pipeline-0.1.0 runs**, as the publisher defines it (`population.excluded_older_pipeline_runs`). The frontend does not filter anything itself.
8. **Overlapping windows.** 6h, 24h, 72h and 168h outcomes of hourly runs overlap, so they are not independent observations. Their intervals are too narrow, and the UI must say so.
9. **No official verdict** is shown unless the publisher explicitly provides one. None does today: `is_verdict` is always false, and checkpoint figures are not published.
10. **Checkpoint progress counts collected eligible hours, not predictive skill.** Use a neutral colour, and label it "Innsamlede timer".
11. **No P&L or real trading performance exists.**
12. **The frontend may do only:** unit formatting, time-zone display, freshness ages, ordering, pagination, and placing missing-hour placeholders from the published list. It may **not** recompute performance, invent statistics, colour results as good or bad, or derive conclusions.

---

## S6. Health and freshness rules (reconfirmed)

There are two independent clocks (`freshness()`):

| clock | measured from | normal | warning | serious |
|---|---|---|---|---|
| Snapshot freshness | now − `generated_at` | ≤ 90 min | > 90 min | > 3 h: "Rapporteringen oppdateres ikke. Viser data fra {generated_at}." |
| Latest saved analysis | now − (`overview.latest_hour` + 1 h) | ≤ 2 h | > 2 h: "Ingen ny analyse lagret siden {latest_hour + 1 h}" | — |

**Device-clock errors:**
- An age between −5 and 0 minutes is normal clock jitter; clamp it to 0.
- An age below −5 minutes means the device clock is behind. Show "Enhetens klokke ser ut til å gå feil" and suppress age-based warnings.
- Always show the **absolute** UTC/Oslo times next to every age.
- Also always show the **server-judged** `health.status` / `headline_status`. It was computed by the backend at `generated_at` and does not depend on the device clock.
- A device clock that runs ahead cannot be detected without a server time. The absolute times let the reader notice it.

**Other rules:**
- **Missing-hour placeholders** come only from `document.body.health.missing_hours_all_time` (`withMissingHourPlaceholders`). The UI never infers gaps from the run list.
- **Incidents:** `document.body.health.incident_history` is the complete, preferred list. `reporting_incidents` is the recorded subset and is already included in that history (`how_known: "recorded (…)"`). **Never merge the two lists.** If the raw table is shown at all, show it on its own as "Registrerte hendelser (rådata)".

---

## S7. Security and research exclusions (reconfirmed)

- **Tables:** `public.reporting_snapshot`, `public.reporting_runs`, `public.reporting_incidents`. SELECT only. No request for any other table.
- **Unchanged:** RLS policies and grants. No new permissions, no new API, no database function, no write.
- **Never included or retrieved:**
  - the blind direction track's probabilities, outcomes, counts or tables;
  - sealed holdout data;
  - raw prediction or research tables;
  - registered pass/fail thresholds or unpublished checkpoint results;
  - secrets, credentials, session tokens;
  - undocumented experiment conclusions.
- **Logging:** no analytics or error-reporting script that captures responses, headers or tokens.
- **Caching:** data is cached in memory only and cleared on sign-out.

---

## S8. Completeness check against the implementation

Done mechanically on 2026-10-22.

| check | result |
|---|---|
| Live `reporting_snapshot` against S1 (strict: unknown keys counted as errors) | **0 errors** |
| Live `reporting_runs` against S1 | **787 of 787 rows valid**, 0 unknown keys |
| Live `reporting_incidents` against S1 | **17 of 17 rows valid** |
| Every field of every type that appears live | present live (0 fields never observed) |
| Types never seen live, covered by fixtures | `OutcomeUnavailable`, `HealthNoData`, `MoveSizeBreakdownsEmpty`, `PublishedStateUnavailable`, `ShadowErrorSummary`, `WeekComparisonUnavailable` |
| Enum values never seen live, covered by fixtures | marked `NOT OBSERVED LIVE` in S1, e.g. `overdue`, `stale`, `no_data`, `nominal`, `coingecko`, `mid`/`high`/`unknown`, `watchdog_failed`, `publisher` |
| All fixtures (4 main rows, E01–E19, the no-data document, all 199 fixture run rows) against S1 | **0 errors**; every type and every field is exercised by at least one fixture |
| Fixture consistency | `generated_at` = `as_known_at`; `overview.latest_hour` = newest row; rows + missing hours = hours span; the graded row's `as_known_at` reproduces its content |
| Every supported outcome state handled | graded / pending / overdue / unavailable, for the signal and for move-size (S1 unions, S3 checks, fixtures) |
| Page mapping | unchanged from contract v1: FULL = Overview, Performance, Runs, Run details, System Health, About; PARTIAL = Models, Roadmap; NONE = Tests & CI, Experiments ("Data ikke tilgjengelig ennå"); "Simulert resultat" fictional only |
| Compatible with `"1"`; no backend change needed | yes and yes |
| Protected information | none. The fixtures are fictional. The only real texts are the backend's constant sentences and repository paths, which are public in the repository. |
| **NOT VERIFIED** | TypeScript not compiled (no `tsc` here); JavaScript not executed (no runtime); browser behaviour (HTTP codes, network-error shape, aal2 after refresh). These belong in Lovable's tests and in your browser test. |

---

## S9. Versioning

**This is Supplement S1 to dashboard data contract v1**, dated 2026-10-22, for reporting contract version `"1"`.

It replaces nothing in contract v1. It restores the parts that were missing from your copy: the TypeScript (S1), the fixtures (S2) and the query code (S3). It also adds the validation rules (S4).

It is a documentation handoff, not authorisation for any production change.

### Norsk sammendrag

1. **Er datakontrakten komplett nå?** Ja, for versjon `"1"`. Typene ble kontrollert mot live-tabellene uten skrivetilgang: 0 feil i øyeblikksbildet, 787 av 787 kjøringsrader og 17 av 17 hendelsesrader. Ingen felt mangler.
2. **Hvilke tekniske definisjoner er levert?**
   - Hele TypeScript-kontrakten, generert fra samme skjema som ble validert.
   - Fiktive JSON-eksempler laget av den ekte rapporteringskoden: én hendelsesrad, én kjøring med ventende og én med registrerte utfall, et komplett øyeblikksbilde i fil, og 19 kanttilfeller (forsinket, utilgjengelig, utdatert, ingen data, manglende `running_figures`, null-intervaller).
   - En lesemodul for supabase-js v2 som gjenbruker den eksisterende klienten, med aal2-sjekk, nøkkelbasert sidevisning, feilhåndtering, ferskhetsklokker og kontroll av publiseringstidspunkt.
   - Valideringsregler, presentasjonsregler og sikkerhetsunntak.
3. **Hva er fortsatt ikke verifisert?**
   - TypeScript er ikke kompilert, og JavaScript er ikke kjørt (verktøyene mangler her).
   - Oppførselen i nettleseren er ikke testet: HTTP-koder, nettverksfeil og om aal2 beholdes etter fornyet økt.
   - Seks tilstandstyper og noen enum-verdier finnes ikke i live-data ennå. De dekkes bare av de fiktive eksemplene.
4. **Kan Lovable trygt begynne?** Ja, Lovable kan begynne å bygge mot kontrakten med de fiktive eksemplene, med live-modus avslått.
   - Tilkobling til ekte data krever fortsatt din egen godkjenning og nettlesertesten.
   - Ingen endring i backend er nødvendig.
