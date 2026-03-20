import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StockScreenerPage from '../StockScreenerPage';
import { screenerApi } from '../../api/screener';
import type {
  FormulaValidationResponse,
  IndicatorMeta,
  ScreenerScanResponse,
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
    getIndicators: vi.fn(),
    getFormulaFunctions: vi.fn(),
    validateFormula: vi.fn(),
    scan: vi.fn(),
    getTaskStatus: vi.fn(),
    getTaskStreamUrl: vi.fn(),
  },
}));

const mockedScreenerApi = vi.mocked(screenerApi);

const indicatorCatalog: IndicatorMeta[] = [
  {
    key: 'RSI',
    name: 'RSI 相对强弱',
    category: '摆动',
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

describe('StockScreenerPage', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    mockedScreenerApi.getIndicators.mockReset();
    mockedScreenerApi.getFormulaFunctions.mockReset();
    mockedScreenerApi.validateFormula.mockReset();
    mockedScreenerApi.scan.mockReset();
    mockedScreenerApi.getTaskStatus.mockReset();
    mockedScreenerApi.getTaskStreamUrl.mockReset();
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
  });

  it('shows a validation alert when hk/us pool is empty and scan is clicked', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(await screen.findByLabelText('市场'), { target: { value: 'us' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    expect(mockedScreenerApi.scan).not.toHaveBeenCalled();
    expect(await screen.findByText('港股和美股扫描需要先填写自定义股票池代码')).toBeTruthy();
  });

  it('shows a validation alert when cn full-market scan is not explicitly enabled', async () => {
    render(<StockScreenerPage />);

    fireEvent.click((await screen.findAllByRole('button', { name: '开始选股' }))[0]);

    expect(mockedScreenerApi.scan).not.toHaveBeenCalled();
    expect(await screen.findByText('A 股全市场扫描耗时较长。请先填写股票池，或勾选“允许全市场扫描（较慢）”后再开始选股。')).toBeTruthy();
  });

  it('submits a custom cn condition scan and renders returned results', async () => {
    render(<StockScreenerPage />);

    fireEvent.change(await screen.findByLabelText('选股模式'), { target: { value: 'condition' } });
    fireEvent.change(await screen.findByLabelText('自定义股票池'), { target: { value: '600519' } });
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledTimes(1);
    });

    expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'condition',
        market: 'cn',
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

    fireEvent.change(await screen.findByLabelText('公式名称'), { target: { value: '趋势延续' } });
    fireEvent.change(await screen.findByLabelText('自定义股票池'), { target: { value: 'AAPL' } });
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
          market: 'cn',
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

    fireEvent.click(await screen.findByLabelText('允许全市场扫描（较慢）'));
    fireEvent.click(screen.getAllByRole('button', { name: '开始选股' })[0]);

    await waitFor(() => {
      expect(mockedScreenerApi.scan).toHaveBeenCalledWith(
        expect.objectContaining({
          market: 'cn',
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
