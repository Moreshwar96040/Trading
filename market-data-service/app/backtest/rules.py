"""Strategy rule DSL: series resolution + boolean signal construction.

A rule is {"left": <series>, "op": <op>, "right": <series | number>}.
Series names: close, open, high, low, volume, sma_N, ema_N, rsi_N,
macd, macd_signal, macd_hist, bb_upper, bb_mid, bb_lower, atr_N.
Ops: gt, gte, lt, lte, crosses_above, crosses_below.
"""
import re

import pandas as pd

from app.indicators import core

OPS = {"gt", "gte", "lt", "lte", "crosses_above", "crosses_below"}
_PRICE_COLUMNS = {"close", "open", "high", "low", "volume"}
_PARAM_PATTERN = re.compile(r"^(sma|ema|rsi|atr)_(\d{1,3})$")
#: vol_sma_N = N-bar simple average of VOLUME (e.g. "volume gt vol_sma_20" =
#: today's volume above its 20-bar average — the honest "volume surge" filter).
_VOL_PATTERN = re.compile(r"^vol_sma_(\d{1,3})$")
_MACD_NAMES = {"macd", "macd_signal", "macd_hist"}
_BB_NAMES = {"bb_upper", "bb_mid", "bb_lower"}
#: Ichimoku lines + derived cloud edges. Chikou is intentionally excluded: it is
#: shifted backward (future data) and must never appear in a tradable rule.
_ICHIMOKU_NAMES = {"ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a",
                   "ichimoku_senkou_b", "ichimoku_cloud_top", "ichimoku_cloud_bottom"}
_SR_NAMES = {"support", "resistance"}
#: Fundamental ratios usable as rule operands (e.g. "roe_pct gt 15"). They are
#: injected by the backtest service as constant columns holding the CURRENT
#: stored value — a quality filter, not a time series (mild lookahead bias,
#: surfaced to the user as a coverage note).
FUNDAMENTAL_FIELDS = {"roe_pct", "pe_trailing", "pe_forward", "pb", "ps",
                      "debt_to_equity", "profit_margin_pct", "operating_margin_pct",
                      "revenue_growth_pct", "earnings_growth_pct", "dividend_yield_pct"}
#: Cross-sectional series, injected point-in-time by the backtest service.
#: rs_rank = 0-100 relative-strength percentile vs the tested universe at each
#: bar, built only from trailing returns — safe (no lookahead) in rules.
CROSS_SECTIONAL_FIELDS = {"rs_rank"}


class RuleError(ValueError):
    """Invalid rule definition."""


def is_valid_series(name: str) -> bool:
    return (name in _PRICE_COLUMNS or name in _MACD_NAMES or name in _BB_NAMES
            or name in _ICHIMOKU_NAMES or name in _SR_NAMES
            or name in FUNDAMENTAL_FIELDS or name in CROSS_SECTIONAL_FIELDS
            or _PARAM_PATTERN.match(name) is not None
            or _VOL_PATTERN.match(name) is not None)


def cross_sectional_fields_used(rules: list[dict]) -> set[str]:
    """Which cross-sectional fields (rs_rank, ...) appear in a rule list."""
    used: set[str] = set()
    for rule in rules or []:
        for operand in (rule.get("left"), rule.get("right")):
            if isinstance(operand, str) and operand in CROSS_SECTIONAL_FIELDS:
                used.add(operand)
    return used


def fundamental_fields_used(rules: list[dict]) -> set[str]:
    """Which fundamental fields appear in a rule list (left or right operands)."""
    used: set[str] = set()
    for rule in rules or []:
        for operand in (rule.get("left"), rule.get("right")):
            if isinstance(operand, str) and operand in FUNDAMENTAL_FIELDS:
                used.add(operand)
    return used


def validate_rules(rules: list[dict]) -> list[str]:
    """Returns a list of human-readable problems (empty = valid)."""
    problems = []
    if not isinstance(rules, list):
        return ["rules must be a list"]
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            problems.append(f"rule {i}: must be an object")
            continue
        left, op, right = rule.get("left"), rule.get("op"), rule.get("right")
        if not isinstance(left, str) or not is_valid_series(left):
            problems.append(f"rule {i}: unknown left series '{left}'")
        if op not in OPS:
            problems.append(f"rule {i}: unknown op '{op}' (use {sorted(OPS)})")
        if isinstance(right, str):
            if not is_valid_series(right):
                problems.append(f"rule {i}: unknown right series '{right}'")
        elif not isinstance(right, (int, float)) or isinstance(right, bool):
            problems.append(f"rule {i}: right must be a series name or number")
        if op in ("crosses_above", "crosses_below") and not isinstance(right, (str, int, float)):
            problems.append(f"rule {i}: crossover needs a series or number on the right")
    return problems


