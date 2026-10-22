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
