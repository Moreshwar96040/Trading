"""Mapping tests — no yfinance/DB needed (pure functions)."""
import pandas as pd

from app.services.fundamentals_mapping import map_ratios, map_statements

INFO = {
    "marketCap": 2_000_000_000_000,
    "trailingPE": 25.5,
    "forwardPE": 22.1,
    "priceToBook": 3.2,
    "priceToSalesTrailing12Months": 2.4,
    "dividendYield": 0.0125,          # fraction → 1.25 %
    "returnOnEquity": 0.181,          # fraction → 18.1 %
    "debtToEquity": 41.5,             # percent number → 0.415 ratio
    "profitMargins": 0.09,
    "operatingMargins": 0.15,
    "revenueGrowth": 0.12,
    "earningsGrowth": -0.05,
    "trailingEps": 98.7,
    "bookValue": 1450.2,
    "beta": 1.1,
}


def test_map_ratios_happy_path():
    row = map_ratios(INFO)
    assert row["market_cap"] == 2_000_000_000_000
    assert row["dividend_yield_pct"] == 1.25
    assert row["roe_pct"] == 18.1
    assert row["debt_to_equity"] == 0.415
    assert row["earnings_growth_pct"] == -5.0
    assert row["beta"] == 1.1


def test_map_ratios_missing_and_garbage_keys():
    row = map_ratios({"trailingPE": "not-a-number", "marketCap": None,
                      "dividendYield": float("nan")})
    assert row["pe_trailing"] is None
    assert row["market_cap"] is None
    assert row["dividend_yield_pct"] is None
    assert row["roe_pct"] is None                     # absent key


def test_map_ratios_empty_info():
    row = map_ratios({})
    assert all(v is None for v in row.values())


def _income(periods, revenue, net_income):
    return pd.DataFrame([revenue, net_income],
                        index=["Total Revenue", "Net Income"],
                        columns=[pd.Timestamp(p) for p in periods])


def test_map_statements_basic():
    income = _income(["2025-03-31", "2024-03-31"], [1000.0, 900.0], [100.0, 80.0])
    rows = map_statements(income, None, None, "ANNUAL")

    assert len(rows) == 2
    assert rows[0]["period_type"] == "ANNUAL"
    assert rows[0]["revenue"] == 1000.0
    assert rows[0]["net_income"] == 100.0
    assert rows[0]["total_assets"] is None            # no balance sheet provided


def test_map_statements_label_variants():
    income = pd.DataFrame([[500.0]], index=["Operating Revenue"],
                          columns=[pd.Timestamp("2025-03-31")])
    rows = map_statements(income, None, None, "QUARTERLY")
    assert rows[0]["revenue"] == 500.0                # fallback label matched


def test_map_statements_empty():
    assert map_statements(None, None, None, "ANNUAL") == []
    assert map_statements(pd.DataFrame(), None, None, "ANNUAL") == []


def test_map_statements_balance_and_cashflow():
    period = pd.Timestamp("2025-03-31")
    income = _income(["2025-03-31"], [1000.0], [100.0])
    balance = pd.DataFrame([[5000.0], [3000.0], [2000.0]],
                           index=["Total Assets", "Total Liabilities Net Minority Interest",
                                  "Stockholders Equity"], columns=[period])
    cashflow = pd.DataFrame([[150.0], [120.0]],
                            index=["Operating Cash Flow", "Free Cash Flow"], columns=[period])

    row = map_statements(income, balance, cashflow, "ANNUAL")[0]
    assert row["total_assets"] == 5000.0
    assert row["shareholders_equity"] == 2000.0
    assert row["free_cash_flow"] == 120.0
