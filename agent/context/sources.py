"""
Markedskontekst for retningsforskningen (research/RETNINGSPLAN_2026-11-16.md, kandidat B; eierens ja 2026-11-16):
belåning og tvangssalg (terminmarkedet), frykt (opsjoner) og ordrebok, fra seks gratis kilder som svarer fra GitHubs
servere (tools/source_probe.py, 2026-11-16). Ingen nøkkel, bare offentlige markedsdata.

**Punkt i tid:** hver kilde lagrer bare det den viste da vi spurte (`fetched_at`), med kildens egne tidsstempler.
Ingenting fylles inn bakover. En senere test kan derfor bare bruke en rad for prediksjoner med informasjonsgrense
etter `fetched_at`. Dataene ses ikke mot utfall før et registrert eksperiment (retningsplanen, port 3).

Hver `parse_*` er ren (testet uten nett) og gir en liten ordbok; `fetchers` henter og tolker.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

OKX = "https://www.okx.com/api/v5"
DERIBIT = "https://www.deribit.com/api/v2/public"
HOUR_MS = 3_600_000
OKX_CONTRACT_BTC = 0.01        # BTC-USDT-SWAP: én kontrakt = 0,01 BTC (OKX' spesifikasjon); lagres for å kunne regne om
MAX_LIQUIDATION_PAGES = 10      # 100 likvidasjoner per side; et kraftig fall kan trenge flere sider for én time
BANDS = (0.001, 0.005, 0.01, 0.02)


def _f(x):
    return None if x in (None, "") else float(x)


# ---------------------------------------------------------------- OKX: funding, åpne posisjoner, long/short, likvidasjoner

def parse_okx(funding: dict, oi: dict, ls: dict, oivol: dict, liq_pages: list[dict], hour_ms: int) -> dict:
    fr = funding["data"][0]
    o = oi["data"][0]
    liq = summarize_liquidations(liq_pages, hour_ms - HOUR_MS, hour_ms)
    return {
        "funding": {"rate": _f(fr.get("fundingRate")), "settled_rate": _f(fr.get("settFundingRate")),
                    "premium": _f(fr.get("premium")), "funding_time": int(fr["fundingTime"]), "ts": int(fr["ts"])},
        "open_interest": {"contracts": _f(o["oi"]), "btc": _f(o["oiCcy"]), "usd": _f(o["oiUsd"]), "ts": int(o["ts"])},
        # de to siste timepunktene slik de sto da vi spurte (kildens tidsstempel; om et punkt er ferdig, avgjøres senere)
        "long_short_accounts_1h": [[int(t), _f(v)] for t, v in ls["data"][:2]],
        "oi_volume_1h": [[int(t), _f(a), _f(b)] for t, a, b in oivol["data"][:2]],
        "liquidations_prev_hour": liq,
        "contract_btc": OKX_CONTRACT_BTC,
    }


def summarize_liquidations(pages: list[dict], start_ms: int, end_ms: int) -> dict:
    """Likvidasjoner i [start, slutt): antall og kontrakter for tvangssolgte long-posisjoner og tvangskjøpte short.
    `complete` er sann bare når sidene gikk eldre enn starten (ellers er tallet et minimum)."""
    seen, out, oldest = set(), {"long": [0, 0.0], "short": [0, 0.0]}, None
    for page in pages:
        for block in page.get("data", []):
            for d in block.get("details", []):
                ts = int(d["ts"])
                oldest = ts if oldest is None else min(oldest, ts)
                key = (ts, d.get("posSide"), d.get("sz"), d.get("bkPx"))
                if key in seen or not start_ms <= ts < end_ms:
                    continue
                seen.add(key)
                side = d.get("posSide")
                if side in out:
                    out[side][0] += 1
                    out[side][1] += float(d["sz"])
    return {"long_count": out["long"][0], "long_contracts": out["long"][1], "short_count": out["short"][0],
            "short_contracts": out["short"][1], "complete": oldest is not None and oldest < start_ms,
            "window": [start_ms, end_ms]}


def fetch_okx(get, hour_ms: int) -> dict:
    funding = get(f"{OKX}/public/funding-rate?instId=BTC-USDT-SWAP")
    oi = get(f"{OKX}/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP")
    ls = get(f"{OKX}/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H")
    oivol = get(f"{OKX}/rubik/stat/contracts/open-interest-volume?ccy=BTC&period=1H")
    pages, after = [], None
    for _ in range(MAX_LIQUIDATION_PAGES):
        url = f"{OKX}/public/liquidation-orders?instType=SWAP&uly=BTC-USDT&state=filled" + (f"&after={after}" if after else "")
        page = get(url)
        pages.append(page)
        details = [d for b in page.get("data", []) for d in b.get("details", [])]
        if not details:
            break
        after = min(int(d["ts"]) for d in details)
        if after < hour_ms - HOUR_MS:
            break
    return parse_okx(funding, oi, ls, oivol, pages, hour_ms)


# ---------------------------------------------------------------- Deribit: frykt (DVOL, opsjoner) og funding

_OPT = re.compile(r"BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-([CP])$")
_MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}


def _expiry(code: str) -> datetime:
    m = re.fullmatch(r"(\d{1,2})([A-Z]{3})(\d{2})", code)
    return datetime(2000 + int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)), 8, tzinfo=timezone.utc)  # 08:00 UTC


def summarize_options(rows: list[dict], now: datetime) -> dict:
    """Opsjonene i korte trekk: for nærmeste forfall minst 2 dager unna og forfallet nærmest 30 dager, implisitt
    volatilitet ved pengene, for salgsopsjoner ~10 % under og kjøpsopsjoner ~10 % over (skjevheten = frykt for fall),
    og åpne posisjoner og volum for salgs- mot kjøpsopsjoner."""
    by_exp: dict[str, list[tuple[float, str, dict]]] = {}
    tot = {"put_oi": 0.0, "call_oi": 0.0, "put_volume_usd": 0.0, "call_volume_usd": 0.0}
    for r in rows:
        m = _OPT.match(r.get("instrument_name", ""))
        if not m:
            continue
        exp, strike, kind = m.group(1), float(m.group(2)), m.group(3)
        by_exp.setdefault(exp, []).append((strike, kind, r))
        side = "put" if kind == "P" else "call"
        tot[f"{side}_oi"] += float(r.get("open_interest") or 0)
        tot[f"{side}_volume_usd"] += float(r.get("volume_usd") or 0)
    days = {e: (_expiry(e) - now).total_seconds() / 86400 for e in by_exp}
    future = {e: d for e, d in days.items() if d >= 2}
    picks = {}
    if future:
        picks["near"] = min(future, key=future.get)
        picks["d30"] = min(future, key=lambda e: abs(future[e] - 30))

    def iv_at(rows_e, kind, target):
        cand = [(abs(s - target), r) for s, k, r in rows_e if k == kind and r.get("mark_iv")]
        return float(min(cand, key=lambda x: x[0])[1]["mark_iv"]) if cand else None

    out = {"totals": {k: round(v, 2) for k, v in tot.items()}}
    for name, e in picks.items():
        rows_e = by_exp[e]
        und = next((float(r["underlying_price"]) for _, _, r in rows_e if r.get("underlying_price")), None)
        if und is None:
            continue
        atm = [x for x in (iv_at(rows_e, "C", und), iv_at(rows_e, "P", und)) if x is not None]
        put90, call110 = iv_at(rows_e, "P", 0.9 * und), iv_at(rows_e, "C", 1.1 * und)
        out[name] = {"expiry": e, "days": round(days[e], 3), "underlying": und,
                     "atm_iv": round(sum(atm) / len(atm), 3) if atm else None, "put90_iv": put90, "call110_iv": call110,
                     "skew": None if put90 is None or call110 is None else round(put90 - call110, 3),
                     "put_oi": round(sum(float(r.get("open_interest") or 0) for _, k, r in rows_e if k == "P"), 2),
                     "call_oi": round(sum(float(r.get("open_interest") or 0) for _, k, r in rows_e if k == "C"), 2)}
    return out


def parse_deribit(dvol: dict, perp: dict, options: dict, now: datetime) -> dict:
    p = perp["result"]
    return {
        "dvol_1h": [list(c) for c in dvol["result"]["data"][-2:]],  # [tid, åpning, høy, lav, slutt]; det siste kan være uferdig
        "perpetual": {k: p.get(k) for k in ("timestamp", "current_funding", "funding_8h", "open_interest", "mark_price",
                                            "index_price")},
        "options": summarize_options(options["result"], now),
    }


def fetch_deribit(get, now: datetime) -> dict:
    now_ms = int(now.timestamp() * 1000)
    dvol = get(f"{DERIBIT}/get_volatility_index_data?currency=BTC&start_timestamp={now_ms - 3 * HOUR_MS}"
               f"&end_timestamp={now_ms}&resolution=3600")
    perp = get(f"{DERIBIT}/ticker?instrument_name=BTC-PERPETUAL")
    options = get(f"{DERIBIT}/get_book_summary_by_currency?currency=BTC&kind=option")
    return parse_deribit(dvol, perp, options, now)


# ---------------------------------------------------------------- Kraken Futures, Hyperliquid, Bitfinex

def parse_kraken(tickers: dict) -> dict:
    t = next(x for x in tickers["tickers"] if x.get("symbol") == "PF_XBTUSD")
    return {k: t.get(k) for k in ("lastTime", "relativeFundingRate", "relativeFundingRatePrediction", "openInterest",
                                  "markPrice", "indexPrice", "bid", "ask", "vol24h")}


def parse_hyperliquid(meta_ctx: list) -> dict:
    names = [u["name"] for u in meta_ctx[0]["universe"]]
    c = meta_ctx[1][names.index("BTC")]
    return {k: _f(c.get(k)) for k in ("funding", "openInterest", "premium", "markPx", "oraclePx", "midPx", "dayNtlVlm")}


def parse_bitfinex(status: list, longs: list, shorts: list) -> dict:
    s = status[0]  # Bitfinex' faste rekkefølge for derivatstatus
    return {"ts": s[1], "deriv_price": s[3], "spot_price": s[4], "next_funding_ts": s[8], "next_funding_accrued": s[9],
            "current_funding": s[12], "mark_price": s[15], "open_interest": s[18],
            "margin_longs_btc": [longs[0], longs[1]], "margin_shorts_btc": [shorts[0], shorts[1]]}


# ---------------------------------------------------------------- Binance-ordreboken (speilet timesjobben bruker)

def parse_book(depth: dict) -> dict:
    """Ordrebokens form: midtkurs, gap, og dollar på kjøps- og salgssiden innenfor 0,1 / 0,5 / 1 / 2 % av midtkursen.
    `reach` sier hvor langt de 1000 nivåene rakk på hver side (et bånd utenfor er ufullstendig)."""
    bids = [(float(p), float(q)) for p, q in depth["bids"]]
    asks = [(float(p), float(q)) for p, q in depth["asks"]]
    bid, ask = bids[0][0], asks[0][0]
    mid = (bid + ask) / 2
    out = {"mid": mid, "spread_bps": round((ask - bid) / mid * 1e4, 4),
           "reach": [round(1 - bids[-1][0] / mid, 5), round(asks[-1][0] / mid - 1, 5)], "update_id": depth.get("lastUpdateId")}
    for b in BANDS:
        out[f"bid_usd_{b}"] = round(sum(p * q for p, q in bids if p >= mid * (1 - b)), 2)
        out[f"ask_usd_{b}"] = round(sum(p * q for p, q in asks if p <= mid * (1 + b)), 2)
    return out


def fetchers(get, post, now: datetime) -> dict:
    hour_ms = int(now.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
    return {
        "okx": lambda: fetch_okx(get, hour_ms),
        "deribit": lambda: fetch_deribit(get, now),
        "kraken": lambda: parse_kraken(get("https://futures.kraken.com/derivatives/api/v3/tickers")),
        "hyperliquid": lambda: parse_hyperliquid(post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})),
        "bitfinex": lambda: parse_bitfinex(get("https://api-pub.bitfinex.com/v2/status/deriv?keys=tBTCF0:USTF0"),
                                           get("https://api-pub.bitfinex.com/v2/stats1/pos.size:1h:tBTCUSD:long/last"),
                                           get("https://api-pub.bitfinex.com/v2/stats1/pos.size:1h:tBTCUSD:short/last")),
        "binance_book": lambda: parse_book(get("https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=1000")),
    }


SOURCES = ("okx", "deribit", "kraken", "hyperliquid", "bitfinex", "binance_book")
