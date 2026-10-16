"""
The integrity pre-check for a registered move-size checkpoint (master plan Phase 5, "Before the 2,000-hour
checkpoint"): every mandatory requirement verified BEFORE the reading is computed, without computing or previewing it.

    python -m agent.research.checkpoint_precheck [--hours 2000]

Exit codes: 0 = READY (every mandatory item passed and the size is reached); 3 = not reached yet, nothing failed;
1 = a mandatory item FAILED (repair first; never run the checkpoint as though it were valid).

It reads no outcome VALUE: only whether an hour is graded (outcome_status, outcome_checked_at), never outcome_large or
outcome_return, and it computes no statistic of the model against outcomes. It reads only the live shadow table, never
a holdout candle. It writes nothing: one SELECT on a connection the server holds read-only. It can therefore run at any
time, as a dry run now and for real at the first session after N graded hours.

It fails closed (addendum 2026-10-16, item 4): a check that cannot be completed, or that raises, is a FAIL, and a
change to the checkpoint's code without a written review is a FAIL.

The eight requirements, in the master plan's order:
  1. the correct data window and number of eligible prospective hours
  2. no change to the frozen model (its bytes and its input definitions)
  3. no change that violates the registered grading rules: every commit on the checkpoint's path since the last
     reading must be reviewed in research/CHECKPOINT_PATH_REVIEWS.json
  4. no holdout access through warm-up or another path
  5. every available outcome graded by the original rules
  6. the registered baselines, metrics, thresholds and uncertainty settings
  7. the result reproducible from stored predictions and data
  8. deviations, missing data and uncertainty documented: the facts are listed (REVIEW); the reading's report must
     state them, which no pre-check can verify in advance
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOUR = timedelta(hours=1)
REGISTERED_ARTEFACT = {"move_size_1h_v1": "7d53cd073fc2007ede16a3096ffa7f0db9b4d926ea933b662cd97a98717f40ab"}
REGISTERED_BOOTSTRAP = (48, 500, 17)        # research/LIVE_EVALUATION.md rule 3 and clarification 9
# rule 4 of research/LIVE_EVALUATION.md, copied from E012 and E013: skill bar, accuracy margin, rho bar, ECE bar
REGISTERED_THRESHOLDS = {"E012_SKILL_BAR": 0.05, "E012_ACCURACY_MARGIN": 0.05, "E012_RHO_BAR": 0.10, "E013_ECE_BAR": 0.03}
READING_500H_COMMIT = "ed96b2a"             # the 500-hour reading, committed unchanged
HOLDOUT_LOG = Path("research/HOLDOUT_ACCESS.log")
REVIEWS_PATH = Path("research/CHECKPOINT_PATH_REVIEWS.json")
ALLOWED_VERDICTS = ("registered amendment", "outside the checkpoint's computation")
# Files whose change could alter what a checkpoint selects, grades, computes or compares against.
CHECKPOINT_PATH = ("agent/research/live_checkpoint.py", "research/LIVE_EVALUATION.md", "agent/shadow/", "agent/outcome_tracker.py",
                   "agent/research/weekly_report.py", "agent/research/simple_baselines.py", "agent/research/checkpoint_power.py",
                   "agent/research/metrics.py")
COLUMNS = ("as_of", "fetched_at", "created_at", "status", "status_reason", "model_version", "features", "p_calibrated",
           "horizon_hours", "outcome_status", "outcome_checked_at")  # never outcome_large or outcome_return
LIVE_CHECKPOINT_NAMES_USED = {"prospective", "prospective_graded", "reproducibility", "regime_of", "TERCILES_PATH", "BLOCK_HOURS",
                              "N_BOOT", "SEED", "CHECKPOINTS", "REGISTERED", "E012_ACCURACY_MARGIN", "E012_RHO_BAR"}
SQL_ROWS = "SELECT " + ", ".join(COLUMNS) + " FROM shadow_move_size ORDER BY as_of"


def fetch_rows() -> list[dict]:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True  # the server refuses any write on this connection
        with conn.cursor() as cur:
            cur.execute(SQL_ROWS)
            return [dict(zip(COLUMNS, r)) for r in cur.fetchall()]


def fetch_errors(since: datetime, until: datetime) -> int:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM shadow_run_errors WHERE occurred_at >= %s AND occurred_at < %s", (since, until))
            return int(cur.fetchone()[0])


def item(status: str, what: str, detail: str) -> dict:
    return {"status": status, "what": what, "detail": detail}


def safely(what: str, fn, *args) -> dict:
    """Fail closed: a check that raises is a FAIL with its reason, never a crash and never a pass."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        return item("FAIL", what, f"the check could not be completed: {type(exc).__name__}: {str(exc)[:200]}")


