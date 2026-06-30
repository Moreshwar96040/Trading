"""
==========================================================================
 NSE Self-Learning Trade-Price Predictor
==========================================================================
Predicts the NEXT-DAY price and trend direction for 20 NSE stocks.

Design choices (the "why"):
  * Target is next-day LOG RETURN, not raw price. Predicting raw price is a
    near-random-walk trap; modelling returns is the correct framing and the
    price is reconstructed as  price_t * exp(pred_return).
  * One PANEL model over all 20 stocks (with a ticker feature) -> ~7.5k rows
    instead of 20 tiny models. More data, cross-stock learning.
  * Engine: LightGBM if installed, else scikit-learn HistGradientBoosting
    (built in, no extra install). Gradient-boosted trees beat deep nets on
    this little data.
  * SELF-LEARNING = WALK-FORWARD: we expand the training window through time,
    retraining at every step so the model continuously absorbs new outcomes,
    exactly like "going back in history and re-tuning on the results".
  * AUTOTUNE: Optuna searches hyper-parameters with a time-series split
    (no future leakage). Falls back to a built-in random search if Optuna
    is missing.

Run:
    python trade_model.py                 # full pipeline, default settings
    python trade_model.py --trials 40     # deeper autotuning (slower, better)
    python trade_model.py --retune-each-fold   # re-tune every walk-forward step
==========================================================================
"""
import os
import sys
import time
import argparse
import warnings
import numpy as np
import pandas as pd
try:
    import joblib
except Exception:
    import pickle as _pk
    class _JL:
        @staticmethod
        def dump(obj, path): _pk.dump(obj, open(path,"wb"))
        @staticmethod
        def load(path): return _pk.load(open(path,"rb"))
    joblib = _JL()

warnings.filterwarnings("ignore")
from features import build_panel, FEATURE_COLS

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "nse_dataset", "ALL_STOCKS_combined.csv")
ART = os.path.join(HERE, "artifacts")
os.makedirs(ART, exist_ok=True)

# ---- engine detection ---------------------------------------------------
try:
    import lightgbm as lgb
    HAVE_LGB = True
except Exception:
    HAVE_LGB = False
try:
    from sklearn.ensemble import HistGradientBoostingRegressor
    HAVE_SK = True
except Exception:
    HAVE_SK = False
from _fallback import NumpyGBR

def mean_absolute_error(y, p):
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))

def mean_squared_error(y, p):
    return float(np.mean((np.asarray(y) - np.asarray(p)) ** 2))

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAVE_OPTUNA = True
except Exception:
    HAVE_OPTUNA = False


def make_regressor(params):
    """Build a regressor from a param dict, using the best available engine."""
    if HAVE_LGB:
        p = dict(objective="regression", n_estimators=params.get("n_estimators", 400),
                 learning_rate=params.get("learning_rate", 0.03),
                 num_leaves=params.get("num_leaves", 31),
                 max_depth=params.get("max_depth", -1),
                 min_child_samples=params.get("min_child_samples", 30),
                 subsample=params.get("subsample", 0.8),
                 colsample_bytree=params.get("colsample_bytree", 0.8),
                 reg_lambda=params.get("reg_lambda", 1.0),
                 verbosity=-1, n_jobs=-1)
        return lgb.LGBMRegressor(**p)
    if HAVE_SK:
        return HistGradientBoostingRegressor(
            learning_rate=params.get("learning_rate", 0.05),
            max_iter=params.get("n_estimators", 400),
            max_leaf_nodes=params.get("num_leaves", 31),
            min_samples_leaf=params.get("min_child_samples", 30),
            l2_regularization=params.get("reg_lambda", 1.0),
            max_depth=None if params.get("max_depth", -1) in (-1, None) else params["max_depth"],
            early_stopping=False)
    return NumpyGBR(n_estimators=min(params.get("n_estimators", 400), int(os.environ.get("NPGBR_CAP","150"))),
                    learning_rate=params.get("learning_rate", 0.05),
                    max_depth=3)


