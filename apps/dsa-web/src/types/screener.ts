export type IndicatorKey = 'MA' | 'MACD' | 'RSI' | 'KDJ' | 'BOLL' | 'VOL' | 'OBV';
export type Operator = '>' | '>=' | '<' | '<=' | '=' | 'cross_up' | 'cross_down';
export type LogicOp = 'AND' | 'OR';
export type MarketType = 'cn' | 'hk' | 'us';
export type ScreenerMode = 'condition' | 'formula';
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
  boardFilters?: string[];
  volumeHeatRatio?: number;
  limit?: number;
  offset?: number;
  exportCsv?: boolean;
  codes?: string[];
  lookbackDays?: number;
  sortBy?: 'lastClose' | 'heat' | 'code' | 'name';
  sortDir?: 'asc' | 'desc';
  asyncMode?: boolean;
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
