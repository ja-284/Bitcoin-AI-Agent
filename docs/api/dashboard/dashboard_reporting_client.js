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
