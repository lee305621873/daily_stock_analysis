import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  FormulaFunctionMeta,
  FormulaValidationResponse,
  IndicatorMeta,
  ScreenerScanRequest,
  ScreenerScanResponse,
  ScreenerTaskAccepted,
  ScreenerTaskStatusResponse,
} from '../types/screener';

export const screenerApi = {
  async getIndicators(): Promise<IndicatorMeta[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/indicators');
    return toCamelCase<IndicatorMeta[]>(response.data);
  },

  async getFormulaFunctions(): Promise<FormulaFunctionMeta[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/formula/functions');
    return toCamelCase<FormulaFunctionMeta[]>(response.data);
  },

  async validateFormula(formula: string): Promise<FormulaValidationResponse> {
    const response = await apiClient.post('/api/v1/stocks/screener/formula/validate', { formula });
    return toCamelCase<FormulaValidationResponse>(response.data);
  },

  async scan(payload: ScreenerScanRequest): Promise<ScreenerScanResponse | ScreenerTaskAccepted> {
    const requestData: Record<string, unknown> = {
      mode: payload.mode || 'condition',
      conditions: payload.conditions?.map((condition) => ({
        indicator: condition.indicator,
        params: condition.params,
        output: condition.output,
        operator: condition.operator,
        compare_to: {
          type: condition.compareTo.type,
          value: condition.compareTo.value,
          indicator: condition.compareTo.indicator,
          params: condition.compareTo.params,
          output: condition.compareTo.output,
        },
        logic_with_previous: condition.logicWithPrevious,
      })),
      formula: payload.formula,
      formula_name: payload.formulaName,
      market: payload.market,
      board_filters: payload.boardFilters,
      volume_heat_ratio: payload.volumeHeatRatio,
      limit: payload.limit,
      offset: payload.offset,
      export_csv: payload.exportCsv,
      codes: payload.codes,
      lookback_days: payload.lookbackDays,
      sort_by: payload.sortBy === 'lastClose' ? 'last_close' : payload.sortBy,
      sort_dir: payload.sortDir,
      async_mode: payload.asyncMode,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/scan', requestData, {
      timeout: payload.asyncMode ? 30000 : 120000,
      validateStatus: (status) => status === 200 || status === 202,
    });
    return response.status === 202
      ? toCamelCase<ScreenerTaskAccepted>(response.data)
      : toCamelCase<ScreenerScanResponse>(response.data);
  },

  async getTaskStatus(taskId: string): Promise<ScreenerTaskStatusResponse> {
    const response = await apiClient.get(`/api/v1/stocks/screener/tasks/${taskId}`);
    const data = toCamelCase<ScreenerTaskStatusResponse>(response.data);
    if (data.result) {
      data.result = toCamelCase<ScreenerScanResponse>(data.result);
    }
    return data;
  },

  getTaskStreamUrl(): string {
    const baseUrl = apiClient.defaults.baseURL || '';
    return `${baseUrl}/api/v1/stocks/screener/tasks/stream`;
  },
};