def window(rows: list[dict], n: int) -> tuple[dict, list[dict]]:
    """1: the fixed prefix (counts only) and the span's composition."""
    from agent.research.live_checkpoint import prospective, prospective_graded

    graded = prospective_graded(rows)
    first = graded[:n]
    if not first:
        return item("FAIL", "window", "no prospective graded hour exists"), first
    lo, hi = first[0]["as_of"], first[-1]["as_of"]
    span = [r for r in rows if lo <= r["as_of"] <= hi]
    hours_in_span = int((hi - lo) / HOUR) + 1
    detail = (f"{len(graded)} prospective graded hours available; the reading uses the first {len(first)}: {lo:%Y-%m-%d %H:%M} -> "
              f"{hi:%Y-%m-%d %H:%M} UTC. Inside that span: {hours_in_span} hours, {len(span)} rows "
              f"({hours_in_span - len(span)} hours with no row; {sum(1 for r in span if r['status'] != 'ok')} unavailable; "
              f"{sum(1 for r in span if r['status'] == 'ok' and not prospective(r))} not prospective; "
              f"{sum(1 for r in span if r['outcome_status'] == 'unavailable')} outcome unavailable)")
    reached = len(first) == n  # the size is reached only by exactly N eligible hours
    return item("PASS" if reached else "NOT YET", "window", detail), first