def param_space(trial):
    return dict(
        n_estimators=trial.suggest_int("n_estimators", 200, 800, step=100),
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        num_leaves=trial.suggest_int("num_leaves", 15, 63),
        min_child_samples=trial.suggest_int("min_child_samples", 10, 60),
        subsample=trial.suggest_float("subsample", 0.6, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
        reg_lambda=trial.suggest_float("reg_lambda", 0.0, 5.0),
    )


def _ts_splits(n, n_splits=3):
    """Expanding-window indices (numpy; no sklearn needed)."""
    fold = n // (n_splits + 1)
    for i in range(1, n_splits + 1):
        tr_end = fold * i
        va_end = fold * (i + 1) if i < n_splits else n
        yield np.arange(0, tr_end), np.arange(tr_end, va_end)

def time_series_score(X, y, params, n_splits=3):
    """Average MAE over expanding time-series folds (lower is better)."""
    errs = []
    for tr, va in _ts_splits(len(X), n_splits):
        if len(tr) < 50 or len(va) < 10:
            continue
        m = make_regressor(params)
        m.fit(X[tr], y[tr])
        errs.append(mean_absolute_error(y[va], m.predict(X[va])))
    return float(np.mean(errs)) if errs else 1e9


def autotune(X, y, n_trials):
    """Return best hyper-parameters via Optuna, or random search fallback."""
    if HAVE_OPTUNA and n_trials > 0:
        study = optuna.create_study(direction="minimize")
        t0 = time.time()
        def _cb(study, trial):
            print(f"      tuning trial {trial.number + 1}/{n_trials}  "
                  f"best MAE={study.best_value:.5f}  ({time.time()-t0:.0f}s)",
                  flush=True)
        study.optimize(lambda t: time_series_score(X, y, param_space(t)),
                       n_trials=n_trials, callbacks=[_cb], show_progress_bar=False)
        return study.best_params
    # ---- fallback: simple random search ----
    rng = np.random.default_rng(7)
    best, best_p = 1e9, None
    n = max(1, n_trials)
    for i in range(n):
        p = dict(n_estimators=int(rng.choice([200, 300, 400, 600])),
                 learning_rate=float(rng.choice([0.02, 0.03, 0.05, 0.08])),
                 num_leaves=int(rng.integers(15, 63)),
                 min_child_samples=int(rng.integers(10, 60)),
                 subsample=float(rng.uniform(0.6, 1.0)),
                 colsample_bytree=float(rng.uniform(0.6, 1.0)),
                 reg_lambda=float(rng.uniform(0, 5)))
        sc = time_series_score(X, y, p)
        if sc < best:
            best, best_p = sc, p
        print(f"      tuning trial {i+1}/{n}  best MAE={best:.5f}", flush=True)
    return best_p


def walk_forward(panel, n_folds=6, trials=20, retune_each=False):
    """
    Expanding-window walk-forward. At each fold we (optionally) re-tune,
    retrain on everything up to the fold start, then predict the next block.
    Returns a dataframe of out-of-sample predictions.
    """
    df = panel.dropna(subset=FEATURE_COLS + ["target_ret"]).copy()
    df = df.sort_values("Date").reset_index(drop=True)
    dates = np.sort(df["Date"].unique())
    # fold boundaries over the last ~40% of the timeline
    start_idx = int(len(dates) * 0.55)
    bounds = np.linspace(start_idx, len(dates) - 1, n_folds + 1).astype(int)

    preds = []
    best_params = None
    for i in range(n_folds):
        d_lo, d_hi = dates[bounds[i]], dates[bounds[i + 1]]
        train = df[df["Date"] < d_lo]
        test = df[(df["Date"] >= d_lo) & (df["Date"] <= d_hi)]
        if len(test) == 0 or len(train) < 200:
            continue
        Xtr = train[FEATURE_COLS].values
        ytr = train["target_ret"].values
        if best_params is None or retune_each:
            print(f"    [fold {i+1}] auto-tuning on {len(Xtr)} rows ...", flush=True)
            best_params = autotune(Xtr, ytr, trials)
        print(f"    [fold {i+1}] training final model ...", flush=True)
        model = make_regressor(best_params)
        model.fit(Xtr, ytr)
        t = test.copy()
        t["pred_ret"] = model.predict(test[FEATURE_COLS].values)
        preds.append(t)
        print(f"  fold {i+1}/{n_folds}: train={len(train):5d}  test={len(test):4d}"
              f"  [{pd.Timestamp(d_lo).date()} -> {pd.Timestamp(d_hi).date()}]")
    out = pd.concat(preds, ignore_index=True)
    out["pred_price"] = out["price"] * np.exp(out["pred_ret"])
    out["true_price"] = out["price"] * np.exp(out["target_ret"])
    return out, best_params


def evaluate(out):
    rows = []
    for tic, g in out.groupby("Ticker"):
        dir_acc = (np.sign(g["pred_ret"]) == np.sign(g["target_ret"])).mean()
        mae_p = mean_absolute_error(g["true_price"], g["pred_price"])
        mape = (np.abs(g["true_price"] - g["pred_price"]) / g["true_price"]).mean() * 100
        # simple long/flat strategy: be in the market when we predict up
        strat = (g["pred_ret"] > 0).astype(int) * g["target_ret"]
        bh = g["target_ret"]
        sharpe = strat.mean() / (strat.std() + 1e-9) * np.sqrt(252)
        bh_sharpe = bh.mean() / (bh.std() + 1e-9) * np.sqrt(252)
        rows.append([tic, len(g), round(dir_acc * 100, 1), round(mape, 2),
                     round(mae_p, 2), round(sharpe, 2), round(bh_sharpe, 2)])
    res = pd.DataFrame(rows, columns=[
        "Ticker", "N", "DirAcc%", "MAPE%", "MAE_price", "Strat_Sharpe", "BuyHold_Sharpe"])
    return res.sort_values("DirAcc%", ascending=False).reset_index(drop=True)


def fit_final_and_save(panel, params):
    """Fit on ALL available history and save artifacts for live prediction."""
    df = panel.dropna(subset=FEATURE_COLS + ["target_ret"])
    model = make_regressor(params)
    model.fit(df[FEATURE_COLS].values, df["target_ret"].values)
    joblib.dump({"model": model, "features": FEATURE_COLS, "params": params,
                 "engine": "lightgbm" if HAVE_LGB else ("sklearn-histgb" if HAVE_SK else "numpy-gbr")},
                os.path.join(ART, "model.joblib"))
    # save latest feature row per ticker so predict_next can run instantly
    latest = (panel.sort_values("Date").groupby("Ticker").tail(1))
    latest.to_csv(os.path.join(ART, "latest_rows.csv"), index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--retune-each-fold", action="store_true")
    args = ap.parse_args()

    print("=" * 64)
    print("Engine :", "LightGBM" if HAVE_LGB else ("scikit-learn HistGradientBoosting" if HAVE_SK else "numpy fallback GBR (install requirements for full power)"))
    print("Tuner  :", "Optuna" if HAVE_OPTUNA else "random-search fallback")
    print("=" * 64)
    t_start = time.time()
    print("Building features ...", flush=True)
    panel = build_panel(DATA)
    print(f"Panel: {len(panel)} rows, {panel['Ticker'].nunique()} tickers, "
          f"{len(FEATURE_COLS)} features\n")

    print("Walk-forward (self-learning, expanding window):")
    out, best = walk_forward(panel, args.folds, args.trials, args.retune_each_fold)
    print("\nBest hyper-parameters:", best)

    res = evaluate(out)
    print("\n" + "=" * 64)
    print("OUT-OF-SAMPLE RESULTS (per stock)")
    print("=" * 64)
    print(res.to_string(index=False))
    print("-" * 64)
    print(f"AVG directional accuracy: {res['DirAcc%'].mean():.1f}%   "
          f"(50% = coin flip)")
    print(f"Strategy beats buy&hold Sharpe on "
          f"{(res['Strat_Sharpe'] > res['BuyHold_Sharpe']).sum()}/{len(res)} stocks")

    out.to_csv(os.path.join(ART, "oos_predictions.csv"), index=False)
    res.to_csv(os.path.join(ART, "metrics.csv"), index=False)
    print("\nFitting final model on full history & saving artifacts ...")
    fit_final_and_save(panel, best)
    print("Saved -> artifacts/  (model.joblib, metrics.csv, oos_predictions.csv)")
    print("Next:  python predict_next.py")


if __name__ == "__main__":
    main()
