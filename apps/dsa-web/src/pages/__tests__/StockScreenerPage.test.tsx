import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StockScreenerPage from '../StockScreenerPage';
import { screenerApi } from '../../api/screener';
import type {
  ScreenerBoardOption,
  ScreenerBoardPreview,
  FormulaValidationResponse,
  IndicatorMeta,
  ScreenerScanResponse,
  ScreenerScopeOption,
  ScreenerTaskAccepted,
  ScreenerTaskStatusResponse,
} from '../../types/screener';

class MockEventSource {
  static instances: MockEventSource[] = [];

  listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  onerror: ((event: Event) => void) | null = null;
  url: string;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: Record<string, unknown>) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) || []) {
      listener(event);
    }
  }
}

vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);

vi.mock('../../api/screener', () => ({
  screenerApi: {
    getScopes: vi.fn(),
    getBoards: vi.fn(),
    getBoardPreview: vi.fn(),
    getIndicators: vi.fn(),
    getFormulaFunctions: vi.fn(),
    validateFormula: vi.fn(),
    scan: vi.fn(),
    getTaskStatus: vi.fn(),
    getTaskStreamUrl: vi.fn(),
  },
}));

const mockedScreenerApi = vi.mocked(screenerApi);

function getConfigSelect(index: number) {
  return screen.getAllByRole('combobox')[index];
}

const indicatorCatalog: IndicatorMeta[] = [
  {
    key: 'RSI',
    name: 'RSI 相对强弱',
    category: '摆动',
    summary: '衡量超买超卖，常见阈值是 30 和 70。',
    params: [{ name: 'period', label: '周期', type: 'int', default: 14 }],
    outputs: [{ key: 'rsi', label: 'RSI' }],
    operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'],
  },
];

const formulaValidation: FormulaValidationResponse = {
  valid: true,
  normalizedFormula: 'CROSS(MA(CLOSE, 5), MA(CLOSE, 20))',
  referencedFields: ['CLOSE'],
  functions: ['CROSS', 'MA'],
  message: '公式校验通过',
  estimatedLookback: 250,
  warnings: [],
};

const scanResponse: ScreenerScanResponse = {
  total: 1,
  results: [
    {
      code: '600519',
      name: '贵州茅台',
      lastClose: 1888.88,
      dataSource: 'mock',
      matchedConditions: ['RSI < 30'],
      boards: ['白酒'],
      heat: 1.23,
    },
  ],
  csv: 'code,name\n600519,贵州茅台\n',
};

const scopeCatalog: ScreenerScopeOption[] = [
  { key: 'all_market', market: 'cn', label: 'A 股全市场', description: '扫描全部 A 股标的。', kind: 'full_market', estimatedCount: 5000, previewCodes: ['600519', '000001'] },
  { key: 'cn_board_industry_dynamic', market: 'cn', label: 'A 股行业板块（自选）', description: '从真实行业板块目录中选择。', kind: 'board_dynamic', estimatedCount: null, previewCodes: [], boardType: 'industry' },
  { key: 'cn_board_concept_dynamic', market: 'cn', label: 'A 股概念板块（自选）', description: '从真实概念板块目录中选择。', kind: 'board_dynamic', estimatedCount: null, previewCodes: [], boardType: 'concept' },
  { key: 'cn_semiconductor', market: 'cn', label: 'A 股半导体', description: '半导体板块成分股。', kind: 'board', estimatedCount: 132, previewCodes: ['603986', '688041', '688981'], boardName: '半导体', boardType: 'industry' },
  { key: 'custom_pool', market: 'cn', label: '自定义股票池', description: '手工输入 A 股代码。', kind: 'custom_pool', estimatedCount: null, previewCodes: [] },
  { key: 'hk_board_industry_dynamic', market: 'hk', label: '港股行业板块（自选）', description: '从港股行业池中选择。', kind: 'board_dynamic', estimatedCount: null, previewCodes: [], boardType: 'industry' },
  { key: 'hk_finance', market: 'hk', label: '港股金融蓝筹', description: '港股金融蓝筹。', kind: 'preset_pool', estimatedCount: 20, previewCodes: ['00005', '02318', '01299'] },
  { key: 'custom_pool', market: 'hk', label: '自定义股票池', description: '手工输入港股代码。', kind: 'custom_pool', estimatedCount: null, previewCodes: [] },
  { key: 'us_board_industry_dynamic', market: 'us', label: '美股行业板块（自选）', description: '从美股行业池中选择。', kind: 'board_dynamic', estimatedCount: null, previewCodes: [], boardType: 'industry' },
  { key: 'us_semiconductor', market: 'us', label: '美股半导体', description: '美股半导体范围。', kind: 'preset_pool', estimatedCount: 20, previewCodes: ['NVDA', 'AMD', 'AVGO'] },
  { key: 'custom_pool', market: 'us', label: '自定义股票池', description: '手工输入美股代码。', kind: 'custom_pool', estimatedCount: null, previewCodes: [] },
];

