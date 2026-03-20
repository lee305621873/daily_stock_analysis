import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { screenerApi } from '../api/screener';
import type { ParsedApiError } from '../api/error';
import { createParsedApiError, getParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Input, Select, StickyActionBar } from '../components/common';
import type {
  FormulaFunctionMeta,
  FormulaValidationResponse,
  IndicatorKey,
  IndicatorMeta,
  LogicOp,
  MarketType,
  Operator,
  ScreenerCondition,
  ScreenerMode,
  ScreenerScanResponse,
  ScreenerTaskAccepted,
  ScreenerTaskInfo,
  ScreenerTaskStatusResponse,
} from '../types/screener';

const FALLBACK_INDICATORS: IndicatorMeta[] = [
  { key: 'MA', name: 'MA 移动平均', category: '趋势', params: [{ name: 'period', label: '周期', type: 'int', default: 5 }], outputs: [{ key: 'ma', label: 'MA' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'MACD', name: 'MACD 指标', category: '趋势', params: [{ name: 'fast', label: '快线', type: 'int', default: 12 }, { name: 'slow', label: '慢线', type: 'int', default: 26 }, { name: 'signal', label: '平滑', type: 'int', default: 9 }], outputs: [{ key: 'macd', label: 'Diff' }, { key: 'signal', label: 'Dea' }, { key: 'hist', label: '柱子' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'RSI', name: 'RSI 相对强弱', category: '摆动', params: [{ name: 'period', label: '周期', type: 'int', default: 14 }], outputs: [{ key: 'rsi', label: 'RSI' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'KDJ', name: 'KDJ 随机指标', category: '摆动', params: [{ name: 'period', label: '周期', type: 'int', default: 9 }, { name: 'k_smooth', label: 'K 平滑', type: 'int', default: 3 }, { name: 'd_smooth', label: 'D 平滑', type: 'int', default: 3 }], outputs: [{ key: 'k', label: 'K' }, { key: 'd', label: 'D' }, { key: 'j', label: 'J' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'BOLL', name: 'BOLL 布林带', category: '通道', params: [{ name: 'period', label: '周期', type: 'int', default: 20 }, { name: 'multiplier', label: '倍数', type: 'float', default: 2 }], outputs: [{ key: 'upper', label: '上轨' }, { key: 'mid', label: '中轨' }, { key: 'lower', label: '下轨' }, { key: 'bandwidth', label: '带宽' }, { key: 'percent_b', label: '%B' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'VOL', name: 'VOL 成交量', category: '能量', params: [{ name: 'period', label: '均量周期', type: 'int', default: 5 }], outputs: [{ key: 'volume', label: '量' }, { key: 'vol_ma', label: '均量' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'OBV', name: 'OBV 能量潮', category: '能量', params: [], outputs: [{ key: 'obv', label: 'OBV' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
];

const FORMULA_TEMPLATES = [
  { label: '均线金叉', value: 'CROSS(MA(CLOSE,5), MA(CLOSE,20))' },
  { label: '放量突破 20 日新高', value: 'CLOSE > HHV(HIGH,20) AND VOL > 2 * MA(VOL,5)' },
  { label: '超跌反弹', value: 'RSI(CLOSE,14) < 30 AND CLOSE > REF(CLOSE,1)' },
  { label: '趋势延续', value: 'EVERY(CLOSE > MA(CLOSE,20), 5) AND MACD(CLOSE,12,26,9).hist > 0' },
];

function createDefaultCondition(indicator: IndicatorKey): ScreenerCondition {
  return {
    indicator,
    params: {},
    output: undefined,
    operator: '>' as Operator,
    compareTo: { type: 'value', value: 0 },
    logicWithPrevious: 'AND' as LogicOp,
  };
}

function parseCodes(codesText: string): string[] {
  return codesText
    .split(/[\s,，\n\r\t]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function isTaskAccepted(response: ScreenerScanResponse | ScreenerTaskAccepted): response is ScreenerTaskAccepted {
  return 'taskId' in response;
}

function fromSseTaskPayload(payload: string): ScreenerTaskInfo | null {
  try {
    const data = JSON.parse(payload) as Record<string, unknown>;
    return {
      taskId: String(data.task_id ?? ''),
      market: String(data.market ?? 'cn') as MarketType,
      status: String(data.status ?? 'pending') as ScreenerTaskStatusResponse['status'],
      progress: Number(data.progress ?? 0),
      scannedCount: Number(data.scanned_count ?? 0),
      totalCount: Number(data.total_count ?? 0),
      matchedCount: Number(data.matched_count ?? 0),
      message: typeof data.message === 'string' ? data.message : undefined,
      createdAt: String(data.created_at ?? ''),
      startedAt: typeof data.started_at === 'string' ? data.started_at : undefined,
      completedAt: typeof data.completed_at === 'string' ? data.completed_at : undefined,
      error: typeof data.error === 'string' ? data.error : undefined,
    };
  } catch (error) {
    console.error('Failed to parse screener SSE payload:', error);
    return null;
  }
}

interface ConditionRowProps {
  metaList: IndicatorMeta[];
  value: ScreenerCondition;
  onChange: (next: ScreenerCondition) => void;
  onRemove: () => void;
  isFirst: boolean;
}

const ConditionRow: React.FC<ConditionRowProps> = ({ metaList, value, onChange, onRemove, isFirst }) => {
  const meta = metaList.find((item) => item.key === value.indicator) ?? metaList[0];
  const compareMeta = metaList.find((item) => item.key === value.compareTo.indicator);

  const update = (patch: Partial<ScreenerCondition>) => {
    onChange({ ...value, ...patch });
  };

  return (
    <Card className="space-y-4">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end">
        {!isFirst ? (
          <Select
            className="xl:w-32"
            value={value.logicWithPrevious}
            onChange={(next) => update({ logicWithPrevious: next as LogicOp })}
            options={[
              { value: 'AND', label: 'AND' },
              { value: 'OR', label: 'OR' },
            ]}
          />
        ) : null}

        <Select
          className="xl:w-52"
          label="指标"
          value={value.indicator}
          onChange={(next) => update({ indicator: next as IndicatorKey, params: {}, output: undefined })}
          options={metaList.map((item) => ({ value: item.key, label: item.name }))}
        />

        {meta?.params.map((param) => (
          <Input
            key={param.name}
            label={param.label}
            type="number"
            min={param.min}
            max={param.max}
            value={value.params[param.name] ?? param.default ?? ''}
            onChange={(event) => update({ params: { ...value.params, [param.name]: Number(event.target.value) } })}
            className="xl:w-32"
          />
        ))}

        {meta?.outputs.length ? (
          <Select
            className="xl:w-40"
            label="输出"
            value={value.output || meta.outputs[0].key}
            onChange={(next) => update({ output: next })}
            options={meta.outputs.map((output) => ({ value: output.key, label: output.label }))}
          />
        ) : null}

        <Select
          className="xl:w-40"
          label="比较"
          value={value.operator}
          onChange={(next) => update({ operator: next as Operator })}
          options={(meta?.operators || []).map((operator) => ({ value: operator, label: operator }))}
        />

        <Select
          className="xl:w-40"
          label="右侧"
          value={value.compareTo.type}
          onChange={(next) => update({
            compareTo: next === 'indicator'
              ? { ...value.compareTo, type: 'indicator', indicator: value.compareTo.indicator || metaList[0]?.key }
              : { ...value.compareTo, type: 'value', value: value.compareTo.value ?? 0 },
          })}
          options={[
            { value: 'value', label: '阈值' },
            { value: 'indicator', label: '另一指标' },
          ]}
        />

        {value.compareTo.type === 'indicator' ? (
          <>
            <Select
              className="xl:w-52"
              label="对比指标"
              value={value.compareTo.indicator || metaList[0]?.key || ''}
              onChange={(next) => update({ compareTo: { ...value.compareTo, indicator: next as IndicatorKey } })}
              options={metaList.map((item) => ({ value: item.key, label: item.name }))}
            />
            <Select
              className="xl:w-40"
              label="对比输出"
              value={value.compareTo.output || compareMeta?.outputs[0]?.key || ''}
              onChange={(next) => update({ compareTo: { ...value.compareTo, output: next } })}
              options={(compareMeta?.outputs || []).map((output) => ({ value: output.key, label: output.label }))}
            />
          </>
        ) : (
          <Input
            className="xl:w-40"
            label="阈值"
            type="number"
            value={value.compareTo.value ?? ''}
            onChange={(event) => update({ compareTo: { ...value.compareTo, value: Number(event.target.value) } })}
          />
        )}

        <Button type="button" variant="outline" onClick={onRemove} disabled={isFirst} className="xl:mb-0">
          删除
        </Button>
      </div>
    </Card>
  );
};

const MARKET_HINTS: Record<MarketType, string> = {
  cn: 'A 股支持留空后扫描全市场，也支持手工限定股票池。',
  hk: '港股当前支持自定义股票池扫描，例如 00700, 09988, 01810。',
  us: '美股当前支持自定义股票池扫描，例如 AAPL, MSFT, NVDA。',
};

const MARKET_PLACEHOLDERS: Record<MarketType, string> = {
  cn: '留空表示 A 股全市场，或输入 600519,000001,300750',
  hk: '请输入港股代码，如 00700,09988,01810',
  us: '请输入美股代码，如 AAPL,MSFT,NVDA',
};

const StockScreenerPage: React.FC = () => {
  const [indicators, setIndicators] = useState<IndicatorMeta[]>(FALLBACK_INDICATORS);
  const [formulaFunctions, setFormulaFunctions] = useState<FormulaFunctionMeta[]>([]);
  const [conditions, setConditions] = useState<ScreenerCondition[]>([createDefaultCondition(FALLBACK_INDICATORS[0].key)]);
  const [scanMode, setScanMode] = useState<ScreenerMode>('formula');
  const [formulaName, setFormulaName] = useState(FORMULA_TEMPLATES[0].label);
  const [formulaText, setFormulaText] = useState(FORMULA_TEMPLATES[0].value);
  const [formulaValidation, setFormulaValidation] = useState<FormulaValidationResponse | null>(null);
  const [formulaValidationError, setFormulaValidationError] = useState<ParsedApiError | null>(null);
  const [market, setMarket] = useState<MarketType>('cn');
  const [codesText, setCodesText] = useState('');
  const [boardFilters, setBoardFilters] = useState('');
  const [allowFullMarketScan, setAllowFullMarketScan] = useState(false);
  const [heat, setHeat] = useState('');
  const [sortBy, setSortBy] = useState<'lastClose' | 'heat' | 'code' | 'name'>('lastClose');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [results, setResults] = useState<ScreenerScanResponse | null>(null);
  const [taskInfo, setTaskInfo] = useState<ScreenerTaskStatusResponse | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isValidatingFormula, setIsValidatingFormula] = useState(false);
  const [pageError, setPageError] = useState<ParsedApiError | null>(null);
  const [metadataWarning, setMetadataWarning] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [indicatorData, functionData] = await Promise.all([
          screenerApi.getIndicators(),
          screenerApi.getFormulaFunctions(),
        ]);
        if (indicatorData.length > 0) {
          setIndicators(indicatorData);
          setConditions([createDefaultCondition(indicatorData[0].key)]);
        }
        setFormulaFunctions(functionData);
        setMetadataWarning(null);
      } catch (error) {
        console.error('Failed to load screener metadata:', error);
        setMetadataWarning('指标或公式元数据加载失败，已回退为本地默认配置。');
      }
    };
    void loadMetadata();
  }, []);

  const syncTaskStatus = async (taskId: string) => {
    const status = await screenerApi.getTaskStatus(taskId);
    setTaskInfo(status);
    if (status.result) {
      setResults(status.result);
    }
    if (status.status === 'completed') {
      setIsLoading(false);
      setStreamConnected(false);
      setActiveTaskId(null);
    } else if (status.status === 'failed') {
      setIsLoading(false);
      setStreamConnected(false);
      setActiveTaskId(null);
      setPageError(createParsedApiError({
        title: '后台选股失败',
        message: status.error || status.message || '后台选股任务执行失败',
        category: 'http_error',
      }));
    }
    return status;
  };

  useEffect(() => {
    if (!activeTaskId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return undefined;
    }

    let cancelled = false;
    const eventSource = new EventSource(screenerApi.getTaskStreamUrl(), { withCredentials: true });
    eventSourceRef.current = eventSource;

    const handleTaskEvent = (event: MessageEvent<string>) => {
      const nextTask = fromSseTaskPayload(event.data);
      if (!nextTask || nextTask.taskId !== activeTaskId || cancelled) {
        return;
      }
      setTaskInfo((previous) => ({ ...previous, ...nextTask }));
    };

    eventSource.addEventListener('connected', () => {
      if (!cancelled) {
        setStreamConnected(true);
      }
    });
    eventSource.addEventListener('task_created', handleTaskEvent);
    eventSource.addEventListener('task_started', handleTaskEvent);
    eventSource.addEventListener('task_progress', handleTaskEvent);
    eventSource.addEventListener('task_completed', (event) => {
      handleTaskEvent(event as MessageEvent<string>);
      void syncTaskStatus(activeTaskId);
    });
    eventSource.addEventListener('task_failed', (event) => {
      handleTaskEvent(event as MessageEvent<string>);
      void syncTaskStatus(activeTaskId);
    });
    eventSource.addEventListener('heartbeat', () => {
      if (!cancelled) {
        setStreamConnected(true);
      }
    });
    eventSource.onerror = () => {
      if (!cancelled) {
        setStreamConnected(false);
      }
    };

    const kickoffTimer = window.setTimeout(() => {
      void syncTaskStatus(activeTaskId).catch((error) => {
        console.error('Failed to fetch screener task status:', error);
      });
    }, 0);

    const pollTimer = window.setInterval(() => {
      void syncTaskStatus(activeTaskId).catch((error) => {
        console.error('Failed to poll screener task status:', error);
      });
    }, 5000);

    return () => {
      cancelled = true;
      window.clearTimeout(kickoffTimer);
      window.clearInterval(pollTimer);
      eventSource.close();
      if (eventSourceRef.current === eventSource) {
        eventSourceRef.current = null;
      }
    };
  }, [activeTaskId]);

  const handleConditionChange = (index: number, next: ScreenerCondition) => {
    setConditions((previous) => previous.map((item, currentIndex) => (currentIndex === index ? next : item)));
  };

  const handleAddCondition = () => {
    if (indicators.length === 0) return;
    setConditions((previous) => [...previous, createDefaultCondition(indicators[0].key)]);
  };

  const handleRemoveCondition = (index: number) => {
    setConditions((previous) => previous.filter((_, currentIndex) => currentIndex !== index));
  };

  const handleValidateFormula = async () => {
    const trimmedFormula = formulaText.trim();
    if (!trimmedFormula) {
      const error = createParsedApiError({
        title: '公式不能为空',
        message: '请先输入一个选股公式再进行校验。',
        category: 'missing_params',
      });
      setFormulaValidation(null);
      setFormulaValidationError(error);
      return false;
    }

    setIsValidatingFormula(true);
    setFormulaValidationError(null);
    try {
      const validation = await screenerApi.validateFormula(trimmedFormula);
      setFormulaValidation(validation);
      setFormulaValidationError(null);
      return true;
    } catch (error) {
      const parsedError = getParsedApiError(error);
      setFormulaValidation(null);
      setFormulaValidationError(parsedError);
      return false;
    } finally {
      setIsValidatingFormula(false);
    }
  };

  const handleDownloadCsv = () => {
    if (!results?.csv) return;
    const blob = new Blob([results.csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `stock-screener-${market}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleScan = async () => {
    const codes = parseCodes(codesText);
    const trimmedFormula = formulaText.trim();

    if (scanMode === 'formula' && !trimmedFormula) {
      const error = createParsedApiError({
        title: '公式不能为空',
        message: '公式模式下需要先填写公式。',
        category: 'missing_params',
      });
      setFormulaValidation(null);
      setFormulaValidationError(error);
      return;
    }

    if (scanMode === 'formula') {
      const isFormulaValid = await handleValidateFormula();
      if (!isFormulaValid) {
        return;
      }
    }

    if (market !== 'cn' && codes.length === 0) {
      setPageError(createParsedApiError({
        title: '股票池不能为空',
        message: '港股和美股扫描需要先填写自定义股票池代码',
        category: 'missing_params',
      }));
      return;
    }

    if (market === 'cn' && codes.length === 0 && !allowFullMarketScan) {
      setPageError(createParsedApiError({
        title: '请确认扫描范围',
        message: 'A 股全市场扫描耗时较长。请先填写股票池，或勾选“允许全市场扫描（较慢）”后再开始选股。',
        category: 'missing_params',
      }));
      return;
    }

    const shouldRunAsync = market === 'cn' && codes.length === 0 && allowFullMarketScan;

    setIsLoading(true);
    setPageError(null);
    setFormulaValidationError(null);
    setResults(null);
    setTaskInfo(null);
    setActiveTaskId(null);
    setStreamConnected(false);

    try {
      const response = await screenerApi.scan({
        mode: scanMode,
        conditions: scanMode === 'condition' ? conditions : undefined,
        formula: scanMode === 'formula' ? trimmedFormula : undefined,
        formulaName: scanMode === 'formula' ? formulaName.trim() || undefined : undefined,
        market,
        boardFilters: market === 'cn' && boardFilters
          ? boardFilters.split(',').map((item) => item.trim()).filter(Boolean)
          : undefined,
        volumeHeatRatio: heat ? Number(heat) : undefined,
        exportCsv: true,
        sortBy,
        sortDir,
        limit: 200,
        codes: codes.length > 0 ? codes : undefined,
        asyncMode: shouldRunAsync,
      });

      if (isTaskAccepted(response)) {
        const now = new Date().toISOString();
        setTaskInfo({
          taskId: response.taskId,
          market,
          status: response.status,
          progress: 0,
          scannedCount: 0,
          totalCount: 0,
          matchedCount: 0,
          message: response.message,
          createdAt: now,
          startedAt: null,
          completedAt: null,
          error: null,
          result: null,
        });
        setActiveTaskId(response.taskId);
        return;
      }

      setResults(response);
      setIsLoading(false);
    } catch (error) {
      setIsLoading(false);
      setPageError(getParsedApiError(error));
    }
  };

  const statusBadge = useMemo(() => {
    if (!taskInfo) return null;
    if (taskInfo.status === 'completed') return <Badge variant="success">已完成</Badge>;
    if (taskInfo.status === 'failed') return <Badge variant="danger">失败</Badge>;
    if (taskInfo.status === 'processing') return <Badge variant="info">扫描中</Badge>;
    return <Badge variant="warning">排队中</Badge>;
  }, [taskInfo]);

  const formulaSummary = useMemo(() => {
    if (!formulaValidation) return null;
    return `${formulaValidation.message}，预计至少加载 ${formulaValidation.estimatedLookback} 个交易日`;
  }, [formulaValidation]);

  return (
    <AppPage className="space-y-6">
      <Card variant="gradient" padding="lg">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <span className="label-uppercase">Stock Screener</span>
            <h1 className="text-2xl font-semibold text-white">技术指标选股</h1>
            <p className="max-w-3xl text-sm text-secondary-text">
              在主 Web 里直接按 A 股、港股、美股做条件选股或公式选股。A 股全市场扫描会自动切到后台任务，并实时回传进度。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="info">条件模式</Badge>
            <Badge variant="info">公式模式</Badge>
            <Badge variant="warning">A/H/US 通用</Badge>
          </div>
        </div>
      </Card>

      {pageError ? <ApiErrorAlert error={pageError} /> : null}
      {metadataWarning ? (
        <Card className="border border-warning/20 bg-warning/10 text-sm text-warning">
          {metadataWarning}
        </Card>
      ) : null}

      {taskInfo ? (
        <Card title="后台扫描进度" subtitle="A 股全市场扫描会持续更新">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {statusBadge}
              <Badge variant={streamConnected ? 'success' : 'warning'}>
                {streamConnected ? '实时连接已建立' : '等待进度连接'}
              </Badge>
              <span className="text-sm text-secondary-text">任务 ID: {taskInfo.taskId}</span>
            </div>

            <div className="h-3 overflow-hidden rounded-full bg-white/8">
              <div
                className="h-full rounded-full bg-primary-gradient transition-all duration-500"
                style={{ width: `${Math.max(4, taskInfo.progress)}%` }}
              />
            </div>

            <div className="grid gap-3 text-sm text-secondary-text md:grid-cols-4">
              <div>进度 {taskInfo.progress}%</div>
              <div>已扫描 {taskInfo.scannedCount}</div>
              <div>总数量 {taskInfo.totalCount || '--'}</div>
              <div>已命中 {taskInfo.matchedCount}</div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-elevated/40 px-4 py-3 text-sm text-white">
              {taskInfo.message || '后台任务已创建，等待执行...'}
            </div>
          </div>
        </Card>
      ) : null}

      <Card title="扫描配置" subtitle="配置市场、股票池与扫描模式">
        <div className="grid gap-4 lg:grid-cols-[220px_220px_minmax(0,1fr)]">
          <Select
            label="市场"
            value={market}
            onChange={(next) => setMarket(next as MarketType)}
            options={[
              { value: 'cn', label: 'A 股' },
              { value: 'hk', label: '港股' },
              { value: 'us', label: '美股' },
            ]}
          />
          <Select
            label="选股模式"
            value={scanMode}
            onChange={(next) => {
              setScanMode(next as ScreenerMode);
              setFormulaValidation(null);
              setFormulaValidationError(null);
            }}
            options={[
              { value: 'condition', label: '条件模式' },
              { value: 'formula', label: '公式模式' },
            ]}
          />

          <div className="flex flex-col">
            <label htmlFor="screener-codes" className="mb-2 text-sm font-medium text-foreground">自定义股票池</label>
            <textarea
              id="screener-codes"
              value={codesText}
              onChange={(event) => setCodesText(event.target.value)}
              placeholder={MARKET_PLACEHOLDERS[market]}
              rows={4}
              className="min-h-[120px] w-full rounded-xl border border-white/10 bg-card px-4 py-3 text-sm text-foreground shadow-soft-card transition-all placeholder:text-muted-text focus:border-cyan/40 focus:outline-none focus:ring-4 focus:ring-cyan/15 hover:border-white/18"
            />
            <p className="mt-2 text-xs text-secondary-text">{MARKET_HINTS[market]}</p>
            {market === 'cn' ? (
              <label className="mt-3 inline-flex items-center gap-3 rounded-xl border border-white/8 bg-card/60 px-3 py-2 text-sm text-secondary-text">
                <input
                  type="checkbox"
                  checked={allowFullMarketScan}
                  onChange={(event) => setAllowFullMarketScan(event.target.checked)}
                  className="h-4 w-4 rounded border-white/10 bg-card text-cyan accent-cyan"
                />
                <span>允许全市场扫描（较慢）</span>
              </label>
            ) : null}
          </div>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-4">
          <Input
            label="板块过滤"
            value={boardFilters}
            onChange={(event) => setBoardFilters(event.target.value)}
            placeholder="如 半导体,算力"
            disabled={market !== 'cn'}
            hint={market === 'cn' ? '仅 A 股支持按板块过滤。' : '港股和美股会忽略板块过滤。'}
          />
          <Input
            label="量能热度 >="
            type="number"
            value={heat}
            onChange={(event) => setHeat(event.target.value)}
            placeholder="如 1.5"
            hint="最新成交量 / 近 20 日均量。"
          />
          <Select
            label="排序字段"
            value={sortBy}
            onChange={(next) => setSortBy(next as 'lastClose' | 'heat' | 'code' | 'name')}
            options={[
              { value: 'lastClose', label: '最新价' },
              { value: 'heat', label: '热度' },
              { value: 'code', label: '代码' },
              { value: 'name', label: '名称' },
            ]}
          />
          <Select
            label="排序方向"
            value={sortDir}
            onChange={(next) => setSortDir(next as 'asc' | 'desc')}
            options={[
              { value: 'desc', label: '降序' },
              { value: 'asc', label: '升序' },
            ]}
          />
        </div>
      </Card>

      {scanMode === 'formula' ? (
        <Card title="公式编辑器" subtitle="统一公式 DSL，可复用到 A 股、港股、美股">
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
              <Select
                label="示例模板"
                value=""
                onChange={(next) => {
                  const selected = FORMULA_TEMPLATES.find((item) => item.value === next);
                  if (selected) {
                    setFormulaText(selected.value);
                    setFormulaName(selected.label);
                    setFormulaValidation(null);
                    setFormulaValidationError(null);
                  }
                }}
                options={[
                  { value: '', label: '选择一个模板' },
                  ...FORMULA_TEMPLATES.map((item) => ({ value: item.value, label: item.label })),
                ]}
              />
              <Input
                label="公式名称"
                value={formulaName}
                onChange={(event) => setFormulaName(event.target.value)}
                placeholder="如 趋势延续 / 放量突破"
                hint="名称会显示在结果列表中，便于区分不同公式。"
              />
            </div>

            <div>
              <label htmlFor="screener-formula" className="mb-2 block text-sm font-medium text-foreground">
                选股公式
              </label>
              <textarea
                id="screener-formula"
                value={formulaText}
                onChange={(event) => {
                  setFormulaText(event.target.value);
                  setFormulaValidation(null);
                  setFormulaValidationError(null);
                }}
                rows={6}
                className="min-h-[160px] w-full rounded-xl border border-white/10 bg-card px-4 py-3 font-mono text-sm text-foreground shadow-soft-card transition-all placeholder:text-muted-text focus:border-cyan/40 focus:outline-none focus:ring-4 focus:ring-cyan/15 hover:border-white/18"
                placeholder="例如：CROSS(MA(CLOSE,5), MA(CLOSE,20)) AND RSI(CLOSE,14) < 35"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="secondary" onClick={handleValidateFormula} isLoading={isValidatingFormula} loadingText="校验中...">
                校验公式
              </Button>
              <Badge variant="info">支持 OHLCV / MA / EMA / MACD / RSI / KDJ / BOLL / ATR / COUNT / EVERY / CROSS</Badge>
            </div>

            {formulaValidation ? (
              <Card className="border border-cyan/20 bg-cyan/5">
                <div className="space-y-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="success">校验通过</Badge>
                    <span className="text-secondary-text">{formulaSummary}</span>
                  </div>
                  <div className="font-mono text-white">{formulaValidation.normalizedFormula}</div>
                  <div className="flex flex-wrap gap-2">
                    {formulaValidation.functions.map((item) => (
                      <Badge key={item} variant="info">{item}</Badge>
                    ))}
                  </div>
                  {formulaValidation.warnings.length ? (
                    <div className="space-y-1 text-secondary-text">
                      {formulaValidation.warnings.map((warning) => (
                        <div key={warning}>- {warning}</div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </Card>
            ) : null}

            {formulaValidationError ? (
              <Card className="border border-danger/20 bg-danger/10">
                <div className="space-y-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="danger">公式校验失败</Badge>
                    <span className="text-white">{formulaValidationError.title}</span>
                  </div>
                  <div className="text-secondary-text">{formulaValidationError.message}</div>
                </div>
              </Card>
            ) : null}

            <div className="grid gap-4 xl:grid-cols-2">
              {formulaFunctions.slice(0, 10).map((item) => (
                <Card key={item.name} className="border border-white/8 bg-card/60">
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-white">{item.name}</span>
                      <Badge variant="warning">{item.category}</Badge>
                    </div>
                    <div className="font-mono text-cyan">{item.signature}</div>
                    <div className="text-secondary-text">{item.summary}</div>
                    {item.examples[0] ? <div className="font-mono text-xs text-muted-text">{item.examples[0]}</div> : null}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </Card>
      ) : null}

      {scanMode === 'condition' ? (
        <>
          <StickyActionBar className="top-20 bottom-auto">
            <div className="mr-auto flex flex-col gap-1 px-1">
              <span className="text-sm font-medium text-white">先点这里开始选股</span>
              <span className="text-xs text-secondary-text">
                当前 {conditions.length} 个条件，{market === 'cn' ? 'A 股可直接扫描' : '港股/美股请先填写股票池'}
              </span>
            </div>
            <Button type="button" variant="secondary" onClick={handleAddCondition}>
              添加条件
            </Button>
            <Button type="button" onClick={handleScan} isLoading={isLoading} loadingText="扫描中..." glow>
              开始选股
            </Button>
            <Button type="button" variant="outline" onClick={handleDownloadCsv} disabled={!results?.csv}>
              下载 CSV
            </Button>
          </StickyActionBar>

          <div className="space-y-4">
            {conditions.map((condition, index) => (
              <ConditionRow
                key={`${condition.indicator}-${index}`}
                metaList={indicators}
                value={condition}
                onChange={(next) => handleConditionChange(index, next)}
                onRemove={() => handleRemoveCondition(index)}
                isFirst={index === 0}
              />
            ))}
          </div>
        </>
      ) : (
        <StickyActionBar className="top-20 bottom-auto">
          <div className="mr-auto flex flex-col gap-1 px-1">
            <span className="text-sm font-medium text-white">默认公式选股，开始前会自动校验公式</span>
            <span className="text-xs text-secondary-text">
              当前为公式模式，支持一套公式复用到 A 股、港股、美股。
            </span>
          </div>
          <Button type="button" variant="secondary" onClick={handleValidateFormula} isLoading={isValidatingFormula} loadingText="校验中...">
            校验公式
          </Button>
          <Button type="button" onClick={handleScan} isLoading={isLoading} loadingText="扫描中..." glow>
            开始选股
          </Button>
          <Button type="button" variant="outline" onClick={handleDownloadCsv} disabled={!results?.csv}>
            下载 CSV
          </Button>
        </StickyActionBar>
      )}

      <div className="flex flex-wrap gap-3">
        {scanMode === 'condition' ? (
          <Button type="button" variant="secondary" onClick={handleAddCondition}>
            添加条件
          </Button>
        ) : (
          <Button type="button" variant="secondary" onClick={handleValidateFormula} isLoading={isValidatingFormula} loadingText="校验中...">
            校验公式
          </Button>
        )}
        <Button type="button" onClick={handleScan} isLoading={isLoading} loadingText="扫描中...">
          开始选股
        </Button>
        <Button type="button" variant="outline" onClick={handleDownloadCsv} disabled={!results?.csv}>
          下载 CSV
        </Button>
      </div>

      <Card title="结果列表" subtitle="Screening Results">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-sm text-secondary-text">
          <span>
            {results
              ? `共命中 ${results.total} 条，当前显示 ${results.results.length} 条`
              : taskInfo
                ? '后台任务执行中，完成后结果会自动刷新到这里'
                : '尚未开始扫描'}
          </span>
          <div className="flex flex-wrap gap-2">
            <Badge variant={scanMode === 'formula' ? 'info' : 'warning'}>
              {scanMode === 'formula' ? '当前为公式模式' : '当前为条件模式'}
            </Badge>
            {market !== 'cn' ? <Badge variant="warning">当前为自定义股票池扫描</Badge> : null}
          </div>
        </div>

        {results?.results.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.18em] text-muted-text">
                <tr className="border-b border-white/10">
                  <th className="px-3 py-3">代码</th>
                  <th className="px-3 py-3">名称</th>
                  <th className="px-3 py-3">最新价</th>
                  <th className="px-3 py-3">热度</th>
                  <th className="px-3 py-3">命中条件/公式</th>
                  <th className="px-3 py-3">板块</th>
                  <th className="px-3 py-3">数据源</th>
                </tr>
              </thead>
              <tbody>
                {results.results.map((item) => (
                  <tr key={`${item.code}-${item.dataSource}`} className="border-b border-white/5 align-top last:border-b-0">
                    <td className="px-3 py-3 font-mono text-cyan">{item.code}</td>
                    <td className="px-3 py-3 text-white">{item.name}</td>
                    <td className="px-3 py-3 text-white">{item.lastClose.toFixed(2)}</td>
                    <td className="px-3 py-3 text-white">{item.heat != null ? item.heat.toFixed(2) : '--'}</td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-2">
                        {item.matchedConditions.map((matched) => (
                          <Badge key={matched} variant="info">{matched}</Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-secondary-text">{item.boards.length ? item.boards.join(' / ') : '--'}</td>
                    <td className="px-3 py-3 text-secondary-text">{item.dataSource}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-white/10 bg-elevated/30 px-5 py-10 text-center text-sm text-secondary-text">
            {taskInfo
              ? taskInfo.message || '后台扫描任务执行中，请稍候...'
              : results
                ? '当前条件下没有命中结果，可以调整阈值、公式或股票池后重试。'
                : '设置条件或公式后点击“开始选股”，结果会显示在这里。'}
          </div>
        )}
      </Card>
    </AppPage>
  );
};

export default StockScreenerPage;
