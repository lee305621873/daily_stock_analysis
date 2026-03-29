# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
3. 定义技术指标选股模型
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class StockQuote(BaseModel):
    """股票实时行情"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
    update_time: Optional[str] = Field(None, description="更新时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "current_price": 1800.00,
                "change": 15.00,
                "change_percent": 0.84,
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "prev_close": 1785.00,
                "volume": 10000000,
                "amount": 18000000000,
                "update_time": "2024-01-01T15:00:00"
            }
        }


class KLineData(BaseModel):
    """K 线数据点"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-01",
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "close": 1800.00,
                "volume": 10000000,
                "amount": 18000000000,
                "change_percent": 0.84
            }
        }


class ExtractItem(BaseModel):
    """单条提取结果（代码、名称、置信度）"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片股票代码提取响应"""

    codes: List[str] = Field(..., description="提取的股票代码（已去重，向后兼容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取结果明细（代码+名称+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应（调试用）")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: str = Field(..., description="K 线周期")
    data: List[KLineData] = Field(default_factory=list, description="K 线数据列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "period": "daily",
                "data": []
            }
        }


class BrokerRecommendationItem(BaseModel):
    """单只月度金股聚合结果。"""

    rank: int = Field(..., description="按券商覆盖数排序后的名次")
    code: str = Field(..., description="展示用股票代码")
    ts_code: str = Field(..., description="Tushare 股票代码")
    name: Optional[str] = Field(None, description="股票名称")
    market: str = Field(..., description="市场：cn/hk/us")
    broker_count: int = Field(..., description="覆盖该股票的券商数量")
    brokers: List[str] = Field(default_factory=list, description="券商名称列表")


class BrokerRecommendationBrokerPick(BaseModel):
    """单家券商名下的一只推荐股。"""

    rank: int = Field(..., description="该股票在按股票聚合视图中的名次")
    code: str = Field(..., description="展示用股票代码")
    ts_code: str = Field(..., description="Tushare 股票代码")
    name: Optional[str] = Field(None, description="股票名称")
    market: str = Field(..., description="市场：cn/hk/us")
    broker_count: int = Field(..., description="该股票被多少家券商共同推荐")


class BrokerRecommendationBrokerItem(BaseModel):
    """单家券商的月度推荐聚合结果。"""

    rank: int = Field(..., description="按荐股数量排序后的名次")
    broker: str = Field(..., description="券商名称")
    pick_count: int = Field(..., description="该券商当月推荐股票数")
    picks: List[BrokerRecommendationBrokerPick] = Field(default_factory=list, description="该券商推荐的股票列表")


class BrokerRecommendationResponse(BaseModel):
    """券商月度金股聚合响应。"""

    month: Optional[str] = Field(None, description="月份，格式 YYYYMM")
    updated_at: Optional[str] = Field(None, description="本地缓存更新时间")
    available_months: List[str] = Field(default_factory=list, description="已缓存月份列表")
    broker_total: int = Field(0, description="当月覆盖券商数")
    total_picks: int = Field(0, description="当月聚合后的股票数")
    items: List[BrokerRecommendationItem] = Field(default_factory=list, description="按券商覆盖数排序后的股票列表")
    brokers: List[BrokerRecommendationBrokerItem] = Field(default_factory=list, description="按荐股数量排序后的券商列表")


class IndicatorKey(str, Enum):
    MA = "MA"
    MACD = "MACD"
    RSI = "RSI"
    KDJ = "KDJ"
    BOLL = "BOLL"
    VOL = "VOL"
    OBV = "OBV"
    HEAT = "HEAT"
    PE = "PE"
    PB = "PB"
    PEG = "PEG"
    ROE = "ROE"
    REVENUE_YOY = "REVENUE_YOY"
    NET_PROFIT_YOY = "NET_PROFIT_YOY"


class Operator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "="
    CROSS_UP = "cross_up"
    CROSS_DOWN = "cross_down"


class LogicOp(str, Enum):
    AND = "AND"
    OR = "OR"


class CompareType(str, Enum):
    VALUE = "value"
    INDICATOR = "indicator"


class MarketType(str, Enum):
    CN = "cn"
    HK = "hk"
    US = "us"


class ScreenerTaskStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ScreenerMode(str, Enum):
    CONDITION = "condition"
    FORMULA = "formula"
    HYBRID = "hybrid"


class ScreenerScopeKind(str, Enum):
    FULL_MARKET = "full_market"
    PRESET_POOL = "preset_pool"
    BOARD = "board"
    BOARD_DYNAMIC = "board_dynamic"
    CUSTOM_POOL = "custom_pool"


class ScreenerBoardType(str, Enum):
    INDUSTRY = "industry"
    CONCEPT = "concept"


class IndicatorParamMeta(BaseModel):
    name: str
    label: str
    type: str
    default: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class IndicatorOutputMeta(BaseModel):
    key: str
    label: str


class IndicatorMeta(BaseModel):
    key: IndicatorKey
    name: str
    category: str
    summary: Optional[str] = None
    params: List[IndicatorParamMeta] = Field(default_factory=list)
    outputs: List[IndicatorOutputMeta] = Field(default_factory=list)
    operators: List[str] = Field(default_factory=list)


class ScreenerScopeOption(BaseModel):
    key: str
    market: MarketType
    label: str
    description: str
    kind: ScreenerScopeKind
    estimated_count: Optional[int] = None
    preview_codes: List[str] = Field(default_factory=list)
    board_name: Optional[str] = None
    board_type: Optional[ScreenerBoardType] = None


class ScreenerBoardTier(BaseModel):
    key: str
    label: str
    count: int
    codes: List[str] = Field(default_factory=list)


class ScreenerBoardOption(BaseModel):
    market: MarketType
    board_type: ScreenerBoardType
    board_name: str
    label: str
    estimated_count: Optional[int] = None
    description: Optional[str] = None
    tier_summary: Optional[str] = None
    tiers: List[ScreenerBoardTier] = Field(default_factory=list)


class ScreenerBoardPreview(BaseModel):
    market: MarketType
    board_type: ScreenerBoardType
    board_name: str
    estimated_count: Optional[int] = None
    preview_codes: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    tier_summary: Optional[str] = None
    tiers: List[ScreenerBoardTier] = Field(default_factory=list)


class ScreenerBoardConstituent(BaseModel):
    code: str
    name: Optional[str] = None


class ScreenerBoardConstituentResponse(BaseModel):
    market: MarketType
    board_type: ScreenerBoardType
    board_name: str
    total: int
    source: str
    items: List[ScreenerBoardConstituent] = Field(default_factory=list)


class CompareTo(BaseModel):
    type: CompareType = Field(default=CompareType.VALUE)
    value: Optional[float] = Field(default=None, description="Literal threshold")
    indicator: Optional[IndicatorKey] = Field(default=None, description="Secondary indicator key")
    params: Dict[str, Any] = Field(default_factory=dict, description="Params for the secondary indicator")
    output: Optional[str] = Field(default=None, description="Which output field of the secondary indicator")

    @validator("indicator", always=True)
    def ensure_indicator_when_needed(cls, v, values):
        if values.get("type") == CompareType.INDICATOR and v is None:
            raise ValueError("indicator must be provided when type=indicator")
        return v


class IndicatorCondition(BaseModel):
    indicator: IndicatorKey
    params: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[str] = Field(default=None)
    operator: Operator = Field(default=Operator.GT)
    compare_to: CompareTo = Field(default_factory=CompareTo)
    logic_with_previous: LogicOp = Field(default=LogicOp.AND)


