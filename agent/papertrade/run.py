"""
Papirhandelens daglige steg (E042). Ingen ekte penger, ingen nøkkel, ingen konto.

    python -m agent.papertrade.run            # timesjobben: behandler den siste hele UTC-dagen én gang
    python -m agent.papertrade.run --status   # bare lesing: en oversikt over papirhandelen så langt

Hver time forsøker timesjobben dette steget. Det gjør noe bare når den siste hele dagen (23:00-timen lagret) ikke er
behandlet ennå: da regner det ut alle 118 strategienes beslutning for den dagen fra det live registeret, henter Firis
offentlige kjøps- og salgskurs, og skriver én rad per strategi og regnskapsbok i sine egne tabeller, alt i én
transaksjon. Det kan aldri få timesjobben til å feile: feil lagres i paper_errors, og exit-koden er alltid 0.
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from agent.papertrade import engine
from agent.papertrade import strategies as S

START_CASH = 500.0
COST_MODEL = 0.0125  # modellboken: 0,7 % gebyr + halve spreaden, per side (E038)
FIRI_FEE = 0.007  # Firis offisielle gebyr, per side (firi.com/no/priser, lest 2026-11-15)
FIRI_TICKER = "https://api.firi.com/v2/markets/BTCNOK/ticker"
BOOKS = ("modell", "firi")
MAX_DELAY_HOURS = 6  # en dag behandles bare innen 6 timer etter sluttkursen, så Firi-prisen hører til beslutningen

INSERT_DAY = """INSERT INTO paper_days (day, strategy_set, code_commit, close, firi_bid, firi_ask, firi_fetched_at, inputs,
                                        strategies)
                VALUES (%(day)s, %(strategy_set)s, %(code_commit)s, %(close)s, %(firi_bid)s, %(firi_ask)s,
                        %(firi_fetched_at)s, %(inputs)s, %(strategies)s)"""
INSERT_ROW = """INSERT INTO paper_ledger (day, strategy, book, active, desired, size, action, notional, fee, cash, btc, value,
                                          state)
                VALUES (%(day)s, %(strategy)s, %(book)s, %(active)s, %(desired)s, %(size)s, %(action)s, %(notional)s,
                        %(fee)s, %(cash)s, %(btc)s, %(value)s, %(state)s)"""
INSERT_ERROR = """INSERT INTO paper_errors (day, step, error_type, error_message, code_commit)
                  VALUES (%(day)s, %(step)s, %(error_type)s, %(error_message)s, %(code_commit)s)"""


def code_commit() -> str | None:
    return (os.environ.get("GITHUB_SHA") or "")[:64] or None


def firi_quote(get=requests.get):
    """(bid, ask, fetched_at) fra Firis offentlige ticker, eller (None, grunn)."""
    try:
        r = get(FIRI_TICKER, timeout=15)
        r.raise_for_status()
        t = r.json()
        bid, ask = float(t["bid"]), float(t["ask"])
        if not (0 < bid <= ask and (ask - bid) / bid < 0.10):
            return None, f"implausible quote bid {bid} ask {ask}"
        return (bid, ask, datetime.now(timezone.utc)), None
    except Exception as e:  # a missing quote only stops the Firi book for the day
        return None, f"{type(e).__name__}: {str(e)[:300]}"


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def too_late(day_start, now) -> bool:
    """Dagens sluttkurs kommer ved midnatt UTC etter dagen; senere enn MAX_DELAY_HOURS etter det handles det ikke."""
    close_at = day_start.to_pydatetime() + timedelta(days=1)
    return (now - close_at).total_seconds() > MAX_DELAY_HOURS * 3600


def decide_day(df, specs: dict, i: int, states: dict, quote) -> list[dict]:
    """Rene beregninger: radene som skal skrives for dag-indeks i. `states` = {(strategi, bok): State}."""
    close = float(df["close"].iat[i])
    day = df.index[i].date()
    rows = []
    for name, spec in specs.items():
        w = float(spec["des"][i])
        size = S.size_today(df, spec, i) if spec["mode"] != "full" else None
        act = S.active(df, name, i)
        for book in BOOKS:
            if book == "firi" and quote is None:
                continue
            st = states.get((name, book)) or engine.State(cash=START_CASH)
            if book == "modell":
                r = engine.step(st, w, close, COST_MODEL, size=size, **spec["ov"])
            else:
                bid, ask, _ = quote
                r = engine.step(st, w, close, FIRI_FEE, buy_px=ask, sell_px=bid, mark_px=bid, size=size, **spec["ov"])
            rows.append({"day": day, "strategy": name, "book": book, "active": act, "desired": _num(w), "size": size,
                         "action": r.action, "notional": r.notional, "fee": r.fee, "cash": r.state.cash,
                         "btc": r.state.btc, "value": r.value, "state": r.state.to_json()})
    return rows


def record_error(day, step: str, err: BaseException | str) -> None:
    from agent.database.db import get_connection
    etype = type(err).__name__ if isinstance(err, BaseException) else "Note"
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(INSERT_ERROR, {"day": day, "step": step, "error_type": etype[:200],
                                       "error_message": str(err)[:2000], "code_commit": code_commit()})
            conn.commit()
    except Exception as e:  # never fail the job, not even here
        print(f"paper trading: could not record the error ({type(e).__name__}): {err}")


def run_once() -> str:
    import psycopg
    from psycopg.types.json import Jsonb

    from agent.database.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT as_of, close_price, signal, overall_score FROM predictions "
                        "WHERE pipeline_version = '0.2.0' ORDER BY as_of")
            pred = cur.fetchall()
            cur.execute("SELECT as_of, p_calibrated FROM shadow_move_size WHERE status = 'ok' ORDER BY as_of")
            shadow = cur.fetchall()
            df = S.daily_frame(pred, shadow)
            i = len(df) - 1
            day = df.index[i].date()
            cur.execute("SELECT 1 FROM paper_days WHERE day = %s", (day,))
            if cur.fetchone():
                conn.rollback()
                return f"{day}: already done"
            if too_late(df.index[i], datetime.now(timezone.utc)):
                conn.rollback()
                return f"{day}: too late to trade on (more than {MAX_DELAY_HOURS} h after its close); no decision"
            specs = S.strategy_set(df)
            cur.execute("SELECT DISTINCT ON (strategy, book) strategy, book, state FROM paper_ledger "
                        "ORDER BY strategy, book, day DESC")
            states = {(s, b): engine.State(**st) for s, b, st in cur.fetchall()}
            quote, qerr = firi_quote()
            rows = decide_day(df, specs, i, states, quote)
            inputs = {"sig23": _num(df["sig23"].iat[i]), "vote": _num(df["vote"].iat[i]), "pbar": _num(df["pbar"].iat[i]),
                      "sigma30": _num(df["SIGMA30"].iat[i]), "history_days": int(len(df)), "firi_error": qerr}
            for r in rows:
                r["state"] = Jsonb(r["state"])
            try:  # a concurrent run (a backup slot) may have written the same day a moment earlier
                cur.execute(INSERT_DAY, {"day": day, "strategy_set": S.STRATEGY_SET, "code_commit": code_commit(),
                                         "close": float(df["close"].iat[i]), "firi_bid": quote[0] if quote else None,
                                         "firi_ask": quote[1] if quote else None,
                                         "firi_fetched_at": quote[2] if quote else None,
                                         "inputs": Jsonb(inputs), "strategies": len(specs)})
                cur.executemany(INSERT_ROW, rows)
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return f"{day}: another run wrote it first"
        conn.commit()
    if qerr:
        record_error(day, "firi_quote", qerr)
    trades = sum(1 for r in rows if r["action"] != "NONE")
    return f"{day}: {len(specs)} strategies, {len(rows)} ledger rows, {trades} paper trades, Firi {'ok' if quote else 'missing'}"


def status() -> int:
    """Bare lesing: hvordan papirhandelen står (for eieren og den ukentlige gjennomgangen)."""
    from agent.database.db import get_connection
    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), min(day), max(day) FROM paper_days")
            n, first, last = cur.fetchone()
            cur.execute("SELECT count(*) FROM paper_errors")
            errors = cur.fetchone()[0]
            print(f"Papirhandel {S.STRATEGY_SET}: {n} dager behandlet ({first} til {last}), {errors} feil lagret.")
            for book in BOOKS:
                cur.execute("SELECT DISTINCT ON (strategy) strategy, value, active, (state->>'trades')::int FROM paper_ledger "
                            "WHERE book = %s ORDER BY strategy, day DESC", (book,))
                rows = sorted(cur.fetchall(), key=lambda r: -r[1])
                if not rows:
                    continue
                print(f"\nBok «{book}» ({len(rows)} strategier, startverdi 500):")
                for s, v, a, t in rows[:10]:
                    print(f"  {s:40s} {v:9.2f}  handler {t:3d}{'' if a else '  (ikke aktiv ennå)'}")
                print("  ...")
                for s, v, a, t in rows[-3:]:
                    print(f"  {s:40s} {v:9.2f}  handler {t:3d}{'' if a else '  (ikke aktiv ennå)'}")
        conn.rollback()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--status" in argv:
        return status()
    try:
        print("paper trading:", run_once())
    except Exception as e:  # the hourly job must never fail because of paper trading
        print(f"paper trading failed ({type(e).__name__}): {e}")
        record_error(None, "run", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
