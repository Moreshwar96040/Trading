# NSE Self-Learning Trade-Price Predictor

Predicts the **next-day price** and **trend direction** for 20 NSE stocks
(one per sector) using a self-learning, auto-tuning gradient-boosting model.

## What it does
- **Predicts next-day return**, then reconstructs the price (`price x exp(return)`).
  Modelling returns instead of raw price avoids the random-walk trap.
- **One panel model** over all 20 stocks (with a ticker feature) — more data,
  cross-stock learning, than 20 tiny models.
- **Self-learning (walk-forward):** expands the training window through time and
  retrains at each step, continuously absorbing new outcomes — i.e. it "goes
  back through history and re-tunes on the results".
- **Auto-tuning:** Optuna searches hyper-parameters using time-series splits
  (no look-ahead leakage).
- **Engine auto-detect:** LightGBM if installed -> else scikit-learn
  HistGradientBoosting -> else a built-in numpy model. Always runnable.

## Files
- `trade_model.py`  — trains, autotunes, walk-forward backtests, saves the model.
- `predict_next.py` — loads the saved model, prints next-day price + trend.
- `features.py`     — technical-indicator feature engineering (no leakage).
- `_fallback.py`    — pure-numpy engine used only if nothing else is installed.
- `nse_dataset/`    — the data (per-stock CSVs + combined file).
- `requirements.txt`— full stack for best results.

## Setup (on your computer)
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Open a terminal (PowerShell) in this folder and run:
   ```
   pip install -r requirements.txt
   ```
   (Minimal install — lower accuracy but zero heavy deps: `pip install -r requirements-minimal.txt`)

## Run
```
python trade_model.py                 # train + backtest (default)
python trade_model.py --trials 40     # deeper autotuning -> better accuracy (slower)
python trade_model.py --retune-each-fold   # re-tune at every walk-forward step
python predict_next.py                # next-day forecast for all stocks
python predict_next.py RELIANCE       # one stock
```
Results print to screen and save to `artifacts/`:
`metrics.csv` (per-stock accuracy), `oos_predictions.csv`, `model.joblib`.

## How to read the metrics
- **DirAcc%** — directional (up/down) accuracy. 50% = coin flip. Anything
  consistently above ~52-53% out-of-sample is meaningful for daily equities.
- **MAPE%** — average price error (typically ~1%).
- **Strat_Sharpe vs BuyHold_Sharpe** — risk-adjusted return of a simple
  "long when predicted up" rule vs just holding the stock.

## Updating with new data
Re-download fresh prices into `nse_dataset/` (Yahoo Finance), then re-run
`trade_model.py`. The walk-forward design means it re-learns automatically.

## Important
This is a research/education tool, **not financial advice**. Daily price
prediction is inherently hard; treat signals as probabilistic, never certain.
