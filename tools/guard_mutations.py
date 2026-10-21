"""
Test the tests: break each critical guard on purpose and check that the suite notices.

    python tools/guard_mutations.py            # all mutations; exit 1 if any survives
    python tools/guard_mutations.py --list     # show them without running

A passing test suite proves only that the code does what the tests check. This asks the reverse
question for the guards that matter most -- the ones whose silent failure would leak the future
into research, corrupt the live record, or misstate what a number means. Each mutation is a
single, realistic mistake (an off-by-one hour, a filter that lets one more hour of news through,
a rolling window accidentally centred, the row-counting bug scoring 0.1.0 actually had). If the
suite still passes with the mutation in place, that guard is unprotected, whatever the test count
says.

Safety: it refuses to start unless every file it will touch is committed and unmodified, restores
each file in a `finally`, and at the end verifies every file is byte-identical to its original.
The suite runs with an unreachable DATABASE_URL, as in CI, so no mutation can reach a database.
"""

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    area: str
    file: str
    old: str
    new: str
    what: str


MUTATIONS = [
    # ---- point in time: nothing may see past the information cutoff
    Mutation("point-in-time", "agent/orchestrator.py",
             "return reference_bar.as_of + timedelta(hours=1)", "return reference_bar.as_of + timedelta(hours=2)",
             "the information cutoff moved one hour into the future"),
    Mutation("point-in-time", "agent/news/news_service.py",
             "elif item.published_at > cutoff:", "elif item.published_at > cutoff + timedelta(hours=1):",
             "news published up to an hour AFTER the cutoff is let through"),
    Mutation("point-in-time", "agent/research/features.py",
             'prev_close = df["close"].shift(1)', 'prev_close = df["close"].shift(-1)',
             "true range reads the NEXT candle's close instead of the previous one"),
    Mutation("point-in-time", "agent/research/features.py",
             'out[f"rv_{w}"] = log_ret.rolling(w, min_periods=w).std()',
             'out[f"rv_{w}"] = log_ret.rolling(w, min_periods=w, center=True).std()',
             "realised volatility computed on a CENTRED window (half of it in the future)"),
    Mutation("point-in-time", "agent/research/labels.py",
             "known_at.index = known_at.index + timedelta(hours=spec.horizon_hours)",
             "known_at.index = known_at.index + timedelta(hours=0)",
             "volatility-scaled threshold uses returns that had not completed yet"),
    Mutation("point-in-time", "agent/research/simple_baselines.py",
             "real_hour = closes.index.to_series().diff() == pd.Timedelta(hours=1)",
             "real_hour = closes.index.to_series().diff() >= pd.Timedelta(hours=1)",
             "a return spanning a data gap is counted as a one-hour move"),
    # ---- labels and outcomes: the thing being predicted must be the thing measured
    Mutation("labels", "agent/research/labels.py",
             "target_index = closes.index + timedelta(hours=horizon_hours)",
             "target_index = closes.index + timedelta(hours=horizon_hours + 1)",
             "every research label is one hour off its horizon"),
    Mutation("labels", "agent/outcome_tracker.py",
             "return now >= target_candle_open(as_of, horizon_hours) + HOUR",
             "return now >= target_candle_open(as_of, horizon_hours)",
             "live outcomes graded before their target candle has closed"),
    # ---- validation design
    Mutation("validation", "agent/research/walkforward.py",
             "if last_fit_hour + spec.purge >= fold.test_start:",
             "if last_fit_hour >= fold.test_start:",
             "the purge gap between training and test rows is no longer enforced"),
    # Re-pointed 2026-10-20 (weekly audit, F1): 59aa794 moved this condition into load_bars' non-holdout branch.
    Mutation("validation", "agent/research/history.py",
             "        if requested_end > HOLDOUT.start:",
             "        if False:",
             "the sealed holdout is no longer truncated -- the request would go on to the governed reader past the cutoff"),
    # ---- data quality and history
    Mutation("data", "agent/indicators/engine.py",
             "while cut > 0 and bars[cut].as_of - bars[cut - 1].as_of == HOUR:",
             "while cut > 0 and bars[cut].as_of - bars[cut - 1].as_of >= HOUR:",
             "a window with missing hours treated as consecutive (the scoring 0.1.0 gap bug)"),
    Mutation("data", "agent/scoring/scorer.py",
             "reference = next((b for b in reversed(bars) if b.as_of == reference_hour), None)",
             "reference = bars[-1 - RECENT_CHANGE_LOOKBACK] if len(bars) > RECENT_CHANGE_LOOKBACK else None",
             "the volume reference candle found by ROW count again (the 0.1.0 bug)"),
    Mutation("data", "agent/data_providers/market_data.py",
             "if bars[-1].as_of != expected_last_closed(now):",
             "if False:",
             "stale market data accepted as current"),
    # ---- the live record and its protections
    Mutation("live", "agent/database/db.py",
             "return found is not None and int(found) >= int(SCHEMA_VERSION)",
             "return found is not None and int(found) >= 0",
             "a database OLDER than the code (missing invariants or the lockdown) accepted"),
    Mutation("live", "agent/healthcheck.py",
             "ok = age <= timedelta(hours=max_age_hours)",
             "ok = True",
             "the staleness self-check can never fail"),
    Mutation("live", "agent/research/weekly_report.py",
             'return fetched is not None and fetched < r["as_of"] + timedelta(hours=int(r.get("horizon_hours") or 1) + 1)',
             'return fetched is not None',
             "shadow rows written AFTER their outcome counted as prospective evidence"),
    # ---- security and honesty
    Mutation("security", "agent/database/security.py",
             'if not t["rls"]:',
             "if False:",
             "the exposure detector no longer reports RLS switched off"),
    # ---- round 2 (2026-09-23): research-validity guards the first round did not reach
    Mutation("validation", "agent/research/walkforward.py",
             "cal.fit(np.asarray(model.predict_proba(calib[feature_cols]), dtype=float), calib[label_col].to_numpy(dtype=float))",
             "cal.fit(np.asarray(model.predict_proba(test[feature_cols]), dtype=float), test[label_col].to_numpy(dtype=float))",
             "the calibrator is fitted on the TEST rows it will be scored on"),
    Mutation("point-in-time", "agent/research/replay.py",
             "return analyze_window_detailed(_BARS[i - HISTORY_HOURS + 1 : i + 1])",
             "return analyze_window_detailed(_BARS[i - HISTORY_HOURS + 2 : i + 2])",
             "the historical replay sees one candle from the future"),
    Mutation("versioning", "agent/shadow/model.py",
             "FEATURE_CHECK_RTOL = 1e-6", "FEATURE_CHECK_RTOL = 1e6",
             "the frozen model's feature-definition guard can never fire"),
    Mutation("data", "agent/news/news_service.py",
             "        if _is_duplicate(item.headline, seen_normalized):",
             "        if False:",
             "the same story from several feeds is counted several times"),
    Mutation("labels", "agent/outcome_tracker.py",
             "if now >= target_open + HOUR + UNAVAILABLE_GRACE:",
             "if now >= target_open + HOUR:",
             "an outcome is declared permanently unavailable the moment its candle is late"),
    Mutation("security", "agent/database/security.py",
             'if not set(pol["roles"]) & PUBLIC_REACHING:',
             "if True:",
             "the exposure detector ignores every policy, including ones that open a table to anon"),
    Mutation("holdout", "agent/research/holdout_secondary.py",
             '"pass": bool(best == "trades_rel_168h" and vol_cost < H4_MAX_VOL_COST)}',
             '"pass": bool(vol_cost < H4_MAX_VOL_COST)}',
             "E023's H4 pass rule loses its first clause (the registered rule silently weakened)"),
    Mutation("holdout", "agent/research/holdout_secondary.py",
             'df = df[df[cols + ["y", "y_vol"]].notna().all(axis=1)]  # identical rows for every comparison',
             'df = df[df[cols + ["y"]].notna().all(axis=1)]',
             "E023's comparisons no longer forced onto identical rows"),
    Mutation("honesty", "agent/api/state.py",
             '"confidence": Quantity(pred["overall_confidence"], "heuristic", False, CONFIDENCE_MEANING).as_dict()',
             '"confidence": Quantity(pred["overall_confidence"], "heuristic", True, CONFIDENCE_MEANING).as_dict()',
             "the heuristic confidence published as if it were a probability"),
    # ---- 2026-09-23: the AI cost record
    Mutation("cost", "agent/ai/news_scorer.py",
             '    ai_usage.record("news", MODEL, response)',
             "    pass",
             "the news call's token usage is no longer recorded"),
    Mutation("cost", "agent/ai/usage.py",
             'else {"model": model, "usage_unavailable": True}',
             'else {"model": model, "input_tokens": 0, "output_tokens": 0}',
             "missing usage figures recorded as zero cost instead of unavailable"),
    # ---- 2026-09-23 evening: the wider public-API review
    Mutation("security", "agent/database/security.py",
             '        for role in f["callable_by"]:',
             "        for role in []:",
             "the exposure detector ignores functions callable at /rest/v1/rpc"),
    Mutation("security", "agent/database/security.py",
             # single line on purpose: a multi-line pattern cannot match a working copy with CRLF line endings
             '                problems.append(f"view {name}:',
             '                None and problems.append(f"view {name}:',
             "the exposure detector ignores a view granted to the public API (views bypass RLS)"),
    Mutation("security", "agent/database/schema.sql",
             "EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM %I', current_schema(), r);",
             "NULL;",
             "the standing rule that grants every NEW table to the public API is left in place"),
    Mutation("security", "agent/database/role_check.py",
             "        for p in sorted(set(held) - want):",
             "        for p in []:",
             "the least-privilege role check ignores a privilege beyond the proven file"),
    Mutation("provenance", "agent/database/db.py",
             "%s, %s, %s, %s, %s || jsonb_build_object('db_role', current_user::text),",
             "%s, %s, %s, %s, %s,",
             "predictions no longer record which database role wrote them"),
    Mutation("live", ".github/workflows/hourly.yml",
             "        if: failure() && env.HEARTBEAT_URL != ''",
             "        if: env.HEARTBEAT_URL != ''",
             "the heartbeat's FAIL signal is sent after every successful hour too"),
    # The single-missed-hour signal (operational change 1, 2026-10-14).
    Mutation("live", "agent/healthcheck.py",
             "    if not rows or rows[0][1] < inserted_since:", "    if not rows:",
             "the missed-hour signal reports the same gap again from every later run of the hour (duplicate alarms)"),
    Mutation("live", "agent/healthcheck.py",
             "    while t < saved:", "    while t <= saved:",
             "the missed-hour signal reports the hour that was just saved as missing (an alarm every hour)"),
    Mutation("live", ".github/workflows/hourly.yml",
             "if [ -s missed-hours.txt ]; then curl", "if [ -e missed-hours.txt ]; then curl",
             "the missed-hour signal is sent on every run, even when nothing is missing"),
    # The technical backtest's holdout guard (post-500h plan, Phase 5, 2026-10-14): it used to bypass load_bars.
    Mutation("holdout", "agent/backtest/runner.py",
             "    overlap = holdout_overlap(end, hours + HISTORY_HOURS)  # checked BEFORE anything is fetched",
             "    overlap = None",
             "the technical backtest fetches a window reaching into the sealed holdout again (the E000 bypass)"),
    Mutation("holdout", "agent/backtest/runner.py",
             "    lo, hi = max(first, HOLDOUT.start), min(last, HOLDOUT.end - HOUR)",
             "    lo, hi = max(first, HOLDOUT.start), min(last, HOLDOUT.end - 2 * HOUR)",
             "the backtest's holdout check misses the holdout's last hour"),
    Mutation("holdout", "agent/research/weekly_report.py",
             "    return min(wanted, allowed)", "    return wanted",
             "the free EWMA rule's warm-up reaches into the sealed holdout again (Amendment A1 undone)"),
    # GitHub's answers to the dispatch, kept 90 days (operational change 2, 2026-10-14).
    Mutation("security", "agent/database/dispatch_log.sql",
             "ELSE left(dispatch_redact(r.content), 300) END", "ELSE left(r.content, 300) END",
             "the dispatch log keeps GitHub's error text without redacting it"),
    Mutation("security", "agent/database/dispatch_log.sql",
             "    REVOKE ALL ON FUNCTION record_dispatch_responses() FROM PUBLIC;", "    PERFORM 1;",
             "the dispatch recorder stays executable by PUBLIC, so by the public API's anon role"),
    Mutation("live", "agent/database/dispatch_log.sql",
             "now() - interval '90 days'", "now() - interval '9000 days'",
             "the dispatch log is kept for 25 years instead of its documented 90 days"),
    Mutation("validation", "agent/research/live_checkpoint.py",
             "    first = graded[:checkpoint]",
             "    first = graded[-checkpoint:]",
             "a live checkpoint reads the LATEST N hours (a movable window) instead of the first N"),
    Mutation("validation", "agent/research/live_checkpoint.py",
             '"rho_ge_0_10_interval_above_0": s["rho"] >= E012_RHO_BAR and "rho_ci95" in s and s["rho_ci95"][0] > 0}',
             '"rho_ge_0_10_interval_above_0": s["rho"] >= E012_RHO_BAR}',
             "E012's rho part passes without its interval excluding zero"),
    Mutation("leakage", "agent/research/news_power.py",
             "    FROM predictions",
             "    FROM predictions JOIN prediction_outcomes o ON o.prediction_id = predictions.id",
             "the news planning study quietly reads outcomes (spending the future news test)"),
    Mutation("honesty", "agent/research/weekly_report.py",
             "        if n < INTERVALS_NOMINAL_FROM_HOURS:",
             "        if False:",
             "small-sample intervals shown without the E025 'optimistic' label"),
    Mutation("security", "agent/database/try_connection.py",
             # Not the whole-string replacement: that one is belt-and-braces (tried first, it survived,
             # because the password step still removed the secret). This is the line that protects it.
             '        out = out.replace(secret, "***")',
             "        pass",
             "the connection tester can print the password in an error message"),
    Mutation("security", "agent/database/setup_role.py",
             "sql.Identifier(ROLE), sql.Literal(verifier)))",
             "sql.Identifier(ROLE), sql.Literal(password)))",
             "the role setup sends the PLAIN password to the server (it would stay in statement statistics)"),
    Mutation("separation", "agent/orchestrator.py",
             "from agent.ai import usage as ai_usage",
             "from agent.ai import usage as ai_usage; from agent.shadow import model as _shadow_model  # noqa",
             "the live signal's path imports the shadow move-size model"),
    Mutation("separation", "agent/shadow/db.py",
             '"SELECT close_price FROM predictions WHERE as_of = %s"',
             '"UPDATE predictions SET close_price = close_price WHERE as_of = %s"',
             "the shadow step writes to the live record"),
    Mutation("security", "agent/database/role_check.py",
             "    if current == ROLE:",
             "    if True:",
             "the watchdog accepts a job connection that is not the least-privilege role"),
    Mutation("integrity", "agent/research/live_checkpoint.py",
             "        bad += int(d > 1e-9)",
             "        bad += 0",
             "the checkpoint's integrity precondition passes a probability that does not reproduce"),
    Mutation("security", ".github/workflows/hourly.yml",
             "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4, pinned 2026-09-26",
             "uses: actions/checkout@v4",
             "a workflow action goes back to a movable tag (the job's secrets would follow whatever the tag points at)"),
    # The read-only reporting layer (2026-09-27): downstream of production, never upstream of anything.
    Mutation("separation", "agent/orchestrator.py",
             "from agent.version import PIPELINE_VERSION",
             "from agent.version import PIPELINE_VERSION; from agent import reporting as _reporting  # noqa",
             "the live signal's path imports the reporting layer (reporting output could feed a prediction)"),
    Mutation("separation", ".github/workflows/hourly.yml",
             "run: python -m agent.api.publish",
             "run: python -m agent.api.publish && python -m agent.reporting all",
             "the hourly workflow runs the reporting layer (reporting becomes part of production)"),
    Mutation("read-only", "agent/reporting/source.py",
             'BACKEND_STATE_SQL = "SELECT contract_version, generated_at FROM backend_state WHERE id = 1"',
             'BACKEND_STATE_SQL = "UPDATE backend_state SET generated_at = now() WHERE id = 1"',
             "the reporting layer gains a write statement"),
    Mutation("read-only", "agent/reporting/source.py",
             "    conn.read_only = True",
             "    conn.read_only = False",
             "the reporting connection is no longer held read-only by the server"),
    Mutation("read-only", "agent/reporting/source.py",
             "    if conn.read_only is not True:",
             "    if False:",
             "the reporting connection no longer fails closed when read-only mode does not stick"),
    Mutation("leakage", "agent/reporting/views.py",
             '    outcomes = [o for o in records.outcomes if o["prediction_id"] in ids and o["checked_at"] <= at]',
             '    outcomes = [o for o in records.outcomes if o["prediction_id"] in ids]',
             "a reporting view shows an outcome before it was recorded (future leakage into an earlier run)"),
    Mutation("leakage", "agent/reporting/views.py",
             "        if checked is None or checked > at:",
             "        if checked is None:",
             "a reporting view shows a shadow outcome before it was recorded (future leakage)"),
    Mutation("leakage", "agent/reporting/views.py",
             '    preds = [p for p in records.predictions if p["created_at"] <= at]',
             "    preds = list(records.predictions)",
             "a reporting view of a past moment includes runs saved after it"),
    Mutation("honesty", "agent/reporting/views.py",
             "    if n < MIN_HOURS_FOR_INTERVALS:",
             "    if False:",
             "the reporting layer labels a tiny sample as if it were evidence"),
    Mutation("honesty", "agent/reporting/views.py",
             "    if hours < MIN_HOURS_FOR_INTERVALS:",
             "    if False:",
             "a share below 192 hours carries an interval its own sample label says was not computed (stats website)"),
    Mutation("honesty", "agent/reporting/views.py",
             "    if len(y) < MIN_HOURS_FOR_INTERVALS:  # the `sample` beside these figures says `not_computed`",
             "    if False:",
             "the move-size running figures below 192 hours carry an interval their sample label says was not computed (stats website)"),
    Mutation("honesty", "agent/reporting/views.py",
             'CORE_DESCRIPTIVE_KEYS = ("n", ',
             'CORE_DESCRIPTIVE_KEYS = ("e013_ece_ok", "e013_buckets_ok", "n", ',
             "the reporting layer publishes the checkpoint's pass flags on a running sample (a verdict that is not one)"),
    Mutation("security", "agent/reporting/views.py",
             '"error_type": errors[-1]["error_type"]} if errors else None),',
             '"error_type": errors[-1]["error_type"], "message": errors[-1].get("error_message")} if errors else None),',
             "the reporting layer publishes the text of a shadow-job error"),
    # The private stats read surface (2026-09-27): exactly two caches, SELECT, signed-in viewers with an owner-set claim.
    Mutation("stats-access", "agent/database/security.py",
             "            allowed = {VIEWER_PRIVILEGE} if viewer_table and role == VIEWER_ROLE else set()",
             "            allowed = {VIEWER_PRIVILEGE} if viewer_table else set()",
             "the security check lets `anon` read the stats caches (stats website)"),
    Mutation("stats-access", "agent/database/security.py",
             '    if _normalised(pol.get("qual")) not in ACCEPTED_VIEWER_CONDITIONS:',
             "    if False:",
             "the security check accepts a stats read policy with any condition (stats website)"),
    # 2026-10-21 (the dashboard reader): permissive policies combine with OR, and the API login role's memberships
    Mutation("stats-access", "agent/database/security.py",
             "        if viewer_table and len(reaching) > 1:", "        if False:",
             "the security check accepts a second API-reaching policy on a stats table, which ORs access wider (stats website)"),
    Mutation("stats-access", "agent/database/security.py",
             "    extra = sorted(set(switchable) - API_SWITCHABLE_ROLES)", "    extra = []",
             "the security check ignores a role the API login role could switch into (stats website)"),
    Mutation("stats-access", "agent/database/security.py",
             '    if set(pol["roles"]) != {VIEWER_ROLE}:',
             '    if not set(pol["roles"]) & {VIEWER_ROLE}:',
             "the security check accepts a stats read policy that also reaches `anon` (stats website)"),
    # 2026-10-21: the dashboard reader is one named account AND a two-factor (aal2) session -- each half guarded
    Mutation("stats-access", "agent/reporting/schema.sql",
             "USING (auth.uid() = '9e021560-dd06-40f1-80ad-d58d44d9a3f6'::uuid",
             "USING (true",
             "the stats read policy lets every signed-in account with two factors read, not just the dashboard account (stats website)"),
    Mutation("stats-access", "agent/reporting/schema.sql",
             "AND (auth.jwt() ->> 'aal') = 'aal2')$p$, t);",
             ")$p$, t);",
             "the stats read policy lets the dashboard account read with a password alone, without two factors (stats website)"),
    Mutation("stats-access", "agent/reporting/schema.sql",
             "EXECUTE format('GRANT SELECT ON TABLE %I TO authenticated', t);",
             "EXECUTE format('GRANT SELECT ON TABLE %I TO authenticated, anon', t);",
             "the schema file grants the stats caches to `anon` too (stats website)"),
    Mutation("stats-access", "agent/reporting/publish.py",
             "    INSERT INTO reporting_runs (hour, reporting_contract_version, as_known_at, run)",
             "    INSERT INTO predictions (hour, reporting_contract_version, as_known_at, run)",
             "the stats publisher writes to the production record (stats website)"),
    Mutation("stats-access", "agent/reporting/publish.py",
             "    inside = [h for h in hours if HOLDOUT.start <= h < HOLDOUT.end]",
             "    inside = []",
             "the stats publisher no longer refuses sealed-holdout hours (stats website)"),
    Mutation("stats-access", ".github/workflows/reporting.yml",
             "        run: python -m agent.reporting.publish",
             "        run: python run.py && python -m agent.reporting.publish",
             "the stats workflow also runs the prediction job (stats website)"),
    Mutation("stats-access", ".github/workflows/reporting.yml",
             "  workflow_run:",  # one line, so the pattern matches whatever the file's line endings are
             '  schedule:\n    - cron: "0 * * * *"\n  workflow_run:',
             "the stats workflow gets a schedule of its own, a second scheduler (stats website)"),
    Mutation("stats-access", ".github/workflows/reporting.yml",
             "  DATABASE_URL: ${{ secrets.DATABASE_URL }}",
             "  DATABASE_URL: ${{ secrets.DATABASE_URL }}\n  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}",
             "the stats workflow receives the AI key (stats website)"),
    # The stats website's incident history and predicted-vs-actual views (2026-10-05). Single-line patterns only.
    Mutation("stats-incidents", "agent/reporting/incidents.py",
             "    if conclusion not in FAILURE_CONCLUSIONS:",
             "    if False:",
             "the incident recorder accepts a run that did not fail (stats website)"),
    Mutation("stats-incidents", "agent/reporting/incidents.py",
             "    if not RUN_URL.fullmatch(url):",
             "    if False:",
             "the incident recorder stores a link that is not this repository's run page (stats website)"),
    Mutation("stats-incidents", "agent/reporting/views.py",
             '    incidents = [i for i in records.incidents if i["recorded_at"] <= at] if records.incidents is not None else None',
             "    incidents = list(records.incidents) if records.incidents is not None else None",
             "a view of a past moment shows an incident recorded after it (stats website)"),
    Mutation("stats-incidents", "agent/reporting/views.py",
             '    run_failed = any(i["kind"] in ("hourly_run_failed", "watchdog_failed") for i in recent_incidents)',
             "    run_failed = False",
             "a failed hourly run in the last day no longer raises the headline to attention required (stats website)"),
    Mutation("stats-incidents", "agent/reporting/views.py",
             '    check = "no_direction_stated" if stated not in (UP, DOWN) else ("matched" if stated == state["direction"] else "not_matched")',
             '    check = "no_direction_stated" if stated not in (UP, DOWN) else ("not_matched" if stated == state["direction"] else "matched")',
             "the predicted-vs-actual check is reversed (stats website)"),
    Mutation("stats-incidents", "agent/reporting/views.py",
             '    wording = ("higher than the previous week" if diff > 0 else "lower than the previous week" if diff < 0',
             '    wording = ("better than the previous week" if diff > 0 else "worse than the previous week" if diff < 0',
             "a week-on-week change is worded as an improvement (stats website)"),
    Mutation("stats-incidents", ".github/workflows/reporting.yml",
             "        run: python -m agent.reporting.incidents record-workflow-run",
             '        run: python -m agent.reporting.incidents record-workflow-run "${{ github.event.workflow_run.name }}"',
             "event data is pasted into a shell line of the stats workflow (stats website)"),
    Mutation("stats-incidents", ".github/workflows/reporting.yml",
             "      group: reporting-incident-${{ github.event.workflow_run.id }}",
             "      group: reporting-snapshot",
             "a later run can cancel the recording of a failed one (stats website)"),
    Mutation("stats-incidents", ".github/workflows/reporting.yml",
             """    if: ${{ !cancelled() && (github.event_name == 'workflow_dispatch' || contains(fromJSON('["success", "failure", "timed_out", "startup_failure", "action_required"]'), github.event.workflow_run.conclusion)) }}""",
             """    if: ${{ !cancelled() && (github.event_name == 'workflow_dispatch' || contains(fromJSON('["success"]'), github.event.workflow_run.conclusion)) }}""",
             "the stats snapshot is refreshed only after successes again, hiding failures (stats website)"),
    Mutation("stats-incidents", "agent/reporting/schema.sql",
             "CREATE TRIGGER reporting_incidents_append_only BEFORE UPDATE OR DELETE ON reporting_incidents",
             "CREATE TRIGGER reporting_incidents_append_only BEFORE DELETE ON reporting_incidents",
             "a recorded incident can be edited (stats website)"),
    Mutation("stats-incidents", "docs/ops/least_privilege_role.sql",
             "GRANT SELECT, INSERT ON reporting_incidents TO bitcoin_agent;",
             "GRANT SELECT, INSERT, UPDATE ON reporting_incidents TO bitcoin_agent;",
             "the job role may rewrite recorded incidents (stats website)"),
    # ---- the prospective direction shadow track (E034, research/DIRECTION_TRACK.md; 2026-10-15)
    Mutation("direction", "agent/direction_shadow/run.py",
             "    raw = [k for k in payload if k[6] <= now_ms][-count:]",
             "    raw = payload[-count:]",
             "the still-open target candle is mixed into the model's input window (direction track)"),
    Mutation("direction", "agent/direction_shadow/run.py",
             "price_at_prediction = next((price for opened, price in open_candles if opened == cutoff), None)",
             "price_at_prediction = next((price for opened, price in open_candles if True), None)",
             "the economics' entry price may come from a candle other than the target one (direction track)"),
    Mutation("direction", "agent/direction_shadow/run.py",
             "    if fetched_at < cutoff:",
             "    if fetched_at < reference.as_of:",
             "a row fetched before its reference candle closed is accepted (direction track)"),
    Mutation("direction", "agent/direction_shadow/run.py",
             "    if quality.gaps:",
             "    if False:",
             "a window with missing hours still gets probabilities (direction track)"),
    Mutation("direction", "agent/direction_shadow/run.py",
             "    if scoring_version != model.scoring_version:",
             "    if False:",
             "the frozen artefact runs on category scores from another scoring version (direction track)"),
    Mutation("direction", "agent/direction_shadow/run.py",
             "        return 1",
             "        return 0",
             "a failure that could not even be recorded passes silently (direction track)"),
    Mutation("direction", "agent/direction_shadow/model.py",
             "        if problems:",
             "        if False:",
             "old coefficients run on changed input definitions (direction track)"),
    Mutation("direction", "agent/direction_shadow/features.py",
             "    detail = analyze_window_detailed(bars)",
             "    detail = analyze_window_detailed(bars[1:])",
             "the category scores are computed on a different window than the replay's (direction track)"),
    Mutation("direction", "agent/direction_shadow/outcomes.py",
             "    return ret, ret > 0",
             "    return ret, ret >= 0",
             "a tie is graded UP (direction track)"),
    Mutation("direction", "agent/direction_shadow/schema.sql",
             "    IF (to_jsonb(NEW) - outcome) IS DISTINCT FROM (to_jsonb(OLD) - outcome) THEN",
             "    IF false THEN",
             "a stored direction probability or input can be rewritten (direction track)"),
    Mutation("direction", "docs/ops/least_privilege_role.sql",
             "GRANT UPDATE (outcome_status, outcome_close, outcome_return, outcome_up, outcome_checked_at)",
             "GRANT UPDATE (outcome_status, outcome_close, outcome_return, outcome_up, outcome_checked_at, p_model)",
             "the job role may rewrite a stored direction probability (direction track)"),
    Mutation("direction", ".github/workflows/hourly.yml",
             "        run: python -m agent.direction_shadow.run",
             "        run: python -m agent.direction_shadow.run --raise-errors",
             "a direction failure is no longer recorded and fails the hourly job (direction track)"),
    Mutation("direction-reading", "agent/research/direction_checkpoint.py",
             "    first = ok[:n]",
             "    first = ok[-n:]",
             "a reading uses the latest hours instead of the registered fixed prefix (direction track)"),
    Mutation("direction-reading", "agent/research/direction_checkpoint.py",
             "    return r[\"fetched_at\"] < limit and r[\"created_at\"] < limit",
             "    return r[\"fetched_at\"] < limit",
             "a row stored after its outcome was known counts as prospective (direction track)"),
    Mutation("direction-reading", "agent/research/direction_checkpoint.py",
             "    if hi < SESOI:",
             "    if hi < 2 * SESOI:",
             "'no improvement' is declared on a looser rule than registered (direction track)"),
    Mutation("direction-reading", "agent/research/direction_checkpoint.py",
             "            \"live_scores_mismatches\": sum(1 for r in mine if r[\"live_scores_match\"] is False),",
             "            \"live_scores_mismatches\": sum(1 for r in mine if r[\"live_scores_match\"] is False), \"up_share\": 0,",
             "an outcome-based figure leaks into the blind operational view (direction track)"),
    # ---- the quality gate: a failure must stop the commit-and-push workflow (addendum 2026-10-16, item 3)
    Mutation("quality-gate", "tools/gate.py",
             "            break  # the first failure stops the gate",
             "            pass  # the first failure stops the gate",
             "the gate keeps running steps after a failure (quality gate)"),
    Mutation("quality-gate", "tools/gate.py",
             "    if not gate.ok:  # never commit after a failed gate",
             "    if False:  # never commit after a failed gate",
             "ship commits after a failed gate (quality gate)"),
    Mutation("quality-gate", "tools/gate.py",
             "    if not gate.ok:  # never push after a failed gate",
             "    if False:  # never push after a failed gate",
             "push proceeds after a failed gate (quality gate)"),
    Mutation("quality-gate", "tools/gate.py",
             "    if r.returncode != 0:",
             "    if False:",
             "a git push that failed is reported as pushed (quality gate)"),
    Mutation("quality-gate", "tools/gate.py",
             '        return bool(self.results) and all(r.status == "PASSED" and r.code == 0 for r in self.results)',
             '        return all(r.status == "PASSED" and r.code == 0 for r in self.results)',
             "an empty gate counts as passed (quality gate)"),
    # ---- the 2,000-hour integrity pre-check: each of its eight rules fails closed (addendum 2026-10-16, item 4)
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    first = graded[:n]',
             '    first = graded[-n:]',
             "the reading's window is the latest hours, not the registered first N (pre-check rule 1)"),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    reached = len(first) == n  # the size is reached only by exactly N eligible hours',
             '    reached = True  # the size is reached only by exactly N eligible hours',
             'a window short of N counts as reached (pre-check rule 1)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    bytes_ok = digest == REGISTERED_ARTEFACT.get(DEFAULT_VERSION)',
             '    bytes_ok = True',
             'a changed model artefact passes (pre-check rule 2)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    rows_ok = versions == [DEFAULT_VERSION]',
             '    rows_ok = True',
             'rows from another model version pass (pre-check rule 2)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    load_model(DEFAULT_VERSION, verify_features=True)  # raises ModelVersionError if an input definition changed',
             '    pass  # raises ModelVersionError if an input definition changed',
             'changed input definitions pass (pre-check rule 2)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        if not valid:  # a missing, unrecognised or empty review is no review',
             '        if False:  # a missing, unrecognised or empty review is no review',
             "an unreviewed change to the checkpoint's code passes (pre-check rule 3)"),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        valid = r is not None and r.get("verdict") in ALLOWED_VERDICTS and len(str(r.get("evidence", "")).strip()) >= 40',
             '        valid = r is not None',
             'a review with no allowed verdict or no evidence counts (pre-check rule 3)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        return item("FAIL", "changes to the checkpoint path",  # no git history: fail closed',
             '        return item("PASS", "changes to the checkpoint path",  # no git history: fail closed',
             'missing git history passes the change review (pre-check rule 3)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    warmup_ok = start >= HOLDOUT.end',
             '    warmup_ok = True',
             'a warm-up reaching into the holdout passes (pre-check rule 4)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    ok = warmup_ok and not log',
             '    ok = warmup_ok',
             'an existing holdout access log passes (pre-check rule 4)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    none_overdue, none_early = not overdue, not early',
             '    none_overdue, none_early = True, not early',
             'an overdue ungraded hour passes (pre-check rule 5)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    none_overdue, none_early = not overdue, not early',
             '    none_overdue, none_early = not overdue, True',
             'an hour graded before its candle closed passes (pre-check rule 5)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    checks = {"bootstrap": (lc.BLOCK_HOURS, lc.N_BOOT, lc.SEED) == REGISTERED_BOOTSTRAP,',
             '    checks = {"bootstrap": True,',
             'a changed bootstrap setting passes (pre-check rule 6)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '              "sizes": lc.CHECKPOINTS == (500, 2000, 5000),',
             '              "sizes": True,',
             'changed checkpoint sizes pass (pre-check rule 6)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '              "thresholds": now == REGISTERED_THRESHOLDS,',
             '              "thresholds": True,',
             'a changed E012/E013 threshold passes (pre-check rule 6)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '              "bucket_rule": bool(at_limit) and not bool(beyond)}',
             '              "bucket_rule": True}',
             'a loosened E013 bucket rule passes (pre-check rule 6)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    return item("PASS" if r["ok"] else "FAIL", "reproducible from stored predictions",',
             '    return item("PASS", "reproducible from stored predictions",',
             'a probability that does not reproduce passes (pre-check rule 7)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        return item("FAIL", what, f"the check could not be completed: {type(exc).__name__}: {str(exc)[:200]}")',
             '        return item("PASS", what, f"the check could not be completed: {type(exc).__name__}: {str(exc)[:200]}")',
             'a check that crashes counts as passed (pre-check, fail closed)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '            "ready": w["status"] == "PASS" and not failures}',
             '            "ready": w["status"] == "PASS"}',
             'readiness ignores a failed item (pre-check)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        return 1  # a mandatory item failed',
             '        return 0  # a mandatory item failed',
             'a failed pre-check exits 0 (pre-check)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '    return 0 if r["ready"] else 3',
             '    return 0',
             'a pre-check short of N exits 0 as if ready (pre-check)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '           "horizon_hours", "outcome_status", "outcome_checked_at")  # never outcome_large or outcome_return',
             '           "horizon_hours", "outcome_status", "outcome_checked_at", "outcome_large")  # never outcome_large or outcome_return',
             'the pre-check reads an outcome value (pre-check, blind)'),
    Mutation("precheck", "agent/research/checkpoint_precheck.py",
             '        conn.read_only = True  # the server refuses any write on this connection',
             '        conn.read_only = False  # the server refuses any write on this connection',
             "the pre-check's connection is writable (pre-check, read-only)"),
    # ---- the direction track's own alert (addendum 2026-10-16, item 5)
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '            if t not in valid and now >= t + 2 * HOUR:  # the deadline passed: lost for good',
             '            if t not in valid:  # the deadline passed: lost for good',
             'a late but recoverable direction hour counts as lost (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '            if t not in valid and now >= t + 2 * HOUR:  # the deadline passed: lost for good',
             '            if t not in valid and now >= t + 200 * HOUR:  # the deadline passed: lost for good',
             'a lost direction hour is never detected (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '    if new_lost and not open_before:',
             '    if new_lost:',
             'an unresolved direction incident alerts every hour (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '    open_before = bool(events) and events[-1]["kind"] == "hour_lost"',
             '    open_before = False',
             'an open direction incident is forgotten (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '    recorded = {e["hour"] for e in events if e["kind"] == "hour_lost"}',
             '    recorded = set()',
             'an already recorded lost hour alerts again (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '        a.record_recovered = open_before or bool(new_lost)',
             '        a.record_recovered = False',
             'a direction recovery is never recorded (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '    return row["status"] == "unavailable" and any(r in reason for r in VALID_UNAVAILABLE)',
             '    return row["status"] == "unavailable"',
             'a broken direction track counts as a valid observation (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/health.py',
             '    if "fail" in send and inserted == 0:  # a concurrent run recorded these hours first and sent the alert',
             '    if False:  # a concurrent run recorded these hours first and sent the alert',
             'two overlapping runs both alert (direction alert)'),
    Mutation("direction-alert", '.github/workflows/hourly.yml',
             '          if [ -n "$DIRECTION_HEARTBEAT_URL" ] && grep -qx success direction-actions.txt; then curl -fsS -m 10 --retry 3 "$DIRECTION_HEARTBEAT_URL" > /dev/null; fi',
             '          if [ -n "$DIRECTION_HEARTBEAT_URL" ] && grep -qx success direction-actions.txt; then curl -fsS -m 10 --retry 3 "$HEARTBEAT_URL" > /dev/null; fi',
             "the direction track pings the main model's heartbeat (direction alert)"),
    Mutation("direction-alert", '.github/workflows/hourly.yml',
             '        if: ${{ !cancelled() }}',
             '        if: success()',
             'the direction alert is skipped after a failed step (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/schema.sql',
             'CREATE TRIGGER shadow_direction_health_append_only BEFORE UPDATE OR DELETE ON shadow_direction_health',
             'CREATE TRIGGER shadow_direction_health_append_only BEFORE DELETE ON shadow_direction_health',
             'a recorded direction health event can be edited (direction alert)'),
    Mutation("direction-alert", 'agent/direction_shadow/schema.sql',
             '    UNIQUE (kind, hour)',
             '    CHECK (true)',
             'the same direction health event can be recorded twice (direction alert)'),
    Mutation("direction-alert", 'docs/ops/least_privilege_role.sql',
             'GRANT SELECT, INSERT ON shadow_direction_health TO bitcoin_agent;',
             'GRANT SELECT, INSERT, UPDATE ON shadow_direction_health TO bitcoin_agent;',
             'the job role may rewrite the direction health record (direction alert)'),
    # ---- the direction experiment's integrity check (addendum 2026-10-16, item 6)
    Mutation("direction-integrity", 'agent/research/direction_integrity.py',
             '    out.append(("version", not bad and model.sha256 == REGISTERED_SHA256,',
             '    out.append(("version", True,',
             'a row from another model or version passes the integrity check (direction integrity)'),
    Mutation("direction-integrity", 'agent/research/direction_integrity.py',
             '                                     and r["fetched_at"] < r["as_of"] + 2 * HOUR and r["created_at"] < r["as_of"] + 2 * HOUR)]',
             '                                     and r["fetched_at"] < r["as_of"] + 2 * HOUR)]',
             'a row stored after its outcome was known passes the integrity check (direction integrity)'),
    Mutation("direction-integrity", 'agent/research/direction_integrity.py',
             '    out.append(("preserved as predicted", refused == 0 and worst <= 1e-12,',
             '    out.append(("preserved as predicted", refused == 0,',
             'a stored probability that no longer reproduces passes (direction integrity)'),
    Mutation("direction-integrity", 'agent/research/direction_integrity.py',
             '    out.append(("graded correctly", not arith and candle_bad == 0, detail))',
             '    out.append(("graded correctly", candle_bad == 0, detail))',
             'an inconsistent grading passes (direction integrity)'),
    Mutation("direction-integrity", 'agent/research/direction_integrity.py',
             '    unrecorded = [h for h in missing if h + 2 * HOUR <= now and h not in set(state["lost"])]',
             '    unrecorded = []',
             'a silently skipped hour passes (direction integrity)'),
    # ---- the governed snapshot reader (master plan "Safe signal research", Phase 1, 2026-10-17)
    Mutation("data-boundary", "agent/research/snapshots.py",
             "                    break  # the first row not visible at the last development cutoff: nothing after it is read",
             "                    pass  # the first row not visible at the last development cutoff: nothing after it is read",
             "the snapshot reader keeps reading past the last development cutoff (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             "    if whole and not history.holdout_opened():", "    if False:",
             "side data past the cutoff is served without the logged holdout route (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             "    if dev_rows != snap.development_rows or dev_hash.hexdigest() != snap.development_sha256:", "    if False:",
             "a changed snapshot is served as if it were the registered one (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             "            if previous is not None and t <= previous:", "            if False:",
             "a snapshot with rows out of time order is served (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             "    if snap.refused:", "    if False:",
             "the refused macro snapshot is served again (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             "    path = DATA_DIR / snap.file",
             '    path = sorted(DATA_DIR.glob(snap.file.rsplit("_", 1)[0] + "_*.csv"))[-1]',
             "the newest file of a kind silently replaces the registered snapshot (data boundary)"),
    Mutation("data-boundary", "agent/research/snapshots.py",
             '"klines_extra": Snapshot("klines_extra_btcusdt_1h_2026-09-20.csv", "as_of", timedelta(hours=1), 68868,',
             '"klines_extra": Snapshot("klines_extra_btcusdt_1h_2026-09-20.csv", "as_of", timedelta(0), 68868,',
             "the trade-count snapshot's point-in-time rule loses its hour, serving the first holdout candle (data boundary)"),
    Mutation("data-boundary", "agent/research/feature_test.py",
             "    until = information_cutoff(bars)", "    until = HOLDOUT.end",
             "research routes ask for side data through the whole holdout (data boundary)"),
    Mutation("data-boundary", "agent/research/history.py",
             '_HOLDOUT_OPENED_FOR = ""', '_HOLDOUT_OPENED_FOR = "opened at import"',
             "every process starts with the holdout opened for side data (data boundary)"),
    Mutation("data-boundary", "agent/research/history.py",
             "            requested_end = HOLDOUT.start", "            pass",
             "load_bars no longer cuts a request at the holdout's start (data boundary)"),
    Mutation("data-boundary", "agent/research/history.py",
             '    bars = _parse(snapshots.read_snapshot_rows("spot", requested_end).decode("utf-8"))',
             '    bars = _parse(snapshots.read_snapshot_rows("spot", requested_end).decode("utf-8")) or _parse(download_snapshot().read_text())',
             "load_bars falls back to downloading a new snapshot again (data boundary)"),
    # ---- the AI-failure alarm (the user's approval, 2026-10-17, after the Anthropic key rotation)
    Mutation("ai-alarm", "agent/healthcheck.py",
             '    news_failed, explanation_failed = "news_error" in run_meta, "explanation_error" in run_meta',
             '    news_failed, explanation_failed = "news_error" in run_meta, False',
             "a failed explanation no longer raises the AI-failure alarm (ai alarm)"),
    Mutation("ai-alarm", "agent/healthcheck.py",
             '        report = ai_failure(*state) if state else ""',
             '        report = ""',
             "the AI-failure report is never written, whatever failed (ai alarm)"),
    Mutation("ai-alarm", "agent/healthcheck.py",
             '    auth = (run_meta.get("news_error_type") in AI_AUTH_ERROR_TYPES',
             '    auth = (False',
             "an authentication failure of the news step is no longer named as a key problem (ai alarm)"),
    Mutation("ai-alarm", ".github/workflows/hourly.yml",
             "        if: env.HEARTBEAT_URL != '' && env.AI_FAILING != '1'",
             "        if: env.HEARTBEAT_URL != ''",
             "the success ping clears the AI-failure alarm at once (ai alarm)"),
    Mutation("ai-alarm", ".github/workflows/hourly.yml",
             'if [ -s ai-failure.txt ]; then echo "AI_FAILING=1"',
             'if [ -e ai-failure.txt ]; then echo "AI_FAILING=1"',
             "the AI-failure signal fires on every run, even when nothing failed (ai alarm)"),
    # ---- the database backup (2026-10-20, the user's "protect live evidence" plan): agent/database/backup.py
    Mutation("backup", "agent/database/backup.py",
             "    conn.read_only = True", "    conn.read_only = False",
             "the backup snapshot is no longer a read-only transaction (backup)"),
    Mutation("backup", "agent/database/backup.py",
             "    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ",
             "    conn.isolation_level = psycopg.IsolationLevel.READ_COMMITTED",
             "the tables of one backup no longer come from one consistent snapshot (backup)"),
    Mutation("backup", "agent/database/backup.py",
             "    if d == REPO_ROOT or REPO_ROOT in d.parents:", "    if False:",
             "a backup may be written inside the repository, where git could pick it up (backup)"),
    Mutation("backup", "agent/database/backup.py",
             "            if cur.fetchone()[0] and t not in COMPARED_NOT_LOADED:", "            if False:",
             "a restore may load into a database that already holds a record (backup)"),
    Mutation("backup", "agent/database/backup.py",
             "    if not FINGERPRINT.fullmatch(fingerprint):", "    if False:",
             "a name or short key ID may choose the encryption key (backup)"),
    Mutation("backup", "agent/database/backup.py",
             "    for line in sorted(lines):", "    for line in lines:",
             "a table's hash depends on row order, so a correct restore may fail to verify (backup)"),
    Mutation("backup", "agent/database/backup.py",
             '            if (n, h) != (d["rows"], d["rows_sha256"]):', "            if False:",
             "a damaged table passes the manifest check (backup)"),
]


