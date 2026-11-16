"""
Strategisettet pt-1.0 (E042): E040s 104 regler, E041s 12 størrelsesvarianter og to grunnlinjer, 118 i alt, kjørt på
daglige data bygget fra det live registeret alene. Ingen research-loader, ingen nedlasting, ingen forseglet periode:
bare rader fra `predictions` (pipeline 0.2.0) og `shadow_move_size`, som timesjobben selv har skrevet.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from agent.papertrade import engine
from agent.research import daily_direction as dd
from agent.research import protection_goal as pg

STRATEGY_SET = "pt-1.0"
SIZING_BASES = ["G_up55_down20", "C_MA100_b5", "A_sig23", "BH"]
SIZING_MODES = ["msmore", "msless", "vol"]


def daily_frame(pred_rows: list[tuple], shadow_rows: list[tuple]) -> pd.DataFrame:
    """pred_rows: (as_of, close_price, signal, overall_score); shadow_rows: (as_of, p_calibrated). Én rad per UTC-dag
    som har en 23:00-time; alle verdiene for dag d bruker bare timer fra og med dag d og tidligere."""
    idx = pd.DatetimeIndex([pd.Timestamp(r[0]) for r in pred_rows]).tz_convert("UTC").as_unit("ns")
    pred = pd.DataFrame({"close": [float(r[1]) for r in pred_rows], "signal": [r[2] for r in pred_rows],
                         "score": [float(r[3]) for r in pred_rows]}, index=idx).sort_index()
    at23 = pred[pred.index.hour == 23]
    daily = pd.Series(at23["close"].to_numpy(), index=at23.index.floor("D"), name="close")
    empty = pd.Series(np.nan, index=daily.index)
    df = dd.build_signals(daily, empty, empty * 21.0)
    rows = [{"as_of": t.isoformat(), "signal": s, "overall_score": sc}
            for t, s, sc in zip(pred.index, pred["signal"], pred["score"])]
    df = pg.add_inputs(df.join(pg.daily_signal_inputs(df, rows)))
    if shadow_rows:
        sidx = pd.DatetimeIndex([pd.Timestamp(r[0]) for r in shadow_rows]).tz_convert("UTC").as_unit("ns")
        p = pd.Series([np.nan if r[1] is None else float(r[1]) for r in shadow_rows], index=sidx)
        g = p.groupby(p.index.floor("D"))
        df["pbar"] = g.mean().where(g.count() >= 20).reindex(df.index)
    else:
        df["pbar"] = np.nan
    return df


def _required(name: str) -> list[str]:
    """Inndataene en strategi trenger for å være aktiv (rapportert, ikke brukt til beslutningen)."""
    if name.startswith("MS_"):
        _, base, mode = name.split("__")
        return _required(base) + (["pbar"] if mode in ("msmore", "msless") else ["SIGMA30"])
    if name in ("BH", "BASE_buy_and_hold", "BASE_cash") or name.startswith("H_BH_"):
        return []
    if name.startswith("H_"):
        return _required(re.sub(r"^H_|_(sl10|tr15)$", "", name))
    if name.startswith("A_sig23") or name == "A_confirm2":
        return ["sig23"]
    if name.startswith("A_vote"):
        return ["vote"]
    if name.startswith("D_"):
        return (["sig23"] if "sig23" in name else ["vote"]) + (["MA200"] if name.endswith("ma200") else ["TREND"])
    if name.startswith("B_TREND"):
        return ["TREND"]
    if name.startswith("B_"):
        return [name[2:]]
    if name.startswith("C_"):
        return [name.split("_")[1]]
    if name.startswith("E_calm"):
        return ["calm"] + (["MA200"] if name.endswith("ma200") else [])
    if name.startswith("F_"):
        return ["R1"]
    if name.startswith("G_"):
        n, m = re.match(r"G_up(\d+)_down(\d+)", name).groups()
        return [f"HI{n}", f"LO{m}"]
    raise ValueError(name)


def strategy_set(df: pd.DataFrame) -> dict[str, dict]:
    """navn -> {"des": ønsket posisjon per dag, "ov": overlegg, "mode": størrelsesmodus}. 118 strategier."""
    base = pg.strategies(df)
    out = {name: {"des": des, "ov": ov, "mode": "full"} for name, (des, ov) in base.items()}
    for b in SIZING_BASES:
        des = np.ones(len(df)) if b == "BH" else base[b][0]
        for m in SIZING_MODES:
            out[f"MS_{STRATEGY_SET}__{b}__{m}"] = {"des": des, "ov": {}, "mode": m}
    out["BASE_buy_and_hold"] = {"des": np.ones(len(df)), "ov": {}, "mode": "full"}
    out["BASE_cash"] = {"des": np.zeros(len(df)), "ov": {}, "mode": "full"}
    if len(out) != 118:
        raise RuntimeError(f"{len(out)} strategies, not the registered 118")
    return out


def active(df: pd.DataFrame, name: str, i: int) -> bool:
    req = _required(name)
    return all(c in df.columns and not (isinstance(df[c].iat[i], float) and math.isnan(df[c].iat[i])) for c in req)


def size_today(df: pd.DataFrame, spec: dict, i: int) -> float | None:
    pbar, sigma = df["pbar"].iat[i], df["SIGMA30"].iat[i]
    return engine.size_for(spec["mode"], None if math.isnan(pbar) else float(pbar),
                           None if math.isnan(sigma) else float(sigma))
