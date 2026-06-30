# NSE Stock Dataset — 20 Sectors (Daily, 2 Years)

**Source:** Yahoo Finance historical chart API (verified market data, currency INR).
**Period:** 2024-06-30 to 2026-06-30 (daily OHLCV, ~498 trading days/stock).
**Split (in the `Split` column):**
- `train` — 2024-06-30 → 2025-12-31  (~1.5 years, 375 rows/stock)
- `test`  — 2026-01-01 → 2026-06-30  (~0.5 year, ~123 rows/stock)

## Files
- `<TICKER>.csv` — one file per stock. Columns: Date, Open, High, Low, Close, AdjClose, Volume, Split.
- `ALL_STOCKS_combined.csv` — all 20 stacked (long format) with Ticker, Name, Sector columns. 9,956 rows.
- `load_data.py` — helper: `load_stock()`, `train_test()`, `load_all()`, `features()`.

## The 20 stocks (one per sector)
RELIANCE (Oil&Gas), TCS (IT), HDFCBANK (Banking), SUNPHARMA (Pharma), MARUTI (Auto),
HINDUNILVR (FMCG), TATASTEEL (Steel), BHARTIARTL (Telecom), LT (Construction),
ULTRACEMCO (Cement), ASIANPAINT (Paints), NTPC (Power), TITAN (Jewellery/Retail),
DMART (Retail), BAJFINANCE (NBFC), COALINDIA (Mining), INDIGO (Aviation),
ADANIPORTS (Logistics), UPL (Agrochem), APOLLOHOSP (Healthcare).

## Quick start
```python
from load_data import train_test, features
tr, te = train_test("RELIANCE")
tr = features(tr).dropna()   # adds Return, MA5, MA20, Vol20, Target_NextClose
```
Use `AdjClose` for return-based modelling; `Target_NextClose` is the value to predict.