class ScreenerScanRequest(BaseModel):
    mode: ScreenerMode = Field(default=ScreenerMode.CONDITION, description="condition | formula | hybrid")
    conditions: Optional[List[IndicatorCondition]] = Field(default=None)
    formula: Optional[str] = Field(default=None, description="Formula expression used when mode=formula")
    formula_name: Optional[str] = Field(default=None, description="Optional human-readable formula name")
    market: MarketType = Field(default=MarketType.CN, description="Universe market: cn | hk | us")
    scope: Optional[str] = Field(default=None, description="Universe scope key returned by screener scope catalog")
    board_filters: Optional[List[str]] = Field(default=None)
    board_name: Optional[str] = Field(default=None, description="Dynamic CN board name when scope requires board selection")
    board_type: Optional[ScreenerBoardType] = Field(default=None, description="Dynamic CN board type: industry | concept")
    volume_heat_ratio: Optional[float] = Field(default=None)
    scan_limit: Optional[int] = Field(default=None, ge=1, le=2000, description="Max candidate stocks to scan")
    limit: int = Field(default=200, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)
    export_csv: bool = Field(default=False)
    codes: Optional[List[str]] = Field(default=None)
    lookback_days: Optional[int] = Field(default=None)
    sort_by: str = Field(default="last_close", description="last_close | heat | code | name")
    sort_dir: str = Field(default="desc", description="asc | desc")
    async_mode: bool = Field(default=False, description="Whether to run as background task")

    @root_validator(skip_on_failure=True)
    def validate_scan_mode(cls, values):
        mode = values.get("mode") or ScreenerMode.CONDITION
        conditions = values.get("conditions") or []
        formula = (values.get("formula") or "").strip()
        board_name = (values.get("board_name") or "").strip()

        if mode == ScreenerMode.FORMULA:
            if not formula:
                raise ValueError("formula cannot be empty when mode=formula")
            values["formula"] = formula
        elif mode == ScreenerMode.CONDITION:
            if not conditions:
                raise ValueError("conditions cannot be empty when mode=condition")
        elif mode == ScreenerMode.HYBRID:
            if not conditions:
                raise ValueError("conditions cannot be empty when mode=hybrid")
            if not formula:
                raise ValueError("formula cannot be empty when mode=hybrid")
            values["formula"] = formula
        if board_name:
            values["board_name"] = board_name
        return values


class ScreenerScanResultItem(BaseModel):
    code: str
    name: str
    last_close: float
    data_source: str
    matched_conditions: List[str] = Field(default_factory=list)
    boards: List[str] = Field(default_factory=list)
    heat: Optional[float] = None


class ScreenerExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"


class ScreenerExportScope(str, Enum):
    ALL = "all"
    PAGE = "page"


class ScreenerScanResponse(BaseModel):
    total: int
    results: List[ScreenerScanResultItem] = Field(default_factory=list)
    csv: Optional[str] = None


class ScreenerRowsExportRequest(BaseModel):
    format: ScreenerExportFormat = Field(default=ScreenerExportFormat.XLSX)
    items: List[ScreenerScanResultItem] = Field(default_factory=list)
    filename: Optional[str] = Field(default=None)


class ScreenerTaskAccepted(BaseModel):
    task_id: str
    status: ScreenerTaskStatusEnum = Field(default=ScreenerTaskStatusEnum.PENDING)
    message: str


class ScreenerTaskInfo(BaseModel):
    task_id: str
    market: MarketType
    status: ScreenerTaskStatusEnum
    progress: int = Field(0, ge=0, le=100)
    scanned_count: int = Field(0, ge=0)
    total_count: int = Field(0, ge=0)
    matched_count: int = Field(0, ge=0)
    message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class ScreenerTaskStatusResponse(ScreenerTaskInfo):
    result: Optional[ScreenerScanResponse] = None


class FormulaFunctionParamMeta(BaseModel):
    name: str
    type: str
    description: str
    optional: bool = False


class FormulaFunctionMeta(BaseModel):
    name: str
    category: str
    summary: str
    signature: str
    returns: str
    examples: List[str] = Field(default_factory=list)
    params: List[FormulaFunctionParamMeta] = Field(default_factory=list)


class FormulaValidationRequest(BaseModel):
    formula: str = Field(..., min_length=1)


class FormulaValidationResponse(BaseModel):
    valid: bool
    normalized_formula: str
    referenced_fields: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    function_usage: Dict[str, int] = Field(default_factory=dict)
    expression_nodes: int = Field(default=0, ge=0)
    complexity_score: int = Field(default=0, ge=0)
    complexity_level: str = Field(default="medium", description="low | medium | high")
    message: str
    estimated_lookback: int = Field(default=250, ge=1)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class ScreenerFormulaTemplate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ScreenerFormulaTemplateUpsertRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
    label: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1)

    @validator("id")
    def normalize_id(cls, v):
        if v is None:
            return None
        normalized = str(v).strip()
        return normalized or None


class ScreenerFormulaTemplateDeleteResponse(BaseModel):
    id: str
    deleted: bool