def frozen_model(rows: list[dict]) -> dict:
    """2: the artefact's bytes are the registered ones, its input definitions still match, and every row names it."""
    from agent.shadow.model import DEFAULT_VERSION, MODEL_DIR, load_model

    text = (MODEL_DIR / f"{DEFAULT_VERSION}.json").read_text(encoding="utf-8")
    digest = hashlib.sha256(json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    versions = sorted({r["model_version"] for r in rows})
    bytes_ok = digest == REGISTERED_ARTEFACT.get(DEFAULT_VERSION)
    rows_ok = versions == [DEFAULT_VERSION]
    load_model(DEFAULT_VERSION, verify_features=True)  # raises ModelVersionError if an input definition changed
    ok = bytes_ok and rows_ok
    return item("PASS" if ok else "FAIL", "frozen model",
                f"artefact {DEFAULT_VERSION} canonical sha256 {digest[:12]}… (registered {REGISTERED_ARTEFACT[DEFAULT_VERSION][:12]}…); "
                f"input definitions match; row model versions {versions}")


def commits_on_path(since_commit: str = READING_500H_COMMIT) -> list[str]:
    """Full hashes of every commit after `since_commit` that touches the checkpoint's path. Raises if git cannot say."""
    out = subprocess.run(["git", "log", "--format=%H", f"{since_commit}..HEAD", "--", *CHECKPOINT_PATH],
                         capture_output=True, text=True, check=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def changes_since_last_reading(since_commit: str = READING_500H_COMMIT, reviews_path: Path | None = None) -> dict:
    """3: every commit on the checkpoint's path since the last reading must carry a written review, or it FAILS."""
    try:
        commits = commits_on_path(since_commit)
    except Exception as exc:  # noqa: BLE001 -- e.g. a shallow clone (CI checks out one commit) cannot see the history
        detail = getattr(exc, "stderr", "") or str(exc)
        return item("FAIL", "changes to the checkpoint path",  # no git history: fail closed
                    f"git history since {since_commit} is not available here ({str(detail).strip()[:160]}); run the pre-check from a "
                    "full clone, where every change since the last reading can be listed")
    reviews = json.loads((reviews_path or REVIEWS_PATH).read_text(encoding="utf-8"))["reviews"]
    unreviewed = []
    for c in commits:
        r = reviews.get(c)
        valid = r is not None and r.get("verdict") in ALLOWED_VERDICTS and len(str(r.get("evidence", "")).strip()) >= 40
        if not valid:  # a missing, unrecognised or empty review is no review
            unreviewed.append(c[:7])
    if unreviewed:
        return item("FAIL", "changes to the checkpoint path",
                    f"{len(unreviewed)} of {len(commits)} commit(s) since {since_commit} on the checkpoint's path have no valid review in "
                    f"{(reviews_path or REVIEWS_PATH).as_posix()}: {', '.join(unreviewed)}. Review each diff and record the evidence first.")
    listed = "; ".join(f"{c[:7]} ({reviews[c]['verdict']})" for c in commits) or "none"
    return item("PASS", "changes to the checkpoint path", f"{len(commits)} commit(s) since {since_commit}, each reviewed: {listed}")


def registered_settings() -> dict:
    """6: the bootstrap, sizes, verdicts and pass thresholds are the ones written in research/LIVE_EVALUATION.md."""
    import numpy as np

    from agent.research import checkpoint_power as cpw
    from agent.research import live_checkpoint as lc

    now = {"E012_SKILL_BAR": cpw.E012_SKILL_BAR, "E012_ACCURACY_MARGIN": lc.E012_ACCURACY_MARGIN,
           "E012_RHO_BAR": lc.E012_RHO_BAR, "E013_ECE_BAR": cpw.E013_ECE_BAR}
    # E013's bucket rule is code, not a constant: a bucket of 100 rows off by exactly 0.05 passes, off by 0.06 fails
    p = np.full(100, 0.45)
    at_limit = cpw.e013_passes(p, (np.arange(100) < 50).astype(float))[1]
    beyond = cpw.e013_passes(p, (np.arange(100) < 51).astype(float))[1]
    checks = {"bootstrap": (lc.BLOCK_HOURS, lc.N_BOOT, lc.SEED) == REGISTERED_BOOTSTRAP,
              "sizes": lc.CHECKPOINTS == (500, 2000, 5000),
              "verdicts": lc.REGISTERED[2000]["verdict"] == "E012" and lc.REGISTERED[5000]["verdict"] == "E013",
              "thresholds": now == REGISTERED_THRESHOLDS,
              "bucket_rule": bool(at_limit) and not bool(beyond)}
    bad = [k for k, v in checks.items() if not v]
    return item("FAIL" if bad else "PASS", "registered settings",
                f"bootstrap {lc.BLOCK_HOURS}h blocks, {lc.N_BOOT} resamples, seed {lc.SEED}; sizes {lc.CHECKPOINTS}; verdicts "
                f"2,000 -> {lc.REGISTERED[2000]['verdict']}, 5,000 -> {lc.REGISTERED[5000]['verdict']}; thresholds {now}; "
                f"E013 bucket rule at 0.05 {'kept' if checks['bucket_rule'] else 'CHANGED'}" + (f"; NOT as registered: {bad}" if bad else ""))


def holdout(first: list[dict], now: datetime) -> dict:
    """4: no access log, and the free rule's warm-up the reading would request starts no earlier than the buffer."""
    from agent.research.periods import HOLDOUT
    from agent.research.weekly_report import ewma_fetch_hours

    log = HOLDOUT_LOG.exists()
    if not first:
        return item("FAIL" if log else "PASS", "holdout", f"access log {'EXISTS' if log else 'absent'}; no window to check")
    lookback = int((now - first[0]["as_of"]).total_seconds() // 3600) + 800  # exactly live_checkpoint.main's request
    hours = ewma_fetch_hours(now, lookback)
    start = now.replace(minute=0, second=0, microsecond=0) - (hours - 1) * HOUR
    warmup_ok = start >= HOLDOUT.end
    ok = warmup_ok and not log
    return item("PASS" if ok else "FAIL", "holdout",
                f"access log {'EXISTS' if log else 'absent'}; the reading's EWMA warm-up would start {start:%Y-%m-%d %H:%M} UTC "
                f"(the buffer starts {HOLDOUT.end:%Y-%m-%d %H:%M}; Amendment A1)")


def all_graded(rows: list[dict], now: datetime) -> dict:
    """5: no row is waiting past the grading grace period, and none was graded early (graded or not only; no value)."""
    from agent.outcome_tracker import UNAVAILABLE_GRACE

    def target_close(r):
        return r["as_of"] + (int(r["horizon_hours"] or 1) + 1) * HOUR

    overdue = [r for r in rows if r["status"] == "ok" and r["outcome_status"] is None and now >= target_close(r) + UNAVAILABLE_GRACE]
    early = [r for r in rows if r["outcome_checked_at"] is not None and r["outcome_checked_at"] < target_close(r)]
    none_overdue, none_early = not overdue, not early
    return item("PASS" if (none_overdue and none_early) else "FAIL", "every available outcome graded by the original rules",
                f"{len(overdue)} overdue (ungraded past the {UNAVAILABLE_GRACE} grace); {len(early)} graded before their target candle closed")


def reproducible(first: list[dict]) -> dict:
    """7: every judged probability is the frozen artefact's for its stored inputs (no outcome is involved)."""
    from agent.research.live_checkpoint import reproducibility

    if not first:
        return item("FAIL", "reproducible from stored predictions", "no rows")
    r = reproducibility(first)
    return item("PASS" if r["ok"] else "FAIL", "reproducible from stored predictions",
                f"{r['rows']} rows, max difference {r['max_abs_diff']:.1e}, not reproducible {r['not_reproducible']}")


def deviations(first: list[dict], errors: int) -> dict:
    """8: what the reading's text must state. Always REVIEW: a person writes it, this lists the facts. The regime mix
    comes from each hour's stored INPUT rv_168 and the frozen development terciles; no outcome is involved."""
    from agent.research.live_checkpoint import TERCILES_PATH, regime_of

    cuts = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"])
    mix: dict[str, int] = {}
    for r in first:
        g = regime_of(r, cuts)
        mix[g] = mix.get(g, 0) + 1
    return item("REVIEW", "deviations to document",
                f"shadow-step errors recorded during the window: {errors}; volatility regime mix of the window (frozen "
                f"terciles of the stored input rv_168): {mix}; the hours with no row and the excluded rows are in item 1. State also: "
                "the reading is not blind (weekly reports showed the running record), and intervals are optimistic below 2,000 hours (E025)")


def run(n: int, rows: list[dict] | None = None, now: datetime | None = None, errors: int | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = fetch_rows() if rows is None else rows
    w, first = window(rows, n)
    if errors is None:
        errors = fetch_errors(first[0]["as_of"], first[-1]["as_of"] + 2 * HOUR) if first else 0
    items = [w, safely("frozen model", frozen_model, rows), safely("changes to the checkpoint path", changes_since_last_reading),
             safely("holdout", holdout, first, now), safely("every available outcome graded by the original rules", all_graded, rows, now),
             safely("registered settings", registered_settings), safely("reproducible from stored predictions", reproducible, first),
             safely("deviations to document", deviations, first, errors)]
    failures = [i["what"] for i in items if i["status"] == "FAIL"]
    return {"checkpoint_hours": n, "checked_at": now.isoformat(), "items": items, "mandatory_failures": failures,
            "ready": w["status"] == "PASS" and not failures}


def exit_code(r: dict) -> int:
    if r["mandatory_failures"]:
        return 1  # a mandatory item failed
    return 0 if r["ready"] else 3


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=2000)
    args = parser.parse_args(argv)
    r = run(args.hours)
    for i, it in enumerate(r["items"], 1):
        print(f"{i}. [{it['status']}] {it['what']}: {it['detail']}")
    code = exit_code(r)
    if code == 1:
        print(f"\nNOT READY (exit 1): repair first -> {', '.join(r['mandatory_failures'])}. Do not run the checkpoint as though it were valid.")
    elif code == 3:
        print("\nNo mandatory failure, but the checkpoint size is not reached yet (exit 3: a dry run).")
    else:
        print("\nREADY to run the checkpoint (exit 0).")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