def resolve_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Resolve a series name against an OHLCV frame (columns open/high/low/close/volume)."""
    if name in _PRICE_COLUMNS:
        return df[name].astype(float)
    if name in FUNDAMENTAL_FIELDS:
        if name in df.columns:
            return df[name].astype(float)
        raise RuleError(f"'{name}' needs stored fundamentals for this symbol — "
                        "refresh fundamentals first (POST /api/v1/sync/fundamentals)")
    if name in CROSS_SECTIONAL_FIELDS:
        if name in df.columns:
            return df[name].astype(float)
        raise RuleError(f"'{name}' is cross-sectional — it is only available inside "
                        "backtests (the service injects it per universe)")
    vol_match = _VOL_PATTERN.match(name)
    if vol_match:
        period = int(vol_match.group(1))
        if period < 1:
            raise RuleError(f"period must be >= 1 in '{name}'")
        return core.sma(df["volume"].astype(float), period)
    match = _PARAM_PATTERN.match(name)
    if match:
        kind, period = match.group(1), int(match.group(2))
        if period < 1:
            raise RuleError(f"period must be >= 1 in '{name}'")
        close = df["close"].astype(float)
        if kind == "sma":
            return core.sma(close, period)
        if kind == "ema":
            return core.ema(close, period)
        if kind == "rsi":
            return core.rsi(close, period)
        return core.atr(df["high"].astype(float), df["low"].astype(float), close, period)
    if name in _MACD_NAMES:
        m = core.macd(df["close"].astype(float))
        return {"macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["hist"]}[name]
    if name in _BB_NAMES:
        bb = core.bollinger(df["close"].astype(float))
        return {"bb_upper": bb["upper"], "bb_mid": bb["mid"], "bb_lower": bb["lower"]}[name]
    if name in _ICHIMOKU_NAMES:
        ich = core.ichimoku(df["high"].astype(float), df["low"].astype(float),
                            df["close"].astype(float))
        return {
            "ichimoku_tenkan": ich["tenkan"], "ichimoku_kijun": ich["kijun"],
            "ichimoku_senkou_a": ich["senkou_a"], "ichimoku_senkou_b": ich["senkou_b"],
            "ichimoku_cloud_top": ich[["senkou_a", "senkou_b"]].max(axis=1),
            "ichimoku_cloud_bottom": ich[["senkou_a", "senkou_b"]].min(axis=1),
        }[name]
    if name in _SR_NAMES:
        sr = core.support_resistance(df["high"].astype(float), df["low"].astype(float))
        return sr[name]
    raise RuleError(f"Unknown series: {name}")


def _as_series(df: pd.DataFrame, operand) -> pd.Series | float:
    return resolve_series(df, operand) if isinstance(operand, str) else float(operand)


def rule_signal(df: pd.DataFrame, rule: dict) -> pd.Series:
    """Boolean Series: True on bars where the rule holds. NaN comparisons are False."""
    left = resolve_series(df, rule["left"])
    right = _as_series(df, rule["right"])
    op = rule["op"]

    if op in ("gt", "gte", "lt", "lte"):
        cmp = {"gt": left.gt, "gte": left.ge, "lt": left.lt, "lte": left.le}[op]
        return cmp(right).fillna(False)

    right_series = right if isinstance(right, pd.Series) else pd.Series(right, index=left.index)
    above_now = left > right_series
    above_prev = left.shift(1) > right_series.shift(1)
    if op == "crosses_above":
        out = above_now & ~above_prev & left.shift(1).notna() & right_series.shift(1).notna()
    else:  # crosses_below
        out = ~above_now & above_prev & left.notna() & right_series.notna()
    return out.fillna(False)


def combined_signal(df: pd.DataFrame, rules: list[dict]) -> pd.Series:
    """AND of all rules; empty rule list = never True (safety default)."""
    if not rules:
        return pd.Series(False, index=df.index)
    signal = rule_signal(df, rules[0])
    for rule in rules[1:]:
        signal &= rule_signal(df, rule)
    return signal
