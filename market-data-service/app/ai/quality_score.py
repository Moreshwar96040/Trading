"""Fundamental quality score: is this a business worth timing?

Pure function over the stored ratios -> 0-100 + grade + component breakdown.
Used as the quality floor in the Alpha Stack (technical signals on weak
businesses get down-weighted) and shown wherever conviction is explained.

Deliberately simple and inspectable — closer to Piotroski than to a black box.
Missing data earns neutral half-credit, never a penalty: absence of evidence
is not evidence of absence.
"""


def _scale(value: float | None, lo: float, hi: float, max_points: float) -> float:
    """Linear 0..max_points as value moves lo..hi (clamped). None = half credit."""
    if value is None:
        return max_points / 2
    if hi == lo:
        return max_points / 2
    frac = (float(value) - lo) / (hi - lo)
    return max_points * min(1.0, max(0.0, frac))


def quality_score(f: dict) -> dict:
    """`f` holds any of: roe_pct, profit_margin_pct, operating_margin_pct,
    earnings_growth_pct, revenue_growth_pct, debt_to_equity, pe_trailing."""

    # -- profitability (0-30): does the business earn well on its capital? --
    profitability = (_scale(f.get("roe_pct"), 0, 25, 20)
                     + _scale(f.get("profit_margin_pct"), 0, 20, 10))

    # -- growth (0-25): is it getting bigger? --
    growth = (_scale(f.get("earnings_growth_pct"), -20, 30, 15)
              + _scale(f.get("revenue_growth_pct"), -10, 25, 10))

    # -- balance sheet (0-25): can it survive a bad year? (lower D/E is better) --
    de = f.get("debt_to_equity")
    balance = 25 - _scale(de, 0.0, 2.0, 25) if de is not None else 12.5

    # -- valuation sanity (0-20): not "cheap = good", just "priced like reality" --
    pe = f.get("pe_trailing")
    if pe is None:
        valuation = 10.0
    elif pe <= 0:                      # loss-making or broken ratio
        valuation = 2.0
    elif pe <= 15:
        valuation = 20.0
    elif pe <= 40:                     # taper 20 -> 8 across the growth band
        valuation = 20 - (pe - 15) / 25 * 12
    elif pe <= 80:                     # taper 8 -> 0 in nosebleed territory
        valuation = 8 - (pe - 40) / 40 * 8
    else:
        valuation = 0.0

    score = round(profitability + growth + balance + valuation)
    grade = ("A" if score >= 75 else "B" if score >= 60 else
             "C" if score >= 45 else "D")
    return {
        "score": score,
        "grade": grade,
        "components": {
            "profitability": round(profitability, 1),
            "growth": round(growth, 1),
            "balance_sheet": round(balance, 1),
            "valuation": round(valuation, 1),
        },
    }
