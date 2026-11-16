"""
Kildeprøve (research/RETNINGSPLAN_2026-11-16.md, kandidat B): svarer de gratis, offentlige kildene for terminmarked,
opsjoner og ordrebok, sett fra maskinen dette kjører på? Arbeidsflyten «Kildeprøve» kjører den på GitHubs servere
(USA), der timesjobben kjører, fordi flere børser stenger amerikanske adresser.

Bare lesing av offentlige markedsdata: ingen nøkkel, ingen hemmelighet, ingen database, ingenting lagres. Skriver én
linje per kilde (på GitHub som merknader, `::notice`, som kan leses uten innlogging) og avslutter alltid med 0.

    python tools/source_probe.py [--github]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

NOW = int(time.time() * 1000)
H = 3_600_000

# gruppe -> [(navn, metode, adresse, kropp)]
SOURCES: dict[str, list[tuple[str, str, str, dict | None]]] = {
    "binance-termin": [
        ("premiumIndex (funding, basis nå)", "GET", "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", None),
        ("openInterest (nå)", "GET", "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", None),
        ("fundingRate (historikk)", "GET", "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=3", None),
        ("openInterestHist 1h", "GET", "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=3", None),
        ("globalLongShortAccountRatio 1h", "GET", "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=3", None),
        ("takerlongshortRatio 1h", "GET", "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=3", None),
        ("premiumIndexKlines 1h", "GET", "https://fapi.binance.com/fapi/v1/premiumIndexKlines?symbol=BTCUSDT&interval=1h&limit=3", None),
    ],
    "okx": [
        ("funding-rate (nå)", "GET", "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP", None),
        ("open-interest (nå)", "GET", "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP", None),
        ("long-short-account-ratio 1H", "GET", "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H", None),
        ("liquidation-orders", "GET", "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly=BTC-USDT&state=filled", None),
    ],
    "bybit": [
        ("tickers (funding, OI nå)", "GET", "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", None),
        ("open-interest 1h", "GET", "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1h&limit=3", None),
        ("account-ratio 1h", "GET", "https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=1h&limit=3", None),
    ],
    "deribit": [
        ("DVOL 1h", "GET", f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp={NOW - 3 * H}&end_timestamp={NOW}&resolution=3600", None),
        ("opsjoner (sammendrag)", "GET", "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option", None),
        ("BTC-PERPETUAL ticker", "GET", "https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL", None),
    ],
    "andre": [
        ("kraken futures tickers", "GET", "https://futures.kraken.com/derivatives/api/v3/tickers", None),
        ("hyperliquid metaAndAssetCtxs", "POST", "https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"}),
        ("bitfinex deriv status", "GET", "https://api-pub.bitfinex.com/v2/status/deriv?keys=tBTCF0:USTF0", None),
        ("bitfinex long-posisjoner", "GET", "https://api-pub.bitfinex.com/v2/stats1/pos.size:1h:tBTCUSD:long/last", None),
        ("bitmex funding", "GET", "https://www.bitmex.com/api/v1/funding?symbol=XBTUSD&count=1&reverse=true", None),
        ("binance spot depth (speilet)", "GET", "https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=100", None),
    ],
}


def check(method: str, url: str, body: dict | None, timeout: float = 15) -> tuple[str, str]:
    """('ok' | 'nei', kort forklaring). Svaret lagres aldri; bare status, tid og om det var gyldig JSON."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": "research-probe/1.0", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(2_000_000)
            ms = int((time.time() - t0) * 1000)
            try:
                json.loads(raw)
            except ValueError:
                return "nei", f"HTTP {r.status}, men ikke JSON ({ms} ms)"
            return "ok", f"HTTP {r.status}, {len(raw)} byte, {ms} ms"
    except urllib.error.HTTPError as e:
        return "nei", f"HTTP {e.code} ({e.reason})"
    except Exception as e:  # noqa: BLE001 -- en prøve skal aldri stoppe
        return "nei", f"{type(e).__name__}: {str(e)[:80]}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    github = "--github" in argv
    for group, items in SOURCES.items():
        for name, method, url, body in items:
            status, why = check(method, url, body)
            line = f"{status.upper():3s} {name}: {why}"
            print(f"::notice title={group}::{line}" if github else f"{group:15s} {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
