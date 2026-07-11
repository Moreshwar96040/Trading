"""Portfolio backtest engine — pure computation, no I/O.

Execution model (deliberately conservative, no lookahead):
- Signals are evaluated on bar T; entries/exits execute at the OPEN of T+1.
- Stop-loss / take-profit are checked intra-bar: a gap through the level fills at
  the open (the worse price), otherwise at the level itself.
- Long-only, one position per symbol, equal-weight sizing: each new position gets
  equity / max_positions, limited by available cash. Commission charged per side.
"""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest.rules import combined_signal
from app.indicators import core


@dataclass
class BacktestParams:
    initial_capital: float = 1_000_000.0
    max_positions: int = 5
    commission_pct: float = 0.05           # per side, in percent
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    max_holding_days: int | None = None    # trading days
    # ---- self-adjusting (ATR-based) stop ----
    atr_stop_mult: float | None = None     # stop = entry - mult*ATR (volatility-scaled)
    atr_trail: bool = False                # ratchet the stop up as price rises
    atr_period: int = 14


@dataclass
class Trade:
    ticker: str
    entry_date: date
    entry_price: float
    quantity: int
    exit_date: date | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    exit_reason: str | None = None


@dataclass
class BacktestResult:
    equity_curve: pd.Series                 # index: date, values: portfolio value
    trades: list[Trade] = field(default_factory=list)


@dataclass
class _Position:
    trade: Trade
    bars_held: int = 0
    exit_pending: bool = False              # signal fired; exit at next open
    trailing_stop: float | None = None      # current ATR stop level (ratchets up)


