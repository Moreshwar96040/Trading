"""Show the model's accuracy from the last training run."""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
f = os.path.join(HERE, "artifacts", "metrics.csv")

if not os.path.exists(f):
    print("No metrics found. Run START_HERE.bat (or 'python trade_model.py') first.")
    raise SystemExit

m = pd.read_csv(f).sort_values("DirAcc%", ascending=False)
print("=" * 64)
print("MODEL ACCURACY  (out-of-sample, per stock)")
print("=" * 64)
print(m.to_string(index=False))
print("-" * 64)
avg = m["DirAcc%"].mean()
above = (m["DirAcc%"] > 50).sum()
beat = (m["Strat_Sharpe"] > m["BuyHold_Sharpe"]).sum()
print(f"AVERAGE directional accuracy : {avg:.1f}%   (50% = coin flip)")
print(f"Stocks above 50%             : {above}/20")
print(f"Strategy beats buy & hold    : {beat}/20")
verdict = ("STRONG signal" if avg >= 54 else
           "real but modest signal" if avg >= 52 else
           "weak / near random - needs more tuning" if avg >= 50 else
           "below random - retune or add features")
print(f"Verdict                      : {verdict}")
print("=" * 64)
