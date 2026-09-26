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
             '            if allowed is None or [p for p in granted if p != allowed]:',
             "            if False:",
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
