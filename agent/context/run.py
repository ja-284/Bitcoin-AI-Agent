"""
Timesjobbens innsamling av markedskontekst (research/RETNINGSPLAN_2026-11-16.md, kandidat B; eierens ja 2026-11-16).

Hver kjøring (også reserveslottene) henter bare kildene som mangler for den inneværende klokketimen og lagrer én rad
per kilde og time i `context_hourly`. En kilde som feiler, lagres én gang per time i `context_errors` og prøves igjen
av neste kjøring samme time. Skriver bare i sine egne tabeller, rører aldri prediksjonen eller noe spor, og avslutter
alltid med 0: timesjobben kan aldri feile på grunn av dette steget.

    python -m agent.context.run            # samle (timesjobben)
    python -m agent.context.run --status   # bare lesing: hvor mye som er samlet
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from agent.context import sources as S

TIMEOUT = 15
DEADLINE_SECONDS = 90   # hele steget; en treg kilde kan ikke holde timesjobben igjen
UA = {"User-Agent": "bitcoin-agent-research/1.0"}

INSERT_ROW = """INSERT INTO context_hourly (hour, source, fetched_at, code_commit, data)
                VALUES (%(hour)s, %(source)s, %(fetched_at)s, %(code_commit)s, %(data)s)
                ON CONFLICT (hour, source) DO NOTHING"""
INSERT_ERROR = """INSERT INTO context_errors (hour, source, error_type, error_message, code_commit)
                  VALUES (%(hour)s, %(source)s, %(error_type)s, %(error_message)s, %(code_commit)s)
                  ON CONFLICT (hour, source) DO NOTHING"""


def code_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _get(url: str):
    r = requests.get(url, timeout=TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.json()


def _post(url: str, body: dict):
    r = requests.post(url, json=body, timeout=TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.json()


def collect(missing: list[str], now: datetime, get=_get, post=_post, deadline: float = DEADLINE_SECONDS):
    """Henter de manglende kildene. Gir (rader, feil): rader = [(kilde, hentet, data)], feil = [(kilde, unntak)]."""
    table = S.fetchers(get, post, now)
    rows, errors, t0 = [], [], time.monotonic()
    for source in missing:
        if time.monotonic() - t0 > deadline:
            errors.append((source, TimeoutError(f"not tried: the step's {deadline} s were used up")))
            continue
        try:
            data = table[source]()
            rows.append((source, datetime.now(timezone.utc), data))
        except Exception as e:  # noqa: BLE001 -- én kilde som feiler, stopper ikke de andre
            errors.append((source, e))
    return rows, errors


def run_once(now: datetime | None = None) -> str:
    from psycopg.types.json import Jsonb

    from agent.database.db import get_connection

    now = now or datetime.now(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source FROM context_hourly WHERE hour = %s", (hour,))
            have = {r[0] for r in cur.fetchall()}
        conn.rollback()
    missing = [s for s in S.SOURCES if s not in have]
    if not missing:
        return f"{hour:%Y-%m-%d %H}:00: all {len(S.SOURCES)} sources already saved"
    rows, errors = collect(missing, now)
    commit = code_commit()
    saved = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for source, fetched_at, data in rows:
                try:
                    with conn.transaction():  # én rad som brytes (for stor, ugyldig), stopper ikke de andre
                        cur.execute(INSERT_ROW, {"hour": hour, "source": source, "fetched_at": fetched_at,
                                                 "code_commit": commit, "data": Jsonb(data)})
                    saved += 1
                except Exception as e:  # noqa: BLE001
                    errors.append((source, e))
            for source, e in errors:
                cur.execute(INSERT_ERROR, {"hour": hour, "source": source, "error_type": type(e).__name__[:200],
                                           "error_message": str(e)[:2000], "code_commit": commit})
        conn.commit()
    failed = ", ".join(f"{s} ({type(e).__name__})" for s, e in errors)
    return f"{hour:%Y-%m-%d %H}:00: saved {saved} of {len(missing)} missing sources" + (f"; failed: {failed}" if failed else "")


def status() -> int:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT source, count(*), min(hour), max(hour) FROM context_hourly GROUP BY 1 ORDER BY 1")
            rows = cur.fetchall()
            cur.execute("SELECT source, count(*) FROM context_errors WHERE hour > now() - interval '7 days' GROUP BY 1 ORDER BY 1")
            errs = dict(cur.fetchall())
        conn.rollback()
    print("Markedskontekst (kandidat B i retningsplanen):")
    for source, n, first, last in rows:
        print(f"  {source:14s} {n:6d} timer  {first:%Y-%m-%d %H}:00 → {last:%Y-%m-%d %H}:00  feil siste 7 d: {errs.get(source, 0)}")
    if not rows:
        print("  ingenting samlet ennå")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--status" in argv:
        return status()
    try:
        print("market context:", run_once())
    except Exception as e:  # noqa: BLE001 -- research data; the hourly job must never fail because of it
        print(f"market context failed ({type(e).__name__}): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
