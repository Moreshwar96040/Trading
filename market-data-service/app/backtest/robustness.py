"""Overfitting guard: how much should you trust a backtest?

Three independent checks, combined into a 0-100 robustness score:

1. Monte Carlo bootstrap — resample the trade sequence many times. The single
   equity curve a backtest shows is one draw from a distribution; the p5..p95
   spread of that distribution is what you might actually experience.
2. Holdout consistency — the caller re-runs the strategy on an out-of-sample
   slice the "full" run also covered, and we compare. A real edge survives on
   data it wasn't (mentally) tuned on; an overfit one collapses.
3. Sample size — 8 trades tell you nothing. Confidence scales with trade count.

Pure functions, no I/O — unit-testable in isolation.
"""
import random
from dataclasses import dataclass

N_RESAMPLES = 500


def monte_carlo(trade_returns_pct: list[float], n_resamples: int = N_RESAMPLES,
                seed: int = 7) -> dict | None:
    """Bootstrap the per-trade %-returns into `n_resamples` alternate histories.

    Returns percentiles of compounded total return and of max drawdown, plus the
    probability of ending in a loss. None when there are no closed trades.
    Compounding trade returns sequentially approximates a one-position-at-a-time
    account; good enough to show the *spread*, which is the point.
    """
    if not trade_returns_pct:
        return None
    rng = random.Random(seed)
    n = len(trade_returns_pct)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(n_resamples):
        equity, peak, max_dd = 1.0, 1.0, 0.0
        for _ in range(n):
            r = trade_returns_pct[rng.randrange(n)] / 100.0
            equity *= (1.0 + r)
            peak = max(peak, equity)
            max_dd = max(max_dd, 1.0 - equity / peak)
        finals.append((equity - 1.0) * 100.0)
        drawdowns.append(-max_dd * 100.0)

    finals.sort()
    drawdowns.sort()

    def pct(sorted_vals: list[float], q: float) -> float:
        idx = min(int(q * len(sorted_vals)), len(sorted_vals) - 1)
        return round(sorted_vals[idx], 2)

    return {
        "resamples": n_resamples,
        "return_p5": pct(finals, 0.05), "return_p25": pct(finals, 0.25),
        "return_p50": pct(finals, 0.50), "return_p75": pct(finals, 0.75),
        "return_p95": pct(finals, 0.95),
        "drawdown_p50": pct(drawdowns, 0.50),
        "drawdown_p95": pct(drawdowns, 0.05),   # 5th pct of negatives = worst tail
        "prob_loss_pct": round(sum(1 for f in finals if f < 0) / len(finals) * 100, 1),
        # 20-bucket histogram for the UI
        "histogram": _histogram(finals, buckets=20),
    }


def _histogram(sorted_vals: list[float], buckets: int) -> dict:
    lo, hi = sorted_vals[0], sorted_vals[-1]
    if hi <= lo:
        return {"min": round(lo, 2), "max": round(hi, 2), "counts": [len(sorted_vals)]}
    width = (hi - lo) / buckets
    counts = [0] * buckets
    for v in sorted_vals:
        counts[min(int((v - lo) / width), buckets - 1)] += 1
    return {"min": round(lo, 2), "max": round(hi, 2), "counts": counts}


@dataclass
class HoldoutComparison:
    in_sample_return_pct: float | None
    out_sample_return_pct: float | None
    in_sample_trades: int
    out_sample_trades: int

    def consistency(self) -> float | None:
        """1.0 = OOS as good as IS (or better); 0.0 = OOS lost everything IS made."""
        is_r, oos_r = self.in_sample_return_pct, self.out_sample_return_pct
        if is_r is None or oos_r is None:
            return None
        if is_r <= 0:                       # no in-sample edge to preserve
            return 1.0 if oos_r > 0 else 0.0
        return max(0.0, min(1.0, oos_r / is_r if oos_r < is_r else 1.0))


def robustness_score(n_trades: int, mc: dict | None,
                     holdout: HoldoutComparison | None) -> dict:
    """Blend the three checks into a 0-100 score + verdict + reasons list."""
    reasons: list[str] = []

    # -- sample size (0..35) --
    sample = min(1.0, n_trades / 30.0) * 35
    if n_trades < 10:
        reasons.append(f"Only {n_trades} closed trades — far too few to trust any statistic")
    elif n_trades < 30:
        reasons.append(f"{n_trades} closed trades — treat every metric as provisional")
    else:
        reasons.append(f"{n_trades} closed trades — a workable sample")

    # -- Monte Carlo tail (0..35) --
    tail = 0.0
    if mc:
        p5 = mc["return_p5"]
        tail = 35.0 if p5 > 0 else max(0.0, 35.0 * (1 + p5 / 30.0))   # -30% p5 -> 0
        if p5 > 0:
            reasons.append(f"Even the unlucky 5% of reshuffled histories stay profitable "
                           f"({p5:+.1f}%)")
        else:
            reasons.append(f"In the unlucky 5% of reshuffled histories you'd be at {p5:+.1f}% "
                           f"— could you sit through that?")
        if mc["prob_loss_pct"] > 25:
            reasons.append(f"{mc['prob_loss_pct']:.0f}% of alternate histories end in a loss")

    # -- holdout consistency (0..30) --
    consist = 0.0
    if holdout is not None:
        c = holdout.consistency()
        if c is not None:
            consist = 30.0 * c
            if holdout.out_sample_trades < 3:
                consist = min(consist, 12.0)
                reasons.append("Too few out-of-sample trades to confirm the edge")
            elif c >= 0.7:
                reasons.append(
                    f"Edge held out of sample ({holdout.out_sample_return_pct:+.1f}% on unseen "
                    f"data vs {holdout.in_sample_return_pct:+.1f}% in-sample)")
            else:
                reasons.append(
                    f"Edge faded out of sample ({holdout.out_sample_return_pct:+.1f}% vs "
                    f"{holdout.in_sample_return_pct:+.1f}% in-sample) — classic overfit smell")

    score = round(sample + tail + consist)
    verdict = ("ROBUST" if score >= 75 else
               "PROMISING" if score >= 55 else
               "FRAGILE" if score >= 35 else "OVERFIT_RISK")
    return {
        "score": score,
        "verdict": verdict,
        "components": {"sample_size": round(sample), "monte_carlo": round(tail),
                       "holdout": round(consist)},
        "reasons": reasons,
        "monte_carlo": mc,
        "holdout": ({
            "in_sample_return_pct": holdout.in_sample_return_pct,
            "out_sample_return_pct": holdout.out_sample_return_pct,
            "in_sample_trades": holdout.in_sample_trades,
            "out_sample_trades": holdout.out_sample_trades,
        } if holdout is not None else None),
    }
