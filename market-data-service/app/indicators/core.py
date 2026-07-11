"""Technical indicators — pure pandas, no native dependencies.

Every function takes/returns pd.Series aligned to the input index, with NaN
during the warm-up window. RSI and ATR use Wilder's smoothing (industry standard).
"""
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out[loss == 0] = 100.0          # all-gains window
    out[:period] = float("nan")     # warm-up not meaningful
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    sd = close.rolling(period).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + num_std * sd,
                         "lower": mid - num_std * sd})


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series,
             tenkan: int = 9, kijun: int = 26, senkou_b: int = 52,
             displacement: int = 26) -> pd.DataFrame:
    """Ichimoku Kinko Hyo. Returns tenkan, kijun, senkou_a, senkou_b, chikou.

    Senkou spans are shifted FORWARD by `displacement` (the cloud is plotted ahead),
    so the value at bar T is the cloud that applies to bar T — computed from data
    `displacement` bars ago. That means the cloud at T uses only past data: no
    lookahead. Chikou (close shifted back) is for visual reference only and must
    never be used in a tradable rule.
    """
    high, low, close = high.astype(float), low.astype(float), close.astype(float)

    def _mid(period: int) -> pd.Series:
        return (high.rolling(period).max() + low.rolling(period).min()) / 2.0

    tenkan_line = _mid(tenkan)
    kijun_line = _mid(kijun)
    span_a = ((tenkan_line + kijun_line) / 2.0).shift(displacement)
    span_b = _mid(senkou_b).shift(displacement)
    chikou = close.shift(-displacement)
    return pd.DataFrame({
        "tenkan": tenkan_line, "kijun": kijun_line,
        "senkou_a": span_a, "senkou_b": span_b, "chikou": chikou,
    })


def swing_points(high: pd.Series, low: pd.Series, left: int = 3,
                 right: int = 3) -> pd.DataFrame:
    """Fractal swing highs/lows: a pivot high is a bar whose high is the strict
    maximum of the `left` bars before and `right` bars after it (mirror for lows).

    The `right` lookahead means a pivot is only *confirmed* `right` bars later; use
    `support_resistance` for a no-lookahead level series suitable for trading rules.
    """
    high, low = high.astype(float), low.astype(float)
    window = left + right + 1
    is_high = high == high.rolling(window, center=True).max()
    is_low = low == low.rolling(window, center=True).min()
    return pd.DataFrame({
        "swing_high": high.where(is_high),
        "swing_low": low.where(is_low),
    })


def support_resistance(high: pd.Series, low: pd.Series, left: int = 3,
                       right: int = 3) -> pd.DataFrame:
    """Most-recent confirmed swing low (support) / swing high (resistance) as a
    step series, forward-filled and lagged by `right` bars so each value is only
    known once the pivot is confirmed — safe to use in backtest rules (no lookahead).
    """
    swings = swing_points(high, low, left, right)
    resistance = swings["swing_high"].shift(right).ffill()
    support = swings["swing_low"].shift(right).ffill()
    return pd.DataFrame({"support": support, "resistance": resistance})