# Changes nothing that runs -- a comment. The suite must NOT catch it.
NULL_MUTATION = Mutation("control", "agent/orchestrator.py",
                         '"""The reference candle\'s close: the last instant whose information a prediction may use."""',
                         '"""The reference candle\'s close: the last instant whose information a prediction may use. (control)"""',
                         "comment-only change (must survive)")


def stale_anchors(mutations: list[Mutation], root: Path | None = None) -> list[tuple[Mutation, int]]:
    """
    Every mutation whose target text does not occur exactly once in its file, with the count: 0 means the code it
    breaks is gone (the guard would test nothing), 2 or more that it is ambiguous. Read as bytes, exactly as the run
    reads them. Checked before any run starts, and on every commit by tests/test_guard_anchors.py: on 2026-10-17 a
    rewrite of load_bars left one guard pointing at nothing, unnoticed until the next full run (weekly audit, F1).
    """
    out = []
    for m in mutations:
        path = (root or ROOT) / m.file
        n = path.read_bytes().decode("utf-8").count(m.old) if path.is_file() else 0
        if n != 1:
            out.append((m, n))
    return out


# The anchor check is left out of mutation runs: every mutation removes its own anchor, so that test would "catch"
# all of them and say nothing about the guards (control 2 would fail if it were included).
ANCHOR_TEST = "tests/test_guard_anchors.py"


