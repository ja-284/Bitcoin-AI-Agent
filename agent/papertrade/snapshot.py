"""
Papirhandelens oversikt som ett dokument («paper-state 1»): det mobilsiden viser, og det `--status` skriver ut.

Bare lesing og bare beskrivende. Ingen avlesning og ingen konklusjon: avlesningene ved 90, 180 og 365 dager er
registrert i E042 (research/experiments/E042_paper_trading.json) og regnes der, med fersk start. Tallene her er
løpende tall fra regnskapsbøkene, slik de står. Med 118 strategier vil den beste se bedre ut enn den er.

`build_document` er ren utregning (testet uten database); `read_rows` henter radene (fra papirhandelens egne tabeller).
"""

from __future__ import annotations

import bisect
import math
import statistics
from datetime import date, datetime, timedelta, timezone

SCHEMA = "paper-state 1"
START_VALUE = 500.0
READINGS = (90, 180, 365)
FIRST_DAY = date(2026, 11, 16)  # E042: første papirdag
PASSIVE_WINDOW = timedelta(minutes=60)
NOTE = ("Papirhandel: ingen ekte penger. Signalet har ingen påvist evne til å forutsi kursen, og med 118 strategier "
        "vil den beste se bedre ut enn den er. Svaret kommer ved avlesningene etter 90, 180 og 365 dager.")

FAMILY_NAMES = {
    "A": "Modellens signal", "B": "Trend", "C": "Snitt med margin", "D": "Signal med filter", "E": "Rolig marked",
    "F": "Kjøp etter fall", "G": "Utbrudd", "H": "Med stopp", "MS": "Størrelse", "BASE": "Grunnlinjer",
}
SIZE_NAMES = {"msmore": "mer ved stor bevegelse", "msless": "mindre ved stor bevegelse", "vol": "etter svingninger"}
REASON_NAMES = {"signal": "signal", "stop_loss": "stopp", "trailing_stop": "glidende stopp", "time_stop": "tidsstopp",
                "rebalance": "justering"}


# ---------------------------------------------------------------- names

def family(name: str) -> str:
    return name.split("_", 1)[0]


def nice_name(name: str) -> str:
    """Et kort, forståelig norsk navn for en strategi i pt-1.0."""
    if name == "BASE_buy_and_hold" or name == "BH":
        return "Kjøp og hold"
    if name == "BASE_cash":
        return "Bare kontanter"
    if name.startswith("MS_"):
        _, base, mode = name.split("__")
        return f"{nice_name(base)} · {SIZE_NAMES.get(mode, mode)}"
    if name.startswith("H_"):
        base, overlay = name[2:].rsplit("_", 1)
        tail = {"sl10": "stopp 10 %", "tr15": "glidende stopp 15 %"}.get(overlay, overlay)
        return f"{nice_name(base)} + {tail}"
    fixed = {"A_sig23": "Signal kl. 23", "A_vote": "Dagens snitt-score", "A_confirm2": "Signal to dager på rad",
             "B_X20_100": "20-snitt over 100-snitt", "B_X50_200": "50-snitt over 200-snitt",
             "B_TREND02": "Trend over 0,2", "B_TREND06": "Trend over 0,6", "B_TREND10": "Full trend",
             "D_sig23_ma200": "Signal kl. 23 over 200-snitt", "D_sig23_trend": "Signal kl. 23 i trend",
             "D_vote_ma200": "Snitt-score over 200-snitt", "D_vote_trend": "Snitt-score i trend",
             "E_calm": "Rolig marked", "E_calm_ma200": "Rolig marked over 200-snitt"}
    if name in fixed:
        return fixed[name]
    parts = name.split("_")
    if parts[0] == "B" and parts[1].startswith("R"):
        return f"Opp siste {parts[1][1:]} dager"
    if parts[0] == "B" and parts[1].startswith("MA"):
        return f"Over {parts[1][2:]}-dagers snitt"
    if parts[0] == "C":
        return f"{parts[1][2:]}-dagers snitt ± {parts[2][1:]} %"
    if parts[0] == "F":
        return f"Kjøp etter −{parts[1][3:]} %, hold {parts[2][4:]} d"
    if parts[0] == "G":
        return f"Utbrudd {parts[1][2:]}/{parts[2][4:]}"
    return name


