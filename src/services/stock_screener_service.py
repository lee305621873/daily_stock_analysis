# -*- coding: utf-8 -*-
"""
Technical stock screener service for the main API/Web app.
"""

from __future__ import annotations

import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.v1.schemas.stocks import (
    CompareType,
    FormulaFunctionMeta,
    FormulaValidationResponse,
    IndicatorCondition,
    IndicatorKey,
    IndicatorMeta,
    IndicatorOutputMeta,
    IndicatorParamMeta,
    LogicOp,
    MarketType,
    Operator,
    ScreenerMode,
    ScreenerScanRequest,
    ScreenerScanResponse,
    ScreenerScanResultItem,
)
from src.config import get_config
from src.services.stock_formula_engine import FormulaParseResult, FormulaValidationError, StockFormulaEngine

logger = logging.getLogger(__name__)


@dataclass
class StockBasic:
    code: str
    name: str


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    if "date" in prepared.columns:
        prepared["date"] = pd.to_datetime(prepared["date"])
        prepared = prepared.sort_values("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col in prepared.columns:
            prepared[col] = pd.to_numeric(prepared[col], errors="coerce")
    return prepared


def _ma(df: pd.DataFrame, period: int = 5) -> pd.Series:
    prepared = _prepare(df)
    return prepared["close"].rolling(window=int(period), min_periods=int(period)).mean()


def _macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    prepared = _prepare(df)
    close = prepared["close"]
    ema_fast = close.ewm(span=int(fast), adjust=False).mean()
    ema_slow = close.ewm(span=int(slow), adjust=False).mean()
    diff = ema_fast - ema_slow
    dea = diff.ewm(span=int(signal), adjust=False).mean()
    hist = diff - dea
    return {"macd": diff, "signal": dea, "hist": hist}


def _rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prepared = _prepare(df)
    delta = prepared["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / int(period), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / int(period), adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _kdj(df: pd.DataFrame, period: int = 9, k_smooth: int = 3, d_smooth: int = 3) -> Dict[str, pd.Series]:
    prepared = _prepare(df)
    low_min = prepared["low"].rolling(window=int(period), min_periods=int(period)).min()
    high_max = prepared["high"].rolling(window=int(period), min_periods=int(period)).max()
    rsv = (prepared["close"] - low_min) / (high_max - low_min)
    rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(0)
    k = rsv.ewm(alpha=1 / int(k_smooth), adjust=False).mean()
    d = k.ewm(alpha=1 / int(d_smooth), adjust=False).mean()
    j = 3 * k - 2 * d
    return {"k": k, "d": d, "j": j}


def _boll(df: pd.DataFrame, period: int = 20, multiplier: float = 2.0) -> Dict[str, pd.Series]:
    prepared = _prepare(df)
    mid = prepared["close"].rolling(window=int(period), min_periods=int(period)).mean()
    std = prepared["close"].rolling(window=int(period), min_periods=int(period)).std()
    upper = mid + float(multiplier) * std
    lower = mid - float(multiplier) * std
    bandwidth = (upper - lower) / mid
    percent_b = (prepared["close"] - lower) / (upper - lower)
    return {"mid": mid, "upper": upper, "lower": lower, "bandwidth": bandwidth, "percent_b": percent_b}


def _vol(df: pd.DataFrame, period: int = 5) -> Dict[str, pd.Series]:
    prepared = _prepare(df)
    volume = prepared["volume"]
    vol_ma = volume.rolling(window=int(period), min_periods=int(period)).mean()
    return {"volume": volume, "vol_ma": vol_ma}


def _obv(df: pd.DataFrame) -> pd.Series:
    prepared = _prepare(df)
    direction = np.sign(prepared["close"].diff()).fillna(0)
    return (prepared["volume"] * direction).cumsum()


def _compute_indicator(key: IndicatorKey, df: pd.DataFrame, params: Dict[str, int | float]) -> Dict[str, pd.Series]:
    if key == IndicatorKey.MA:
        return {"ma": _ma(df, int(params.get("period", 5)))}
    if key == IndicatorKey.MACD:
        return _macd(
            df,
            fast=int(params.get("fast", 12)),
            slow=int(params.get("slow", 26)),
            signal=int(params.get("signal", 9)),
        )
    if key == IndicatorKey.RSI:
        return {"rsi": _rsi(df, int(params.get("period", 14)))}
    if key == IndicatorKey.KDJ:
        return _kdj(
            df,
            period=int(params.get("period", 9)),
            k_smooth=int(params.get("k_smooth", 3)),
            d_smooth=int(params.get("d_smooth", 3)),
        )
    if key == IndicatorKey.BOLL:
        return _boll(
            df,
            period=int(params.get("period", 20)),
            multiplier=float(params.get("multiplier", 2.0)),
        )
    if key == IndicatorKey.VOL:
        return _vol(df, int(params.get("period", 5)))
    if key == IndicatorKey.OBV:
        return {"obv": _obv(df)}
    raise ValueError(f"Unsupported indicator: {key}")


def _latest_non_nan(series: pd.Series):
    if series is None or not isinstance(series, pd.Series) or series.empty:
        return None
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return cleaned.iloc[-1]


def _tail_pair(series: pd.Series) -> Tuple[float | None, float | None]:
    cleaned = series.dropna()
    if len(cleaned) < 2:
        return None, None
    return float(cleaned.iloc[-2]), float(cleaned.iloc[-1])


def _max_lookback_for_conditions(conditions: Iterable[IndicatorKey]) -> int:
    mapping = {
        IndicatorKey.MA: 250,
        IndicatorKey.MACD: 250,
        IndicatorKey.RSI: 250,
        IndicatorKey.KDJ: 120,
        IndicatorKey.BOLL: 120,
        IndicatorKey.VOL: 120,
        IndicatorKey.OBV: 250,
    }
    return max(mapping.get(condition, 250) for condition in conditions)


class StockScreenerService:
    """Service backing multi-market technical screening."""

    def __init__(self, manager=None):
        if manager is None:
            from data_provider import DataFetcherManager  # type: ignore

            manager = DataFetcherManager()
        self._manager = manager
        config = get_config()
        configured_workers = int(getattr(config, "max_workers", 3) or 3)
        self._max_workers = max(1, min(configured_workers, 8))
        self._formula_engine = StockFormulaEngine()

    def formula_function_catalog(self) -> List[FormulaFunctionMeta]:
        return self._formula_engine.list_functions()

    def validate_formula(self, formula: str) -> FormulaValidationResponse:
        return self._formula_engine.validate(formula)

    def indicator_catalog(self) -> List[IndicatorMeta]:
        return [
            IndicatorMeta(
                key=IndicatorKey.MA,
                name="MA 移动平均",
                category="趋势",
                params=[IndicatorParamMeta(name="period", label="周期", type="int", default=5, min=1, max=250)],
                outputs=[IndicatorOutputMeta(key="ma", label="MA")],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.MACD,
                name="MACD 指标",
                category="趋势",
                params=[
                    IndicatorParamMeta(name="fast", label="快线", type="int", default=12),
                    IndicatorParamMeta(name="slow", label="慢线", type="int", default=26),
                    IndicatorParamMeta(name="signal", label="平滑", type="int", default=9),
                ],
                outputs=[
                    IndicatorOutputMeta(key="macd", label="Diff"),
                    IndicatorOutputMeta(key="signal", label="Dea"),
                    IndicatorOutputMeta(key="hist", label="柱子"),
                ],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.RSI,
                name="RSI 相对强弱",
                category="摆动",
                params=[IndicatorParamMeta(name="period", label="周期", type="int", default=14, min=2, max=250)],
                outputs=[IndicatorOutputMeta(key="rsi", label="RSI")],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.KDJ,
                name="KDJ 随机指标",
                category="摆动",
                params=[
                    IndicatorParamMeta(name="period", label="周期", type="int", default=9),
                    IndicatorParamMeta(name="k_smooth", label="K 平滑", type="int", default=3),
                    IndicatorParamMeta(name="d_smooth", label="D 平滑", type="int", default=3),
                ],
                outputs=[
                    IndicatorOutputMeta(key="k", label="K"),
                    IndicatorOutputMeta(key="d", label="D"),
                    IndicatorOutputMeta(key="j", label="J"),
                ],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.BOLL,
                name="BOLL 布林带",
                category="通道",
                params=[
                    IndicatorParamMeta(name="period", label="周期", type="int", default=20),
                    IndicatorParamMeta(name="multiplier", label="倍数", type="float", default=2.0),
                ],
                outputs=[
                    IndicatorOutputMeta(key="upper", label="上轨"),
                    IndicatorOutputMeta(key="mid", label="中轨"),
                    IndicatorOutputMeta(key="lower", label="下轨"),
                    IndicatorOutputMeta(key="bandwidth", label="带宽"),
                    IndicatorOutputMeta(key="percent_b", label="%B"),
                ],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.VOL,
                name="VOL 成交量",
                category="能量",
                params=[IndicatorParamMeta(name="period", label="均量周期", type="int", default=5)],
                outputs=[
                    IndicatorOutputMeta(key="volume", label="量"),
                    IndicatorOutputMeta(key="vol_ma", label="均量"),
                ],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.OBV,
                name="OBV 能量潮",
                category="能量",
                params=[],
                outputs=[IndicatorOutputMeta(key="obv", label="OBV")],
                operators=[op.value for op in Operator],
            ),
        ]

    def scan(
        self,
        request: ScreenerScanRequest,
        progress_callback: Optional[Callable[[int, int, int, str], None]] = None,
    ) -> ScreenerScanResponse:
        if request.market != MarketType.CN and request.board_filters:
            raise ValueError("board filters are only supported for cn market")

        lookback = request.lookback_days or 250
        universe = self._build_universe(request)
        parsed_formula: Optional[FormulaParseResult] = None
        if request.mode == ScreenerMode.FORMULA and request.formula:
            parsed_formula = self._formula_engine.parse(request.formula)
            lookback = max(lookback, parsed_formula.estimated_lookback)
        else:
            lookback = max(lookback, _max_lookback_for_conditions([c.indicator for c in request.conditions or []]))
        total_candidates = len(universe)

        if progress_callback is not None:
            if total_candidates == 0:
                progress_callback(0, 0, 0, "股票池为空，没有可扫描的标的")
            else:
                progress_callback(0, total_candidates, 0, f"股票池准备完成，共 {total_candidates} 只标的待扫描")

        results: List[ScreenerScanResultItem] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                executor.submit(self._evaluate_stock, basic, request, lookback)
                if parsed_formula is None else
                executor.submit(self._evaluate_stock, basic, request, lookback, parsed_formula)
                for basic in universe
            ]
            scanned = 0
            for future in as_completed(futures):
                try:
                    item = future.result()
                except Exception as exc:  # pragma: no cover - defensive log
                    logger.debug("stock screener worker failed: %s", exc, exc_info=True)
                    scanned += 1
                    if progress_callback is not None:
                        progress_callback(scanned, total_candidates, len(results), f"正在扫描 {scanned}/{total_candidates}，当前命中 {len(results)} 条")
                    continue
                if item is not None:
                    results.append(item)
                scanned += 1
                if progress_callback is not None:
                    progress_callback(scanned, total_candidates, len(results), f"正在扫描 {scanned}/{total_candidates}，当前命中 {len(results)} 条")

        reverse = request.sort_dir.lower() != "asc"
        sort_key = self._build_sort_key(request.sort_by)
        results.sort(key=sort_key, reverse=reverse)
        total = len(results)
        sliced = results[request.offset: request.offset + request.limit]
        csv_payload = self._to_csv(sliced) if request.export_csv else None
        if progress_callback is not None:
            progress_callback(total_candidates, total_candidates, total, f"扫描完成，共命中 {total} 条")
        return ScreenerScanResponse(total=total, results=sliced, csv=csv_payload)

    def _build_universe(self, request: ScreenerScanRequest) -> List[StockBasic]:
        if request.codes:
            return self._build_custom_universe(request.codes, request.market)
        if request.market != MarketType.CN:
            raise ValueError("hk/us scan requires explicit codes; full-market list is only available for cn")
        return self._list_a_share()

    def _list_a_share(self) -> List[StockBasic]:
        for fetcher in getattr(self._manager, "_fetchers", []):
            if not hasattr(fetcher, "get_stock_list"):
                continue
            try:
                df = fetcher.get_stock_list()
                if df is None or df.empty:
                    continue
                code_col = next((c for c in df.columns if str(c).lower() in {"code", "代码"}), None)
                name_col = next((c for c in df.columns if str(c).lower() in {"name", "名称", "code_name"}), None)
                if not code_col or not name_col:
                    continue
                basics: List[StockBasic] = []
                for _, row in df.iterrows():
                    code = str(row.get(code_col, "")).strip()
                    name = str(row.get(name_col, "")).strip()
                    if code and name:
                        basics.append(StockBasic(code=code, name=name))
                if basics:
                    return basics
            except Exception:
                continue

        try:
            from src.data.stock_mapping import STOCK_NAME_MAP  # type: ignore

            return [StockBasic(code=code, name=name) for code, name in STOCK_NAME_MAP.items() if code and name and code.isdigit() and len(code) == 6]
        except Exception:
            return []

    def _build_custom_universe(self, codes: List[str], market: MarketType) -> List[StockBasic]:
        basics: List[StockBasic] = []
        invalid_codes: List[str] = []
        seen: set[str] = set()

        for code in codes:
            normalized = self._normalize_code_for_market(code, market)
            if normalized is None:
                invalid_codes.append(str(code))
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            basics.append(StockBasic(code=normalized, name=self._resolve_name(normalized)))

        if invalid_codes:
            raise ValueError(f"invalid {market.value} codes: {', '.join(invalid_codes)}")
        if not basics:
            raise ValueError("codes cannot be empty after normalization")
        return basics

    def _normalize_code_for_market(self, code: str, market: MarketType) -> Optional[str]:
        from data_provider.base import canonical_stock_code, normalize_stock_code  # type: ignore
        from data_provider.us_index_mapping import is_us_stock_code  # type: ignore

        raw = (code or "").strip()
        if not raw:
            return None

        normalized = normalize_stock_code(canonical_stock_code(raw))
        if market == MarketType.CN:
            return normalized if normalized.isdigit() and len(normalized) == 6 else None
        if market == MarketType.HK:
            hk_code = normalized.upper()
            if hk_code.startswith("HK"):
                hk_code = hk_code[2:]
            return hk_code.zfill(5) if hk_code.isdigit() and 1 <= len(hk_code) <= 5 else None
        if market == MarketType.US:
            us_code = normalized.upper()
            return us_code if is_us_stock_code(us_code) else None
        return None

    def _resolve_name(self, code: str) -> str:
        try:
            name = self._manager.get_stock_name(code)
            if name:
                return name
        except Exception:
            pass
        return code

    def _get_history(self, code: str, lookback: int) -> Tuple[pd.DataFrame, str]:
        return self._manager.get_daily_data(code, days=lookback)

    def _get_boards(self, code: str) -> List[str]:
        try:
            boards = self._manager.get_belong_boards(code)
            return [item.get("name", "") for item in boards if item.get("name")]
        except Exception:
            return []

    def _evaluate_stock(
        self,
        basic: StockBasic,
        request: ScreenerScanRequest,
        lookback: int,
        parsed_formula: Optional[FormulaParseResult] = None,
    ) -> Optional[ScreenerScanResultItem]:
        try:
            df, source = self._get_history(basic.code, lookback)
        except Exception:
            return None
        if df is None or df.empty:
            return None

        boards: List[str] = []
        if request.board_filters:
            boards = self._get_boards(basic.code)
            if boards and not set(request.board_filters).intersection(set(boards)):
                return None
            if not boards:
                return None

        heat = self._compute_heat(df)
        if request.volume_heat_ratio is not None and heat is not None and heat < request.volume_heat_ratio:
            return None

        if request.mode == ScreenerMode.FORMULA and request.formula:
            formula_match = self._evaluate_formula(df, request.formula, request.formula_name, parsed_formula)
            if not formula_match[0]:
                return None
            matched = formula_match[1]
        else:
            ok, matched = self._evaluate_conditions(df, request.conditions or [])
            if not ok:
                return None

        last_close = float(df["close"].dropna().iloc[-1]) if "close" in df else 0.0
        return ScreenerScanResultItem(
            code=basic.code,
            name=basic.name or self._resolve_name(basic.code),
            last_close=last_close,
            data_source=source,
            matched_conditions=matched,
            boards=boards,
            heat=heat,
        )

    def _evaluate_formula(
        self,
        df: pd.DataFrame,
        formula: str,
        formula_name: Optional[str],
        parsed_formula: Optional[FormulaParseResult] = None,
    ) -> Tuple[bool, List[str]]:
        try:
            result = self._formula_engine.evaluate_parsed(parsed_formula or self._formula_engine.parse(formula), df)
        except FormulaValidationError as exc:
            raise ValueError(str(exc)) from exc
        description = formula_name.strip() if formula_name else result.description
        return result.matched, [description]

    def _compute_heat(self, df: pd.DataFrame) -> Optional[float]:
        try:
            volume = df["volume"].dropna()
            if len(volume) < 10:
                return None
            recent = volume.tail(1).iloc[0]
            base = volume.tail(20).mean()
            if base == 0:
                return None
            return float(recent / base)
        except Exception:
            return None

    def _evaluate_conditions(
        self,
        df: pd.DataFrame,
        conditions: List[IndicatorCondition],
    ) -> Tuple[bool, List[str]]:
        computed_cache: Dict[tuple, Dict[str, pd.Series]] = {}
        matched_desc: List[str] = []
        overall: Optional[bool] = None

        for condition in conditions:
            left_series = self._get_indicator_series(df, condition, computed_cache)
            if left_series is None:
                return False, []

            target_value = None
            target_series = None
            if condition.compare_to.type == CompareType.VALUE:
                target_value = condition.compare_to.value
            else:
                target_series = self._get_indicator_series(
                    df,
                    IndicatorCondition(
                        indicator=condition.compare_to.indicator,
                        params=condition.compare_to.params,
                        output=condition.compare_to.output,
                        operator=condition.operator,
                        compare_to=condition.compare_to,
                        logic_with_previous=condition.logic_with_previous,
                    ),
                    computed_cache,
                )
                if target_series is None:
                    return False, []

            is_hit, description = self._compare(left_series, target_value, target_series, condition)
            matched_desc.append(description)

            if overall is None:
                overall = is_hit
            elif condition.logic_with_previous == LogicOp.AND:
                overall = overall and is_hit
            else:
                overall = overall or is_hit

        return bool(overall), matched_desc

    def _get_indicator_series(
        self,
        df: pd.DataFrame,
        condition: IndicatorCondition,
        cache: Dict[tuple, Dict[str, pd.Series]],
    ) -> Optional[pd.Series]:
        key = (condition.indicator, tuple(sorted(condition.params.items())))
        if key not in cache:
            cache[key] = _compute_indicator(condition.indicator, df, condition.params)
        outputs = cache[key]
        field = condition.output or self._default_output(condition.indicator)
        return outputs.get(field)

    def _compare(
        self,
        left: pd.Series,
        target_value: Optional[float],
        right: Optional[pd.Series],
        condition: IndicatorCondition,
    ) -> Tuple[bool, str]:
        description = f"{condition.indicator} {condition.operator.value}"

        if condition.operator in (Operator.CROSS_UP, Operator.CROSS_DOWN):
            if right is None:
                return False, description
            left_prev, left_curr = _tail_pair(left)
            right_prev, right_curr = _tail_pair(right)
            if None in (left_prev, left_curr, right_prev, right_curr):
                return False, description
            if condition.operator == Operator.CROSS_UP:
                matched = left_prev <= right_prev and left_curr > right_curr
            else:
                matched = left_prev >= right_prev and left_curr < right_curr
            return matched, description

        left_now = _latest_non_nan(left)
        if left_now is None:
            return False, description

        if right is not None:
            target_value = _latest_non_nan(right)
        if target_value is None:
            return False, description

        if condition.operator == Operator.GT:
            matched = left_now > target_value
        elif condition.operator == Operator.GTE:
            matched = left_now >= target_value
        elif condition.operator == Operator.LT:
            matched = left_now < target_value
        elif condition.operator == Operator.LTE:
            matched = left_now <= target_value
        elif condition.operator == Operator.EQ:
            matched = abs(left_now - target_value) < 1e-6
        else:
            matched = False

        return matched, f"{description} {float(left_now):.3f} vs {float(target_value):.3f}"

    @staticmethod
    def _default_output(indicator: IndicatorKey) -> str:
        mapping = {
            IndicatorKey.MA: "ma",
            IndicatorKey.MACD: "macd",
            IndicatorKey.RSI: "rsi",
            IndicatorKey.KDJ: "k",
            IndicatorKey.BOLL: "mid",
            IndicatorKey.VOL: "volume",
            IndicatorKey.OBV: "obv",
        }
        return mapping.get(indicator, "value")

    @staticmethod
    def _build_sort_key(field: str):
        def sorter(item: ScreenerScanResultItem):
            if field == "code":
                return item.code
            if field == "name":
                return item.name
            if field == "heat":
                return item.heat or 0
            return item.last_close

        return sorter

    @staticmethod
    def _to_csv(items: List[ScreenerScanResultItem]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["code", "name", "last_close", "data_source", "heat", "matched_conditions", "boards"])
        for item in items:
            writer.writerow(
                [
                    item.code,
                    item.name,
                    f"{item.last_close:.2f}",
                    item.data_source,
                    f"{item.heat:.2f}" if item.heat is not None else "",
                    " | ".join(item.matched_conditions),
                    ",".join(item.boards),
                ]
            )
        return output.getvalue()
