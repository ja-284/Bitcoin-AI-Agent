"""
Strategy rule-1.0: the owner's rule (BUY -> invested, SELL -> cash, HOLD -> keep) made fee-aware and risk-limited.

Every parameter below is a stated, unvalidated choice, shown in the website next to each decision. None of them was
chosen from the live record (docs/platform/PLATFORM_PLAN.md section 3.1). The BUY/HOLD/SELL signal itself has no
demonstrated predictive value (E001, E017), so this strategy is built to waste as little as possible on fees and to
bound losses, not to promise a return.

`decide` is a pure function: the same inputs always give the same decision, and it never talks to an exchange or a
database. Sizing uses only inputs that are either risk measures or calibrated: the stored 24 h realised volatility and
the frozen move-size probability. The "confidence" heuristic is deliberately NOT used (measured as uninformative,
ECE 0.41); its factor is fixed at 1 and reported as disabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

STRATEGY_VERSION = "rule-1.0"

HARD_MAX_ALLOCATION = 500.0  # account currency; raising it needs a reviewed commit, never a setting
TARGET_HOURLY_VOL = 0.006  # full size unless the last 24 h moved more than ~0.6% an hour
F_VOL_MIN = 0.25
F_MOVE_MIN = 0.5  # also the factor used when the move-size probability is missing
BAND_FRACTION = 0.20  # resize only when the change exceeds 20% of the cap
MIN_HOLD_HOURS = 6  # no reversal of the last trade's direction within this time, except a risk exit
MAX_TRADES_24H = 4
DAILY_LOSS_LIMIT = 0.10  # equity down more than this vs 24 h ago -> flatten and halt
MAX_DRAWDOWN = 0.30  # equity down more than this from its peak -> flatten and halt
MAX_SIGNAL_AGE_HOURS = 2.0  # the hour's candle must have closed at most this long ago

SIGNALS = ("BUY", "HOLD", "SELL")


@dataclass(frozen=True)
class Snapshot:
    """What the strategy may know at decision time: the newest saved hour and the move-size row for it."""

    as_of: datetime  # the hour the prediction describes (its candle opens here and closes an hour later)
    signal: str
    price: float  # the price an order would fill near, in the account currency per BTC
    rv_24: float | None  # stored 24 h realised volatility of hourly returns
    p_large: float | None  # frozen move-size model: P(next-hour move > 0.25%)
    pipeline_version: str
    scoring_version: str
    price_is_synthetic: bool = False
    overall_score: float | None = None  # shown, never used for sizing
    confidence: float | None = None  # shown, never used for sizing (uninformative)


@dataclass(frozen=True)
class Settings:
    """The owner's settings. The cap is bounded by HARD_MAX_ALLOCATION in code."""

    allocation_cap: float
    paused: bool = False
    min_order_value: float = 50.0  # the venue's minimum order, in the account currency
    expected_versions: tuple[str, str] = ("0.2.0", "0.2.0")  # (pipeline, scoring) the strategy was written for

    def __post_init__(self):
        if not 0 < self.allocation_cap <= HARD_MAX_ALLOCATION:
            raise ValueError(f"allocation cap must be in (0, {HARD_MAX_ALLOCATION}]; got {self.allocation_cap}")
        if self.min_order_value <= 0:
            raise ValueError("min_order_value must be positive")


@dataclass(frozen=True)
class Portfolio:
    """The strategy's own capital: cash and BTC it controls, never the rest of the exchange account."""

    cash: float
    btc: float = 0.0
    peak_equity: float = 0.0
    equity_24h_ago: float | None = None
    last_trade_at: datetime | None = None
    last_trade_side: str | None = None
    trade_times: tuple[datetime, ...] = ()
    halted: str | None = None  # set by a risk exit or a failed reconciliation; only the owner clears it

    def equity(self, price: float) -> float:
        return self.cash + self.btc * price


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Order:
    side: str  # "BUY" spends `quote_amount`; "SELL" sells `base_qty`
    quote_amount: float = 0.0
    base_qty: float = 0.0


