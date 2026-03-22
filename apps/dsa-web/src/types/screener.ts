export type IndicatorKey = 'MA' | 'MACD' | 'RSI' | 'KDJ' | 'BOLL' | 'VOL' | 'OBV';
export type Operator = '>' | '>=' | '<' | '<=' | '=' | 'cross_up' | 'cross_down';
export type LogicOp = 'AND' | 'OR';
export type MarketType = 'cn' | 'hk' | 'us';
export type ScreenerMode = 'condition' | 'formula';
export type ScreenerScopeKind = 'full_market' | 'preset_pool' | 'board' | 'board_dynamic' | 'custom_pool';
export type ScreenerBoardType = 'industry' | 'concept';
export type ScreenerTaskStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ScreenerTaskEventType =
  | 'connected'
  | 'task_created'
  | 'task_started'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  | 'heartbeat';

export interface IndicatorParamMeta {
  name: string;
  label: string;
  type: 'int' | 'float';
  default?: number;
  min?: number;
  max?: number;
}

export interface IndicatorOutputMeta {
  key: string;
  label: string;
}

export interface IndicatorMeta {
  key: IndicatorKey;
  name: string;
  category: string;
  summary?: string;
  params: IndicatorParamMeta[];
  outputs: IndicatorOutputMeta[];
  operators: Operator[];
}

export interface CompareTo {
  type: 'value' | 'indicator';
  value?: number;
  indicator?: IndicatorKey;
  params?: Record<string, number>;
  output?: string;
}

export interface ScreenerCondition {
  indicator: IndicatorKey;
  params: Record<string, number>;
  output?: string;
  operator: Operator;
  compareTo: CompareTo;
  logicWithPrevious: LogicOp;
}

export interface ScreenerScanRequest {
  mode?: ScreenerMode;
  conditions?: ScreenerCondition[];
  formula?: string;
  formulaName?: string;
  market?: MarketType;
  scope?: string;
  boardFilters?: string[];
  boardName?: string;
  boardType?: ScreenerBoardType;
  volumeHeatRatio?: number;
  scanLimit?: number;
  limit?: number;
  offset?: number;
  exportCsv?: boolean;
  codes?: string[];
  lookbackDays?: number;
  sortBy?: 'lastClose' | 'heat' | 'code' | 'name';
  sortDir?: 'asc' | 'desc';
  asyncMode?: boolean;
}

export interface ScreenerScopeOption {
  key: string;
  market: MarketType;
  label: string;
  description: string;
  kind: ScreenerScopeKind;
  estimatedCount?: number | null;
  previewCodes: string[];
  boardName?: string | null;
  boardType?: ScreenerBoardType | null;
}

export interface ScreenerBoardTier {
  key: string;
  label: string;
  count: number;
  codes: string[];
}

export interface ScreenerBoardOption {
  market: MarketType;
  boardType: ScreenerBoardType;
  boardName: string;
  label: string;
  estimatedCount?: number | null;
  description?: string | null;
  tierSummary?: string | null;
  tiers?: ScreenerBoardTier[] | null;
}

export interface ScreenerBoardPreview {
  market: MarketType;
  boardType: ScreenerBoardType;
  boardName: string;
  estimatedCount?: number | null;
  previewCodes: string[];
  description?: string | null;
  tierSummary?: string | null;
  tiers?: ScreenerBoardTier[] | null;
}

export interface ScreenerBoardConstituent {
  code: string;
  name?: string | null;
}

export interface ScreenerBoardConstituentResponse {
  market: MarketType;
  boardType: ScreenerBoardType;
  boardName: string;
  total: number;
  source: string;
  items: ScreenerBoardConstituent[];
}

export interface ScreenerScanResultItem {
  code: string;
  name: string;
  lastClose: number;
  dataSource: string;
  matchedConditions: string[];
  boards: string[];
  heat?: number | null;
}

export interface ScreenerScanResponse {
  total: number;
  results: ScreenerScanResultItem[];
  csv?: string | null;
}

export interface ScreenerTaskAccepted {
  taskId: string;
  status: ScreenerTaskStatus;
  message: string;
}

export interface ScreenerTaskInfo {
  taskId: string;
  market: MarketType;
  status: ScreenerTaskStatus;
  progress: number;
  scannedCount: number;
  totalCount: number;
  matchedCount: number;
  message?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  error?: string | null;
}

export interface ScreenerTaskStatusResponse extends ScreenerTaskInfo {
  result?: ScreenerScanResponse | null;
}

export interface FormulaFunctionParamMeta {
  name: string;
  type: string;
  description: string;
  optional?: boolean;
}

export interface FormulaFunctionMeta {
  name: string;
  category: string;
  summary: string;
  signature: string;
  returns: string;
  examples: string[];
  params: FormulaFunctionParamMeta[];
}

export interface FormulaValidationResponse {
  valid: boolean;
  normalizedFormula: string;
  referencedFields: string[];
  functions: string[];
  message: string;
  estimatedLookback: number;
  warnings: string[];
}
