"""
Predict the NEXT trading day's price and trend for every stock,
using the model saved by trade_model.py.

    python predict_next.py            # all stocks
    python predict_next.py RELIANCE   # one stock
"""
import os
import sys
import warnings
warnings.filterwarnings('ignore')
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

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts")


def main():
    bundle = joblib.load(os.path.join(ART, "model.joblib"))
    model, feats = bundle["model"], bundle["features"]
    latest = pd.read_csv(os.path.join(ART, "latest_rows.csv"), parse_dates=["Date"])

    only = sys.argv[1].upper() + ".NS" if len(sys.argv) > 1 else None
    if only:
        latest = latest[latest["Ticker"] == only]

    rows = []
    for _, r in latest.iterrows():
        X = r[feats].values.reshape(1, -1).astype(float)
        pred_ret = float(model.predict(X)[0])
        last_price = r["price"]
        next_price = last_price * np.exp(pred_ret)
        trend = "UP ^" if pred_ret > 0.0015 else ("DOWN v" if pred_ret < -0.0015 else "FLAT -")
        rows.append([r["Ticker"].replace(".NS", ""),
                     r["Date"].date(), round(last_price, 2),
                     round(next_price, 2), round(pred_ret * 100, 2), trend])

    df = pd.DataFrame(rows, columns=[
        "Ticker", "AsOf", "LastClose", "PredNextClose", "PredMove%", "Trend"])
    df = df.sort_values("PredMove%", ascending=False).reset_index(drop=True)
    print("=" * 60)
    print("NEXT-DAY FORECAST  (model = self-learning gradient boosting)")
    print("=" * 60)
    print(df.to_string(index=False))
    print("\nNote: PredMove% is the modelled next-day return. Trends are")
    print("directional signals, not financial advice.")


if __name__ == "__main__":
    main()
