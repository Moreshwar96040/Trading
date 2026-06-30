"""
NSE Trade-Price Dataset Loader
==============================

20 NSE stocks (one per sector), daily OHLCV for 2024-06-30 -> 2026-06-30.
Source: Yahoo Finance historical chart API (currency: INR).

Split (pre-labelled in the "Split" column):
    train -> 2024-06-30 .. 2025-12-31   (~1.5 years)
    test  -> 2026-01-01 .. 2026-06-30   (~0.5 years)

Usage:
    from load_data import load_stock, load_all, train_test, features
    df = load_stock("RELIANCE")          # one stock, full history
    tr, te = train_test("RELIANCE")      # train/test frames for one stock
    alldf = load_all()                   # every stock stacked (long format)

Requires: pandas  (pip install pandas)
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

TICKERS = ["RELIANCE","TCS","HDFCBANK","SUNPHARMA","MARUTI","HINDUNILVR",
    "TATASTEEL","BHARTIARTL","LT","ULTRACEMCO","ASIANPAINT","NTPC",
    "TITAN","DMART","BAJFINANCE","COALINDIA","INDIGO","ADANIPORTS",
    "UPL","APOLLOHOSP"]


def load_stock(ticker):
    path = os.path.join(HERE, f"{ticker.upper().replace('.NS','')}.csv")
    df = pd.read_csv(path, parse_dates=["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def train_test(ticker):
    df = load_stock(ticker)
    tr = df[df["Split"] == "train"].reset_index(drop=True)
    te = df[df["Split"] == "test"].reset_index(drop=True)
    return tr, te


def load_all():
    path = os.path.join(HERE, "ALL_STOCKS_combined.csv")
    df = pd.read_csv(path, parse_dates=["Date"])
    return df.sort_values(["Ticker", "Date"]).reset_index(drop=True)


def features(df):
    """Example feature engineering; Target_NextClose is what a model predicts."""
    df = df.copy()
    df["Return"] = df["Close"].pct_change()
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["Vol20"] = df["Return"].rolling(20).std()
    df["Target_NextClose"] = df["Close"].shift(-1)
    return df


if __name__ == "__main__":
    print(f"{'Ticker':12s} {'rows':>5s} {'train':>6s} {'test':>5s}  date range")
    for t in TICKERS:
        df = load_stock(t)
        tr = (df["Split"] == "train").sum()
        te = (df["Split"] == "test").sum()
        print(f"{t:12s} {len(df):5d} {tr:6d} {te:5d}  {df['Date'].min().date()} -> {df['Date'].max().date()}")
