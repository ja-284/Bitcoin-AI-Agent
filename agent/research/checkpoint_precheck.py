"""
The integrity pre-check for a registered move-size checkpoint (master plan Phase 5, "Before the 2,000-hour
checkpoint"): every mandatory requirement verified BEFORE the reading is computed, without computing or previewing it.

    python -m agent.research.checkpoint_precheck [--hours 2000]

It reads no outcome VALUE: only whether an hour is graded (outcome_status), never outcome_large or outcome_return, and
it computes no statistic of the model against outcomes. It can therefore run at any time, as a dry run now and for
real at the first session after N graded hours. It prints PASS / FAIL / REVIEW per requirement and exits 1 on any
FAIL. If a mandatory item fails, the checkpoint is not run as though it were valid (the master plan's rule); what
must be repaired is named.

The eight requirements, in the master plan's order:
  1. the correct data window and number of eligible prospective hours
  2. no change to the frozen model
  3. no change that violates the registered grading rules
  4. no holdout access through warm-up or another path
  5. every available outcome graded by the original rules
  6. the registered baselines, metrics and uncertainty settings
  7. the result reproducible from stored predictions and data
  8. deviations, missing data and uncertainty documented
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOUR = timedelta(hours=1)
REGISTERED_ARTEFACT = {"move_size_1h_v1": "7d53cd073fc2007ede16a3096ffa7f0db9b4d926ea933b662cd97a98717f40ab"}
REGISTERED_BOOTSTRAP = (48, 500, 17)        # research/LIVE_EVALUATION.md rule 3 and clarification 9
READING_500H_COMMIT = "ed96b2a"             # the 500-hour reading, committed unchanged
# Files whose change could alter what a checkpoint selects, grades, computes or compares against. Any commit touching
# them after the last reading is listed for review; each must be a documented, registered amendment or unrelated.
CHECKPOINT_PATH = ("agent/research/live_checkpoint.py", "research/LIVE_EVALUATION.md", "agent/shadow/", "agent/outcome_tracker.py",
                   "agent/research/weekly_report.py", "agent/research/simple_baselines.py", "agent/research/checkpoint_power.py",
                   "agent/research/metrics.py")
COLUMNS = ("as_of", "fetched_at", "created_at", "status", "status_reason", "model_version", "features", "p_calibrated",
           "horizon_hours", "outcome_status", "outcome_checked_at")  # never outcome_large or outcome_return


def fetch_rows() -> list[dict]:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(COLUMNS) + " FROM shadow_move_size ORDER BY as_of")
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
    return item("PASS" if len(first) == n else "NOT YET", "window", detail), first


def frozen_model(rows: list[dict]) -> dict:
    """2: the artefact is the registered one, and every row says so."""
    from agent.shadow.model import DEFAULT_VERSION, MODEL_DIR

    text = (MODEL_DIR / f"{DEFAULT_VERSION}.json").read_text(encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    versions = sorted({r["model_version"] for r in rows})
    ok = digest == REGISTERED_ARTEFACT.get(DEFAULT_VERSION) and versions == [DEFAULT_VERSION]
    return item("PASS" if ok else "FAIL", "frozen model",
                f"artefact {DEFAULT_VERSION} canonical sha256 {digest[:12]}… (registered {REGISTERED_ARTEFACT[DEFAULT_VERSION][:12]}…); "
                f"row model versions {versions}")


def changes_since_last_reading(since_commit: str = READING_500H_COMMIT) -> dict:
    """3 and 6: every commit after the last reading that touches the checkpoint's path, listed for review."""
    try:
        out = subprocess.run(["git", "log", "--oneline", f"{since_commit}..HEAD", "--", *CHECKPOINT_PATH],
                             capture_output=True, text=True, check=True).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return item("FAIL", "changes to the checkpoint path", f"git log failed: {exc}")
    commits = [l for l in out.splitlines() if l]
    return item("REVIEW" if commits else "PASS", "changes to the checkpoint path since the last reading",
                f"{len(commits)} commit(s) since {since_commit}: " + ("; ".join(commits) if commits else "none") +
                ". Each must be a documented, registered amendment (e.g. A1) or provably outside the checkpoint's computation.")


