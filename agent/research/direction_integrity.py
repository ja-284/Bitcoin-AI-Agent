"""
Integrity of the live direction experiment (E034), verified without looking at how it is doing (master plan addendum
2026-10-16, item 6). Read-only; prints COUNTS and match results only, never a probability, an outcome, a return or any
score, so the registered readings stay blind (research/DIRECTION_TRACK.md, Amendment 1.1).

    python -m agent.research.direction_integrity [--no-candles]

Exit 1 if any integrity check fails. What it checks:
  1. version: every row names direction_1h_v1, the pinned artefact sha256, scoring 0.2.0 and this pipeline version
  2. development-only fit: the artefact's last fitting row is at least 25 h before the holdout begins
  3. timestamps: cutoff = as_of + 1h; fetched at or after the cutoff; stored after the fetch; stored before the
     outcome candle closed (prospective); graded only after the target candle closed
  4. storage and immutability: the live table's immutability and delete triggers exist and are enabled
  5. preserved as at prediction time: every stored probability equals the frozen artefact's on its stored inputs
  6. nothing skipped silently: every hour since the first row has a row (or is recorded as lost in the health record),
     unavailable rows carry a reason, and every recorded failure is listed
  7. graded correctly: the stored return equals (outcome close - reference close) / reference close, UP equals
     return > 0, and (with candles) the reference and outcome closes equal the exchange's candles for those hours
  8. inputs: (with candles) every stored input equals the research code's recomputation from the exchange's candles
"""

import argparse
import math
import sys
from datetime import timedelta
from pathlib import Path

HOUR = timedelta(hours=1)
REGISTERED_SHA256 = "f04d6e322c24dde98e2209b78492e6a2feff6d9fba41dab19dd971f6e6d224d9"
INPUT_RTOL = 1e-6  # the cross-machine tolerance of the definition guard
COLUMNS = ("as_of", "cutoff_at", "fetched_at", "created_at", "model_version", "artefact_sha256", "pipeline_version", "scoring_version",
           "code_commit", "reference_close", "status", "status_reason", "features", "p_model", "p_one_feature", "p_base",
           "horizon_hours", "outcome_status", "outcome_close", "outcome_return", "outcome_up", "outcome_checked_at")


def read() -> dict:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True  # nothing here can write
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(COLUMNS) + " FROM shadow_direction ORDER BY as_of")
            rows = [dict(zip(COLUMNS, r)) for r in cur.fetchall()]
            cur.execute("SELECT occurred_at, step, error_type FROM shadow_direction_errors ORDER BY occurred_at")
            errors = cur.fetchall()
            cur.execute("SELECT to_regclass('shadow_direction_health')")
            lost = []
            if cur.fetchone()[0] is not None:
                cur.execute("SELECT hour FROM shadow_direction_health WHERE kind = 'hour_lost'")
                lost = [r[0] for r in cur.fetchall()]
            cur.execute("""SELECT t.tgname, t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                           WHERE c.relname = 'shadow_direction' AND NOT t.tgisinternal""")
            triggers = dict(cur.fetchall())
    return {"rows": rows, "errors": errors, "lost": lost, "triggers": triggers}


