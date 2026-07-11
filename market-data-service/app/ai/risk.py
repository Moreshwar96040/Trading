"""Self-adjusting risk recommendations: volatility- and regime-aware stop-loss and
profit-booking levels. Pure pandas — no sklearn, no DB, fully unit-testable.

The idea (R4): a fixed 5% stop is wrong in both a calm blue-chip and a wild small-cap.
We scale the stop to recent volatility (ATR) and adapt the tactics to the market
*regime* the stock is currently in:

    strong uptrend  -> give the trade room, trail the stop, let profits run
    weak / choppy   -> tighten the stop, book profit at a fixed reward multiple

Every number is a suggestion with a plain-language rationale — never auto-executed
against real money.
"""
from dataclasses import asdict, dataclass

import pandas as pd

from app.indicators import core

MIN_ROWS = 60


@dataclass(frozen=True)
class RiskRecommendation:
    as_of_price: float
    atr: float
    atr_pct: float                 # ATR as % of price — the volatility read
    regime: str                    # STRONG_UPTREND | UPTREND | NEUTRAL | DOWNTREND
    stop_price: float
    stop_pct: float                # distance from price to stop, %
    atr_stop_mult: float           # the multiplier we chose
    trail: bool                    # should the stop ratchet up?
    take_profit_price: float | None
    take_profit_pct: float | None  # None => "let it run" (trail instead)
    reward_risk: float | None
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


class InsufficientDataError(ValueError):
    pass


def _classify_regime(close: pd.Series) -> str:
    price = float(close.iloc[-1])
    sma50 = float(core.sma(close, 50).iloc[-1])
    sma200 = float(core.sma(close, 200).iloc[-1]) if len(close) >= 200 else sma50
    rising_50 = sma50 > float(core.sma(close, 50).iloc[-11])   # 50-SMA higher than 10 bars ago

    if price > sma50 > sma200 and rising_50:
        return "STRONG_UPTREND"
    if price > sma200:
        return "UPTREND"
    if price < sma50 and sma50 < sma200:
        return "DOWNTREND"
    return "NEUTRAL"


def recommend_risk(df: pd.DataFrame, entry_price: float | None = None,
                   atr_period: int = 14) -> RiskRecommendation:
    """df: OHLCV ascending (needs the same columns the engine uses). `entry_price`
    defaults to the latest close (evaluating an existing/at-market long)."""
    if len(df) < MIN_ROWS:
        raise InsufficientDataError(f"Need >= {MIN_ROWS} rows, have {len(df)}")

    high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    price = float(entry_price) if entry_price else float(close.iloc[-1])
    atr = float(core.atr(high, low, close, atr_period).iloc[-1])
    atr_pct = atr / price * 100.0 if price else 0.0
    regime = _classify_regime(close)

    # Volatility-scaled stop multiplier, then nudged by regime.
    if regime == "STRONG_UPTREND":
        mult, trail, tp_mult = 3.0, True, None          # let it run, trail the stop
    elif regime == "UPTREND":
        mult, trail, tp_mult = 2.5, True, 3.0
    elif regime == "DOWNTREND":
        mult, trail, tp_mult = 1.5, False, 1.5          # tight — counter-trend is risky
    else:                                                # NEUTRAL / choppy
        mult, trail, tp_mult = 2.0, False, 2.0

    stop_price = round(price - mult * atr, 2)
    risk_per_share = price - stop_price
    stop_pct = round(risk_per_share / price * 100.0, 2) if price else 0.0

    if tp_mult is None:
        take_profit_price = take_profit_pct = reward_risk = None
        booking = "let profits run behind a trailing stop"
    else:
        take_profit_price = round(price + tp_mult * risk_per_share, 2)
        take_profit_pct = round((take_profit_price / price - 1) * 100.0, 2)
        reward_risk = round(tp_mult, 2)
        booking = f"book profit at {tp_mult:.1f}R (₹{take_profit_price})"

    rationale = (
        f"{regime.replace('_', ' ').title()} regime; volatility (ATR) is "
        f"{atr_pct:.1f}% of price. Stop set {mult:.1f}×ATR below "
        f"(≈{stop_pct:.1f}%){' and trailing up' if trail else ''}; {booking}."
    )

    return RiskRecommendation(
        as_of_price=round(price, 2), atr=round(atr, 4), atr_pct=round(atr_pct, 2),
        regime=regime, stop_price=stop_price, stop_pct=stop_pct, atr_stop_mult=mult,
        trail=trail, take_profit_price=take_profit_price, take_profit_pct=take_profit_pct,
        reward_risk=reward_risk, rationale=rationale)
