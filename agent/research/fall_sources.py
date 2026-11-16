"""
E043: varsler opsjonsfrykt (Deribit DVOL) eller belåning (Bybit åpne posisjoner, Bitfinex belånte long/short) FALL
bedre enn de varsler STIGNING? (research/experiments/E043_fall_sources.json, registrert i 9a67dea; øyeblikksbildene
registrert i e3ff801; denne koden er skrevet etter det og kjøres én gang.)

    python -m agent.research.fall_sources

Bare utviklingsdata: spotlysene gjennom history.load_bars (stopper ved holdout-perioden) og de tre nye seriene
gjennom den styrte leseren (snapshots.read_snapshot_frame), som aldri gir en rad etter utviklingsgrensen.

Punkt i tid: ved referansetimen t (lyset som åpner t, informasjonsgrensen t + 1 t) brukes lysets slutt og verdiene
stemplet t og t − 24 (synlige senest t + 1 t). Målet er framtiden: neste time (r1) og neste døgn (r24, bare ved 23:00).
Ingenting fylles inn: en manglende verdi gir en tom egenskap, og den timen står utenfor den egenskapens test.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.history import load_bars
from agent.research.metrics import block_bootstrap_estimates
from agent.research.periods import HOLDOUT
from agent.research.signal_batch import bootstrap_p, holm
from agent.research.snapshots import read_snapshot_frame

UTC = timezone.utc
EXPLORATION = (datetime(2021, 4, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC))
VALIDATION = (datetime(2024, 1, 1, tzinfo=UTC), HOLDOUT.start)
YEARS = {"2021": (datetime(2021, 4, 1, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC)),
         "2022": (datetime(2022, 1, 1, tzinfo=UTC), datetime(2023, 1, 1, tzinfo=UTC)),
         "2023": (datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC)),
         "2024": (datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)),
         "2025": (datetime(2025, 1, 1, tzinfo=UTC), HOLDOUT.start)}
FEATURES = ("F1_dvol_chg24", "F2_iv_rv", "F3_oi_chg24", "F4_oi_x_ret", "F5_margin_ls_chg24")
CONTROL = "X0_rv_chg24"
HORIZONS = {"1h": ("r1", 48), "24h": ("r24", 7)}   # mål og blokklengde (timer for 1 t, dager for døgnmålet)
N_BOOT, SEED, ALPHA, PRACTICAL = 2000, 43, 0.05, 0.05
OUT = Path("research/results/E043")


# ---------------------------------------------------------------- the hourly frame (pure, tested)

def build_frame(closes: pd.Series, dvol: pd.Series, oi: pd.Series, longs: pd.Series, shorts: pd.Series) -> pd.DataFrame:
    """Én rad per spotlys (indeks = lysets åpning t). Alle seriene er indeksert på eget stempel; bare stempel t og
    t − 24 t brukes for egenskapene ved t, og bare lys t + 1 og t + 24 for målene."""
    idx = closes.index
    h = pd.Timedelta(hours=1)

    def at(s: pd.Series, shift_hours: int) -> pd.Series:
        """Verdien stemplet nøyaktig t − shift (ingen utfylling)."""
        return pd.Series(s.reindex(idx - shift_hours * h).to_numpy(), index=idx)

    c, c_prev = closes, at(closes, 1)
    r = np.log(c / c_prev)                                  # timeavkastningen som slutter ved t (lys t mot t − 1)
    sq = r ** 2
    rv24 = np.sqrt(sq.rolling(24, min_periods=24).mean() * 24 * 365)
    # rolling over posisjoner: krev 24 sammenhengende timer (ellers ville et hull gjort vinduet lengre enn 24 t)
    consecutive = pd.Series(idx, index=idx).diff().eq(h).astype(int).rolling(23, min_periods=23).sum().eq(23)
    rv24 = rv24.where(consecutive & r.notna())
    rv24_prev = pd.Series(rv24.reindex(idx - 24 * h).to_numpy(), index=idx)
    f = pd.DataFrame(index=idx)
    f["close"] = c
    f["F1_dvol_chg24"] = np.log(at(dvol, 0) / at(dvol, 24))
    f["F2_iv_rv"] = np.log((at(dvol, 0) / 100.0) / rv24)
    f["F3_oi_chg24"] = np.log(at(oi, 0) / at(oi, 24))
    f["F4_oi_x_ret"] = f["F3_oi_chg24"] * np.log(c / at(closes, 24))
    ls = np.log(longs / shorts)
    f["F5_margin_ls_chg24"] = at(ls, 0) - at(ls, 24)
    f[CONTROL] = np.log(rv24 / rv24_prev)
    f["r1"] = np.log(at(closes, -1) / c)
    f["r24"] = np.log(at(closes, -24) / c)
    return f.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------- the registered statistic (pure, tested)

def contrast(pairs: np.ndarray) -> float:
    """C = A_topp − A_bunn. pairs[:, 0] = egenskapen, pairs[:, 1] = målet. A = P(mål ≤ 10-persentilen) −
    P(mål ≥ 90-persentilen), i egenskapens øverste og nederste desil."""
    return _parts(pairs)[0]


def _parts(pairs: np.ndarray) -> tuple[float, float, float]:
    x, y = pairs[:, 0], pairs[:, 1]
    qlo, qhi = np.quantile(y, [0.1, 0.9])
    flo, fhi = np.quantile(x, [0.1, 0.9])
    top, bot = x >= fhi, x <= flo
    if not top.any() or not bot.any():
        return float("nan"), float("nan"), float("nan")
    a_top = float(np.mean(y[top] <= qlo) - np.mean(y[top] >= qhi))
    a_bot = float(np.mean(y[bot] <= qlo) - np.mean(y[bot] >= qhi))
    return a_top - a_bot, a_top, a_bot


def spearman(pairs: np.ndarray) -> float:
    if len(pairs) < 3:
        return float("nan")
    return float(pd.Series(pairs[:, 0]).rank().corr(pd.Series(pairs[:, 1]).rank()))


def sample(frame: pd.DataFrame, feature: str, horizon: str, span: tuple[datetime, datetime]) -> np.ndarray:
    target, _ = HORIZONS[horizon]
    d = frame[(frame.index >= span[0]) & (frame.index < span[1])]
    if horizon == "24h":
        d = d[d.index.hour == 23]
    d = d[[feature, target]].dropna()
    return d.to_numpy(float)


def evaluate(frame: pd.DataFrame, feature: str, horizon: str) -> dict:
    _, block = HORIZONS[horizon]
    out = {}
    for name, span in (("exploration", EXPLORATION), ("validation", VALIDATION)):
        pairs = sample(frame, feature, horizon, span)
        point, est = block_bootstrap_estimates(pairs, contrast, block, N_BOOT, SEED)
        c, a_top, a_bot = _parts(pairs)
        out[name] = {"n": int(len(pairs)), "C": c, "A_top": a_top, "A_bottom": a_bot, "spearman": spearman(pairs),
                     "ci": [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))] if len(est) else None,
                     "p": bootstrap_p(est) if len(est) else float("nan")}
    out["years"] = {y: _parts(sample(frame, feature, horizon, span))[0] for y, span in YEARS.items()}
    return out


def verdict(r: dict, p_holm: float) -> str:
    ce, cv = r["exploration"]["C"], r["validation"]["C"]
    if any(math.isnan(v) for v in (ce, cv)) or np.sign(ce) != np.sign(cv):
        return "NOT_SUPPORTED"
    same_years = sum(1 for v in r["years"].values() if not math.isnan(v) and np.sign(v) == np.sign(cv))
    if same_years < 4:
        return "NOT_SUPPORTED"
    if p_holm < ALPHA and abs(cv) >= PRACTICAL:
        return "SUPPORTED"
    return "INCONCLUSIVE"


# ---------------------------------------------------------------- the one run

def load_inputs():
    bars, _, _ = load_bars(start=datetime(2021, 3, 1, tzinfo=UTC), end=HOLDOUT.start)
    closes = pd.Series([b.close for b in bars], index=pd.DatetimeIndex([b.as_of for b in bars]).tz_convert(UTC))

    def series(name, col):
        fr = read_snapshot_frame(name)
        return pd.Series(fr[col].to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(fr["as_of"], utc=True)))

    dvol = series("dvol", "close")
    oi = series("oi_bybit", "open_interest")
    longs, shorts = series("margin_bitfinex", "longs"), series("margin_bitfinex", "shorts")
    return closes, dvol, oi, longs, shorts


def run() -> dict:
    closes, dvol, oi, longs, shorts = load_inputs()
    if closes.index.max() >= HOLDOUT.start or max(s.index.max() for s in (dvol, oi, longs)) >= HOLDOUT.start:
        raise SystemExit("a value at or after the holdout's start reached E043: STOP")
    frame = build_frame(closes, dvol, oi, longs, shorts)
    results, pvals = {}, {}
    for horizon in HORIZONS:
        for feat in FEATURES:
            r = evaluate(frame, feat, horizon)
            results[f"{feat}|{horizon}"] = r
            pvals[f"{feat}|{horizon}"] = r["validation"]["p"]
        results[f"{CONTROL}|{horizon}"] = evaluate(frame, CONTROL, horizon)
    adjusted = holm(pvals, ALPHA)
    for key, adj in adjusted.items():
        results[key]["p_holm"] = adj["p_holm"]
        results[key]["verdict"] = verdict(results[key], adj["p_holm"])
    coverage = {f: float(frame.loc[(frame.index >= EXPLORATION[0]), f].notna().mean()) for f in (*FEATURES, CONTROL)}
    return {"experiment": "E043", "run_at": datetime.now(UTC).isoformat(),
            "candles": {"first": closes.index.min().isoformat(), "last": closes.index.max().isoformat(), "n": int(len(closes))},
            "coverage_from_2021_04": coverage, "results": results}


def _fmt(v, pct=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    return f"{v * 100:+.1f}" if pct else f"{v:+.3f}"


def write(doc: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fall_sources.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# E043: nye kilder om fall, resultat", "",
             "Kontrasten C (prosentpoeng) = varsling av fall minus varsling av stigning, øverste mot nederste desil. "
             "C > 0: høye verdier varsler fall mer enn stigning.", "",
             "| Egenskap | Horisont | C utforskning | C kontroll [95 %] | n kontroll | Holm p | år med samme fortegn | Dom |",
             "|---|---|---|---|---|---|---|---|"]
    for key, r in doc["results"].items():
        feat, hz = key.split("|")
        v = r["validation"]
        ci = "–" if not v["ci"] else f"[{v['ci'][0] * 100:+.1f}, {v['ci'][1] * 100:+.1f}]"
        same = sum(1 for y in r["years"].values() if not math.isnan(y) and np.sign(y) == np.sign(v["C"]))
        lines.append(f"| {feat} | {hz} | {_fmt(r['exploration']['C'], True)} | {_fmt(v['C'], True)} {ci} | {v['n']} | "
                     f"{'–' if 'p_holm' not in r else f'{r['p_holm']:.3f}'} | {same} av 5 | {r.get('verdict', 'kontroll')} |")
    (OUT / "fall_sources.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    doc = run()
    write(doc)
    for key, r in doc["results"].items():
        print(f"{key:28s} C_expl {_fmt(r['exploration']['C'], True):>6s}  C_val {_fmt(r['validation']['C'], True):>6s}  "
              f"p_holm {r.get('p_holm', float('nan')):.3f}  {r.get('verdict', 'kontroll')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