def run_backtest(data: dict[str, pd.DataFrame], entry_rules: list[dict],
                 exit_rules: list[dict], params: BacktestParams) -> BacktestResult:
    """data: ticker -> OHLCV frame indexed by trade_date (ascending, date index)."""
    entries: dict[str, pd.Series] = {}
    exits: dict[str, pd.Series] = {}
    atr_series: dict[str, pd.Series] = {}
    for ticker, df in data.items():
        entries[ticker] = combined_signal(df, entry_rules)
        exits[ticker] = combined_signal(df, exit_rules) if exit_rules else \
            pd.Series(False, index=df.index)
        if params.atr_stop_mult is not None:
            atr_series[ticker] = core.atr(df["high"].astype(float), df["low"].astype(float),
                                          df["close"].astype(float), params.atr_period)

    all_dates = sorted({d for df in data.values() for d in df.index})
    cash = params.initial_capital
    positions: dict[str, _Position] = {}
    trades: list[Trade] = []
    entry_pending: set[str] = set()
    equity_points: dict[date, float] = {}
    commission = params.commission_pct / 100.0

    for today in all_dates:
        # ---- 1. exits at today's open (signal / max-days queued yesterday) ----
        for ticker in list(positions):
            df = data[ticker]
            if today not in df.index:
                continue
            pos = positions[ticker]
            bar = df.loc[today]
            open_px = float(bar["open"])

            exit_px = None
            reason = None
            if pos.exit_pending:
                exit_px, reason = open_px, pos.trade.exit_reason or "SIGNAL"
            else:
                entry_px = pos.trade.entry_price
                if pos.trailing_stop is not None:
                    stop = pos.trailing_stop
                    if open_px <= stop:
                        exit_px, reason = open_px, "ATR_STOP"        # gapped through
                    elif float(bar["low"]) <= stop:
                        exit_px, reason = stop, "ATR_STOP"
                if exit_px is None and params.stop_loss_pct is not None:
                    stop = entry_px * (1 - params.stop_loss_pct / 100.0)
                    if open_px <= stop:
                        exit_px, reason = open_px, "STOP_LOSS"      # gapped through
                    elif float(bar["low"]) <= stop:
                        exit_px, reason = stop, "STOP_LOSS"
                if exit_px is None and params.take_profit_pct is not None:
                    target = entry_px * (1 + params.take_profit_pct / 100.0)
                    if open_px >= target:
                        exit_px, reason = open_px, "TAKE_PROFIT"    # gapped through
                    elif float(bar["high"]) >= target:
                        exit_px, reason = target, "TAKE_PROFIT"

            if exit_px is not None:
                cash += _close_position(pos.trade, today, exit_px, reason, commission)
                trades.append(pos.trade)
                del positions[ticker]

        # ---- 2. entries at today's open (signal fired yesterday) ----
        for ticker in sorted(entry_pending):
            df = data[ticker]
            if today not in df.index or ticker in positions:
                continue
            if len(positions) >= params.max_positions:
                break
            open_px = float(df.loc[today, "open"])
            equity_now = cash + _positions_value_at_open(positions, data, today)
            allocation = min(cash, equity_now / params.max_positions)
            quantity = int(allocation / (open_px * (1 + commission)))
            if quantity < 1:
                continue
            cost = quantity * open_px * (1 + commission)
            cash -= cost
            trade = Trade(ticker=ticker, entry_date=today, entry_price=open_px,
                          quantity=quantity)
            pos = _Position(trade=trade)
            if params.atr_stop_mult is not None:
                atr_now = float(atr_series[ticker].loc[today])
                if not pd.isna(atr_now):
                    pos.trailing_stop = open_px - params.atr_stop_mult * atr_now
            positions[ticker] = pos
        entry_pending.clear()

        # ---- 3. evaluate today's signals -> queue for tomorrow ----
        for ticker, df in data.items():
            if today not in df.index:
                continue
            if ticker in positions:
                pos = positions[ticker]
                pos.bars_held += 1
                if (params.atr_trail and params.atr_stop_mult is not None
                        and pos.trailing_stop is not None):
                    atr_today = float(atr_series[ticker].loc[today])
                    if not pd.isna(atr_today):
                        raised = float(df.loc[today, "close"]) - params.atr_stop_mult * atr_today
                        pos.trailing_stop = max(pos.trailing_stop, raised)   # ratchet only
                if not pos.exit_pending:
                    if bool(exits[ticker].loc[today]):
                        pos.exit_pending = True
                        pos.trade.exit_reason = "SIGNAL"
                    elif (params.max_holding_days is not None
                          and pos.bars_held >= params.max_holding_days):
                        pos.exit_pending = True
                        pos.trade.exit_reason = "MAX_DAYS"
            elif bool(entries[ticker].loc[today]):
                entry_pending.add(ticker)

        # ---- 4. mark to market at close ----
        value = cash
        for ticker, pos in positions.items():
            df = data[ticker]
            px_dates = df.index[df.index <= today]
            if len(px_dates):
                value += pos.trade.quantity * float(df.loc[px_dates[-1], "close"])
        equity_points[today] = value

    # ---- close remaining positions at the last available close ----
    for ticker, pos in positions.items():
        df = data[ticker]
        last_date = df.index[-1]
        cash += _close_position(pos.trade, last_date, float(df.loc[last_date, "close"]),
                                "END_OF_DATA", commission)
        trades.append(pos.trade)
    if all_dates:
        equity_points[all_dates[-1]] = cash

    curve = pd.Series(equity_points).sort_index()
    return BacktestResult(equity_curve=curve, trades=trades)


def _close_position(trade: Trade, when: date, price: float, reason: str | None,
                    commission: float) -> float:
    proceeds = trade.quantity * price * (1 - commission)
    cost = trade.quantity * trade.entry_price * (1 + commission)
    trade.exit_date = when
    trade.exit_price = price
    trade.exit_reason = reason
    trade.pnl = round(proceeds - cost, 2)
    trade.pnl_pct = round((proceeds / cost - 1) * 100.0, 4)
    return proceeds


def _positions_value_at_open(positions: dict[str, "_Position"],
                             data: dict[str, pd.DataFrame], today: date) -> float:
    total = 0.0
    for ticker, pos in positions.items():
        df = data[ticker]
        px_dates = df.index[df.index <= today]
        if len(px_dates):
            total += pos.trade.quantity * float(df.loc[px_dates[-1], "close"])
    return total