const boardCatalog: ScreenerBoardOption[] = [
  { market: 'cn', boardType: 'industry', boardName: '半导体', label: '半导体', estimatedCount: 132, description: '半导体板块真实成分股。', tierSummary: null, tiers: [] },
  { market: 'cn', boardType: 'industry', boardName: '白酒', label: '白酒', estimatedCount: 21, description: '白酒板块真实成分股。', tierSummary: null, tiers: [] },
];

const boardPreview: ScreenerBoardPreview = {
  market: 'cn',
  boardType: 'industry',
  boardName: '半导体',
  estimatedCount: 132,
  previewCodes: ['603986', '688981', '688041'],
  description: '半导体板块真实成分股。',
  tierSummary: null,
  tiers: [],
};

describe('StockScreenerPage', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    mockedScreenerApi.getScopes.mockReset();
    mockedScreenerApi.getBoards.mockReset();
    mockedScreenerApi.getBoardPreview.mockReset();
    mockedScreenerApi.getIndicators.mockReset();
    mockedScreenerApi.getFormulaFunctions.mockReset();
    mockedScreenerApi.validateFormula.mockReset();
    mockedScreenerApi.scan.mockReset();
    mockedScreenerApi.getTaskStatus.mockReset();
    mockedScreenerApi.getTaskStreamUrl.mockReset();
    mockedScreenerApi.getScopes.mockResolvedValue(scopeCatalog);
    mockedScreenerApi.getBoards.mockResolvedValue(boardCatalog);
    mockedScreenerApi.getBoardPreview.mockResolvedValue(boardPreview);
    mockedScreenerApi.getIndicators.mockResolvedValue(indicatorCatalog);
    mockedScreenerApi.getFormulaFunctions.mockResolvedValue([
      {
        name: 'MA',
        category: 'trend',
        summary: 'Moving average',
        signature: 'MA(series, period)',
        returns: 'series',
        examples: ['MA(CLOSE, 5)'],
        params: [],
      },
    ]);
    mockedScreenerApi.validateFormula.mockResolvedValue(formulaValidation);
    mockedScreenerApi.scan.mockResolvedValue(scanResponse);
    mockedScreenerApi.getTaskStreamUrl.mockReturnValue('http://localhost/api/v1/stocks/screener/tasks/stream');
    mockedScreenerApi.getTaskStatus.mockResolvedValue({
      taskId: 'task-001',
      market: 'cn',
      status: 'processing',
      progress: 10,
      scannedCount: 100,
      totalCount: 1000,
      matchedCount: 4,
      message: '正在扫描 100/1000，当前命中 4 条',
      createdAt: '2026-03-20T10:00:00',
      startedAt: '2026-03-20T10:00:01',
      completedAt: null,
      error: null,
      result: null,
    } satisfies ScreenerTaskStatusResponse);
  });

  it('renders the screener call-to-action', async () => {
    render(<StockScreenerPage />);

    expect((await screen.findAllByRole('button', { name: '开始选股' })).length).toBeGreaterThan(0);
    expect(screen.getByText('默认公式选股，开始前会自动校验公式')).toBeTruthy();
    expect(screen.getByText('技术指标选股')).toBeTruthy();
    expect(screen.getByText('公式编辑器')).toBeTruthy();
    expect(getConfigSelect(1)).toBeTruthy();
    const templateSelect = await screen.findByLabelText('示例模板');
    expect((templateSelect as HTMLSelectElement).options.length).toBeGreaterThanOrEqual(21);
  });

  it('shows a validation alert when custom pool is empty and scan is clicked', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(getConfigSelect(0), { target: { value: 'us' } });
    fireEvent.change(getConfigSelect(1), { target: { value: 'custom_pool' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    expect(mockedScreenerApi.scan).not.toHaveBeenCalled();
    expect(await screen.findByText('当前已切换到“自定义股票池”，请先填写美股代码')).toBeTruthy();
  });

  it('requires selecting a real cn board before scanning dynamic board scope', async () => {
    render(<StockScreenerPage />);

    await screen.findByRole('option', { name: 'A 股行业板块（自选）' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'cn_board_industry_dynamic' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    expect(mockedScreenerApi.scan).not.toHaveBeenCalled();
    expect(await screen.findByText('当前扫描范围需要先选择一个A股板块，才能开始扫描。')).toBeTruthy();
  });

  it('uses preset sector pool for us scan and passes scan limit', async () => {
    render(<StockScreenerPage />);

    await waitFor(() => {
      expect(mockedScreenerApi.getScopes).toHaveBeenCalledTimes(1);
    });
    fireEvent.change(getConfigSelect(0), { target: { value: 'us' } });
    fireEvent.change(getConfigSelect(1), { target: { value: 'us_semiconductor' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: /扫描上限/ }), { target: { value: '6' } });
    fireEvent.click((await screen.findAllByRole('button', { name: '开始选股' }))[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          market: 'us',
          scanLimit: 6,
          scope: 'us_semiconductor',
          codes: undefined,
          asyncMode: true,
        }),
      );
    });
  });

  it('loads dynamic cn boards and passes selected board to scan request', async () => {
    render(<StockScreenerPage />);

    await screen.findByRole('option', { name: 'A 股行业板块（自选）' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'cn_board_industry_dynamic' } });

    await waitFor(() => {
      expect(mockedScreenerApi.getBoards).toHaveBeenCalledWith('cn', 'industry');
    });

    const boardLabel = await screen.findByText('具体行业板块');
    const boardSelect = boardLabel.closest('label')?.parentElement?.querySelector('select');

    expect(boardSelect).toBeTruthy();
    fireEvent.change(boardSelect as HTMLSelectElement, { target: { value: '半导体' } });

    await waitFor(() => {
      expect(mockedScreenerApi.getBoardPreview).toHaveBeenCalledWith('cn', 'industry', '半导体', 0);
    });

    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          market: 'cn',
          scope: 'cn_board_industry_dynamic',
          boardName: '半导体',
          boardType: 'industry',
          codes: undefined,
          asyncMode: true,
        }),
      );
    });
  });

  it('loads real preview for cn preset board scopes', async () => {
    render(<StockScreenerPage />);

    await screen.findByRole('option', { name: 'A 股半导体' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'cn_semiconductor' } });

    await waitFor(() => {
      expect(mockedScreenerApi.getBoardPreview).toHaveBeenCalledWith('cn', 'industry', '半导体', 0);
    });

    expect(await screen.findByText(/将按 半导体 的完整股票池扫描/)).toBeTruthy();
  });

  it('passes preset cn board metadata in scan request', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(await screen.findByLabelText('选股模式'), { target: { value: 'condition' } });
    await screen.findByRole('option', { name: 'A 股半导体' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'cn_semiconductor' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          market: 'cn',
          scope: 'cn_semiconductor',
          boardName: '半导体',
          boardType: 'industry',
          codes: undefined,
          asyncMode: true,
        }),
      );
    });
  });

  it('shows tier details for configured hk dynamic board pools', async () => {
    mockedScreenerApi.getBoards.mockResolvedValueOnce([
      {
        market: 'hk',
        boardType: 'industry',
        boardName: '科技互联网',
        label: '科技互联网',
        estimatedCount: 12,
        description: '港股平台互联网与软件服务代表公司。',
        tierSummary: '龙头 4 / 中军 4 / 弹性 4',
        tiers: [
          { key: 'leaders', label: '龙头', count: 4, codes: ['00700', '09988', '03690', '09618'] },
          { key: 'core', label: '中军', count: 4, codes: ['09888', '01024', '06618', '09999'] },
          { key: 'momentum', label: '弹性', count: 4, codes: ['09868', '09626', '09961', '03888'] },
        ],
      },
    ]);
    mockedScreenerApi.getBoardPreview.mockResolvedValueOnce({
      market: 'hk',
      boardType: 'industry',
      boardName: '科技互联网',
      estimatedCount: 12,
      previewCodes: ['00700', '09988', '03690', '09618'],
      description: '港股平台互联网与软件服务代表公司。',
      tierSummary: '龙头 4 / 中军 4 / 弹性 4',
      tiers: [
        { key: 'leaders', label: '龙头', count: 4, codes: ['00700', '09988', '03690', '09618'] },
        { key: 'core', label: '中军', count: 4, codes: ['09888', '01024', '06618', '09999'] },
        { key: 'momentum', label: '弹性', count: 4, codes: ['09868', '09626', '09961', '03888'] },
      ],
    });

    render(<StockScreenerPage />);

    fireEvent.change(getConfigSelect(0), { target: { value: 'hk' } });
    await screen.findByRole('option', { name: '港股行业板块（自选）' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'hk_board_industry_dynamic' } });

    await waitFor(() => {
      expect(mockedScreenerApi.getBoards).toHaveBeenCalledWith('hk', 'industry');
    });

    const boardLabel = await screen.findByText('具体行业板块');
    const boardSelect = boardLabel.closest('label')?.parentElement?.querySelector('select');
    fireEvent.change(boardSelect as HTMLSelectElement, { target: { value: '科技互联网' } });

    await screen.findByText('板块分层明细');
    expect(screen.getByText('龙头')).toBeTruthy();
    expect(screen.getByText('00700、09988、03690、09618')).toBeTruthy();
    expect(screen.getByText('中军')).toBeTruthy();
  });

  it('loads dynamic us industry boards independently from cn catalog', async () => {
    mockedScreenerApi.getBoards
      .mockResolvedValueOnce(boardCatalog)
      .mockResolvedValueOnce([
        { market: 'us', boardType: 'industry', boardName: '半导体', label: '半导体', estimatedCount: 12 },
        { market: 'us', boardType: 'industry', boardName: '金融', label: '金融', estimatedCount: 12 },
      ]);
    mockedScreenerApi.getBoardPreview.mockResolvedValueOnce({
      market: 'us',
      boardType: 'industry',
      boardName: '半导体',
      estimatedCount: 12,
      previewCodes: ['NVDA', 'AMD', 'AVGO'],
    });

    render(<StockScreenerPage />);

    await screen.findByRole('option', { name: 'A 股行业板块（自选）' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'cn_board_industry_dynamic' } });
    await waitFor(() => {
      expect(mockedScreenerApi.getBoards).toHaveBeenCalledWith('cn', 'industry');
    });

    fireEvent.change(getConfigSelect(0), { target: { value: 'us' } });
    await screen.findByRole('option', { name: '美股行业板块（自选）' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'us_board_industry_dynamic' } });

    await waitFor(() => {
      expect(mockedScreenerApi.getBoards).toHaveBeenCalledWith('us', 'industry');
    });
  });

  it('submits a custom cn condition scan and renders returned results', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(await screen.findByLabelText('选股模式'), { target: { value: 'condition' } });
    fireEvent.change(getConfigSelect(1), { target: { value: 'custom_pool' } });
    fireEvent.change(await screen.findByRole('textbox', { name: /自定义股票池/ }), { target: { value: '600519' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledTimes(1);
    });

    expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'condition',
        market: 'cn',
        scope: 'custom_pool',
        codes: ['600519'],
        exportCsv: true,
        limit: 200,
        sortBy: 'lastClose',
        sortDir: 'desc',
        asyncMode: false,
      }),
    );
    expect(await screen.findByText('贵州茅台')).toBeTruthy();
    expect(screen.getByText('RSI < 30')).toBeTruthy();
  });

  it('shows inline error when formula validation fails', async () => {
    mockedScreenerApi.validateFormula.mockRejectedValueOnce(new Error('Unsupported function: BADFUNC'));

    render(<StockScreenerPage />);

    fireEvent.change(await screen.findByLabelText('选股公式'), { target: { value: 'BADFUNC(CLOSE)' } });
    fireEvent.click(screen.getAllByRole('button', { name: '校验公式' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.validateFormula).toHaveBeenCalledWith('BADFUNC(CLOSE)');
    });
    expect(await screen.findByText('公式校验失败')).toBeTruthy();
    expect(await screen.findByText('Unsupported function: BADFUNC')).toBeTruthy();
  });

  it('supports formula mode validation and auto-validates before scan', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(getConfigSelect(0), { target: { value: 'us' } });
    fireEvent.change(getConfigSelect(1), { target: { value: 'custom_pool' } });
    fireEvent.change(await screen.findByLabelText('公式名称'), { target: { value: '趋势延续' } });
    fireEvent.change(await screen.findByRole('textbox', { name: /自定义股票池/ }), { target: { value: 'AAPL' } });
    fireEvent.change(await screen.findByLabelText('选股公式'), { target: { value: 'CLOSE > MA(CLOSE, 5)' } });

    fireEvent.click(screen.getAllByRole('button', { name: '校验公式' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.validateFormula).toHaveBeenCalledWith('CLOSE > MA(CLOSE, 5)');
    });

    mockedScreenerApi.scan.mockResolvedValueOnce({
      ...scanResponse,
      results: [
        {
          ...scanResponse.results[0],
          code: 'AAPL',
          matchedConditions: ['趋势延续'],
        },
      ],
    });

    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.validateFormula).toHaveBeenCalledWith('CLOSE > MA(CLOSE, 5)');
    });

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: 'formula',
          formula: 'CLOSE > MA(CLOSE, 5)',
          formulaName: '趋势延续',
          market: 'us',
          scope: 'custom_pool',
          codes: ['AAPL'],
          asyncMode: false,
        }),
      );
    });
    expect(mockedScreenerApi.validateFormula.mock.invocationCallOrder[0]).toBeLessThan(
      mockedScreenerApi.scan.mock.invocationCallOrder[0]
    );

    expect(await screen.findByText('校验通过')).toBeTruthy();
    expect((await screen.findAllByText('趋势延续')).length).toBeGreaterThan(0);
  });

  it('runs full-market cn scan in async mode and refreshes results on completion', async () => {
    const accepted: ScreenerTaskAccepted = {
      taskId: 'task-001',
      status: 'pending',
      message: '选股任务已提交',
    };

    mockedScreenerApi.scan.mockResolvedValueOnce(accepted);
    mockedScreenerApi.getTaskStatus
      .mockResolvedValueOnce({
        taskId: 'task-001',
        market: 'cn',
        status: 'processing',
        progress: 12,
        scannedCount: 120,
        totalCount: 1000,
        matchedCount: 5,
        message: '正在扫描 120/1000，当前命中 5 条',
        createdAt: '2026-03-20T10:00:00',
        startedAt: '2026-03-20T10:00:01',
        completedAt: null,
        error: null,
        result: null,
      } satisfies ScreenerTaskStatusResponse)
      .mockResolvedValueOnce({
        taskId: 'task-001',
        market: 'cn',
        status: 'completed',
        progress: 100,
        scannedCount: 1000,
        totalCount: 1000,
        matchedCount: 1,
        message: '扫描完成，共命中 1 条',
        createdAt: '2026-03-20T10:00:00',
        startedAt: '2026-03-20T10:00:01',
        completedAt: '2026-03-20T10:00:30',
        error: null,
        result: scanResponse,
      } satisfies ScreenerTaskStatusResponse);

    render(<StockScreenerPage />);

    await screen.findByRole('option', { name: 'A 股全市场' });
    fireEvent.change(getConfigSelect(1), { target: { value: 'all_market' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          market: 'cn',
          scope: 'all_market',
          codes: undefined,
          asyncMode: true,
        }),
      );
    });

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    expect(await screen.findByText('后台扫描进度')).toBeTruthy();
    expect(screen.getByText('任务 ID: task-001')).toBeTruthy();

    MockEventSource.instances[0].emit('connected', { message: 'connected' });
    MockEventSource.instances[0].emit('task_progress', {
      task_id: 'task-001',
      market: 'cn',
      status: 'processing',
      progress: 60,
      scanned_count: 600,
      total_count: 1000,
      matched_count: 9,
      message: '正在扫描 600/1000，当前命中 9 条',
      created_at: '2026-03-20T10:00:00',
      started_at: '2026-03-20T10:00:01',
      completed_at: null,
      error: null,
    });

    expect(await screen.findByText('进度 60%')).toBeTruthy();
    expect(screen.getByText('实时连接已建立')).toBeTruthy();

    MockEventSource.instances[0].emit('task_completed', {
      task_id: 'task-001',
      market: 'cn',
      status: 'completed',
      progress: 100,
      scanned_count: 1000,
      total_count: 1000,
      matched_count: 1,
      message: '扫描完成，共命中 1 条',
      created_at: '2026-03-20T10:00:00',
      started_at: '2026-03-20T10:00:01',
      completed_at: '2026-03-20T10:00:30',
      error: null,
    });

    await waitFor(() => {
      expect(mockedScreenerApi.getTaskStatus).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('贵州茅台')).toBeTruthy();
  });
});
