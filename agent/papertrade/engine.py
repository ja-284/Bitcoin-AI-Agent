"""
Papirhandelens motor (E042): ett steg per dag for én strategi i én regnskapsbok. Ren funksjon, ingen database.

To måter å eie på:
  - helt inn / helt ut (E040s regler): ønsket posisjon w = 1, 0 eller NaN (behold), med stop-loss (sl), glidende
    stopp (tr) og tidsstopp (tstop). Regnestykket er nøyaktig det samme som agent/research/protection_goal.run_window
    (en test krever likhet til siste bit).
  - størrelse (E041): grunnregelen bestemmer inne/ute, og `size` (0-1) bestemmer hvor stor andel av verdien som skal
    stå i Bitcoin. Det handles bare når forskjellen er minst 20 prosentpoeng, eller ved full inngang eller utgang.

Prisene: signalet og stoppene bruker dagens sluttkurs (`close`), kjøp skjer til `buy_px` og salg til `sell_px`
(modellboken: begge = close; Firi-boken: ask og bid), og verdien regnes til `mark_px`.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

REBALANCE_BAND = 0.20


@dataclass
class State:
    cash: float
    btc: float = 0.0
    entry: float = 0.0
    peak: float = 0.0
    held: int = 0
    blocked: bool = False
    want_in: bool = False  # størrelsesmodus: grunnregelens siste beslutning
    trades: int = 0

    def to_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Step:
    action: str  # BUY, SELL eller NONE
    notional: float
    fee: float
    state: State
    value: float
    reason: str | None = None  # signal, stop_loss, trailing_stop, time_stop eller rebalance (None uten handel)


def _buy(s: State, amount: float, buy_px: float, c: float) -> float:
    fee = amount * c
    s.btc, s.cash = s.btc + (amount - fee) / buy_px, s.cash - amount
    s.trades += 1
    return fee


def step(s: State, w: float, close: float, c: float, buy_px: float | None = None, sell_px: float | None = None,
         mark_px: float | None = None, sl: float | None = None, tr: float | None = None, tstop: int | None = None,
         size: float | None = None) -> Step:
    buy_px = close if buy_px is None else buy_px
    sell_px = close if sell_px is None else sell_px
    mark_px = close if mark_px is None else mark_px
    s = State(**asdict(s))
    action, notional, fee, reason = "NONE", 0.0, 0.0, None
    if size is None:  # helt inn / helt ut, som E040
        if s.btc > 0.0:
            s.held += 1
            s.peak = max(s.peak, close)
            hit_sl = sl is not None and close <= s.entry * (1 - sl)
            hit_tr = tr is not None and close <= s.peak * (1 - tr)
            stopped = hit_sl or hit_tr
            timed = tstop is not None and s.held >= tstop
            if stopped or timed or w == 0.0:
                gross = s.btc * sell_px
                fee = gross * c
                s.cash, s.btc, s.trades = gross - fee, 0.0, s.trades + 1
                action, notional = "SELL", gross
                reason = "stop_loss" if hit_sl else "trailing_stop" if hit_tr else "time_stop" if timed else "signal"
                if stopped and w != 0.0:
                    s.blocked = True
        elif w == 1.0 and not s.blocked:
            fee = s.cash * c
            notional = s.cash
            s.btc, s.cash = (s.cash - fee) / buy_px, 0.0
            s.entry = s.peak = close
            s.held = 0
            s.trades += 1
            action, reason = "BUY", "signal"
        if s.blocked and w == 0.0:
            s.blocked = False
    else:  # størrelse, E041
        if w == 1.0:
            s.want_in = True
        elif w == 0.0:
            s.want_in = False
        target = size if s.want_in else 0.0
        equity = s.cash + s.btc * mark_px
        cur = s.btc * mark_px / equity if equity > 0 else 0.0
        enter, leave = target > 0 and s.btc == 0.0, target == 0.0 and s.btc > 0.0
        if enter or leave or abs(target - cur) >= REBALANCE_BAND:
            delta = target * equity - s.btc * mark_px
            if delta > 0:
                amount = min(delta, s.cash)
                if amount > 0:
                    fee = _buy(s, amount, buy_px, c)
                    action, notional, reason = "BUY", amount, "signal" if enter else "rebalance"
            elif delta < 0:
                x = s.btc if leave else min(s.btc, -delta / sell_px)
                gross = x * sell_px
                fee = gross * c
                s.cash, s.btc, s.trades = s.cash + gross - fee, max(s.btc - x, 0.0), s.trades + 1
                action, notional, reason = "SELL", gross, "signal" if leave else "rebalance"
    value = s.cash + s.btc * mark_px
    return Step(action, notional, fee, s, value, reason)


def size_for(mode: str, pbar: float | None, sigma30: float | None) -> float | None:
    """E041s størrelsesregler. None = helt inn / helt ut (modus «full»)."""
    def clip(x):
        return max(0.25, min(1.0, x))
    if mode == "full":
        return None
    if mode in ("msmore", "msless"):
        if pbar is None or math.isnan(pbar):
            return 0.25
        return clip((pbar - 0.20) / 0.40) if mode == "msmore" else clip((0.60 - pbar) / 0.40)
    if mode == "vol":
        if sigma30 is None or math.isnan(sigma30) or sigma30 <= 0:
            return 0.25
        return clip(0.0294 / sigma30)
    raise ValueError(mode)
