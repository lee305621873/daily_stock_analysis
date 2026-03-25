# -*- coding: utf-8 -*-
"""Formula DSL engine for stock screening."""

from __future__ import annotations

import ast
import difflib
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency for parse-only mode
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional dependency for parse-only mode
    pd = None  # type: ignore

from api.v1.schemas.stocks import (
    FormulaFunctionMeta,
    FormulaFunctionParamMeta,
    FormulaValidationResponse,
)


class FormulaValidationError(ValueError):
    """Raised when a formula is invalid or unsafe."""


@dataclass
class FormulaParseResult:
    normalized_formula: str
    tree: ast.Expression
    referenced_fields: List[str]
    functions: List[str]
    function_usage: Dict[str, int]
    expression_nodes: int
    estimated_lookback: int


@dataclass
class FormulaScanMatch:
    matched: bool
    description: str


class FormulaStruct:
    """Container that exposes multi-output indicators through attributes."""

    def __init__(self, **items: Any):
        self._items = items

    def __getattr__(self, item: str) -> Any:
        if item not in self._items:
            raise AttributeError(item)
        return self._items[item]

    def get(self, item: str) -> Any:
        return self._items.get(item)


def _ensure_series(value: Any, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.astype(float) if value.dtype == bool else value
    if isinstance(value, (int, float, bool, np.number)):
        return pd.Series([value] * len(index), index=index)
    raise FormulaValidationError(f"Expected numeric series/scalar, got {type(value).__name__}")


def _series_truth(value: Any, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        if value.dtype == bool:
            return value.fillna(False)
        return value.fillna(0).astype(float) != 0
    if isinstance(value, (bool, int, float, np.number)):
        return pd.Series([bool(value)] * len(index), index=index)
    raise FormulaValidationError(f"Expected boolean-compatible value, got {type(value).__name__}")


def _scalar_int(value: Any) -> int:
    if isinstance(value, pd.Series):
        cleaned = value.dropna()
        if cleaned.empty:
            raise FormulaValidationError("Integer parameter cannot be empty")
        value = cleaned.iloc[-1]
    try:
        return int(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise FormulaValidationError(f"Invalid integer parameter: {value}") from exc


def _scalar_float(value: Any) -> float:
    if isinstance(value, pd.Series):
        cleaned = value.dropna()
        if cleaned.empty:
            raise FormulaValidationError("Numeric parameter cannot be empty")
        value = cleaned.iloc[-1]
    try:
        return float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise FormulaValidationError(f"Invalid numeric parameter: {value}") from exc


def _rolling_apply(series: pd.Series, window: int, fn: Callable[[np.ndarray], float]) -> pd.Series:
    return series.rolling(window=window, min_periods=window).apply(fn, raw=True)


def _formula_ref(value: Any, periods: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    return series.shift(_scalar_int(periods))


def _formula_ma(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return series.rolling(window=n, min_periods=n).mean()


def _formula_ema(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    return series.ewm(span=max(1, _scalar_int(period)), adjust=False).mean()


def _formula_sma(value: Any, period: Any, weight: Any = 1) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    m = max(1, _scalar_int(weight))
    result = pd.Series(index=series.index, dtype=float)
    previous: Optional[float] = None
    for idx, raw in series.items():
        current = float(raw) if pd.notna(raw) else (previous if previous is not None else np.nan)
        if previous is None or pd.isna(previous):
            previous = current
        else:
            previous = (m * current + (n - m) * previous) / n
        result.loc[idx] = previous
    return result


def _formula_wma(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    weights = np.arange(1, n + 1)
    return _rolling_apply(series, n, lambda data: float(np.dot(data, weights) / weights.sum()))


def _formula_hhv(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return series.rolling(window=n, min_periods=n).max()


def _formula_llv(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return series.rolling(window=n, min_periods=n).min()


def _formula_sum(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return series.rolling(window=n, min_periods=n).sum()


def _formula_avg(value: Any, period: Any) -> pd.Series:
    return _formula_ma(value, period)


def _formula_std(value: Any, period: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return series.rolling(window=n, min_periods=n).std()


def _formula_abs(value: Any) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    return series.abs()


def _formula_max(left: Any, right: Any) -> pd.Series:
    index = left.index if isinstance(left, pd.Series) else right.index
    left_series = _ensure_series(left, index)
    right_series = _ensure_series(right, index)
    return pd.concat([left_series, right_series], axis=1).max(axis=1)


def _formula_min(left: Any, right: Any) -> pd.Series:
    index = left.index if isinstance(left, pd.Series) else right.index
    left_series = _ensure_series(left, index)
    right_series = _ensure_series(right, index)
    return pd.concat([left_series, right_series], axis=1).min(axis=1)


def _formula_if(condition: Any, if_true: Any, if_false: Any) -> pd.Series:
    index = (
        condition.index if isinstance(condition, pd.Series) else
        if_true.index if isinstance(if_true, pd.Series) else
        if_false.index if isinstance(if_false, pd.Series) else
        pd.RangeIndex(1)
    )
    cond = _series_truth(condition, index)
    true_series = _ensure_series(if_true, index)
    false_series = _ensure_series(if_false, index)
    return true_series.where(cond, false_series)


def _formula_cross(left: Any, right: Any) -> pd.Series:
    index = left.index if isinstance(left, pd.Series) else right.index
    left_series = _ensure_series(left, index)
    right_series = _ensure_series(right, index)
    return (left_series.shift(1) <= right_series.shift(1)) & (left_series > right_series)


def _formula_count(condition: Any, period: Any) -> pd.Series:
    cond = _series_truth(condition, condition.index if isinstance(condition, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return cond.astype(int).rolling(window=n, min_periods=n).sum()


def _formula_every(condition: Any, period: Any) -> pd.Series:
    cond = _series_truth(condition, condition.index if isinstance(condition, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return cond.astype(int).rolling(window=n, min_periods=n).sum() == n


def _formula_exist(condition: Any, period: Any) -> pd.Series:
    cond = _series_truth(condition, condition.index if isinstance(condition, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    return cond.astype(int).rolling(window=n, min_periods=n).sum() > 0


def _formula_barslast(condition: Any) -> pd.Series:
    cond = _series_truth(condition, condition.index if isinstance(condition, pd.Series) else pd.RangeIndex(1))
    result = pd.Series(index=cond.index, dtype=float)
    last_hit: Optional[int] = None
    for position, idx in enumerate(cond.index):
        if bool(cond.loc[idx]):
            last_hit = position
            result.loc[idx] = 0
        elif last_hit is None:
            result.loc[idx] = np.nan
        else:
            result.loc[idx] = position - last_hit
    return result


def _formula_macd(value: Any, fast: Any = 12, slow: Any = 26, signal: Any = 9) -> FormulaStruct:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    fast_n = max(1, _scalar_int(fast))
    slow_n = max(1, _scalar_int(slow))
    signal_n = max(1, _scalar_int(signal))
    ema_fast = series.ewm(span=fast_n, adjust=False).mean()
    ema_slow = series.ewm(span=slow_n, adjust=False).mean()
    diff = ema_fast - ema_slow
    dea = diff.ewm(span=signal_n, adjust=False).mean()
    hist = diff - dea
    return FormulaStruct(macd=diff, signal=dea, hist=hist)


def _formula_rsi(value: Any, period: Any = 14) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _formula_kdj(high: Any, low: Any, close: Any, period: Any = 9, k_smooth: Any = 3, d_smooth: Any = 3) -> FormulaStruct:
    index = high.index if isinstance(high, pd.Series) else close.index
    high_series = _ensure_series(high, index)
    low_series = _ensure_series(low, index)
    close_series = _ensure_series(close, index)
    period_n = max(1, _scalar_int(period))
    k_n = max(1, _scalar_int(k_smooth))
    d_n = max(1, _scalar_int(d_smooth))
    low_min = low_series.rolling(window=period_n, min_periods=period_n).min()
    high_max = high_series.rolling(window=period_n, min_periods=period_n).max()
    rsv = (close_series - low_min) / (high_max - low_min)
    rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(0)
    k = rsv.ewm(alpha=1 / k_n, adjust=False).mean() * 100
    d = k.ewm(alpha=1 / d_n, adjust=False).mean()
    j = 3 * k - 2 * d
    return FormulaStruct(k=k, d=d, j=j)


def _formula_boll(value: Any, period: Any = 20, multiplier: Any = 2.0) -> FormulaStruct:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    mult = _scalar_float(multiplier)
    mid = series.rolling(window=n, min_periods=n).mean()
    std = series.rolling(window=n, min_periods=n).std()
    upper = mid + mult * std
    lower = mid - mult * std
    bandwidth = (upper - lower) / mid.replace(0, np.nan)
    percent_b = (series - lower) / (upper - lower)
    return FormulaStruct(mid=mid, upper=upper, lower=lower, bandwidth=bandwidth, percent_b=percent_b)


def _formula_atr(high: Any, low: Any, close: Any, period: Any = 14) -> pd.Series:
    index = high.index if isinstance(high, pd.Series) else close.index
    high_series = _ensure_series(high, index)
    low_series = _ensure_series(low, index)
    close_series = _ensure_series(close, index)
    n = max(1, _scalar_int(period))
    prev_close = close_series.shift(1)
    true_range = pd.concat(
        [
            high_series - low_series,
            (high_series - prev_close).abs(),
            (low_series - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=n, min_periods=n).mean()


def _formula_cci(high: Any, low: Any, close: Any, period: Any = 14) -> pd.Series:
    index = high.index if isinstance(high, pd.Series) else close.index
    high_series = _ensure_series(high, index)
    low_series = _ensure_series(low, index)
    close_series = _ensure_series(close, index)
    n = max(1, _scalar_int(period))
    typical = (high_series + low_series + close_series) / 3
    ma = typical.rolling(window=n, min_periods=n).mean()
    mad = typical.rolling(window=n, min_periods=n).apply(
        lambda values: float(np.mean(np.abs(values - values.mean()))),
        raw=True,
    )
    return (typical - ma) / (0.015 * mad.replace(0, np.nan))


def _formula_wr(high: Any, low: Any, close: Any, period: Any = 14) -> pd.Series:
    index = high.index if isinstance(high, pd.Series) else close.index
    high_series = _ensure_series(high, index)
    low_series = _ensure_series(low, index)
    close_series = _ensure_series(close, index)
    n = max(1, _scalar_int(period))
    highest = high_series.rolling(window=n, min_periods=n).max()
    lowest = low_series.rolling(window=n, min_periods=n).min()
    return (highest - close_series) / (highest - lowest).replace(0, np.nan) * 100


def _formula_obv(close: Any, volume: Any) -> pd.Series:
    index = close.index if isinstance(close, pd.Series) else volume.index
    close_series = _ensure_series(close, index)
    volume_series = _ensure_series(volume, index)
    direction = np.sign(close_series.diff()).fillna(0)
    return (volume_series * direction).cumsum()


def _formula_mfi(high: Any, low: Any, close: Any, volume: Any, period: Any = 14) -> pd.Series:
    index = high.index if isinstance(high, pd.Series) else close.index
    high_series = _ensure_series(high, index)
    low_series = _ensure_series(low, index)
    close_series = _ensure_series(close, index)
    volume_series = _ensure_series(volume, index)
    n = max(1, _scalar_int(period))
    typical_price = (high_series + low_series + close_series) / 3
    money_flow = typical_price * volume_series
    direction = typical_price.diff()
    positive_flow = money_flow.where(direction > 0, 0.0)
    negative_flow = money_flow.where(direction < 0, 0.0).abs()
    positive_sum = positive_flow.rolling(window=n, min_periods=n).sum()
    negative_sum = negative_flow.rolling(window=n, min_periods=n).sum()
    money_ratio = positive_sum / negative_sum.replace(0, np.nan)
    return 100 - (100 / (1 + money_ratio))


def _formula_roc(value: Any, period: Any = 12) -> pd.Series:
    series = _ensure_series(value, value.index if isinstance(value, pd.Series) else pd.RangeIndex(1))
    n = max(1, _scalar_int(period))
    previous = series.shift(n)
    return (series - previous) / previous.replace(0, np.nan) * 100


FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "REF": _formula_ref,
    "MA": _formula_ma,
    "EMA": _formula_ema,
    "SMA": _formula_sma,
    "WMA": _formula_wma,
    "HHV": _formula_hhv,
    "LLV": _formula_llv,
    "SUM": _formula_sum,
    "AVG": _formula_avg,
    "STD": _formula_std,
    "ABS": _formula_abs,
    "MAX": _formula_max,
    "MIN": _formula_min,
    "IF": _formula_if,
    "CROSS": _formula_cross,
    "COUNT": _formula_count,
    "EVERY": _formula_every,
    "EXIST": _formula_exist,
    "BARSLAST": _formula_barslast,
    "MACD": _formula_macd,
    "RSI": _formula_rsi,
    "KDJ": _formula_kdj,
    "BOLL": _formula_boll,
    "ATR": _formula_atr,
    "CCI": _formula_cci,
    "WR": _formula_wr,
    "OBV": _formula_obv,
    "MFI": _formula_mfi,
    "ROC": _formula_roc,
}


FUNCTION_CATALOG: List[FormulaFunctionMeta] = [
    FormulaFunctionMeta(
        name="MA",
        category="trend",
        summary="Simple moving average",
        signature="MA(series, period)",
        returns="series",
        examples=["MA(CLOSE, 5)", "CLOSE > MA(CLOSE, 20)"],
        params=[
            FormulaFunctionParamMeta(name="series", type="series", description="Price or indicator series"),
            FormulaFunctionParamMeta(name="period", type="int", description="Window length"),
        ],
    ),
    FormulaFunctionMeta(
        name="EMA",
        category="trend",
        summary="Exponential moving average",
        signature="EMA(series, period)",
        returns="series",
        examples=["EMA(CLOSE, 12)"],
        params=[
            FormulaFunctionParamMeta(name="series", type="series", description="Price or indicator series"),
            FormulaFunctionParamMeta(name="period", type="int", description="Window length"),
        ],
    ),
    FormulaFunctionMeta(
        name="SMA",
        category="trend",
        summary="Chinese-style smoothed moving average",
        signature="SMA(series, period, weight=1)",
        returns="series",
        examples=["SMA(CLOSE, 10, 2)"],
        params=[
            FormulaFunctionParamMeta(name="series", type="series", description="Price or indicator series"),
            FormulaFunctionParamMeta(name="period", type="int", description="Window length"),
            FormulaFunctionParamMeta(name="weight", type="int", description="Smoothing weight", optional=True),
        ],
    ),
    FormulaFunctionMeta(
        name="WMA",
        category="trend",
        summary="Weighted moving average",
        signature="WMA(series, period)",
        returns="series",
        examples=["WMA(CLOSE, 20)"],
    ),
    FormulaFunctionMeta(
        name="MACD",
        category="indicator",
        summary="MACD indicator with .macd/.signal/.hist outputs",
        signature="MACD(series, fast=12, slow=26, signal=9)",
        returns="struct",
        examples=["MACD(CLOSE, 12, 26, 9).hist > 0"],
    ),
    FormulaFunctionMeta(
        name="RSI",
        category="indicator",
        summary="Relative strength index",
        signature="RSI(series, period=14)",
        returns="series",
        examples=["RSI(CLOSE, 14) < 30"],
    ),
    FormulaFunctionMeta(
        name="KDJ",
        category="indicator",
        summary="KDJ indicator with .k/.d/.j outputs",
        signature="KDJ(HIGH, LOW, CLOSE, period=9, k_smooth=3, d_smooth=3)",
        returns="struct",
        examples=["KDJ(HIGH, LOW, CLOSE).j > 90"],
    ),
    FormulaFunctionMeta(
        name="BOLL",
        category="indicator",
        summary="Bollinger band with .upper/.mid/.lower/.bandwidth/.percent_b outputs",
        signature="BOLL(series, period=20, multiplier=2.0)",
        returns="struct",
        examples=["CLOSE > BOLL(CLOSE, 20, 2).upper"],
    ),
    FormulaFunctionMeta(
        name="ATR",
        category="indicator",
        summary="Average true range",
        signature="ATR(HIGH, LOW, CLOSE, period=14)",
        returns="series",
        examples=["ATR(HIGH, LOW, CLOSE, 14) > 1.5"],
    ),
    FormulaFunctionMeta(
        name="CCI",
        category="indicator",
        summary="Commodity channel index",
        signature="CCI(HIGH, LOW, CLOSE, period=14)",
        returns="series",
        examples=["CCI(HIGH, LOW, CLOSE, 14) > 100"],
    ),
    FormulaFunctionMeta(
        name="WR",
        category="indicator",
        summary="Williams %R",
        signature="WR(HIGH, LOW, CLOSE, period=14)",
        returns="series",
        examples=["WR(HIGH, LOW, CLOSE, 14) < 20"],
    ),
    FormulaFunctionMeta(
        name="OBV",
        category="volume",
        summary="On-balance volume",
        signature="OBV(CLOSE, VOL)",
        returns="series",
        examples=["OBV(CLOSE, VOL) > REF(OBV(CLOSE, VOL), 1)"],
    ),
    FormulaFunctionMeta(
        name="MFI",
        category="volume",
        summary="Money flow index",
        signature="MFI(HIGH, LOW, CLOSE, VOL, period=14)",
        returns="series",
        examples=["MFI(HIGH, LOW, CLOSE, VOL, 14) < 20"],
    ),
    FormulaFunctionMeta(
        name="ROC",
        category="momentum",
        summary="Rate of change",
        signature="ROC(series, period=12)",
        returns="series",
        examples=["ROC(CLOSE, 12) > 0"],
    ),
    FormulaFunctionMeta(
        name="REF",
        category="utility",
        summary="Historical reference",
        signature="REF(series, periods)",
        returns="series",
        examples=["CLOSE > REF(CLOSE, 1)"],
    ),
    FormulaFunctionMeta(
        name="HHV",
        category="utility",
        summary="Highest high value in rolling window",
        signature="HHV(series, period)",
        returns="series",
        examples=["CLOSE > HHV(HIGH, 20)"],
    ),
    FormulaFunctionMeta(
        name="LLV",
        category="utility",
        summary="Lowest low value in rolling window",
        signature="LLV(series, period)",
        returns="series",
        examples=["CLOSE < LLV(LOW, 20) * 1.05"],
    ),
    FormulaFunctionMeta(
        name="SUM",
        category="utility",
        summary="Rolling sum",
        signature="SUM(series, period)",
        returns="series",
        examples=["SUM(VOL, 5) > SUM(VOL, 20) / 2"],
    ),
    FormulaFunctionMeta(
        name="AVG",
        category="utility",
        summary="Rolling average",
        signature="AVG(series, period)",
        returns="series",
        examples=["AVG(CLOSE, 10) > AVG(CLOSE, 20)"],
    ),
    FormulaFunctionMeta(
        name="STD",
        category="utility",
        summary="Rolling standard deviation",
        signature="STD(series, period)",
        returns="series",
        examples=["STD(CLOSE, 20) > 2"],
    ),
    FormulaFunctionMeta(
        name="ABS",
        category="utility",
        summary="Absolute value",
        signature="ABS(value)",
        returns="series",
        examples=["ABS(CLOSE - MA(CLOSE, 20)) < 1"],
    ),
    FormulaFunctionMeta(
        name="MAX",
        category="utility",
        summary="Element-wise max",
        signature="MAX(left, right)",
        returns="series",
        examples=["MAX(CLOSE, OPEN) > HIGH * 0.99"],
    ),
    FormulaFunctionMeta(
        name="MIN",
        category="utility",
        summary="Element-wise min",
        signature="MIN(left, right)",
        returns="series",
        examples=["MIN(CLOSE, OPEN) < LOW * 1.01"],
    ),
    FormulaFunctionMeta(
        name="COUNT",
        category="signal",
        summary="Rolling count of truthy condition",
        signature="COUNT(condition, period)",
        returns="series",
        examples=["COUNT(CLOSE > MA(CLOSE, 20), 5) >= 4"],
    ),
    FormulaFunctionMeta(
        name="EVERY",
        category="signal",
        summary="All bars satisfy condition in window",
        signature="EVERY(condition, period)",
        returns="series",
        examples=["EVERY(CLOSE > MA(CLOSE, 20), 5)"],
    ),
    FormulaFunctionMeta(
        name="EXIST",
        category="signal",
        summary="At least one bar satisfies condition in window",
        signature="EXIST(condition, period)",
        returns="series",
        examples=["EXIST(CROSS(MA(CLOSE, 5), MA(CLOSE, 10)), 10)"],
    ),
    FormulaFunctionMeta(
        name="BARSLAST",
        category="signal",
        summary="Bars elapsed since last true condition",
        signature="BARSLAST(condition)",
        returns="series",
        examples=["BARSLAST(CROSS(MA(CLOSE, 5), MA(CLOSE, 10))) < 5"],
    ),
    FormulaFunctionMeta(
        name="IF",
        category="signal",
        summary="Conditional series selector",
        signature="IF(condition, if_true, if_false)",
        returns="series",
        examples=["IF(CLOSE > OPEN, VOL, 0)"],
    ),
    FormulaFunctionMeta(
        name="CROSS",
        category="signal",
        summary="Cross-up signal",
        signature="CROSS(left, right)",
        returns="bool_series",
        examples=["CROSS(MA(CLOSE, 5), MA(CLOSE, 20))"],
    ),
]


NAME_ALIASES = {
    "O": "OPEN",
    "H": "HIGH",
    "L": "LOW",
    "C": "CLOSE",
    "V": "VOL",
}

FIELD_NAMES = {"OPEN", "HIGH", "LOW", "CLOSE", "VOL", "AMOUNT"}
ATTR_WHITELIST = {"macd", "signal", "hist", "k", "d", "j", "upper", "mid", "lower", "bandwidth", "percent_b"}


class StockFormulaEngine:
    DEFAULT_LOOKBACK = 250

    @staticmethod
    def _ensure_runtime_deps() -> None:
        global np, pd
        if np is None:
            import numpy as _np  # type: ignore

            np = _np
        if pd is None:
            import pandas as _pd  # type: ignore

            pd = _pd

    def list_functions(self) -> List[FormulaFunctionMeta]:
        return FUNCTION_CATALOG

    def validate(self, formula: str) -> FormulaValidationResponse:
        parsed = self.parse(formula)
        complexity_score, complexity_level = self._estimate_complexity(parsed)
        return FormulaValidationResponse(
            valid=True,
            normalized_formula=parsed.normalized_formula,
            referenced_fields=parsed.referenced_fields,
            functions=parsed.functions,
            function_usage=parsed.function_usage,
            expression_nodes=parsed.expression_nodes,
            complexity_score=complexity_score,
            complexity_level=complexity_level,
            message="公式校验通过",
            estimated_lookback=parsed.estimated_lookback,
            warnings=self._build_warnings(parsed),
            suggestions=self._build_suggestions(parsed, complexity_level),
        )

    def parse(self, formula: str) -> FormulaParseResult:
        normalized = self._normalize_formula(formula)
        if not normalized:
            raise FormulaValidationError("Formula cannot be empty")

        try:
            tree = ast.parse(normalized, mode="eval")
        except SyntaxError as exc:
            raise FormulaValidationError(f"Formula syntax error near position {exc.offset}") from exc

        fields: Set[str] = set()
        functions: Set[str] = set()
        function_usage: Dict[str, int] = {}
        expression_nodes = 0
        estimated_lookback = self.DEFAULT_LOOKBACK

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Load, ast.Expression)):
                expression_nodes += 1
            if not isinstance(
                node,
                (
                    ast.Expression,
                    ast.BoolOp,
                    ast.BinOp,
                    ast.UnaryOp,
                    ast.Compare,
                    ast.Call,
                    ast.Name,
                    ast.Load,
                    ast.Constant,
                    ast.Attribute,
                    ast.keyword,
                    ast.And,
                    ast.Or,
                    ast.Not,
                    ast.Add,
                    ast.Sub,
                    ast.Mult,
                    ast.Div,
                    ast.Mod,
                    ast.Pow,
                    ast.USub,
                    ast.UAdd,
                    ast.Gt,
                    ast.GtE,
                    ast.Lt,
                    ast.LtE,
                    ast.Eq,
                    ast.NotEq,
                ),
            ):
                raise FormulaValidationError(f"Unsupported syntax: {type(node).__name__}")

            if isinstance(node, ast.Name):
                upper_name = node.id.upper()
                if upper_name in FIELD_NAMES:
                    fields.add(upper_name)
                elif upper_name in FUNCTIONS:
                    continue
                elif upper_name in {"TRUE", "FALSE"}:
                    continue
                else:
                    candidates = sorted(FIELD_NAMES.union(FUNCTIONS.keys()))
                    maybe = difflib.get_close_matches(upper_name, candidates, n=3, cutoff=0.6)
                    if maybe:
                        raise FormulaValidationError(
                            f"Unsupported identifier: {node.id}. Did you mean: {', '.join(maybe)}"
                        )
                    raise FormulaValidationError(f"Unsupported identifier: {node.id}")

            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    raise FormulaValidationError("Only direct function calls are supported")
                func_name = node.func.id.upper()
                if func_name not in FUNCTIONS:
                    maybe = difflib.get_close_matches(func_name, list(FUNCTIONS.keys()), n=3, cutoff=0.5)
                    if maybe:
                        raise FormulaValidationError(
                            f"Unsupported function: {func_name}. Did you mean: {', '.join(maybe)}"
                        )
                    raise FormulaValidationError(f"Unsupported function: {func_name}")
                functions.add(func_name)
                function_usage[func_name] = function_usage.get(func_name, 0) + 1
                estimated_lookback = max(estimated_lookback, self._estimate_call_lookback(func_name, node))

            if isinstance(node, ast.Attribute):
                if node.attr not in ATTR_WHITELIST:
                    raise FormulaValidationError(f"Unsupported output field: {node.attr}")

        return FormulaParseResult(
            normalized_formula=normalized,
            tree=tree,
            referenced_fields=sorted(fields),
            functions=sorted(functions),
            function_usage={name: function_usage[name] for name in sorted(function_usage)},
            expression_nodes=expression_nodes,
            estimated_lookback=estimated_lookback,
        )

    def evaluate(self, formula: str, df: pd.DataFrame) -> FormulaScanMatch:
        self._ensure_runtime_deps()
        parsed = self.parse(formula)
        return self.evaluate_parsed(parsed, df)

    def evaluate_parsed(self, parsed: FormulaParseResult, df: pd.DataFrame) -> FormulaScanMatch:
        self._ensure_runtime_deps()
        context = self._build_context(df)
        value = self._eval_node(parsed.tree.body, context, df.index)
        truth_series = _series_truth(value, df.index)
        cleaned = truth_series.dropna()
        matched = bool(cleaned.iloc[-1]) if not cleaned.empty else False
        return FormulaScanMatch(matched=matched, description=parsed.normalized_formula)

    def _normalize_formula(self, formula: str) -> str:
        normalized = (formula or "").strip()
        normalized = normalized.replace("，", ",").replace("（", "(").replace("）", ")")
        normalized = normalized.replace("＋", "+").replace("－", "-").replace("×", "*").replace("÷", "/")
        normalized = re.sub(r"\bAND\b", " and ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bOR\b", " or ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bNOT\b", " not ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"(?<![<>=!])=(?!=)", "==", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for alias, target in NAME_ALIASES.items():
            normalized = re.sub(rf"\b{alias}\b", target, normalized, flags=re.IGNORECASE)
        return normalized

    def _build_warnings(self, parsed: FormulaParseResult) -> List[str]:
        warnings: List[str] = []
        if parsed.estimated_lookback >= 250:
            warnings.append("该公式默认建议至少加载 250 个交易日数据，以降低边界误差。")
        if parsed.estimated_lookback >= 600:
            warnings.append("公式依赖较长历史窗口，扫描耗时会明显上升，建议结合扫描上限使用。")
        if parsed.expression_nodes >= 100:
            warnings.append("公式结构较复杂，建议先拆分验证子条件，避免调试困难。")
        repeated_funcs = [name for name, count in parsed.function_usage.items() if count >= 4]
        if repeated_funcs:
            warnings.append(f"以下函数重复调用较多：{', '.join(repeated_funcs)}，可考虑先中间化或简化表达式。")
        if not parsed.referenced_fields:
            warnings.append("公式未直接引用 OHLCV 字段，请确认函数参数书写正确。")
        return warnings

    def _build_suggestions(self, parsed: FormulaParseResult, complexity_level: str) -> List[str]:
        suggestions: List[str] = []
        if complexity_level == "high":
            suggestions.append("当前复杂度较高，可先将条件拆成两段分别验证后再组合。")
        if "CROSS" not in parsed.functions:
            suggestions.append("若策略关注拐点信号，可尝试引入 CROSS() 与趋势条件组合。")
        if parsed.estimated_lookback > 500:
            suggestions.append("建议在扫描配置中设置“扫描上限”，减少长窗口公式的整体耗时。")
        if len(parsed.functions) <= 1:
            suggestions.append("当前公式函数较少，可叠加量能或波动类函数提升筛选辨识度。")
        if not parsed.referenced_fields:
            suggestions.append("请检查参数是否引用了 CLOSE/HIGH/LOW/VOL 等字段，避免纯常量表达式。")
        return suggestions[:4]

    def _estimate_complexity(self, parsed: FormulaParseResult) -> tuple[int, str]:
        func_weight = sum(parsed.function_usage.values()) * 6
        structure_weight = parsed.expression_nodes
        lookback_weight = max(0, parsed.estimated_lookback - 250) // 25
        score = max(1, func_weight + structure_weight + lookback_weight)
        if score < 45:
            level = "low"
        elif score < 90:
            level = "medium"
        else:
            level = "high"
        return score, level

    def _estimate_call_lookback(self, func_name: str, call: ast.Call) -> int:
        if func_name in {"REF", "MA", "EMA", "SMA", "WMA", "HHV", "LLV", "SUM", "AVG", "STD", "COUNT", "EVERY", "EXIST", "ROC"}:
            if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, (int, float)):
                return max(self.DEFAULT_LOOKBACK, int(call.args[1].value))
        if func_name in {"ATR", "CCI", "WR", "MFI", "RSI"}:
            if call.args and isinstance(call.args[-1], ast.Constant) and isinstance(call.args[-1].value, (int, float)):
                return max(self.DEFAULT_LOOKBACK, int(call.args[-1].value))
        if func_name in {"MACD", "BOLL", "KDJ"}:
            return self.DEFAULT_LOOKBACK
        return self.DEFAULT_LOOKBACK

    def _build_context(self, df: pd.DataFrame) -> Dict[str, Any]:
        prepared = df.copy()
        if "date" in prepared.columns:
            prepared["date"] = pd.to_datetime(prepared["date"])
            prepared = prepared.sort_values("date")
        for column in ("open", "high", "low", "close", "volume", "amount"):
            if column in prepared.columns:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        index = prepared.index
        context: Dict[str, Any] = {
            "OPEN": prepared["open"] if "open" in prepared.columns else pd.Series(np.nan, index=index),
            "HIGH": prepared["high"] if "high" in prepared.columns else pd.Series(np.nan, index=index),
            "LOW": prepared["low"] if "low" in prepared.columns else pd.Series(np.nan, index=index),
            "CLOSE": prepared["close"] if "close" in prepared.columns else pd.Series(np.nan, index=index),
            "VOL": prepared["volume"] if "volume" in prepared.columns else pd.Series(np.nan, index=index),
            "AMOUNT": prepared["amount"] if "amount" in prepared.columns else pd.Series(np.nan, index=index),
            "TRUE": True,
            "FALSE": False,
        }
        context.update(FUNCTIONS)
        return context

    def _eval_node(self, node: ast.AST, context: Dict[str, Any], index: pd.Index) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            key = node.id.upper()
            if key not in context:
                raise FormulaValidationError(f"Unsupported identifier: {node.id}")
            return context[key]

        if isinstance(node, ast.Attribute):
            value = self._eval_node(node.value, context, index)
            if not isinstance(value, FormulaStruct):
                raise FormulaValidationError(f"Attribute access is only allowed on indicator outputs: {node.attr}")
            return value.get(node.attr)

        if isinstance(node, ast.Call):
            func = self._eval_node(node.func, context, index)
            args = [self._eval_node(arg, context, index) for arg in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, context, index) for kw in node.keywords if kw.arg}
            return func(*args, **kwargs)

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context, index)
            if isinstance(node.op, ast.Not):
                return ~_series_truth(operand, index)
            if isinstance(node.op, ast.USub):
                return -_ensure_series(operand, index)
            if isinstance(node.op, ast.UAdd):
                return _ensure_series(operand, index)
            raise FormulaValidationError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context, index)
            right = self._eval_node(node.right, context, index)
            return self._apply_binop(node.op, left, right, index)

        if isinstance(node, ast.BoolOp):
            values = [_series_truth(self._eval_node(value, context, index), index) for value in node.values]
            if isinstance(node.op, ast.And):
                result = values[0]
                for value in values[1:]:
                    result = result & value
                return result
            if isinstance(node.op, ast.Or):
                result = values[0]
                for value in values[1:]:
                    result = result | value
                return result
            raise FormulaValidationError(f"Unsupported boolean operator: {type(node.op).__name__}")

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context, index)
            result: Optional[pd.Series] = None
            current_left = left
            for op_node, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context, index)
                comparison = self._apply_compare(op_node, current_left, right, index)
                result = comparison if result is None else (result & comparison)
                current_left = right
            return result if result is not None else False

        raise FormulaValidationError(f"Unsupported expression node: {type(node).__name__}")

    def _apply_binop(self, op_node: ast.AST, left: Any, right: Any, index: pd.Index) -> pd.Series:
        left_series = _ensure_series(left, index)
        right_series = _ensure_series(right, index)
        if isinstance(op_node, ast.Add):
            return left_series + right_series
        if isinstance(op_node, ast.Sub):
            return left_series - right_series
        if isinstance(op_node, ast.Mult):
            return left_series * right_series
        if isinstance(op_node, ast.Div):
            return left_series / right_series.replace(0, np.nan)
        if isinstance(op_node, ast.Mod):
            return left_series % right_series
        if isinstance(op_node, ast.Pow):
            return left_series ** right_series
        raise FormulaValidationError(f"Unsupported binary operator: {type(op_node).__name__}")

    def _apply_compare(self, op_node: ast.AST, left: Any, right: Any, index: pd.Index) -> pd.Series:
        left_series = _ensure_series(left, index)
        right_series = _ensure_series(right, index)
        operation_map = {
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
        }
        for op_type, func in operation_map.items():
            if isinstance(op_node, op_type):
                return func(left_series, right_series)
        raise FormulaValidationError(f"Unsupported comparison operator: {type(op_node).__name__}")