# ---------------------------------------------------------------- small statistics

def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), nd)


def max_drawdown(values: list[float]) -> float:
    """Største fall fra en topp, som andel (0,25 = 25 %). Startverdien regnes som første topp."""
    peak, worst = START_VALUE, 0.0
    for v in values:
        peak = max(peak, v)
        worst = max(worst, 1 - v / peak if peak > 0 else 0.0)
    return worst


def no_loss(values: list[float], k: int) -> dict | None:
    """Løpende vinduer på k beslutningsdager (ikke fersk start): andelen der verdien på slutten er minst den på
    starten, og snittendringen. Startverdien er første punkt. None før det finnes et helt vindu."""
    v = [START_VALUE] + list(values)
    n = len(v) - k
    if n < 1:
        return None
    ends = [(v[i + k] - v[i]) / v[i] for i in range(n)]
    return {"share": round(sum(1 for e in ends if e >= -1e-12) / n, 4), "mean": round(sum(ends) / n, 5), "n": n}


def passive_fill(quotes: list[dict], trades: list[dict], window: timedelta = PASSIVE_WINDOW) -> dict | None:
    """Ville en tålmodig ordre blitt fylt? For hver time: en kjøpsordre på kjøpskursen (bid) regnes som fylt hvis noen
    handel innen `window` gikk under den; en salgsordre på salgskursen (ask) hvis noen gikk over. Ser bort fra kø og
    mengde, så det er et øvre anslag. Bare timer der handlene er kjent for hele vinduet telles."""
    if not quotes or not trades:
        return None
    ts = sorted(trades, key=lambda t: t["traded_at"])
    times = [t["traded_at"] for t in ts]
    known_until = max(t["fetched_at"] for t in trades)
    hours = bid_hits = ask_hits = 0
    for q in quotes:
        start = q["fetched_at"]
        if start + window > known_until:
            continue
        lo, hi = bisect.bisect_right(times, start), bisect.bisect_right(times, start + window)
        prices = [ts[j]["price"] for j in range(lo, hi)]
        hours += 1
        bid_hits += any(p < q["bid"] for p in prices)
        ask_hits += any(p > q["ask"] for p in prices)
    if not hours:
        return None
    return {"hours": hours, "bid_fill_share": round(bid_hits / hours, 4), "ask_fill_share": round(ask_hits / hours, 4),
            "window_minutes": int(window.total_seconds() // 60)}


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def market_block(quotes: list[dict], trades: list[dict]) -> dict | None:
    """Firis marked fra timeloggen: kjøp/salg-gapet nå og per time på døgnet, hva 500 kr koster gjennom boken,
    handler per dag og om tålmodige ordrer ville blitt fylt."""
    if not quotes:
        return None
    qs = sorted(quotes, key=lambda q: q["hour"])

    def pct(q):
        mid = (q["bid"] + q["ask"]) / 2
        return {"spread": (q["ask"] - q["bid"]) / mid * 100,
                "buy500": None if q.get("buy_500_avg") is None else (q["buy_500_avg"] / mid - 1) * 100,
                "sell500": None if q.get("sell_500_avg") is None else (1 - q["sell_500_avg"] / mid) * 100}

    last = qs[-1]
    p_last = pct(last)
    by_hour: dict[int, list[float]] = {}
    for q in qs:
        by_hour.setdefault(q["hour"].astimezone(timezone.utc).hour, []).append(pct(q)["spread"])
    per_day: dict[str, list[float]] = {}
    for t in trades:
        per_day.setdefault(t["traded_at"].astimezone(timezone.utc).date().isoformat(), []).append(t["total"])
    days = sorted(per_day)[-14:]
    return {
        "quotes": len(qs), "first_hour": qs[0]["hour"].isoformat(), "last_hour": last["hour"].isoformat(),
        "now": {"bid": _r(last["bid"]), "ask": _r(last["ask"]), "spread_pct": _r(p_last["spread"], 3),
                "buy500_pct": _r(p_last["buy500"], 3), "sell500_pct": _r(p_last["sell500"], 3),
                "depth_bid_nok": _r(last.get("depth_bid_nok"), 0), "depth_ask_nok": _r(last.get("depth_ask_nok"), 0)},
        "spread_median_pct": _r(_median(pct(q)["spread"] for q in qs), 3),
        "buy500_median_pct": _r(_median(pct(q)["buy500"] for q in qs), 3),
        "spread_by_hour_utc": [_r(_median(by_hour.get(h, [])), 3) for h in range(24)],
        "trades_by_day": [{"day": d, "count": len(per_day[d]), "volume_nok": _r(sum(per_day[d]), 0)} for d in days],
        "passive": passive_fill(qs, trades),
    }


# ---------------------------------------------------------------- the document

def _account(strategy: str, book: str, rows: list[dict], day_index: dict, days_info: dict, n_days: int) -> dict:
    rows = sorted(rows, key=lambda r: r["day"])
    values: list[float | None] = [None] * n_days
    for r in rows:
        values[day_index[r["day"]]] = _r(r["value"])
    real = [r["value"] for r in rows]
    last = rows[-1]
    events = []
    for r in rows:
        if r["action"] == "NONE":
            continue
        d = days_info[r["day"]]
        if book == "firi":
            price = d["firi_ask"] if r["action"] == "BUY" else d["firi_bid"]
        else:
            price = d["close"]
        events.append({"day": r["day"].isoformat(), "action": r["action"], "price": _r(price),
                       "amount": _r(r["notional"]), "fee": _r(r["fee"]), "reason": r.get("reason")})
    mark = days_info[last["day"]]
    mark_px = mark["firi_bid"] if book == "firi" else mark["close"]
    exposure = (last["btc"] * mark_px / last["value"]) if last["value"] > 0 and mark_px else 0.0
    return {
        "id": strategy, "name": nice_name(strategy), "family": family(strategy),
        "active": bool(last["active"]), "value": _r(last["value"]), "ret": _r(last["value"] / START_VALUE - 1, 5),
        "in_btc": last["btc"] > 0, "exposure": _r(exposure, 3), "trades": len(events),
        "fees": _r(sum(r["fee"] for r in rows)), "max_dd": _r(max_drawdown(real), 4),
        "no_loss_5": no_loss(real, 5), "no_loss_30": no_loss(real, 30),
        "values": values, "events": events,
    }


def _summary(accounts: list[dict]) -> dict:
    ranked = sorted((a for a in accounts if a["family"] != "BASE"), key=lambda a: -a["ret"])
    by_id = {a["id"]: a for a in accounts}
    fams: dict[str, list[dict]] = {}
    for a in accounts:
        fams.setdefault(a["family"], []).append(a)
    eps = 1e-9
    return {
        "accounts": len(accounts), "active": sum(a["active"] for a in accounts),
        "in_btc": sum(a["in_btc"] for a in accounts),
        "in_plus": sum(a["ret"] > eps for a in accounts), "in_minus": sum(a["ret"] < -eps for a in accounts),
        "flat": sum(abs(a["ret"]) <= eps for a in accounts),
        "buy_hold_ret": by_id.get("BASE_buy_and_hold", {}).get("ret"),
        "cash_ret": by_id.get("BASE_cash", {}).get("ret"),
        "best": [a["id"] for a in ranked[:5]], "worst": [a["id"] for a in ranked[-5:][::-1]],
        "beat_buy_hold": sum(a["ret"] > (by_id.get("BASE_buy_and_hold", {}).get("ret") or 0) + eps for a in ranked),
        "families": [{"family": f, "name": FAMILY_NAMES.get(f, f), "n": len(xs),
                      "active": sum(a["active"] for a in xs), "mean_ret": _r(sum(a["ret"] for a in xs) / len(xs), 5)}
                     for f, xs in sorted(fams.items())],
        "goal": {k: sum(1 for a in accounts if a[k] and a[k]["share"] >= 0.75 and a[k]["mean"] > 0)
                 for k in ("no_loss_5", "no_loss_30")},
    }


def build_document(days: list[dict], ledger: list[dict], quotes: list[dict], trades: list[dict], errors: list[dict],
                   now: datetime, fictional: bool = False, strategy_set: str = "pt-1.0",
                   first_day: date = FIRST_DAY) -> dict:
    days = sorted(days, key=lambda d: d["day"])
    day_list = [d["day"] for d in days]
    day_index = {d: i for i, d in enumerate(day_list)}
    days_info = {d["day"]: d for d in days}
    books: dict[str, dict] = {}
    for book in ("firi", "modell"):
        groups: dict[str, list[dict]] = {}
        for r in ledger:
            if r["book"] == book:
                groups.setdefault(r["strategy"], []).append(r)
        accounts = [_account(s, book, rs, day_index, days_info, len(day_list)) for s, rs in sorted(groups.items())]
        books[book] = {"accounts": accounts, "summary": _summary(accounts) if accounts else None}
    # en dag mangler først når 6-timersfristen etter sluttkursen (midnatt UTC) er passert uten en beslutning
    deadline = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1, hours=6)
    span = (now.astimezone(timezone.utc).date() - first_day).days + 1
    expected = [first_day + timedelta(days=i) for i in range(max(span, 0))]
    done = set(day_list)
    last_err = max(errors, key=lambda e: e["occurred_at"]) if errors else None
    return {
        "schema": SCHEMA, "fictional": fictional, "generated_at": now.isoformat(), "strategy_set": strategy_set,
        "start_value": START_VALUE, "note": NOTE,
        "operation": {
            "first_day": day_list[0].isoformat() if day_list else None,
            "last_day": day_list[-1].isoformat() if day_list else None,
            "days": len(day_list), "missing_days": [d.isoformat() for d in expected if d not in done and deadline(d) < now],
            "errors": len(errors),
            "last_error": None if last_err is None else {"at": last_err["occurred_at"].isoformat(),
                                                         "step": last_err["step"], "type": last_err["error_type"]},
        },
        "readings": [{"days": n, "date": (first_day + timedelta(days=n - 1)).isoformat(), "reached": len(day_list) >= n}
                     for n in READINGS],
        "days": [d.isoformat() for d in day_list],
        "btc": {"close": [_r(d["close"]) for d in days],
                "firi_mid": [None if d.get("firi_bid") is None else _r((d["firi_bid"] + d["firi_ask"]) / 2)
                             for d in days]},
        "books": books,
        "market": market_block(quotes, trades),
    }


# ---------------------------------------------------------------- reading the database

def read_rows(conn) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """Alle rader dokumentet trenger, på en tilkobling som er satt til bare lesing av den som kaller."""
    def rows(cur, sql):
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    with conn.cursor() as cur:
        days = rows(cur, "SELECT day, close, firi_bid, firi_ask, inputs, strategies FROM paper_days ORDER BY day")
        ledger = rows(cur, "SELECT day, strategy, book, active, action, notional, fee, cash, btc, value, reason "
                           "FROM paper_ledger ORDER BY day")
        quotes = rows(cur, "SELECT hour, fetched_at, bid, ask, buy_500_avg, sell_500_avg, depth_bid_nok, depth_ask_nok "
                           "FROM firi_quotes WHERE hour > now() - interval '30 days' ORDER BY hour")
        trades = rows(cur, "SELECT traded_at, side, price, amount, total, fetched_at FROM firi_trades "
                           "WHERE traded_at > now() - interval '30 days' ORDER BY traded_at")
        errors = rows(cur, "SELECT occurred_at, step, error_type FROM paper_errors ORDER BY occurred_at")
    return days, ledger, quotes, trades, errors
