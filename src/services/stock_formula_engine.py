# -*- coding: utf-8 -*-
"""Formula DSL engine for stock screening."""

from __future__ import annotations

import ast
import difflib
import fnmatch
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


@dataclass
class FormulaErrorFeedback:
    message: str
    title: str
    detail: str
    suggestions: List[str]


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


def _formula_runtime_only(*_args: Any, **_kwargs: Any) -> float:
    # Runtime-only functions (e.g. FINANCE/DYNAINFO/NAMELIKE) are injected
    # via _build_context with stock-specific closures.
    return float("nan")


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
    "DYNAINFO": _formula_runtime_only,
    "FINANCE": _formula_runtime_only,
    "NAMELIKE": _formula_runtime_only,
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
    FormulaFunctionMeta(
        name="DYNAINFO",
        category="runtime",
        summary="Runtime quote lookup by compatibility code",
        signature="DYNAINFO(code)",
        returns="series",
        examples=["DYNAINFO(39) < 20", "DYNAINFO(35) < 2"],
        params=[
            FormulaFunctionParamMeta(name="code", type="int", description="Compatibility field code"),
        ],
    ),
    FormulaFunctionMeta(
        name="FINANCE",
        category="runtime",
        summary="Runtime fundamental lookup by compatibility code",
        signature="FINANCE(code)",
        returns="series",
        examples=["FINANCE(33) > 0", "FINANCE(40) > 0"],
        params=[
            FormulaFunctionParamMeta(name="code", type="int", description="Compatibility field code"),
        ],
    ),
    FormulaFunctionMeta(
        name="NAMELIKE",
        category="runtime",
        summary="Wildcard stock-name match",
        signature="NAMELIKE(pattern)",
        returns="bool_series",
        examples=["NOT NAMELIKE('*ST*')", "NAMELIKE('中*')"],
        params=[
            FormulaFunctionParamMeta(name="pattern", type="string", description="Wildcard pattern"),
        ],
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
FIELD_LABELS = {
    "OPEN": "开盘价",
    "HIGH": "最高价",
    "LOW": "最低价",
    "CLOSE": "收盘价",
    "VOL": "成交量",
    "AMOUNT": "成交额",
}
ATTRIBUTE_LABELS = {
    "macd": "MACD 快线",
    "signal": "MACD 慢线",
    "hist": "MACD 柱体",
    "k": "K 值",
    "d": "D 值",
    "j": "J 值",
    "upper": "布林上轨",
    "mid": "布林中轨",
    "lower": "布林下轨",
    "bandwidth": "布林带宽",
    "percent_b": "布林 %B",
}
DYNAINFO_CODE_LABELS = {
    3: "最新价",
    4: "最高价",
    5: "最低价",
    6: "开盘价",
    7: "最新价",
    8: "成交量",
    10: "成交额",
    11: "涨跌额",
    12: "涨跌幅",
    35: "市净率 PB",
    39: "动态市盈率 PE",
    40: "总市值",
    41: "流通市值",
}
FINANCE_CODE_LABELS = {
    1: "总股本",
    2: "流通股本",
    6: "每股净资产",
    7: "流通股本",
    30: "营收同比",
    33: "每股收益 EPS",
    34: "每股净资产",
    35: "净资产收益率 ROE",
    37: "总市值",
    38: "流通市值",
    40: "净利润同比",
    41: "市盈率 PE",
    42: "市净率 PB",
    46: "营收同比",
    47: "净利润同比",
}


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
        meaning, meaning_breakdown = self._build_formula_meaning(parsed)
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
            meaning=meaning,
            meaning_breakdown=meaning_breakdown,
            error_title=None,
            error_detail=None,
        )

    def build_invalid_response(self, formula: str, exc: Exception) -> FormulaValidationResponse:
        normalized_formula = self._safe_normalize_formula(formula)
        feedback = self._translate_validation_error(str(exc))
        return FormulaValidationResponse(
            valid=False,
            normalized_formula=normalized_formula,
            referenced_fields=[],
            functions=[],
            function_usage={},
            expression_nodes=0,
            complexity_score=0,
            complexity_level="low",
            message=feedback.message,
            estimated_lookback=self.DEFAULT_LOOKBACK,
            warnings=[],
            suggestions=feedback.suggestions,
            meaning="",
            meaning_breakdown=[],
            error_title=feedback.title,
            error_detail=feedback.detail,
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

    def evaluate(
        self,
        formula: str,
        df: pd.DataFrame,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> FormulaScanMatch:
        self._ensure_runtime_deps()
        parsed = self.parse(formula)
        return self.evaluate_parsed(parsed, df, runtime_context=runtime_context)

    def evaluate_parsed(
        self,
        parsed: FormulaParseResult,
        df: pd.DataFrame,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> FormulaScanMatch:
        self._ensure_runtime_deps()
        context = self._build_context(df, runtime_context=runtime_context)
        value = self._eval_node(parsed.tree.body, context, df.index)
        truth_series = _series_truth(value, df.index)
        cleaned = truth_series.dropna()
        matched = bool(cleaned.iloc[-1]) if not cleaned.empty else False
        return FormulaScanMatch(matched=matched, description=parsed.normalized_formula)

    def _normalize_formula(self, formula: str) -> str:
        normalized = (formula or "").strip()
        normalized = self._strip_tdx_comments(normalized)
        normalized = normalized.replace("，", ",").replace("（", "(").replace("）", ")")
        normalized = normalized.replace("；", ";").replace("：", ":")
        normalized = normalized.replace("＋", "+").replace("－", "-").replace("×", "*").replace("÷", "/")
        normalized = normalized.replace("&&", " AND ").replace("||", " OR ")
        normalized = normalized.replace("<>", "!=")
        normalized = re.sub(r"(?<![<>=!])!(?!=)", " NOT ", normalized)
        if ":=" in normalized or ";" in normalized:
            normalized = self._normalize_tdx_formula(normalized)
        normalized = re.sub(r"\bAND\b", " and ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bOR\b", " or ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bNOT\b", " not ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"(?<![<>=!])=(?!=)", "==", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = self._compact_split_identifiers(normalized)
        for alias, target in NAME_ALIASES.items():
            normalized = re.sub(rf"\b{alias}\b", target, normalized, flags=re.IGNORECASE)
        return normalized

    def _compact_split_identifiers(self, formula: str) -> str:
        compacted = formula
        keywords = sorted(
            set(FIELD_NAMES).union(FUNCTIONS.keys()).union({"TRUE", "FALSE"}),
            key=len,
            reverse=True,
        )
        for keyword in keywords:
            if len(keyword) < 2:
                continue
            pattern = r"\b" + r"\s*".join(re.escape(ch) for ch in keyword) + r"\b"
            compacted = re.sub(pattern, keyword, compacted, flags=re.IGNORECASE)
        return compacted

    @staticmethod
    def _strip_tdx_comments(formula: str) -> str:
        # TongHuaShun/TDX style comments: { ... }
        cleaned = re.sub(r"\{[^{}]*\}", " ", formula, flags=re.DOTALL)
        # Keep compatibility with line comments if users paste mixed scripts.
        cleaned = re.sub(r"//.*", " ", cleaned)
        return cleaned

    def _normalize_tdx_formula(self, formula: str) -> str:
        statements = [segment.strip() for segment in re.split(r";+", formula) if segment.strip()]
        if not statements:
            return formula

        assignments: Dict[str, str] = {}
        assignment_order: List[str] = []
        final_expression: Optional[str] = None
        reserved = set(FIELD_NAMES).union(FUNCTIONS.keys()).union({"AND", "OR", "NOT", "TRUE", "FALSE"})

        for statement in statements:
            statement_upper = statement.upper()
            if self._is_draw_statement(statement_upper) or self._is_style_statement(statement_upper):
                continue
            if ":=" in statement:
                var_name, expression = statement.split(":=", 1)
                var_name = var_name.strip()
                expression = expression.strip()
                if not var_name or not expression:
                    raise FormulaValidationError(f"Invalid TDX assignment: {statement}")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var_name):
                    raise FormulaValidationError(f"Invalid variable name in TDX formula: {var_name}")
                upper_var_name = var_name.upper()
                if upper_var_name in reserved:
                    raise FormulaValidationError(f"Variable name conflicts with reserved keyword: {var_name}")
                assignments[upper_var_name] = expression
                if upper_var_name not in assignment_order:
                    assignment_order.append(upper_var_name)
                continue

            label_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([\s\S]+)$", statement)
            if label_match:
                label_name = label_match.group(1).strip()
                expression = label_match.group(2).strip()
                upper_label_name = label_name.upper()
                # Keep XG-like labels addressable for trailing "XG;" style.
                if upper_label_name not in reserved:
                    assignments[upper_label_name] = expression
                    if upper_label_name not in assignment_order:
                        assignment_order.append(upper_label_name)
                final_expression = expression
                continue
            final_expression = statement

        if final_expression is None:
            if not assignment_order:
                return formula
            final_expression = assignment_order[-1]

        return self._expand_tdx_expression(final_expression, assignments, resolving=[])

    def _expand_tdx_expression(self, expression: str, assignments: Dict[str, str], resolving: List[str]) -> str:
        token_pattern = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

        def _replace(match: re.Match[str]) -> str:
            name = match.group(0)
            upper_name = name.upper()
            if upper_name not in assignments:
                return name
            if upper_name in resolving:
                cycle = " -> ".join(resolving + [upper_name])
                raise FormulaValidationError(f"Circular variable reference detected: {cycle}")
            expanded = self._expand_tdx_expression(assignments[upper_name], assignments, resolving + [upper_name])
            return f"({expanded})"

        return token_pattern.sub(_replace, expression)

    @staticmethod
    def _is_draw_statement(statement_upper: str) -> bool:
        draw_prefixes = (
            "DRAWICON(",
            "DRAWTEXT(",
            "DRAWTEXT_FIX(",
            "DRAWNUMBER(",
            "STICKLINE(",
            "PLOYLINE(",
            "POLYLINE(",
            "DRAWLINE(",
            "DRAWRECTREL(",
            "DRAWBAND(",
        )
        return statement_upper.startswith(draw_prefixes)

    @staticmethod
    def _is_style_statement(statement_upper: str) -> bool:
        return bool(re.fullmatch(r"COLOR[A-Z0-9_]+", statement_upper))

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

    def _safe_normalize_formula(self, formula: str) -> str:
        try:
            return self._normalize_formula(formula)
        except Exception:
            return (formula or "").strip()

    def _build_formula_meaning(self, parsed: FormulaParseResult) -> tuple[str, List[str]]:
        items = self._collect_meaning_items(parsed.tree.body)
        if items:
            connector = "同时满足" if isinstance(parsed.tree.body, ast.BoolOp) and isinstance(parsed.tree.body.op, ast.And) else "满足"
            meaning = f"该公式会在最新一个交易日{connector}以下规则时触发选股：{'；'.join(items)}。"
            breakdown = [f"条件 {index + 1}：{item}" for index, item in enumerate(items)]
            return meaning, breakdown
        summary = self._describe_node(parsed.tree.body)
        return f"该公式的核心判断为：{summary}。", [summary]

    def _collect_meaning_items(self, node: ast.AST) -> List[str]:
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return [self._describe_node(value) for value in node.values]
            return [" 或 ".join(self._describe_node(value) for value in node.values)]
        return [self._describe_node(node)]

    def _describe_node(self, node: ast.AST) -> str:
        if isinstance(node, ast.BoolOp):
            connector = "且" if isinstance(node.op, ast.And) else "或"
            return f"({f' {connector} '.join(self._describe_node(value) for value in node.values)})"
        if isinstance(node, ast.Compare):
            segments: List[str] = []
            left = node.left
            for operator_node, comparator in zip(node.ops, node.comparators):
                segments.append(
                    f"{self._describe_operand(left)}{self._describe_compare_operator(operator_node)}{self._describe_operand(comparator)}"
                )
                left = comparator
            return " 且 ".join(segments)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return f"不满足“{self._describe_operand(node.operand)}”"
            if isinstance(node.op, ast.USub):
                return f"-{self._describe_operand(node.operand)}"
            if isinstance(node.op, ast.UAdd):
                return self._describe_operand(node.operand)
        if isinstance(node, ast.BinOp):
            return (
                f"{self._describe_operand(node.left)}"
                f"{self._describe_binary_operator(node.op)}"
                f"{self._describe_operand(node.right)}"
            )
        if isinstance(node, ast.Call):
            return self._describe_call(node)
        if isinstance(node, ast.Attribute):
            base = self._describe_operand(node.value)
            return f"{base}的{ATTRIBUTE_LABELS.get(node.attr, node.attr)}"
        if isinstance(node, ast.Name):
            return FIELD_LABELS.get(node.id.upper(), node.id)
        if isinstance(node, ast.Constant):
            return self._format_literal(node.value)
        return ast.unparse(node)

    def _describe_operand(self, node: ast.AST) -> str:
        description = self._describe_node(node)
        if isinstance(node, (ast.BoolOp, ast.Compare)):
            return f"（{description}）"
        return description

    @staticmethod
    def _format_literal(value: Any) -> str:
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, bool):
            return "真" if value else "假"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    @staticmethod
    def _describe_compare_operator(operator_node: ast.cmpop) -> str:
        if isinstance(operator_node, ast.Gt):
            return " 大于 "
        if isinstance(operator_node, ast.GtE):
            return " 大于等于 "
        if isinstance(operator_node, ast.Lt):
            return " 小于 "
        if isinstance(operator_node, ast.LtE):
            return " 小于等于 "
        if isinstance(operator_node, ast.Eq):
            return " 等于 "
        if isinstance(operator_node, ast.NotEq):
            return " 不等于 "
        return f" {type(operator_node).__name__} "

    @staticmethod
    def _describe_binary_operator(operator_node: ast.operator) -> str:
        if isinstance(operator_node, ast.Add):
            return " + "
        if isinstance(operator_node, ast.Sub):
            return " - "
        if isinstance(operator_node, ast.Mult):
            return " * "
        if isinstance(operator_node, ast.Div):
            return " / "
        if isinstance(operator_node, ast.Mod):
            return " % "
        if isinstance(operator_node, ast.Pow):
            return " 的幂 "
        return f" {type(operator_node).__name__} "

    def _describe_call(self, node: ast.Call) -> str:
        if not isinstance(node.func, ast.Name):
            return ast.unparse(node)
        func_name = node.func.id.upper()
        args = node.args
        if func_name == "MA" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}的{self._describe_operand(args[1])}周期简单移动平均线"
        if func_name == "EMA" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}的{self._describe_operand(args[1])}周期指数移动平均线"
        if func_name == "SMA" and len(args) >= 2:
            weight = f"，平滑权重 {self._describe_operand(args[2])}" if len(args) >= 3 else ""
            return f"{self._describe_operand(args[0])}的{self._describe_operand(args[1])}周期同花顺/通达信 SMA 平滑均线{weight}"
        if func_name == "WMA" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}的{self._describe_operand(args[1])}周期加权移动平均线"
        if func_name == "REF" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}向前引用 {self._describe_operand(args[1])} 个周期的数值"
        if func_name == "HHV" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内{self._describe_operand(args[0])}的最高值"
        if func_name == "LLV" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内{self._describe_operand(args[0])}的最低值"
        if func_name == "SUM" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内{self._describe_operand(args[0])}的累计值"
        if func_name == "AVG" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内{self._describe_operand(args[0])}的平均值"
        if func_name == "STD" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内{self._describe_operand(args[0])}的标准差"
        if func_name == "ABS" and args:
            return f"{self._describe_operand(args[0])}的绝对值"
        if func_name == "MAX" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}与{self._describe_operand(args[1])}中的较大值"
        if func_name == "MIN" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}与{self._describe_operand(args[1])}中的较小值"
        if func_name == "IF" and len(args) >= 3:
            return f"如果{self._describe_operand(args[0])}，则取{self._describe_operand(args[1])}，否则取{self._describe_operand(args[2])}"
        if func_name == "CROSS" and len(args) >= 2:
            return f"{self._describe_operand(args[0])}上穿{self._describe_operand(args[1])}"
        if func_name == "COUNT" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内“{self._describe_operand(args[0])}”成立的次数"
        if func_name == "EVERY" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期持续满足“{self._describe_operand(args[0])}”"
        if func_name == "EXIST" and len(args) >= 2:
            return f"最近 {self._describe_operand(args[1])} 个周期内至少一次满足“{self._describe_operand(args[0])}”"
        if func_name == "BARSLAST" and args:
            return f"距离上次满足“{self._describe_operand(args[0])}”已经过去的周期数"
        if func_name == "MACD":
            return f"{self._describe_operand(args[0]) if args else '价格序列'}的 MACD 指标"
        if func_name == "RSI":
            period = self._describe_operand(args[1]) if len(args) >= 2 else "14"
            return f"{self._describe_operand(args[0]) if args else '价格序列'}的 {period} 周期 RSI"
        if func_name == "KDJ":
            period = self._describe_operand(args[3]) if len(args) >= 4 else "9"
            return f"基于高低收价格计算的 KDJ 指标（周期 {period}）"
        if func_name == "BOLL":
            period = self._describe_operand(args[1]) if len(args) >= 2 else "20"
            return f"{self._describe_operand(args[0]) if args else '价格序列'}的布林带（周期 {period}）"
        if func_name == "ATR":
            period = self._describe_operand(args[3]) if len(args) >= 4 else "14"
            return f"{period} 周期 ATR 波动率指标"
        if func_name == "CCI":
            period = self._describe_operand(args[3]) if len(args) >= 4 else "14"
            return f"{period} 周期 CCI 顺势指标"
        if func_name == "WR":
            period = self._describe_operand(args[3]) if len(args) >= 4 else "14"
            return f"{period} 周期 WR 威廉指标"
        if func_name == "OBV":
            return "OBV 能量潮指标"
        if func_name == "MFI":
            period = self._describe_operand(args[4]) if len(args) >= 5 else "14"
            return f"{period} 周期 MFI 资金流量指标"
        if func_name == "ROC":
            period = self._describe_operand(args[1]) if len(args) >= 2 else "12"
            return f"{self._describe_operand(args[0]) if args else '价格序列'}相对 {period} 周期前的变动率"
        if func_name == "DYNAINFO" and args:
            field_id = self._try_constant_int(args[0])
            label = DYNAINFO_CODE_LABELS.get(field_id, f"DYNAINFO({self._describe_operand(args[0])})")
            return f"同花顺实时行情字段“{label}”"
        if func_name == "FINANCE" and args:
            field_id = self._try_constant_int(args[0])
            label = FINANCE_CODE_LABELS.get(field_id, f"FINANCE({self._describe_operand(args[0])})")
            return f"同花顺财务字段“{label}”"
        if func_name == "NAMELIKE" and args:
            return f"股票名称匹配模式 {self._describe_operand(args[0])}"
        return ast.unparse(node)

    @staticmethod
    def _try_constant_int(node: ast.AST) -> Optional[int]:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return int(node.value)
        return None

    def _translate_validation_error(self, raw_message: str) -> FormulaErrorFeedback:
        message = (raw_message or "").strip()
        if message == "Formula cannot be empty":
            return FormulaErrorFeedback(
                message="公式不能为空，请先输入选股公式。",
                title="公式不能为空",
                detail="检验时没有检测到有效公式内容。请至少输入一个条件表达式，或粘贴完整的同花顺/通达信公式脚本。",
                suggestions=["可直接输入如 `CLOSE > MA(CLOSE, 5)` 的条件公式。"],
            )

        syntax_match = re.search(r"Formula syntax error near position (\d+)", message)
        if syntax_match:
            position = syntax_match.group(1)
            return FormulaErrorFeedback(
                message=f"公式语法错误，位置大约在第 {position} 个字符附近。",
                title="公式语法错误",
                detail="解析器无法在该位置继续识别公式。常见原因包括括号没有闭合、运算符缺失、逗号/分号位置错误，或 `XG:` 语句结尾不完整。",
                suggestions=[
                    "优先检查括号、逗号和分号是否成对、位置是否正确。",
                    "同花顺/通达信多语句公式建议使用 `;` 分隔，并确保最终有明确输出表达式。",
                ],
            )

        identifier_match = re.search(r"Unsupported identifier: ([^.]+?)(?:\. Did you mean: (.+))?$", message)
        if identifier_match:
            identifier = identifier_match.group(1).strip()
            guess = identifier_match.group(2)
            detail = f"检测到未识别标识符 `{identifier}`。它既不是受支持的行情字段，也不是当前公式内已定义的变量或函数。"
            suggestions = ["请确认字段名称是否写成 `OPEN/HIGH/LOW/CLOSE/VOL/AMOUNT`，或是否存在变量名拼写错误。"]
            if guess:
                detail += f" 你可能想写的是：{guess}。"
                suggestions.insert(0, f"可优先尝试把 `{identifier}` 改成：{guess}。")
            return FormulaErrorFeedback(
                message=f"存在未识别的标识符：{identifier}",
                title="标识符无法识别",
                detail=detail,
                suggestions=suggestions,
            )

        function_match = re.search(r"Unsupported function: ([^.]+?)(?:\. Did you mean: (.+))?$", message)
        if function_match:
            func_name = function_match.group(1).strip()
            guess = function_match.group(2)
            detail = f"检测到未支持函数 `{func_name}()`。当前公式编辑器只允许白名单内的同花顺/通达信兼容函数与内置指标函数。"
            suggestions = ["请改用已支持函数，或将该函数逻辑拆成现有函数组合。"]
            if guess:
                detail += f" 根据当前函数目录，最接近的候选是：{guess}。"
                suggestions.insert(0, f"可优先尝试将 `{func_name}()` 改写为：{guess}。")
            return FormulaErrorFeedback(
                message=f"存在未支持的函数：{func_name}()",
                title="函数暂不支持",
                detail=detail,
                suggestions=suggestions,
            )

        attr_match = re.search(r"Unsupported output field: (\w+)", message)
        if attr_match:
            attr = attr_match.group(1)
            supported = ", ".join(sorted(ATTR_WHITELIST))
            return FormulaErrorFeedback(
                message=f"指标输出字段 `{attr}` 暂不支持。",
                title="指标输出字段不受支持",
                detail=f"当前仅支持多输出指标的白名单属性访问，例如 `{supported}`。请确认你访问的是 MACD/KDJ/BOLL 的合法输出字段。",
                suggestions=["请改用受支持的属性名，或先查看函数列表中的 outputs 示例。"],
            )

        syntax_type_match = re.search(r"Unsupported syntax: (\w+)", message)
        if syntax_type_match:
            syntax_name = syntax_type_match.group(1)
            return FormulaErrorFeedback(
                message=f"公式中包含不受支持的语法：{syntax_name}",
                title="存在危险或非法语法",
                detail="当前公式校验器只允许安全表达式，不支持导入、循环、推导式、lambda、下标执行等脚本行为。这是为了兼容同花顺选股语义并避免任意代码执行。",
                suggestions=["请将复杂脚本改写为字段、函数、比较符和布尔运算组成的纯公式表达式。"],
            )

        if message == "Only direct function calls are supported":
            return FormulaErrorFeedback(
                message="仅支持直接函数调用。",
                title="函数调用方式不正确",
                detail="当前解析器只支持 `MA(CLOSE, 5)` 这类直接调用，不支持把函数结果继续当成函数调用对象，也不支持动态拼接函数名。",
                suggestions=["请改为标准的函数调用写法，并避免链式执行。"],
            )

        circular_match = re.search(r"Circular variable reference detected: (.+)$", message)
        if circular_match:
            return FormulaErrorFeedback(
                message="检测到变量循环引用。",
                title="变量存在循环依赖",
                detail=f"公式变量之间形成了循环依赖链：{circular_match.group(1)}。这种写法在同花顺/通达信选股条件中无法正确展开。",
                suggestions=["请检查 `:=` 定义顺序，避免 A 依赖 B、B 又反过来依赖 A。"],
            )

        invalid_assignment_match = re.search(r"Invalid TDX assignment: (.+)$", message)
        if invalid_assignment_match:
            return FormulaErrorFeedback(
                message="变量赋值语句不完整。",
                title="同花顺/通达信赋值语法错误",
                detail=f"以下赋值语句无法识别：`{invalid_assignment_match.group(1)}`。请确保使用 `变量名 := 表达式` 的完整格式。",
                suggestions=["请检查是否遗漏变量名、`:=` 或右侧表达式。"],
            )

        invalid_variable_match = re.search(r"Invalid variable name in TDX formula: (.+)$", message)
        if invalid_variable_match:
            variable = invalid_variable_match.group(1).strip()
            return FormulaErrorFeedback(
                message=f"变量名 `{variable}` 不符合规则。",
                title="变量名格式错误",
                detail="变量名必须以字母或下划线开头，后续只能包含字母、数字和下划线。请不要使用空格、中文标点或运算符作为变量名的一部分。",
                suggestions=["可改为 `VAR1`、`SIGNAL_A`、`XG1` 这类格式。"],
            )

        reserved_match = re.search(r"Variable name conflicts with reserved keyword: (.+)$", message)
        if reserved_match:
            variable = reserved_match.group(1).strip()
            return FormulaErrorFeedback(
                message=f"变量名 `{variable}` 与保留字冲突。",
                title="变量名与保留字冲突",
                detail="该名称已被字段名、函数名或逻辑关键字占用，继续使用会让公式含义产生歧义。",
                suggestions=["请更换为自定义变量名，例如 `VAR_PE`、`MY_SIGNAL`。"],
            )

        if message.startswith("Expected numeric series/scalar"):
            return FormulaErrorFeedback(
                message="公式中出现了无法参与数值计算的内容。",
                title="数值参数类型不正确",
                detail="某个位置本应传入价格序列、指标序列或数字常量，但实际传入了其他类型。常见于把字符串、结构体对象或布尔表达式直接用于算术运算。",
                suggestions=["请检查函数参数是否传入了正确的字段或数值。"],
            )

        if message.startswith("Expected boolean-compatible value"):
            return FormulaErrorFeedback(
                message="公式结果无法转成布尔条件。",
                title="条件表达式类型不正确",
                detail="最终选股条件必须能判断真/假。请确认布尔运算两侧都是可比较的数值或条件表达式。",
                suggestions=["请补充比较运算符，例如 `>`, `<`, `=`，或使用 `AND/OR/NOT` 组合条件。"],
            )

        if message.startswith("Integer parameter cannot be empty") or message.startswith("Numeric parameter cannot be empty"):
            return FormulaErrorFeedback(
                message="存在空参数，无法完成公式校验。",
                title="参数不能为空",
                detail="某个函数参数在计算时为空，常见于使用了缺失变量、空序列或不完整的函数调用。",
                suggestions=["请检查函数入参是否填写完整，尤其是周期参数和引用变量。"],
            )

        invalid_param_match = re.search(r"Invalid (integer|numeric) parameter: (.+)$", message)
        if invalid_param_match:
            return FormulaErrorFeedback(
                message=f"参数 `{invalid_param_match.group(2).strip()}` 不是合法数值。",
                title="参数格式错误",
                detail="某个周期或数值参数无法转成有效数字，请检查是否误写成文本、空值或带有非法字符。",
                suggestions=["请把该参数改成纯数字，例如 `5`、`14`、`2.5`。"],
            )

        return FormulaErrorFeedback(
            message=f"公式校验未通过：{message}",
            title="公式校验未通过",
            detail="公式未能通过当前规则校验，但未命中预设错误分类。请结合报错原文逐项检查字段名、函数名、括号和赋值语句。",
            suggestions=["如为同花顺公式，请优先检查 `:=` 赋值、`XG:` 输出和绘图语句是否书写规范。"],
        )

    def _build_context(self, df: pd.DataFrame, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        runtime = runtime_context or {}
        context["DYNAINFO"] = self._build_dynainfo_runtime_fn(runtime, index)
        context["FINANCE"] = self._build_finance_runtime_fn(runtime, index)
        context["NAMELIKE"] = self._build_namelike_runtime_fn(runtime, index)
        return context

    @staticmethod
    def _runtime_value_to_series(value: Any, index: pd.Index) -> pd.Series:
        if value is None:
            value = float("nan")
        return _ensure_series(value, index)

    def _build_dynainfo_runtime_fn(self, runtime: Dict[str, Any], index: pd.Index) -> Callable[[Any], pd.Series]:
        def _dynainfo(field_id: Any) -> pd.Series:
            key = f"DYNAINFO_{_scalar_int(field_id)}"
            return self._runtime_value_to_series(runtime.get(key), index)

        return _dynainfo

    def _build_finance_runtime_fn(self, runtime: Dict[str, Any], index: pd.Index) -> Callable[[Any], pd.Series]:
        def _finance(field_id: Any) -> pd.Series:
            key = f"FINANCE_{_scalar_int(field_id)}"
            return self._runtime_value_to_series(runtime.get(key), index)

        return _finance

    @staticmethod
    def _to_pattern(raw: Any) -> str:
        text = str(raw or "")
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        return text.strip()

    def _build_namelike_runtime_fn(self, runtime: Dict[str, Any], index: pd.Index) -> Callable[[Any], pd.Series]:
        def _namelike(pattern: Any) -> pd.Series:
            stock_name = str(runtime.get("STOCK_NAME", "") or "")
            wildcard = self._to_pattern(pattern)
            matched = fnmatch.fnmatchcase(stock_name.upper(), wildcard.upper())
            return self._runtime_value_to_series(bool(matched), index)

        return _namelike

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
