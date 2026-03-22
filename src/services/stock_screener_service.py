# -*- coding: utf-8 -*-
"""
Technical stock screener service for the main API/Web app.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency for metadata-only mode
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional dependency for metadata-only mode
    pd = None  # type: ignore

try:
    import requests
except Exception:  # pragma: no cover - optional dependency for metadata-only mode
    requests = None  # type: ignore

from api.v1.schemas.stocks import (
    ScreenerBoardConstituent,
    ScreenerBoardConstituentResponse,
    ScreenerBoardOption,
    ScreenerBoardPreview,
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
    ScreenerBoardType,
    ScreenerMode,
    ScreenerScopeKind,
    ScreenerScopeOption,
    ScreenerScanRequest,
    ScreenerScanResponse,
    ScreenerScanResultItem,
)
from src.config import get_config
from src.data.stock_screener_board_cache import (
    get_catalog_entries,
    get_constituent_entry,
    get_profile_entry,
    load_board_cache,
    save_board_cache,
    set_catalog_entries,
    set_constituent_entry,
    set_profile_entry,
)
from src.data.stock_screener_board_match_rules import OVERSEAS_BOARD_MATCH_RULES
from src.data.stock_screener_scope_config import STOCK_SCREENER_DYNAMIC_BOARD_CONFIG, STOCK_SCREENER_SCOPE_CONFIG
from src.services.stock_formula_engine import FormulaParseResult, FormulaValidationError, StockFormulaEngine

logger = logging.getLogger(__name__)
_BOARD_CACHE_WRITE_LOCK = threading.Lock()


def _ensure_screener_runtime_deps(require_requests: bool = False) -> None:
    global np, pd, requests
    if np is None:
        import numpy as _np  # type: ignore

        np = _np
    if pd is None:
        import pandas as _pd  # type: ignore

        pd = _pd
    if require_requests and requests is None:
        import requests as _requests  # type: ignore

        requests = _requests


def _is_tushare_permission_error(message: str) -> bool:
    lowered = str(message or "").lower()
    return "没有接口访问权限" in str(message or "") or "doc_id=108" in lowered


@contextmanager
def _temporary_env_overrides(overrides: Dict[str, Optional[str]]):
    original: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            original[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass
class StockBasic:
    code: str
    name: str


def _build_preview_basics(codes: List[str]) -> List[StockBasic]:
    return [StockBasic(code=str(code).strip(), name=str(code).strip()) for code in codes if str(code).strip()]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    _ensure_screener_runtime_deps()
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
    _ensure_screener_runtime_deps()
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


def _scope_market_key(market: MarketType) -> str:
    return market.value if isinstance(market, MarketType) else str(market)


def _parse_optional_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        if pd is not None:
            try:
                if pd.isna(value):
                    return None
            except Exception:
                pass
        return int(float(value))
    except Exception:
        return None


def _fallback_cn_board_catalog(board_type: str) -> List[Dict[str, Any]]:
    boards: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for scope in STOCK_SCREENER_SCOPE_CONFIG.get("cn", []):
        if str(scope.get("kind") or "") != "board":
            continue
        if str(scope.get("board_type") or "") != board_type:
            continue
        board_name = str(scope.get("board_name") or "").strip()
        if not board_name or board_name in seen:
            continue
        seen.add(board_name)
        fallback_codes = [str(code).strip() for code in list(scope.get("fallback_codes") or []) if str(code).strip()]
        boards.append(
            {
                "board_name": board_name,
                "label": str(scope.get("label") or board_name),
                "board_code": None,
                "estimated_count": len(fallback_codes) or None,
                "description": str(scope.get("description") or "").strip() or None,
            }
        )
    return boards


def _extract_board_codes(board: Dict[str, Any]) -> List[str]:
    direct_codes = list(board.get("codes") or [])
    if direct_codes:
        return direct_codes

    codes: List[str] = []
    for tier in board.get("tiers") or []:
        codes.extend(list((tier or {}).get("codes") or []))
    return codes


def _build_board_tier_summary(board: Dict[str, Any]) -> Optional[str]:
    parts: List[str] = []
    for tier in board.get("tiers") or []:
        label = str((tier or {}).get("label") or "").strip()
        codes = list((tier or {}).get("codes") or [])
        if label and codes:
            parts.append(f"{label} {len(codes)}")
    return " / ".join(parts) if parts else None


def _build_board_tiers(board: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tiers: List[Dict[str, Any]] = []
    for tier in (board or {}).get("tiers") or []:
        tier_key = str((tier or {}).get("key") or "").strip()
        tier_label = str((tier or {}).get("label") or "").strip()
        codes = [str(code).strip() for code in list((tier or {}).get("codes") or []) if str(code).strip()]
        if not tier_label and not tier_key and not codes:
            continue
        tiers.append(
            {
                "key": tier_key or tier_label or f"tier_{len(tiers) + 1}",
                "label": tier_label or tier_key or f"Tier {len(tiers) + 1}",
                "count": len(codes),
                "codes": codes,
            }
        )
    return tiers


def _merge_stock_basics(*groups: Iterable[StockBasic]) -> List[StockBasic]:
    basics: List[StockBasic] = []
    seen: set[str] = set()
    for group in groups:
        for basic in group:
            code = str(getattr(basic, "code", "") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            name = str(getattr(basic, "name", "") or "").strip()
            basics.append(StockBasic(code=code, name=name or code))
    return basics


def _profile_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _keywords_match(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(str(keyword or "").strip().lower() in lowered for keyword in keywords if str(keyword or "").strip())


def _normalize_tushare_code(raw_code: str) -> str:
    text = str(raw_code or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _recent_trade_dates(days: int = 10) -> List[str]:
    base = datetime.now()
    return [(base - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(days)]


@lru_cache(maxsize=128)
def _fetch_cn_board_constituents(board_type: str, board_name: str) -> Tuple[List[Tuple[str, str]], str]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(f"akshare unavailable: {exc}") from exc

    if board_type == "industry":
        df = ak.stock_board_industry_cons_em(symbol=board_name)
    elif board_type == "concept":
        df = ak.stock_board_concept_cons_em(symbol=board_name)
    else:
        raise ValueError(f"unsupported board type: {board_type}")

    if df is None or df.empty:
        return [], "akshare"

    code_col = next((col for col in df.columns if str(col) in {"代码", "code"}), None)
    name_col = next((col for col in df.columns if str(col) in {"名称", "name"}), None)
    if code_col is None:
        raise ValueError(f"unexpected board constituent columns: {list(df.columns)}")

    basics: List[Tuple[str, str]] = []
    for _, row in df.iterrows():
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip() if name_col else code
        if code:
            basics.append((code, name))
    return basics, "akshare"


@lru_cache(maxsize=8)
def _fetch_cn_board_catalog(board_type: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(f"akshare unavailable: {exc}") from exc

    if board_type == ScreenerBoardType.INDUSTRY.value:
        df = ak.stock_board_industry_name_em()
    elif board_type == ScreenerBoardType.CONCEPT.value:
        df = ak.stock_board_concept_name_em()
    else:
        raise ValueError(f"unsupported board type: {board_type}")

    if df is None or df.empty:
        return [], "akshare"

    name_col = next((col for col in df.columns if str(col) in {"板块名称", "板块", "名称", "name"}), None)
    if name_col is None:
        raise ValueError(f"unexpected board catalog columns: {list(df.columns)}")

    code_col = next((col for col in df.columns if str(col) in {"板块代码", "代码", "code"}), None)
    total_col = next((col for col in df.columns if str(col) in {"总家数", "成分股数量", "股票家数", "家数"}), None)
    rise_col = next((col for col in df.columns if str(col) in {"上涨家数", "上涨"}), None)
    fall_col = next((col for col in df.columns if str(col) in {"下跌家数", "下跌"}), None)

    boards: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        board_name = str(row.get(name_col, "")).strip()
        if not board_name or board_name in seen:
            continue
        seen.add(board_name)
        estimated_count = _parse_optional_int(row.get(total_col)) if total_col else None
        if estimated_count is None and rise_col and fall_col:
            rise_count = _parse_optional_int(row.get(rise_col))
            fall_count = _parse_optional_int(row.get(fall_col))
            if rise_count is not None and fall_count is not None:
                estimated_count = rise_count + fall_count
        boards.append(
            {
                "board_name": board_name,
                "label": board_name,
                "board_code": str(row.get(code_col, "")).strip() if code_col else None,
                "estimated_count": estimated_count,
            }
        )
    return boards, "akshare"


def _candidate_code_columns(df) -> List[str]:
    candidates = {"代码", "code", "代码symbol", "symbol", "ticker", "代码/名称"}
    return [str(col) for col in df.columns if str(col).strip().lower() in {item.lower() for item in candidates}]


class StockScreenerService:
    """Service backing multi-market technical screening."""

    def __init__(self, manager=None):
        self._manager = manager
        config = get_config()
        configured_workers = int(getattr(config, "max_workers", 3) or 3)
        self._max_workers = max(1, min(configured_workers, 8))
        self._formula_engine = StockFormulaEngine()

    def _get_manager(self):
        if self._manager is None:
            from data_provider import DataFetcherManager  # type: ignore

            self._manager = DataFetcherManager()
        return self._manager

    def _load_board_cache(self) -> Dict[str, Any]:
        return load_board_cache()

    def _get_cached_board_catalog(self, market: MarketType, board_type: str) -> List[Dict[str, Any]]:
        cache = self._load_board_cache()
        return get_catalog_entries(cache, market.value, board_type)

    def _get_cached_board_entry(
        self,
        market: MarketType,
        board_type: str,
        board_name: str,
    ) -> Optional[Dict[str, Any]]:
        cache = self._load_board_cache()
        return get_constituent_entry(cache, market.value, board_type, board_name)

    @staticmethod
    def _cached_entry_to_basics(entry: Optional[Dict[str, Any]]) -> List[StockBasic]:
        basics: List[StockBasic] = []
        seen: set[str] = set()
        for item in list((entry or {}).get("items") or []):
            code = str((item or {}).get("code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            name = str((item or {}).get("name") or "").strip()
            basics.append(StockBasic(code=code, name=name or code))
        return basics

    def _save_board_cache(self, cache: Dict[str, Any]) -> None:
        with _BOARD_CACHE_WRITE_LOCK:
            save_board_cache(cache)

    def _persist_board_catalog_rows(
        self,
        market: MarketType,
        board_type: str,
        rows: List[Dict[str, Any]],
        source: str,
        cache: Optional[Dict[str, Any]] = None,
    ) -> None:
        target_cache = cache if cache is not None else self._load_board_cache()
        updated_at = datetime.now(timezone.utc).isoformat()
        set_catalog_entries(
            target_cache,
            market.value,
            board_type,
            [
                {
                    "board_name": str(row.get("board_name") or ""),
                    "label": str(row.get("label") or row.get("board_name") or ""),
                    "estimated_count": row.get("estimated_count"),
                    "description": row.get("description"),
                    "tier_summary": row.get("tier_summary"),
                    "tiers": row.get("tiers") or [],
                    "source": str(row.get("source") or source),
                    "updated_at": updated_at,
                }
                for row in rows
                if str(row.get("board_name") or "").strip()
            ],
        )
        if cache is None:
            self._save_board_cache(target_cache)

    def _persist_board_basics(
        self,
        market: MarketType,
        board_type: str,
        board_name: str,
        basics: List[StockBasic],
        source: str,
        description: Optional[str] = None,
        tier_summary: Optional[str] = None,
        tiers: Optional[List[Dict[str, Any]]] = None,
        cache: Optional[Dict[str, Any]] = None,
    ) -> None:
        target_cache = cache if cache is not None else self._load_board_cache()
        updated_at = datetime.now(timezone.utc).isoformat()
        set_constituent_entry(
            target_cache,
            market.value,
            board_type,
            board_name,
            {
                "market": market.value,
                "board_type": board_type,
                "board_name": board_name,
                "description": description,
                "tier_summary": tier_summary,
                "tiers": tiers or [],
                "items": [{"code": item.code, "name": item.name} for item in basics],
                "source": source,
                "updated_at": updated_at,
            },
        )
        if cache is None:
            self._save_board_cache(target_cache)

    @staticmethod
    def _profile_entry_text(profile: Dict[str, Any]) -> Dict[str, str]:
        return {
            "name": _profile_text(profile.get("name")),
            "sector": _profile_text(profile.get("sector") or profile.get("sector_key")),
            "industry": _profile_text(profile.get("industry") or profile.get("industry_key")),
            "all": " ".join(
                filter(
                    None,
                    [
                        _profile_text(profile.get("name")),
                        _profile_text(profile.get("sector")),
                        _profile_text(profile.get("sector_key")),
                        _profile_text(profile.get("industry")),
                        _profile_text(profile.get("industry_key")),
                    ],
                )
            ),
        }

    def _get_overseas_board_rule(self, market: MarketType, board_type: str, board_name: str) -> Optional[Dict[str, Any]]:
        return (
            OVERSEAS_BOARD_MATCH_RULES
            .get(_scope_market_key(market), {})
            .get(board_type, {})
            .get((board_name or "").strip())
        )

    def _profile_matches_board(self, profile: Dict[str, Any], rule: Dict[str, Any]) -> bool:
        if not profile or not rule:
            return False
        bundle = self._profile_entry_text(profile)
        exclude_keywords = list(rule.get("exclude_keywords") or [])
        if exclude_keywords and _keywords_match(bundle["all"], exclude_keywords):
            return False
        sector_keywords = list(rule.get("sector_keywords") or [])
        industry_keywords = list(rule.get("industry_keywords") or [])
        name_keywords = list(rule.get("name_keywords") or [])
        if not sector_keywords and not industry_keywords and not name_keywords:
            return _keywords_match(bundle["all"], list(rule.get("keywords") or []))
        matches = [
            _keywords_match(bundle["industry"], industry_keywords) if industry_keywords else False,
            _keywords_match(bundle["name"], name_keywords) if name_keywords else False,
            _keywords_match(bundle["sector"], sector_keywords) if sector_keywords else False,
        ]
        return any(matches)

    def formula_function_catalog(self) -> List[FormulaFunctionMeta]:
        return self._formula_engine.list_functions()

    def validate_formula(self, formula: str) -> FormulaValidationResponse:
        try:
            return self._formula_engine.validate(formula)
        except FormulaValidationError as exc:
            normalized_formula = (formula or "").strip()
            return FormulaValidationResponse(
                valid=False,
                normalized_formula=normalized_formula,
                referenced_fields=[],
                functions=[],
                message=str(exc),
                estimated_lookback=self._formula_engine.DEFAULT_LOOKBACK,
                warnings=[],
            )

    def _market_list_column(self, df, market: MarketType, kind: str) -> Optional[str]:
        candidates: Dict[str, List[str]] = {
            "code": ["代码", "code", "symbol", "ticker"],
            "name": ["名称", "name", "简称", "公司名称"],
        }
        for candidate in candidates.get(kind, []):
            for column in df.columns:
                if str(column).strip().lower() == candidate.lower():
                    return str(column)
        sample_limit = min(len(df.index), 30)
        for column in df.columns:
            values = [str(value or "").strip() for value in df[column].head(sample_limit).tolist()]
            non_empty = [value for value in values if value]
            if not non_empty:
                continue
            if kind == "code":
                valid = sum(1 for value in non_empty if self._normalize_code_for_market(value, market) is not None)
                if valid >= max(3, len(non_empty) // 2):
                    return str(column)
            if kind == "name":
                valid = sum(1 for value in non_empty if any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in value))
                if valid >= max(3, len(non_empty) // 2):
                    return str(column)
        return None

    def _fetch_overseas_market_symbols(
        self,
        market: MarketType,
        limit: Optional[int] = None,
    ) -> Tuple[List[StockBasic], str]:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(f"akshare unavailable: {exc}") from exc

        fetchers: List[Tuple[str, Callable[[], Any]]] = []
        if market == MarketType.HK:
            fetchers = [("akshare_hk_spot_em", ak.stock_hk_spot_em)]
        elif market == MarketType.US:
            if hasattr(ak, "stock_us_spot_em"):
                fetchers.append(("akshare_us_spot_em", ak.stock_us_spot_em))
            if hasattr(ak, "stock_us_spot"):
                fetchers.append(("akshare_us_spot", ak.stock_us_spot))
        else:
            raise ValueError(f"unsupported overseas market: {market.value}")

        last_error: Optional[Exception] = None
        for source, fetcher in fetchers:
            try:
                df = fetcher()
            except Exception as exc:
                last_error = exc
                logger.warning("Failed to load %s market list from %s: %s", market.value.upper(), source, exc)
                continue
            if df is None or df.empty:
                continue
            code_col = self._market_list_column(df, market, "code")
            name_col = self._market_list_column(df, market, "name")
            if code_col is None:
                continue
            basics: List[StockBasic] = []
            seen: set[str] = set()
            for _, row in df.iterrows():
                normalized = self._normalize_code_for_market(row.get(code_col, ""), market)
                if normalized is None or normalized in seen:
                    continue
                seen.add(normalized)
                raw_name = str(row.get(name_col, "")).strip() if name_col else ""
                basics.append(StockBasic(code=normalized, name=raw_name or normalized))
                if limit is not None and len(basics) >= limit:
                    break
            if basics:
                return basics, source
        if last_error is not None:
            raise RuntimeError(f"failed to load {market.value.upper()} market symbols: {last_error}") from last_error
        return [], "empty"

    def _yfinance_symbol_for_market(self, code: str, market: MarketType) -> str:
        normalized = self._normalize_code_for_market(code, market)
        if normalized is None:
            raise ValueError(f"invalid {market.value} code: {code}")
        if market == MarketType.HK:
            return f"{int(normalized):04d}.HK"
        return normalized

    def _load_cached_profile_entry(self, cache: Dict[str, Any], market: MarketType, code: str) -> Optional[Dict[str, Any]]:
        entry = get_profile_entry(cache, market.value, code)
        return entry if isinstance(entry, dict) else None

    def _fetch_yfinance_profile(self, market: MarketType, basic: StockBasic) -> Optional[Dict[str, Any]]:
        try:
            import yfinance as yf  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(f"yfinance unavailable: {exc}") from exc

        symbol = self._yfinance_symbol_for_market(basic.code, market)
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.get_info() if hasattr(ticker, "get_info") else ticker.info
        except Exception as exc:
            logger.debug("Failed to load yfinance profile for %s (%s): %s", basic.code, symbol, exc)
            return None
        if not isinstance(info, dict):
            return None
        return {
            "code": basic.code,
            "symbol": symbol,
            "name": str(info.get("shortName") or info.get("longName") or basic.name or basic.code).strip(),
            "sector": str(info.get("sector") or "").strip(),
            "sector_key": str(info.get("sectorKey") or "").strip(),
            "industry": str(info.get("industry") or "").strip(),
            "industry_key": str(info.get("industryKey") or "").strip(),
            "quote_type": str(info.get("quoteType") or "").strip(),
            "source": "yfinance",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_overseas_market_board_snapshots(
        self,
        market: MarketType,
        board_type: str = ScreenerBoardType.INDUSTRY.value,
        cache: Optional[Dict[str, Any]] = None,
        profile_limit: Optional[int] = None,
    ) -> Tuple[Dict[str, Dict[str, Any]], str]:
        if market == MarketType.CN:
            raise ValueError("CN market does not use overseas board snapshots")

        target_cache = cache if cache is not None else self._load_board_cache()
        boards = list(STOCK_SCREENER_DYNAMIC_BOARD_CONFIG.get(_scope_market_key(market), {}).get(board_type, []))
        if not boards:
            return {}, "config"

        market_basics, market_source = self._fetch_overseas_market_symbols(market, limit=profile_limit)
        if not market_basics:
            return {}, market_source

        cached_profiles: Dict[str, Dict[str, Any]] = {}
        missing_basics: List[StockBasic] = []
        for basic in market_basics:
            cached_profile = self._load_cached_profile_entry(target_cache, market, basic.code)
            if cached_profile is None:
                missing_basics.append(basic)
            else:
                cached_profiles[basic.code] = cached_profile

        if missing_basics:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                future_map = {executor.submit(self._fetch_yfinance_profile, market, basic): basic for basic in missing_basics}
                for future in as_completed(future_map):
                    basic = future_map[future]
                    try:
                        profile = future.result()
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.debug("Failed to fetch yfinance profile for %s: %s", basic.code, exc, exc_info=True)
                        continue
                    if not profile:
                        continue
                    cached_profiles[basic.code] = profile
                    set_profile_entry(target_cache, market.value, basic.code, profile)

        snapshots: Dict[str, Dict[str, Any]] = {}
        for board in boards:
            board_name = str(board.get("board_name") or "").strip()
            if not board_name:
                continue
            rule = self._get_overseas_board_rule(market, board_type, board_name)
            live_basics: List[StockBasic] = []
            if rule:
                for basic in market_basics:
                    profile = cached_profiles.get(basic.code)
                    if not profile or not self._profile_matches_board(profile, rule):
                        continue
                    live_basics.append(
                        StockBasic(
                            code=basic.code,
                            name=str(profile.get("name") or basic.name or basic.code).strip() or basic.code,
                        )
                    )
            seed_basics: List[StockBasic] = []
            seen_seed_codes: set[str] = set()
            for code in _extract_board_codes(board):
                normalized = self._normalize_code_for_market(code, market)
                if normalized is None or normalized in seen_seed_codes:
                    continue
                seen_seed_codes.add(normalized)
                seed_basics.append(StockBasic(code=normalized, name=normalized))
            merged_basics = _merge_stock_basics(live_basics, seed_basics)
            source = f"{market_source}+yfinance" if live_basics else "config"
            snapshots[board_name] = {
                "board_name": board_name,
                "label": str(board.get("label") or board_name),
                "description": board.get("description"),
                "tier_summary": _build_board_tier_summary(board),
                "tiers": _build_board_tiers(board),
                "estimated_count": len(merged_basics),
                "items": [{"code": item.code, "name": item.name} for item in merged_basics],
                "source": source,
                "live_count": len(live_basics),
            }

        if cache is None:
            self._save_board_cache(target_cache)
        return snapshots, market_source

    def indicator_catalog(self) -> List[IndicatorMeta]:
        return [
            IndicatorMeta(
                key=IndicatorKey.MA,
                name="MA 移动平均",
                category="趋势",
                summary="用收盘价均值观察趋势方向，常用于均线支撑、跌破和金叉/死叉判断。",
                params=[IndicatorParamMeta(name="period", label="周期", type="int", default=5, min=1, max=250)],
                outputs=[IndicatorOutputMeta(key="ma", label="MA")],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.MACD,
                name="MACD 指标",
                category="趋势",
                summary="衡量趋势强弱和动量变化，适合找趋势启动、背离和零轴上方增强。",
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
                summary="判断超买超卖与反弹/回落节奏，常见阈值是 30 和 70。",
                params=[IndicatorParamMeta(name="period", label="周期", type="int", default=14, min=2, max=250)],
                outputs=[IndicatorOutputMeta(key="rsi", label="RSI")],
                operators=[op.value for op in Operator],
            ),
            IndicatorMeta(
                key=IndicatorKey.KDJ,
                name="KDJ 随机指标",
                category="摆动",
                summary="适合观察短线拐点与钝化，J 值波动最大，K/D 更平滑。",
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
                summary="通过中轨和上下轨判断波动区间，适合看突破、收口和回归均值。",
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
                summary="比较当前成交量和均量，适合判断放量突破、缩量整理和量价配合。",
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
                summary="把涨跌方向与成交量累积起来，适合看资金持续流入流出趋势。",
                params=[],
                outputs=[IndicatorOutputMeta(key="obv", label="OBV")],
                operators=[op.value for op in Operator],
            ),
        ]

    def scope_catalog(self, market: Optional[MarketType] = None) -> List[ScreenerScopeOption]:
        markets = [market] if market is not None else [MarketType.CN, MarketType.HK, MarketType.US]
        options: List[ScreenerScopeOption] = []
        for current_market in markets:
            for scope in STOCK_SCREENER_SCOPE_CONFIG.get(_scope_market_key(current_market), []):
                preview_basics = self._preview_scope_basics(current_market, scope)
                estimated_count = len(preview_basics) if preview_basics else None
                options.append(
                    ScreenerScopeOption(
                        key=str(scope["key"]),
                        market=current_market,
                        label=str(scope["label"]),
                        description=str(scope["description"]),
                        kind=ScreenerScopeKind(str(scope["kind"])),
                        estimated_count=estimated_count,
                        preview_codes=[item.code for item in preview_basics[:20]],
                        board_name=scope.get("board_name"),
                        board_type=scope.get("board_type"),
                    )
                )
        return options

    def board_catalog(self, market: MarketType, board_type: ScreenerBoardType) -> List[ScreenerBoardOption]:
        cached_rows = self._get_cached_board_catalog(market, board_type.value)
        if cached_rows:
            return [
                ScreenerBoardOption(
                    market=market,
                    board_type=board_type,
                    board_name=str(row["board_name"]),
                    label=str(row.get("label") or row["board_name"]),
                    estimated_count=row.get("estimated_count"),
                    description=row.get("description"),
                    tier_summary=row.get("tier_summary"),
                    tiers=row.get("tiers") or [],
                )
                for row in cached_rows
            ]
        if market == MarketType.CN:
            try:
                rows, source = _fetch_cn_board_catalog(board_type.value)
            except Exception as exc:
                rows = _fallback_cn_board_catalog(board_type.value)
                if not rows:
                    raise
                source = "config_fallback"
                logger.warning("Falling back to configured CN %s boards: %s", board_type.value, exc)
            logger.info("Loaded %s CN %s boards from %s", len(rows), board_type.value, source)
        else:
            rows = list(STOCK_SCREENER_DYNAMIC_BOARD_CONFIG.get(_scope_market_key(market), {}).get(board_type.value, []))
            source = "config"
            if not rows:
                raise ValueError(f"{market.value} market does not support dynamic {board_type.value} boards")
            rows = [
                {
                    **row,
                    "estimated_count": len(_extract_board_codes(row)),
                    "tier_summary": _build_board_tier_summary(row),
                    "tiers": _build_board_tiers(row),
                }
                for row in rows
            ]
            logger.info("Loaded %s %s %s boards from %s", len(rows), market.value.upper(), board_type.value, source)
        self._persist_board_catalog_rows(market, board_type.value, rows, source)
        return [
            ScreenerBoardOption(
                market=market,
                board_type=board_type,
                board_name=str(row["board_name"]),
                label=str(row.get("label") or row["board_name"]),
                estimated_count=row.get("estimated_count"),
                description=row.get("description"),
                tier_summary=row.get("tier_summary"),
                tiers=row.get("tiers") or [],
            )
            for row in rows
        ]

    def board_preview(
        self,
        market: MarketType,
        board_type: ScreenerBoardType,
        board_name: str,
        limit: int = 20,
    ) -> ScreenerBoardPreview:
        board_name = (board_name or "").strip()
        if not board_name:
            raise ValueError("board_name cannot be empty")

        cached_entry = self._get_cached_board_entry(market, board_type.value, board_name)
        if cached_entry is not None:
            basics = self._cached_entry_to_basics(cached_entry)
            return ScreenerBoardPreview(
                market=market,
                board_type=board_type,
                board_name=board_name,
                estimated_count=len(basics),
                preview_codes=[item.code for item in basics[: max(1, limit)]],
                description=cached_entry.get("description"),
                tier_summary=cached_entry.get("tier_summary"),
                tiers=cached_entry.get("tiers") or [],
            )

        board = self._get_dynamic_board_definition(market, board_type.value, board_name) if market != MarketType.CN else None
        scope = self._find_board_scope_definition(market, board_type.value, board_name) if market == MarketType.CN else None
        if market == MarketType.CN:
            basics, _ = self._load_cn_board_basics(
                board_type.value,
                board_name,
                list((scope or {}).get("fallback_codes") or []),
            )
        else:
            basics = self._build_board_universe(market, board_type.value, board_name)
        return ScreenerBoardPreview(
            market=market,
            board_type=board_type,
            board_name=board_name,
            estimated_count=len(basics),
            preview_codes=[item.code for item in basics[: max(1, limit)]],
            description=(board or scope or {}).get("description"),
            tier_summary=_build_board_tier_summary(board) if board else None,
            tiers=_build_board_tiers(board),
        )

    def board_constituents(
        self,
        market: MarketType,
        board_type: ScreenerBoardType,
        board_name: str,
        allow_fallback: bool = True,
    ) -> ScreenerBoardConstituentResponse:
        normalized_board_name = (board_name or "").strip()
        if not normalized_board_name:
            raise ValueError("board_name cannot be empty")

        cached_entry = self._get_cached_board_entry(market, board_type.value, normalized_board_name)
        if cached_entry is not None:
            basics = self._cached_entry_to_basics(cached_entry)
            return ScreenerBoardConstituentResponse(
                market=market,
                board_type=board_type,
                board_name=normalized_board_name,
                total=len(basics),
                source=str(cached_entry.get("source") or "cache"),
                items=[ScreenerBoardConstituent(code=item.code, name=item.name) for item in basics],
            )

        if market == MarketType.CN:
            scope = self._find_board_scope_definition(market, board_type.value, normalized_board_name)
            basics, source = self._load_cn_board_basics(
                board_type.value,
                normalized_board_name,
                list((scope or {}).get("fallback_codes") or []) if allow_fallback else [],
            )
            board_meta = scope or {}
        else:
            basics = self._build_board_universe(market, board_type.value, normalized_board_name)
            board_meta = self._get_dynamic_board_definition(market, board_type.value, normalized_board_name) or {}
            source = str((self._get_cached_board_entry(market, board_type.value, normalized_board_name) or {}).get("source") or "config")

        self._persist_board_basics(
            market,
            board_type.value,
            normalized_board_name,
            basics,
            source,
            description=board_meta.get("description"),
            tier_summary=_build_board_tier_summary(board_meta) if board_meta else None,
            tiers=_build_board_tiers(board_meta),
        )

        return ScreenerBoardConstituentResponse(
            market=market,
            board_type=board_type,
            board_name=normalized_board_name,
            total=len(basics),
            source=source,
            items=[ScreenerBoardConstituent(code=item.code, name=item.name) for item in basics],
        )

    def _get_scope_definition(self, market: MarketType, scope_key: Optional[str]) -> Optional[Dict[str, Any]]:
        if not scope_key:
            return None
        for scope in STOCK_SCREENER_SCOPE_CONFIG.get(_scope_market_key(market), []):
            if scope.get("key") == scope_key:
                return scope
        return None

    def _find_board_scope_definition(
        self,
        market: MarketType,
        board_type: str,
        board_name: str,
    ) -> Optional[Dict[str, Any]]:
        normalized_board_name = (board_name or "").strip()
        normalized_board_type = (board_type or "").strip()
        if not normalized_board_name or not normalized_board_type:
            return None
        for scope in STOCK_SCREENER_SCOPE_CONFIG.get(_scope_market_key(market), []):
            if str(scope.get("kind") or "") != "board":
                continue
            if str(scope.get("board_type") or "").strip() != normalized_board_type:
                continue
            if str(scope.get("board_name") or "").strip() != normalized_board_name:
                continue
            return scope
        return None

    def _find_cn_board_catalog_entry(self, board_type: str, board_name: str) -> Optional[Dict[str, Any]]:
        try:
            rows, _ = _fetch_cn_board_catalog(board_type)
        except Exception:
            return None
        normalized_name = (board_name or "").strip()
        for row in rows:
            if str(row.get("board_name") or "").strip() == normalized_name:
                return row
        return None

    def _tushare_query(self, api_name: str, params: Dict[str, Any], fields: str) -> pd.DataFrame:
        _ensure_screener_runtime_deps(require_requests=True)
        config = get_config()
        token = str(getattr(config, "tushare_token", "") or "").strip()
        if not token:
            raise RuntimeError("TUSHARE_TOKEN not configured")

        response = requests.post(
            "http://api.tushare.pro",
            json={"api_name": api_name, "token": token, "params": params, "fields": fields},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code", -1)) != 0:
            message = str(payload.get("msg") or f"Tushare {api_name} failed")
            if _is_tushare_permission_error(message):
                raise RuntimeError(
                    f"Tushare API 权限不足（api={api_name}）。"
                    "当前 token 无法访问板块相关接口，请升级 Tushare 权限或继续使用 AkShare / 本地回退。"
                )
            raise RuntimeError(message)

        data = payload.get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        if not columns:
            return pd.DataFrame()
        return pd.DataFrame(items, columns=columns)

    def _resolve_tushare_board_ts_code(self, board_type: str, board_name: str) -> str:
        catalog_entry = self._find_cn_board_catalog_entry(board_type, board_name)
        board_code = str((catalog_entry or {}).get("board_code") or "").strip().upper()
        if board_code.startswith("BK"):
            return f"{board_code}.DC"

        last_error: Optional[Exception] = None
        for trade_date in _recent_trade_dates(14):
            try:
                df = self._tushare_query(
                    "dc_index",
                    {"name": board_name, "trade_date": trade_date},
                    "ts_code,name,trade_date",
                )
            except Exception as exc:
                last_error = exc
                continue
            if df is None or df.empty:
                continue
            exact = df[df["name"].astype(str).str.strip() == board_name]
            target = exact if not exact.empty else df
            ts_code = str(target.iloc[0].get("ts_code", "")).strip().upper()
            if ts_code:
                return ts_code

        if last_error is not None:
            if _is_tushare_permission_error(str(last_error)):
                logger.warning("Tushare board code lookup permission denied for %s (%s)", board_name, board_type)
            raise RuntimeError(f"failed to resolve Tushare board code for {board_name}: {last_error}") from last_error
        raise RuntimeError(f"failed to resolve Tushare board code for {board_name}")

    def _fetch_tushare_cn_board_universe(self, board_type: str, board_name: str) -> Tuple[List[StockBasic], str]:
        ts_code = self._resolve_tushare_board_ts_code(board_type, board_name)
        last_error: Optional[Exception] = None
        query_attempts: List[Dict[str, Any]] = [{"ts_code": ts_code, "trade_date": trade_date} for trade_date in _recent_trade_dates(14)]
        query_attempts.append({"ts_code": ts_code})

        for params in query_attempts:
            try:
                df = self._tushare_query("dc_member", params, "con_code,name,con_name,trade_date")
            except Exception as exc:
                last_error = exc
                continue
            if df is None or df.empty:
                continue

            code_col = next((col for col in df.columns if str(col) in {"con_code", "code", "ts_code"}), None)
            name_col = next((col for col in df.columns if str(col) in {"name", "con_name"}), None)
            if code_col is None:
                continue

            basics: List[StockBasic] = []
            seen: set[str] = set()
            for _, row in df.iterrows():
                normalized = self._normalize_code_for_market(_normalize_tushare_code(row.get(code_col, "")), MarketType.CN)
                if normalized is None or normalized in seen:
                    continue
                seen.add(normalized)
                name = str(row.get(name_col, "")).strip() if name_col else ""
                basics.append(StockBasic(code=normalized, name=name or self._resolve_name(normalized)))
            if basics:
                return basics, "tushare"

        if last_error is not None:
            if _is_tushare_permission_error(str(last_error)):
                logger.warning("Tushare board member lookup permission denied for %s (%s)", board_name, board_type)
            raise RuntimeError(f"Tushare board member lookup failed for {board_name}: {last_error}") from last_error
        raise RuntimeError(f"Tushare returned no board constituents for {board_name}")

    def _load_cn_board_basics(
        self,
        board_type: str,
        board_name: str,
        fallback_codes: List[str],
    ) -> Tuple[List[StockBasic], str]:
        last_error: Optional[Exception] = None

        if board_name:
            try:
                basics, source = self._fetch_cn_board_universe(board_type, board_name)
                if basics:
                    return basics, source
            except Exception as exc:
                last_error = exc
                logger.warning("Failed to load CN board constituents from AkShare for %s: %s", board_name, exc)

            try:
                basics, source = self._fetch_tushare_cn_board_universe(board_type, board_name)
                if basics:
                    return basics, source
            except Exception as exc:
                last_error = exc
                logger.warning("Failed to load CN board constituents from Tushare for %s: %s", board_name, exc)

        if fallback_codes:
            return self._build_custom_universe(fallback_codes, MarketType.CN), "fallback"
        if last_error is not None:
            raise last_error
        return [], "empty"

    def _preview_scope_basics(self, market: MarketType, scope: Dict[str, Any]) -> List[StockBasic]:
        kind = str(scope.get("kind") or "")
        if kind in {"preset_pool", "custom_pool"}:
            codes = list(scope.get("codes") or [])
            if not codes:
                return []
            return _build_preview_basics(codes)
        if kind == "board":
            if market == MarketType.CN:
                fallback_codes = list(scope.get("fallback_codes") or [])
                return _build_preview_basics(fallback_codes)
            board_name = str(scope.get("board_name") or "")
            board_type = str(scope.get("board_type") or ScreenerBoardType.INDUSTRY.value)
            if board_name:
                board = self._get_dynamic_board_definition(market, board_type, board_name)
                return _build_preview_basics(_extract_board_codes(board or {}))
        return []

    def _get_dynamic_board_definition(
        self,
        market: MarketType,
        board_type: str,
        board_name: str,
    ) -> Optional[Dict[str, Any]]:
        board_name = (board_name or "").strip()
        if not board_name:
            return None
        boards = STOCK_SCREENER_DYNAMIC_BOARD_CONFIG.get(_scope_market_key(market), {}).get(board_type, [])
        for board in boards:
            if str(board.get("board_name") or "").strip() == board_name:
                return board
        return None

    def _build_market_dynamic_board_universe(self, market: MarketType, board_type: str, board_name: str) -> List[StockBasic]:
        board = self._get_dynamic_board_definition(market, board_type, board_name)
        if board is None:
            raise ValueError(f"未找到 {market.value.upper()} 市场的板块: {board_name}")
        codes = _extract_board_codes(board)
        if not codes:
            return []
        basics = self._build_custom_universe(codes, market)
        self._persist_board_basics(
            market,
            board_type,
            board_name,
            basics,
            "config",
            description=board.get("description"),
            tier_summary=_build_board_tier_summary(board),
            tiers=_build_board_tiers(board),
        )
        return basics

    def _build_board_universe(self, market: MarketType, board_type: str, board_name: str) -> List[StockBasic]:
        cached_entry = self._get_cached_board_entry(market, board_type, board_name)
        cached_basics = self._cached_entry_to_basics(cached_entry)
        if cached_basics:
            return cached_basics
        if market == MarketType.CN:
            scope = self._find_board_scope_definition(market, board_type, board_name)
            return self._build_cn_board_universe(
                board_type,
                board_name,
                list((scope or {}).get("fallback_codes") or []),
            )
        return self._build_market_dynamic_board_universe(market, board_type, board_name)

    def _build_cn_board_universe(self, board_type: str, board_name: str, fallback_codes: List[str]) -> List[StockBasic]:
        basics, source = self._load_cn_board_basics(board_type, board_name, fallback_codes)
        if basics:
            logger.info("Loaded %s CN board constituents for %s from %s", len(basics), board_name, source)
            scope = self._find_board_scope_definition(MarketType.CN, board_type, board_name) or {}
            self._persist_board_basics(
                MarketType.CN,
                board_type,
                board_name,
                basics,
                source,
                description=scope.get("description"),
                tier_summary=None,
                tiers=[],
            )
        return basics

    def _fetch_cn_board_universe(self, board_type: str, board_name: str) -> Tuple[List[StockBasic], str]:
        rows, source = _fetch_cn_board_constituents(board_type, board_name)
        basics: List[StockBasic] = []
        seen: set[str] = set()
        for code, name in rows:
            normalized = self._normalize_code_for_market(code, MarketType.CN)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            basics.append(StockBasic(code=normalized, name=name or self._resolve_name(normalized)))
        return basics, source

    def scan(
        self,
        request: ScreenerScanRequest,
        progress_callback: Optional[Callable[[int, int, int, str], None]] = None,
    ) -> ScreenerScanResponse:
        _ensure_screener_runtime_deps()
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
            universe = self._build_custom_universe(request.codes, request.market)
        elif request.board_name:
            if not request.board_type:
                raise ValueError("board_type is required when board_name is provided")
            universe = self._build_board_universe(request.market, request.board_type.value, request.board_name)
        else:
            scope = self._get_scope_definition(request.market, request.scope)
            if scope is not None:
                kind = str(scope.get("kind") or "")
                if kind == "full_market":
                    if request.market != MarketType.CN:
                        raise ValueError("full-market list is only available for cn")
                    universe = self._list_a_share()
                elif kind == "board":
                    if request.market != MarketType.CN:
                        raise ValueError("board scope is only supported for cn")
                    universe = self._build_cn_board_universe(
                        str(scope.get("board_type") or ""),
                        str(scope.get("board_name") or ""),
                        list(scope.get("fallback_codes") or []),
                    )
                elif kind == "preset_pool":
                    universe = self._build_custom_universe(list(scope.get("codes") or []), request.market)
                elif kind == "board_dynamic":
                    board_name = (request.board_name or "").strip()
                    board_type = request.board_type.value if request.board_type else str(scope.get("board_type") or "")
                    if not board_name:
                        market_label = "A股" if request.market == MarketType.CN else ("港股" if request.market == MarketType.HK else "美股")
                        raise ValueError(f"请选择一个{market_label}板块后再开始扫描")
                    if not board_type:
                        raise ValueError("board_type is required for dynamic board scope")
                    universe = self._build_board_universe(request.market, board_type, board_name)
                elif kind == "custom_pool":
                    raise ValueError("custom pool scope requires explicit codes")
                else:
                    raise ValueError(f"unsupported scope kind: {kind}")
            else:
                if request.market != MarketType.CN:
                    raise ValueError("hk/us scan requires explicit codes or a preset scope; full-market list is only available for cn")
                universe = self._list_a_share()
        if request.scan_limit:
            return universe[: request.scan_limit]
        return universe

    def _list_a_share(self) -> List[StockBasic]:
        manager = self._get_manager()
        for fetcher in getattr(manager, "_fetchers", []):
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
            name = self._get_manager().get_stock_name(code)
            if name:
                return name
        except Exception:
            pass
        return code

    def _get_history(self, code: str, lookback: int) -> Tuple[pd.DataFrame, str]:
        return self._get_manager().get_daily_data(code, days=lookback)

    def _get_boards(self, code: str) -> List[str]:
        try:
            boards = self._get_manager().get_belong_boards(code)
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
