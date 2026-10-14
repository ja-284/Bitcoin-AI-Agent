"""
GitHub's answers to the hourly dispatch, as kept by agent/database/dispatch_log.sql (owner-only diagnostics,
90 days). For a missed hour: did GitHub refuse the :12 dispatch, never answer it, or accept it and then run
nothing?

    python -m agent.database.dispatch_log                 # the last 7 days, summarised
    python -m agent.database.dispatch_log --hours 48 --list

Read-only (the transaction is READ ONLY). Needs the owner connection in the local .env: the job role
`bitcoin_agent` is deliberately given nothing on this table. Nothing in production imports this module.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from agent.database.db import get_connection

HOUR = timedelta(hours=1)
DISPATCH_MINUTE = 12  # docs/ops/supabase_dispatch.sql: '12 * * * *'
# A slot is judged only once the recorder (docs/ops/dispatch_responses_cron.sql: '47 * * * *', 35 minutes later) has
# had its chance to copy the answer, plus a margin. Before that, "no answer kept" would only mean "not copied yet".
JUDGE_AFTER = timedelta(minutes=40)
SQL = """SELECT responded_at, status_code, timed_out, error_msg, github_request_id, detail
         FROM dispatch_responses WHERE responded_at >= %s ORDER BY responded_at"""


def summarise(rows: list[tuple], now: datetime, hours: float) -> dict:
    """
    rows: (responded_at, status_code, timed_out, error_msg, github_request_id, detail), oldest first.
    A dispatch hour "without an answer" is a :12 slot inside the covered period with no row in its clock
    hour, judged only after the :47 recorder has had its chance (JUDGE_AFTER): pg_cron never ran, pg_net
    stored nothing, or the recorder itself did not run (all worth knowing; cron.job_run_details tells them
    apart). The covered period starts at the first kept row, so the time before the log existed is never
    counted as silence.
    """
    since = now - timedelta(hours=hours)
    by_status = Counter("no HTTP answer" if r[1] is None else str(r[1]) for r in rows)
    accepted = sum(1 for r in rows if r[1] is not None and 200 <= r[1] < 300)
    silent = []
    if rows:
        slot = rows[0][0].replace(minute=DISPATCH_MINUTE, second=0, microsecond=0)
        answered = {r[0].replace(minute=0, second=0, microsecond=0) for r in rows}
        while slot + JUDGE_AFTER <= now:  # judged once the :47 recorder has had its chance
            if slot >= since and slot.replace(minute=0) not in answered:
                silent.append(slot)
            slot += HOUR
    return {
        "window_hours": hours,
        "answers": len(rows),
        "accepted_2xx": accepted,
        "by_status": dict(sorted(by_status.items())),
        "timed_out": sum(1 for r in rows if r[2]),
        "with_error_text": sum(1 for r in rows if r[3] or r[5]),
        "slots_without_an_answer": silent,
        "newest": rows[-1][0] if rows else None,
    }


def _line(r: tuple) -> str:
    text = r[3] or r[5] or ""
    return (f"{r[0]:%Y-%m-%d %H:%M:%S} UTC  status {r[1] if r[1] is not None else '-':>3}"
            f"{'  TIMED OUT' if r[2] else ''}  github request {r[4] or '-'}{'  ' + text if text else ''}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=168.0)
    parser.add_argument("--list", action="store_true", help="also print every kept answer in the window")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SQL, (now - timedelta(hours=args.hours),))
            rows = cur.fetchall()
    s = summarise(rows, now, args.hours)
    newest = f"{s['newest']:%Y-%m-%d %H:%M} UTC" if s["newest"] else "none"
    print(f"Dispatch answers kept in the last {args.hours:g} h: {s['answers']} ({s['accepted_2xx']} accepted, 2xx); "
          f"by status {s['by_status']}; timed out {s['timed_out']}; with error text {s['with_error_text']}; newest {newest}")
    silent = s["slots_without_an_answer"]
    print(f":12 dispatch slots with no answer kept: {len(silent)}"
          + (": " + ", ".join(f"{t:%m-%d %H:%M}" for t in silent[:48]) if silent else ""))
    if args.list:
        for r in rows:
            print("  " + _line(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