def registered_settings() -> dict:
    """6: the bootstrap and the registered table are the ones written in research/LIVE_EVALUATION.md."""
    from agent.research import live_checkpoint as lc

    ok = (lc.BLOCK_HOURS, lc.N_BOOT, lc.SEED) == REGISTERED_BOOTSTRAP and lc.CHECKPOINTS == (500, 2000, 5000) \
        and lc.REGISTERED[2000]["verdict"] == "E012" and lc.REGISTERED[5000]["verdict"] == "E013"
    return item("PASS" if ok else "FAIL", "registered settings",
                f"bootstrap {lc.BLOCK_HOURS}h blocks, {lc.N_BOOT} resamples, seed {lc.SEED}; checkpoints {lc.CHECKPOINTS}; "
                f"verdicts 2,000 -> {lc.REGISTERED[2000]['verdict']}, 5,000 -> {lc.REGISTERED[5000]['verdict']}; the free EWMA "
                "rule via weekly_report.ewma_reference_series (E019's rule)")


def holdout(first: list[dict], now: datetime) -> dict:
    """4: no access log, and the free rule's warm-up the reading would request starts no earlier than the buffer."""
    from agent.research.periods import HOLDOUT
    from agent.research.weekly_report import ewma_fetch_hours

    log = Path("research/HOLDOUT_ACCESS.log").exists()
    if not first:
        return item("FAIL" if log else "PASS", "holdout", f"access log {'EXISTS' if log else 'absent'}; no window to check")
    lookback = int((now - first[0]["as_of"]).total_seconds() // 3600) + 800  # exactly live_checkpoint.main's request
    hours = ewma_fetch_hours(now, lookback)
    start = now.replace(minute=0, second=0, microsecond=0) - (hours - 1) * HOUR
    ok = not log and start >= HOLDOUT.end
    return item("PASS" if ok else "FAIL", "holdout",
                f"access log {'EXISTS' if log else 'absent'}; the reading's EWMA warm-up would start {start:%Y-%m-%d %H:%M} UTC "
                f"(the buffer starts {HOLDOUT.end:%Y-%m-%d %H:%M}; Amendment A1)")


def all_graded(rows: list[dict], now: datetime) -> dict:
    """5: no row is waiting past the grading grace period (graded or not only; no value is read)."""
    from agent.outcome_tracker import UNAVAILABLE_GRACE

    overdue = [r for r in rows if r["status"] == "ok" and r["outcome_status"] is None
               and now >= r["as_of"] + (int(r["horizon_hours"] or 1) + 1) * HOUR + UNAVAILABLE_GRACE]
    early = [r for r in rows if r["outcome_checked_at"] is not None and r["outcome_checked_at"] < r["as_of"] + (int(r["horizon_hours"] or 1) + 1) * HOUR]
    ok = not overdue and not early
    return item("PASS" if ok else "FAIL", "every available outcome graded by the original rules",
                f"{len(overdue)} overdue (ungraded past the {UNAVAILABLE_GRACE} grace); {len(early)} graded before their target candle closed")


def reproducible(first: list[dict]) -> dict:
    """7: every judged probability is the frozen artefact's for its stored inputs (no outcome is involved)."""
    from agent.research.live_checkpoint import reproducibility

    if not first:
        return item("FAIL", "reproducibility", "no rows")
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
    items = [w, frozen_model(rows), changes_since_last_reading(), holdout(first, now), all_graded(rows, now),
             registered_settings(), reproducible(first), deviations(first, errors)]
    return {"checkpoint_hours": n, "checked_at": now.isoformat(), "items": items,
            "mandatory_failures": [i["what"] for i in items if i["status"] == "FAIL"],
            "ready": w["status"] == "PASS" and not any(i["status"] == "FAIL" for i in items)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=2000)
    args = parser.parse_args()
    r = run(args.hours)
    for i, it in enumerate(r["items"], 1):
        print(f"{i}. [{it['status']}] {it['what']}: {it['detail']}")
    if r["mandatory_failures"]:
        print(f"\nNOT READY: repair first -> {', '.join(r['mandatory_failures'])}. Do not run the checkpoint as though it were valid.")
        return 1
    print("\nREADY to run the checkpoint" if r["ready"] else "\nNo mandatory failure; the checkpoint size is not reached yet (a dry run).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