def check(state: dict, model, candles: dict | None = None, now=None) -> list[tuple[str, bool, str]]:
    """Pure apart from the model. Returns [(name, ok, detail)] with counts only."""
    from datetime import datetime, timezone

    from agent.research.periods import HOLDOUT
    from agent.version import PIPELINE_VERSION

    now = now or datetime.now(timezone.utc)
    rows = state["rows"]
    out = []
    bad = [r for r in rows if (r["model_version"], r["artefact_sha256"], r["scoring_version"], r["pipeline_version"])
           != ("direction_1h_v1", REGISTERED_SHA256, "0.2.0", PIPELINE_VERSION)]
    out.append(("version", not bad and model.sha256 == REGISTERED_SHA256,
                f"{len(rows) - len(bad)} of {len(rows)} rows name direction_1h_v1, the pinned sha256, scoring 0.2.0 and pipeline {PIPELINE_VERSION}; "
                f"artefact now {model.sha256[:12]}; rows without a code commit: {sum(1 for r in rows if not r['code_commit'])}"))
    from datetime import datetime as _dt

    last_fit = _dt.fromisoformat(model.training["fit_range"][1])
    out.append(("development-only fit", last_fit + 25 * HOUR <= HOLDOUT.start,
                f"last fitting row {last_fit:%Y-%m-%d %H:%M} UTC; the holdout begins {HOLDOUT.start:%Y-%m-%d}"))
    t_bad = [r for r in rows if not (r["cutoff_at"] == r["as_of"] + HOUR and r["fetched_at"] >= r["cutoff_at"]
                                     and r["created_at"] >= r["fetched_at"] - timedelta(seconds=5)
                                     and r["fetched_at"] < r["as_of"] + 2 * HOUR and r["created_at"] < r["as_of"] + 2 * HOUR)]
    g_early = [r for r in rows if r["outcome_checked_at"] is not None and r["outcome_checked_at"] < r["as_of"] + 2 * HOUR]
    out.append(("timestamps", not t_bad and not g_early,
                f"{len(rows) - len(t_bad)} of {len(rows)} rows: cutoff = as_of + 1h, fetched after the cutoff, stored after the fetch and "
                f"before the outcome candle closed; graded before the target closed: {len(g_early)}"))
    trig = state["triggers"]
    want = ("shadow_direction_guard_update", "shadow_direction_forbid_delete")
    out.append(("immutability", all(trig.get(t) == "O" for t in want), f"triggers enabled: {sorted(t for t in want if trig.get(t) == 'O')}"))
    ok_rows = [r for r in rows if r["status"] == "ok"]
    worst, refused = 0.0, 0
    for r in ok_rows:
        got = model.predict(r["features"] or {})
        if got is None:
            refused += 1
            continue
        worst = max(worst, *(abs(a - b) for a, b in zip(got, (r["p_model"], r["p_one_feature"], r["p_base"]))))
    out.append(("preserved as predicted", refused == 0 and worst <= 1e-12,
                f"{len(ok_rows)} ok rows recomputed from their stored inputs: max difference {worst:.1e}; refused {refused}"))
    present = {r["as_of"] for r in rows}
    missing = []
    if rows:
        t, last = rows[0]["as_of"], max(present)
        while t <= last:
            if t not in present:
                missing.append(t)
            t += HOUR
    unrecorded = [h for h in missing if h + 2 * HOUR <= now and h not in set(state["lost"])]
    no_reason = [r for r in rows if r["status"] == "unavailable" and not r["status_reason"]]
    out.append(("nothing skipped silently", not unrecorded and not no_reason,
                f"hours with no row: {len(missing)} (recorded as lost: {len(missing) - len(unrecorded)}); unavailable rows: "
                f"{sum(1 for r in rows if r['status'] == 'unavailable')} (without a reason: {len(no_reason)}); recorded failures: {len(state['errors'])}"
                + (f" at steps {sorted({e[1] for e in state['errors']})}" if state["errors"] else "")))
    graded = [r for r in rows if r["outcome_status"] == "ok"]
    arith = [r for r in graded if not (math.isclose(r["outcome_return"], (r["outcome_close"] - r["reference_close"]) / r["reference_close"], rel_tol=0, abs_tol=1e-12)
                                       and r["outcome_up"] == (r["outcome_return"] > 0))]
    detail = f"{len(graded) - len(arith)} of {len(graded)} graded rows: return and UP consistent with the stored closes"
    candle_bad = 0
    if candles is not None:
        closes = candles["closes"]
        checked = [r for r in graded if r["as_of"] in closes and r["as_of"] + HOUR in closes]
        candle_bad = sum(1 for r in checked if not (math.isclose(closes[r["as_of"]], r["reference_close"], rel_tol=0, abs_tol=1e-9)
                                                    and math.isclose(closes[r["as_of"] + HOUR], r["outcome_close"], rel_tol=0, abs_tol=1e-9)))
        detail += f"; reference and outcome closes equal the exchange's candles in {len(checked) - candle_bad} of {len(checked)} rows checked"
    out.append(("graded correctly", not arith and candle_bad == 0, detail))
    if candles is not None:
        inputs = candles["inputs"]
        compared = [r for r in rows if r["as_of"] in inputs and r["features"]]
        mism = 0
        for r in compared:
            for k, v in r["features"].items():
                w = inputs[r["as_of"]].get(k)
                if v is None or w is None:
                    mism += int((v is None) != (w is None))
                elif abs(v - w) > INPUT_RTOL * max(abs(v), abs(w), 1e-12):
                    mism += 1
        out.append(("inputs reproduce", mism == 0, f"{len(compared)} rows' inputs recomputed from the exchange's candles: {mism} input values differ beyond rtol {INPUT_RTOL:g}"))
    return out


def fetch_candles(rows: list[dict]) -> dict:
    """The exchange's closed candles (with trade fields) over the span, and the research code's inputs for each row's hour."""
    from agent.data_providers.binance import BinanceProvider
    from agent.direction_shadow.features import WINDOW_HOURS, input_row

    bars, extras = BinanceProvider().get_hourly_klines_with_extras(1000)
    closes = {b.as_of: b.close for b in bars}
    pos = {b.as_of: i for i, b in enumerate(bars)}
    inputs = {}
    for r in rows:
        i = pos.get(r["as_of"])
        if i is None or i < WINDOW_HOURS - 1:
            continue
        values, _, _ = input_row(bars[i - WINDOW_HOURS + 1:i + 1], extras[i - WINDOW_HOURS + 1:i + 1])
        inputs[r["as_of"]] = values
    return {"closes": closes, "inputs": inputs}


def main(argv: list[str] | None = None) -> int:
    from agent.direction_shadow.model import load_model

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-candles", action="store_true", help="skip the exchange comparison (no network)")
    a = ap.parse_args(argv)
    state = read()
    model = load_model()
    candles = None if a.no_candles else fetch_candles(state["rows"])
    results = check(state, model, candles)
    readings = sorted(p.name for p in Path("research/monitoring").glob("direction_checkpoint_*"))
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"[{'PASS' if not readings else 'NOTE'}] blind: registered reading files present: {readings or 'none'}; this tool printed counts only")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
