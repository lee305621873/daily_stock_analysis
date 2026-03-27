import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  ScreenerBoardConstituentResponse,
  ScreenerBoardOption,
  ScreenerBoardPreview,
  ScreenerFormulaTemplate,
  ScreenerFormulaTemplateDeleteResponse,
  ScreenerFormulaTemplateUpsertRequest,
  FormulaFunctionMeta,
  FormulaValidationResponse,
  ScreenerExportFormat,
  ScreenerExportScope,
  IndicatorMeta,
  ScreenerScanRequest,
  ScreenerScanResultItem,
  ScreenerScanResponse,
  ScreenerScopeOption,
  ScreenerTaskAccepted,
  ScreenerTaskStatusResponse,
} from '../types/screener';

export const screenerApi = {
  async getScopes(market?: string): Promise<ScreenerScopeOption[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/scopes', {
      params: market ? { market } : undefined,
    });
    return toCamelCase<ScreenerScopeOption[]>(response.data);
  },

  async getBoards(market: string, boardType: string): Promise<ScreenerBoardOption[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/boards', {
      params: { market, board_type: boardType },
    });
    return toCamelCase<ScreenerBoardOption[]>(response.data);
  },

  async getBoardPreview(market: string, boardType: string, boardName: string, limit = 20): Promise<ScreenerBoardPreview> {
    const response = await apiClient.get('/api/v1/stocks/screener/boards/preview', {
      params: { market, board_type: boardType, board_name: boardName, limit },
    });
    return toCamelCase<ScreenerBoardPreview>(response.data);
  },

  async getBoardConstituents(market: string, boardType: string, boardName: string): Promise<ScreenerBoardConstituentResponse> {
    const response = await apiClient.get('/api/v1/stocks/screener/boards/constituents', {
      params: { market, board_type: boardType, board_name: boardName },
    });
    return toCamelCase<ScreenerBoardConstituentResponse>(response.data);
  },

  async getIndicators(): Promise<IndicatorMeta[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/indicators');
    return toCamelCase<IndicatorMeta[]>(response.data);
  },

  async getFormulaFunctions(): Promise<FormulaFunctionMeta[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/formula/functions');
    return toCamelCase<FormulaFunctionMeta[]>(response.data);
  },

  async listFormulaTemplates(): Promise<ScreenerFormulaTemplate[]> {
    const response = await apiClient.get('/api/v1/stocks/screener/formula/templates');
    return toCamelCase<ScreenerFormulaTemplate[]>(response.data);
  },

  async upsertFormulaTemplate(payload: ScreenerFormulaTemplateUpsertRequest): Promise<ScreenerFormulaTemplate> {
    const response = await apiClient.post('/api/v1/stocks/screener/formula/templates', {
      id: payload.id,
      label: payload.label,
      value: payload.value,
    });
    return toCamelCase<ScreenerFormulaTemplate>(response.data);
  },

  async deleteFormulaTemplate(templateId: string): Promise<ScreenerFormulaTemplateDeleteResponse> {
    const response = await apiClient.delete(`/api/v1/stocks/screener/formula/templates/${encodeURIComponent(templateId)}`);
    return toCamelCase<ScreenerFormulaTemplateDeleteResponse>(response.data);
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
      scope: payload.scope,
      board_filters: payload.boardFilters,
      board_name: payload.boardName,
      board_type: payload.boardType,
      volume_heat_ratio: payload.volumeHeatRatio,
      scan_limit: payload.scanLimit,
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

  async exportTaskResults(taskId: string, format: ScreenerExportFormat = 'xlsx', scope: ScreenerExportScope = 'all'): Promise<Blob> {
    const response = await apiClient.get(`/api/v1/stocks/screener/tasks/${taskId}/export`, {
      params: { format, scope },
      responseType: 'blob',
    });
    return response.data as Blob;
  },

  async exportRows(items: ScreenerScanResultItem[], format: ScreenerExportFormat = 'xlsx', filename?: string): Promise<Blob> {
    const response = await apiClient.post(
      '/api/v1/stocks/screener/export/rows',
      { format, items, filename },
      { responseType: 'blob' },
    );
    return response.data as Blob;
  },
};