@dataclass(frozen=True)
class Decision:
    strategy_version: str
    as_of: datetime
    signal: str
    action: str  # BUY, SELL or NONE
    order: Order | None
    exposure_before: float
    target_exposure: float
    equity: float
    factors: dict
    checks: tuple[Check, ...]
    reasons: tuple[str, ...]
    halt: str | None = None  # a risk exit asks the engine to halt after it
    risk_exit: bool = False
    extra: dict = field(default_factory=dict)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sizing_factors(snapshot: Snapshot) -> dict:
    """The three factors, each with what it was computed from. size = min(f_vol, f_move); f_conf is disabled."""
    if snapshot.rv_24 and snapshot.rv_24 > 0:
        f_vol = _clip(TARGET_HOURLY_VOL / snapshot.rv_24, F_VOL_MIN, 1.0)
        vol_note = f"rv_24 {snapshot.rv_24:.5f} vs target {TARGET_HOURLY_VOL}"
    else:
        f_vol, vol_note = F_VOL_MIN, "rv_24 missing: the smallest size"
    if snapshot.p_large is not None:
        f_move = _clip(1.5 - snapshot.p_large, F_MOVE_MIN, 1.0)
        move_note = f"P(move > 0.25%) {snapshot.p_large:.3f}"
    else:
        f_move, move_note = F_MOVE_MIN, "move-size probability missing: half size"
    return {"f_vol": f_vol, "f_move": f_move, "f_conf": 1.0, "size": min(f_vol, f_move),
            "notes": {"f_vol": vol_note, "f_move": move_note,
                      "f_conf": "disabled: the confidence heuristic is not calibrated (ECE 0.41)"}}


