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
    Mutation("validation", "agent/research/history.py",
             "if requested_end > HOLDOUT.start and not allow_holdout:",
             "if False:",
             "the sealed holdout is no longer truncated -- it would be read silently"),
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
             '    if _normalised(pol.get("qual")) != VIEWER_CONDITION:',
             "    if False:",
             "the security check accepts a stats read policy with any condition (stats website)"),
    Mutation("stats-access", "agent/database/security.py",
             '    if set(pol["roles"]) != {VIEWER_ROLE}:',
             '    if not set(pol["roles"]) & {VIEWER_ROLE}:',
             "the security check accepts a stats read policy that also reaches `anon` (stats website)"),
    Mutation("stats-access", "agent/reporting/schema.sql",
             "USING ((auth.jwt() -> 'app_metadata' ->> 'reporting_viewer') = 'true')$p$, t);",
             "USING (true)$p$, t);",
             "the stats read policy lets every signed-in account read, claim or not (stats website)"),
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
]


# Changes nothing that runs -- a comment. The suite must NOT catch it.
NULL_MUTATION = Mutation("control", "agent/orchestrator.py",
                         '"""The reference candle\'s close: the last instant whose information a prediction may use."""',
                         '"""The reference candle\'s close: the last instant whose information a prediction may use. (control)"""',
                         "comment-only change (must survive)")


def run_suite() -> tuple[bool, str]:
    """True when the suite FAILED (the mutation was caught)."""
    env = {**os.environ, "DATABASE_URL": "postgresql://nobody:nobody@127.0.0.1:1/none", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("BITCOIN_AGENT_DB_TESTS", None)
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-x", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"],
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
    originals = {f: (ROOT / f).read_bytes() for f in files}
    for m in MUTATIONS + [NULL_MUTATION]:  # every mutation must match exactly once, or it is testing nothing
        n = originals[m.file].decode("utf-8").count(m.old)
        if n != 1:
            print(f"mutation does not apply cleanly ({n} matches): {m.file}: {m.what}")
            return 2

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
