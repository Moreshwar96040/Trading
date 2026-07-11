"""Performance metrics from an equity curve + trade list. Pure functions."""
import math

import pandas as pd

from app.backtest.engine import Trade

TRADING_DAYS_PER_YEAR = 252


def compute_metrics(equity: pd.Series, trades: list[Trade],
                    initial_capital: float) -> dict:
    if equity.empty:
        return {"total_return_pct": 0.0, "trades": 0}

    final = float(equity.iloc[-1])
    total_return_pct = (final / initial_capital - 1) * 100.0

    n_days = len(equity)
    years = n_days / TRADING_DAYS_PER_YEAR
    cagr_pct = ((final / initial_capital) ** (1 / years) - 1) * 100.0 if years > 0 and final > 0 else None

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown_pct = float(drawdown.min()) * 100.0

    daily_returns = equity.pct_change().dropna()
    sharpe = None
    if len(daily_returns) > 1 and float(daily_returns.std(ddof=1)) > 0:
        sharpe = float(daily_returns.mean() / daily_returns.std(ddof=1)
                       * math.sqrt(TRADING_DAYS_PER_YEAR))

    closed = [t for t in trades if t.pnl is not None]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    return {
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2) if cagr_pct is not None else None,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "trades": len(closed),
        "win_rate_pct": round(len(wins) / len(closed) * 100.0, 2) if closed else None,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "avg_win": round(gross_profit / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "final_equity": round(final, 2),
    }