def decide(snapshot: Snapshot, portfolio: Portfolio, settings: Settings, now: datetime) -> Decision:
    price = snapshot.price
    if not price > 0:
        raise ValueError("price must be positive")
    equity = portfolio.equity(price)
    exposure = portfolio.btc * price
    cap = settings.allocation_cap
    factors = sizing_factors(snapshot)
    checks: list[Check] = []
    reasons: list[str] = []

    def done(target, order=None, halt=None, risk_exit=False):
        return Decision(STRATEGY_VERSION, snapshot.as_of, snapshot.signal,
                        "NONE" if order is None else order.side, order, exposure, target, equity, factors,
                        tuple(checks), tuple(reasons), halt, risk_exit)

    # 1. The owner's pause and an earlier halt stop everything, including exits.
    checks.append(Check("not paused", not settings.paused, "paused by the owner" if settings.paused else "running"))
    checks.append(Check("not halted", portfolio.halted is None, portfolio.halted or "no halt"))
    if settings.paused or portfolio.halted:
        reasons.append("trading is paused by the owner" if settings.paused else f"trading is halted: {portfolio.halted}")
        return done(exposure)

    # 2. Risk exits: they flatten whatever the signal says, and then halt until the owner resumes.
    peak = max(portfolio.peak_equity, equity)
    drawdown = 0.0 if peak <= 0 else 1 - equity / peak
    daily = None if not portfolio.equity_24h_ago else 1 - equity / portfolio.equity_24h_ago
    dd_ok = drawdown <= MAX_DRAWDOWN
    daily_ok = daily is None or daily <= DAILY_LOSS_LIMIT
    checks.append(Check("drawdown limit", dd_ok, f"drawdown {drawdown:.1%} (limit {MAX_DRAWDOWN:.0%})"))
    checks.append(Check("daily loss limit", daily_ok,
                        "no 24 h history yet" if daily is None else f"24 h change {-daily:+.1%} (limit -{DAILY_LOSS_LIMIT:.0%})"))
    if not (dd_ok and daily_ok):
        halt = "drawdown limit reached" if not dd_ok else "daily loss limit reached"
        reasons.append(f"{halt}: everything is sold and trading halts until the owner resumes")
        order = Order("SELL", base_qty=portfolio.btc) if portfolio.btc * price >= settings.min_order_value else None
        if order is None and portfolio.btc > 0:
            reasons.append("the remaining BTC is below the venue's minimum order and stays")
        return done(0.0, order, halt=halt, risk_exit=True)

    # 3. Data quality: a doubtful hour may reduce risk, never add it.
    age_h = (now - (snapshot.as_of + timedelta(hours=1))).total_seconds() / 3600
    fresh = 0 <= age_h <= MAX_SIGNAL_AGE_HOURS
    versions_ok = (snapshot.pipeline_version, snapshot.scoring_version) == settings.expected_versions
    data_ok = fresh and versions_ok and not snapshot.price_is_synthetic and snapshot.signal in SIGNALS
    checks.append(Check("data quality", data_ok,
                        f"age {age_h:.2f} h; versions {snapshot.pipeline_version}/{snapshot.scoring_version}; "
                        f"synthetic {snapshot.price_is_synthetic}; signal {snapshot.signal}"))

    # 4. The target the signal asks for.
    base = min(cap, equity)
    if snapshot.signal == "BUY":
        target = base * factors["size"]
        reasons.append(f"BUY: hold {factors['size']:.0%} of {base:.2f} in BTC")
    elif snapshot.signal == "SELL":
        target = 0.0
        reasons.append("SELL: hold everything in cash")
    else:
        target = min(exposure, base)
        reasons.append("HOLD: keep the current position" + (" (trimmed to the cap)" if target < exposure else ""))
    if target > exposure and not data_ok:
        reasons.append("no risk-increasing order on a doubtful hour")
        target = exposure

    delta = target - exposure
    if abs(delta) < 1e-9:
        reasons.append("no change needed")
        return done(target)
    side = "BUY" if delta > 0 else "SELL"
    full_exit = target == 0.0

    # 5. Turnover controls: minimum holding time and a daily trade cap.
    recent = [t for t in portfolio.trade_times if now - t < timedelta(hours=24)]
    turnover_ok = len(recent) < MAX_TRADES_24H
    checks.append(Check("trades in 24 h", turnover_ok, f"{len(recent)} of {MAX_TRADES_24H}"))
    reversal = portfolio.last_trade_side is not None and portfolio.last_trade_side != side
    held_h = None if portfolio.last_trade_at is None else (now - portfolio.last_trade_at).total_seconds() / 3600
    hold_ok = not reversal or held_h is None or held_h >= MIN_HOLD_HOURS
    checks.append(Check("minimum holding time", hold_ok,
                        "no earlier trade" if held_h is None else f"{held_h:.1f} h since the last {portfolio.last_trade_side} "
                        f"(minimum {MIN_HOLD_HOURS} h before a reversal)"))
    if not turnover_ok:
        reasons.append("the daily trade cap is reached")
        return done(target)
    if not hold_ok:
        reasons.append(f"a {side} now would reverse a trade made {held_h:.1f} h ago")
        return done(target)

    # 6. Size bands: a resize must be worth its fee; a full exit or a first entry only needs the venue minimum.
    band = BAND_FRACTION * cap
    resize = not full_exit and exposure > 0
    need = max(band, settings.min_order_value) if resize else settings.min_order_value
    size_ok = abs(delta) >= need
    checks.append(Check("order size", size_ok, f"change {abs(delta):.2f} vs needed {need:.2f}"
                        + (" (resize band)" if resize else " (venue minimum)")))
    if not size_ok:
        reasons.append("the change is too small to be worth an order")
        return done(target)

    # 7. The order, bounded by what the strategy actually holds.
    if side == "BUY":
        amount = min(delta, portfolio.cash)
        if amount < settings.min_order_value:
            reasons.append("not enough strategy cash for a minimum order")
            return done(target)
        return done(target, Order("BUY", quote_amount=amount))
    qty = portfolio.btc if full_exit else min(portfolio.btc, -delta / price)
    return done(target, Order("SELL", base_qty=qty))