def run_suite() -> tuple[bool, str]:
    """True when the suite FAILED (the mutation was caught)."""
    env = {**os.environ, "DATABASE_URL": "postgresql://nobody:nobody@127.0.0.1:1/none", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("BITCOIN_AGENT_DB_TESTS", None)
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", f"--ignore={ANCHOR_TEST}", "-x", "-q", "-p", "no:warnings",
                           "-p", "no:cacheprovider"],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    failed_test = next((l.split(" ")[1] for l in lines if l.startswith("FAILED ")), "")
    return proc.returncode != 0, failed_test or (lines[-1] if lines else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--controls-only", action="store_true", help="run only the two controls")
    parser.add_argument("--only", default="", help="run only mutations whose description contains this text")
    args = parser.parse_args()
    global MUTATIONS
    if args.only:
        MUTATIONS = [m for m in MUTATIONS if args.only.lower() in m.what.lower()]
        if not MUTATIONS:
            print(f"no mutation matches {args.only!r}")
            return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.list:
        for m in MUTATIONS:
            print(f"[{m.area:13s}] {m.file:36s} {m.what}")
        return 0

    files = sorted({m.file for m in MUTATIONS} | {NULL_MUTATION.file})
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *files], cwd=ROOT, capture_output=True, text=True).stdout
    if dirty.strip():
        print("refusing to run: these files have uncommitted changes and could not be restored safely:\n" + dirty)
        return 2
    stale = stale_anchors(MUTATIONS + [NULL_MUTATION])  # every mutation must match exactly once, or it is testing nothing
    if stale:
        for m, n in stale:  # all of them, not just the first
            print(f"mutation does not apply cleanly ({n} matches): {m.file}: {m.what}")
        return 2
    originals = {f: (ROOT / f).read_bytes() for f in files}

    # Controls, so that "caught" means something. (1) Without any mutation the suite must PASS --
    # otherwise every mutation would look caught. (2) A mutation that changes only a comment must
    # SURVIVE -- otherwise the runner cannot report survival at all. Same idea as E010's memoriser
    # control: prove the instrument can give the other answer before trusting the one it gave.
    caught, detail = run_suite()
    if caught:
        print(f"CONTROL FAILED: the suite fails with NO mutation ({detail}); every result would be meaningless.")
        return 2
    print("control 1 passed: the unmutated suite passes")
    null_file = ROOT / NULL_MUTATION.file
    try:
        null_file.write_bytes(originals[NULL_MUTATION.file].decode("utf-8").replace(NULL_MUTATION.old, NULL_MUTATION.new, 1).encode("utf-8"))
        caught, detail = run_suite()
    finally:
        null_file.write_bytes(originals[NULL_MUTATION.file])
    if caught:
        print(f"CONTROL FAILED: a comment-only change was reported as caught ({detail}).")
        return 2
    print("control 2 passed: a comment-only change survives, so a real survival would be reported")
    if args.controls_only:
        return 0

    results = []
    try:
        for i, m in enumerate(MUTATIONS, 1):
            path = ROOT / m.file
            text = originals[m.file].decode("utf-8")
            try:
                path.write_bytes(text.replace(m.old, m.new, 1).encode("utf-8"))
                t0 = time.time()
                caught, detail = run_suite()
            finally:
                path.write_bytes(originals[m.file])
            results.append((m, caught, detail))
            print(f"{i:2d}/{len(MUTATIONS)} {'caught  ' if caught else 'SURVIVED'} [{m.area}] {m.what}"
                  f"  ({time.time() - t0:.0f}s){'  <- ' + detail if caught else ''}", flush=True)
    finally:
        for f, content in originals.items():
            (ROOT / f).write_bytes(content)
    assert all((ROOT / f).read_bytes() == c for f, c in originals.items()), "a file was not restored"

    survived = [m for m, caught, _ in results if not caught]
    print(f"\n{len(results) - len(survived)} of {len(results)} mutations caught; every file restored byte for byte.")
    for m in survived:
        print(f"  UNPROTECTED: [{m.area}] {m.file}: {m.what}")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
