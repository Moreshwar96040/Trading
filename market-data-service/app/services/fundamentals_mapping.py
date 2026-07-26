"""Yahoo → our schema mapping for fundamentals. Pure functions, no yfinance import,
so the fragile parsing logic is unit-testable anywhere.

Yahoo quirks handled here:
- `info` keys are frequently missing → every read is defensive.
- Fractions (dividendYield, returnOnEquity, margins, growth) are converted to percent.
- debtToEquity arrives as a percentage number (e.g. 41.5) → normalized to a ratio.
- Statement line items get renamed across yfinance versions → `_line()` tries variants.
"""
from datetime import date
from typing import Any

import pandas as pd


def _num(info: dict, key: str) -> float | None:
    value = info.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _pct(info: dict, key: str) -> float | None:
    v = _num(info, key)
    return round(v * 100.0, 4) if v is not None else None


def _dividend_yield_pct(info: dict) -> float | None:
    """Dividend yield as a percent, resilient to Yahoo's unit change.

    yfinance used to expose `dividendYield` as a fraction (0.0052) and now
    exposes it already as a percent (0.52). Blindly multiplying by 100 produced
    absurd yields (Bajaj Finance 52%, Infosys 453%). Strategy:
      1. Prefer `trailingAnnualDividendYield` — a fraction in every version.
      2. Else use `dividendYield`, treating it as already-percent (current
         library behaviour); a genuine equity yield above ~100% is impossible,
         so a value >1 is certainly a percent too.
    """
    trailing = _num(info, "trailingAnnualDividendYield")
    if trailing is not None:
        return round(trailing * 100.0, 4)
    raw = _num(info, "dividendYield")
    return round(raw, 4) if raw is not None else None


def map_ratios(info: dict) -> dict[str, Any]:
    """Yahoo `Ticker.info` dict → fundamentals row (all values may be None)."""
    d2e = _num(info, "debtToEquity")
    return {
        "market_cap": _num(info, "marketCap"),
        "pe_trailing": _num(info, "trailingPE"),
        "pe_forward": _num(info, "forwardPE"),
        "pb": _num(info, "priceToBook"),
        "ps": _num(info, "priceToSalesTrailing12Months"),
        "dividend_yield_pct": _dividend_yield_pct(info),
        "roe_pct": _pct(info, "returnOnEquity"),
        "debt_to_equity": round(d2e / 100.0, 4) if d2e is not None else None,
        "profit_margin_pct": _pct(info, "profitMargins"),
        "operating_margin_pct": _pct(info, "operatingMargins"),
        "revenue_growth_pct": _pct(info, "revenueGrowth"),
        "earnings_growth_pct": _pct(info, "earningsGrowth"),
        "eps_trailing": _num(info, "trailingEps"),
        "book_value": _num(info, "bookValue"),
        "beta": _num(info, "beta"),
    }


def _line(df: pd.DataFrame, period, *labels: str) -> float | None:
    """First matching row label for a period column; None if absent/NaN."""
    for label in labels:
        if label in df.index:
            value = df.loc[label, period]
            if value is not None and not pd.isna(value):
                return float(value)
    return None


def map_statements(income: pd.DataFrame | None, balance: pd.DataFrame | None,
                   cashflow: pd.DataFrame | None, period_type: str) -> list[dict]:
    """Yahoo statement frames (rows = line items, columns = period timestamps)
    → list of financial_statements rows."""
    if income is None or income.empty:
        return []

    rows = []
    for period in income.columns:
        period_end: date = pd.Timestamp(period).date()

        def _bal(*labels: str) -> float | None:
            return _line(balance, period, *labels) \
                if balance is not None and period in getattr(balance, "columns", []) else None

        def _cf(*labels: str) -> float | None:
            return _line(cashflow, period, *labels) \
                if cashflow is not None and period in getattr(cashflow, "columns", []) else None

        rows.append({
            "period_end": period_end,
            "period_type": period_type,
            "revenue": _line(income, period, "Total Revenue", "Operating Revenue"),
            "operating_income": _line(income, period, "Operating Income", "EBIT"),
            "net_income": _line(income, period, "Net Income",
                                "Net Income Common Stockholders"),
            "eps": _line(income, period, "Diluted EPS", "Basic EPS"),
            "total_assets": _bal("Total Assets"),
            "total_liabilities": _bal("Total Liabilities Net Minority Interest",
                                      "Total Liabilities"),
            "shareholders_equity": _bal("Stockholders Equity", "Total Equity Gross Minority Interest"),
            "operating_cash_flow": _cf("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
            "free_cash_flow": _cf("Free Cash Flow"),
        })
    return rows
