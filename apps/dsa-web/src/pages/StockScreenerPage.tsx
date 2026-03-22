import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { screenerApi } from '../api/screener';
import type { ParsedApiError } from '../api/error';
import { createParsedApiError, getParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Input, Select, StickyActionBar } from '../components/common';
import type {
  ScreenerBoardOption,
  ScreenerBoardPreview,
  ScreenerBoardTier,
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
  ScreenerScopeOption,
  ScreenerTaskAccepted,
  ScreenerTaskInfo,
  ScreenerTaskStatusResponse,
} from '../types/screener';

const FALLBACK_INDICATORS: IndicatorMeta[] = [
  { key: 'MA', name: 'MA 移动平均', category: '趋势', summary: '用均价观察趋势方向，常用于看支撑、跌破和金叉/死叉。', params: [{ name: 'period', label: '周期', type: 'int', default: 5 }], outputs: [{ key: 'ma', label: 'MA' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'MACD', name: 'MACD 指标', category: '趋势', summary: '适合观察趋势强弱和动量变化，常用来看零轴和柱体放大。', params: [{ name: 'fast', label: '快线', type: 'int', default: 12 }, { name: 'slow', label: '慢线', type: 'int', default: 26 }, { name: 'signal', label: '平滑', type: 'int', default: 9 }], outputs: [{ key: 'macd', label: 'Diff' }, { key: 'signal', label: 'Dea' }, { key: 'hist', label: '柱子' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'RSI', name: 'RSI 相对强弱', category: '摆动', summary: '衡量超买超卖，常见阈值是 30 和 70。', params: [{ name: 'period', label: '周期', type: 'int', default: 14 }], outputs: [{ key: 'rsi', label: 'RSI' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'KDJ', name: 'KDJ 随机指标', category: '摆动', summary: '适合找短线拐点，J 值最敏感，K/D 更平滑。', params: [{ name: 'period', label: '周期', type: 'int', default: 9 }, { name: 'k_smooth', label: 'K 平滑', type: 'int', default: 3 }, { name: 'd_smooth', label: 'D 平滑', type: 'int', default: 3 }], outputs: [{ key: 'k', label: 'K' }, { key: 'd', label: 'D' }, { key: 'j', label: 'J' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'BOLL', name: 'BOLL 布林带', category: '通道', summary: '用上下轨判断波动区间，适合看突破、收口和回归均值。', params: [{ name: 'period', label: '周期', type: 'int', default: 20 }, { name: 'multiplier', label: '倍数', type: 'float', default: 2 }], outputs: [{ key: 'upper', label: '上轨' }, { key: 'mid', label: '中轨' }, { key: 'lower', label: '下轨' }, { key: 'bandwidth', label: '带宽' }, { key: 'percent_b', label: '%B' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'VOL', name: 'VOL 成交量', category: '能量', summary: '比较当前成交量和均量，常用于判断放量突破或缩量整理。', params: [{ name: 'period', label: '均量周期', type: 'int', default: 5 }], outputs: [{ key: 'volume', label: '量' }, { key: 'vol_ma', label: '均量' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
  { key: 'OBV', name: 'OBV 能量潮', category: '能量', summary: '把涨跌方向与成交量累计起来，适合看资金流入流出趋势。', params: [], outputs: [{ key: 'obv', label: 'OBV' }], operators: ['>', '>=', '<', '<=', '=', 'cross_up', 'cross_down'] },
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
          labelSuffix={meta?.summary ? <HelpHint content={meta.summary} /> : undefined}
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
            labelSuffix={<HelpHint content="不同指标可能有多个输出值，例如 MACD 的 Diff、Dea、柱子。" />}
            value={value.output || meta.outputs[0].key}
            onChange={(next) => update({ output: next })}
            options={meta.outputs.map((output) => ({ value: output.key, label: output.label }))}
          />
        ) : null}

        <Select
          className="xl:w-40"
          label="比较"
          labelSuffix={<HelpHint content="支持大于、小于、等于，以及 cross_up/cross_down 金叉死叉判断。" />}
          value={value.operator}
          onChange={(next) => update({ operator: next as Operator })}
          options={(meta?.operators || []).map((operator) => ({ value: operator, label: operator }))}
        />

        <Select
          className="xl:w-40"
          label="右侧"
          labelSuffix={<HelpHint content="阈值表示和固定数值比较；另一指标表示两个指标之间做对比。" />}
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
              labelSuffix={compareMeta?.summary ? <HelpHint content={compareMeta.summary} /> : undefined}
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
            labelSuffix={<HelpHint content="这里填固定门槛值，例如 RSI 小于 30、量比大于 1.5。" />}
            type="number"
            value={value.compareTo.value ?? ''}
            onChange={(event) => update({ compareTo: { ...value.compareTo, value: Number(event.target.value) } })}
          />
        )}

        <Button type="button" variant="outline" onClick={onRemove} disabled={isFirst} className="xl:mb-0">
          删除
        </Button>
      </div>

      {meta?.summary ? (
        <div className="rounded-2xl border border-white/8 bg-elevated/30 px-4 py-3 text-xs text-secondary-text">
          当前指标说明：{meta.summary}
        </div>
      ) : null}
    </Card>
  );
};

const MARKET_HINTS: Record<MarketType, string> = {
  cn: 'A 股支持全市场、预置板块、真实行业/概念板块与自定义股票池。',
  hk: '港股支持按预置板块、行业板块与自定义股票池扫描。',
  us: '美股支持按预置板块、行业板块与自定义股票池扫描。',
};

const MARKET_PLACEHOLDERS: Record<MarketType, string> = {
  cn: '请输入 600519,000001,300750',
  hk: '请输入港股代码，如 00700,09988,01810',
  us: '请输入美股代码，如 AAPL,MSFT,NVDA',
};

function buildFallbackScopes(market: MarketType): ScreenerScopeOption[] {
  if (market === 'cn') {
    return [{ key: 'all_market', market, label: 'A 股全市场', description: MARKET_HINTS.cn, kind: 'full_market', estimatedCount: null, previewCodes: [] }];
  }
  return [{ key: 'custom_pool', market, label: '自定义股票池', description: MARKET_HINTS[market], kind: 'custom_pool', estimatedCount: null, previewCodes: [] }];
}

function getMarketLabel(market: MarketType): string {
  if (market === 'cn') return 'A股';
  if (market === 'hk') return '港股';
  return '美股';
}

const HelpHint: React.FC<{ content: string }> = ({ content }) => (
  <span
    title={content}
    aria-label={content}
    className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/12 bg-white/6 text-[11px] font-semibold text-secondary-text cursor-help"
  >
    ?
  </span>
);

const TIER_BADGE_VARIANTS: Array<'info' | 'warning' | 'success'> = ['warning', 'info', 'success'];

const StockScreenerPage: React.FC = () => {
  const [indicators, setIndicators] = useState<IndicatorMeta[]>(FALLBACK_INDICATORS);
  const [formulaFunctions, setFormulaFunctions] = useState<FormulaFunctionMeta[]>([]);
  const [scopeCatalog, setScopeCatalog] = useState<Record<MarketType, ScreenerScopeOption[]>>({
    cn: buildFallbackScopes('cn'),
    hk: buildFallbackScopes('hk'),
    us: buildFallbackScopes('us'),
  });
  const [boardCatalog, setBoardCatalog] = useState<Record<string, ScreenerBoardOption[]>>({});
  const [conditions, setConditions] = useState<ScreenerCondition[]>([createDefaultCondition(FALLBACK_INDICATORS[0].key)]);
  const [scanMode, setScanMode] = useState<ScreenerMode>('formula');
  const [formulaName, setFormulaName] = useState(FORMULA_TEMPLATES[0].label);
  const [formulaText, setFormulaText] = useState(FORMULA_TEMPLATES[0].value);
  const [formulaValidation, setFormulaValidation] = useState<FormulaValidationResponse | null>(null);
  const [formulaValidationError, setFormulaValidationError] = useState<ParsedApiError | null>(null);
  const [market, setMarket] = useState<MarketType>('cn');
  const [scanScope, setScanScope] = useState('all_market');
  const [selectedBoardName, setSelectedBoardName] = useState('');
  const [boardSearchText, setBoardSearchText] = useState('');
  const [boardPreview, setBoardPreview] = useState<ScreenerBoardPreview | null>(null);
  const [codesText, setCodesText] = useState('');
  const [heat, setHeat] = useState('');
  const [scanLimit, setScanLimit] = useState('');
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
        const [indicatorData, functionData, scopeData] = await Promise.all([
          screenerApi.getIndicators(),
          screenerApi.getFormulaFunctions(),
          screenerApi.getScopes(),
        ]);
        if (indicatorData.length > 0) {
          setIndicators(indicatorData);
          setConditions([createDefaultCondition(indicatorData[0].key)]);
        }
        setFormulaFunctions(functionData);
        const groupedScopes: Record<MarketType, ScreenerScopeOption[]> = {
          cn: scopeData.filter((item) => item.market === 'cn'),
          hk: scopeData.filter((item) => item.market === 'hk'),
          us: scopeData.filter((item) => item.market === 'us'),
        };
        setScopeCatalog({
          cn: groupedScopes.cn.length ? groupedScopes.cn : buildFallbackScopes('cn'),
          hk: groupedScopes.hk.length ? groupedScopes.hk : buildFallbackScopes('hk'),
          us: groupedScopes.us.length ? groupedScopes.us : buildFallbackScopes('us'),
        });
        setMetadataWarning(null);
      } catch (error) {
        console.error('Failed to load screener metadata:', error);
        setMetadataWarning('指标、公式或扫描范围元数据加载失败，已回退为本地默认配置。');
      }
    };
    void loadMetadata();
  }, []);

  useEffect(() => {
    const availableScopes = scopeCatalog[market] || [];
    if (!availableScopes.length) return;
    if (!availableScopes.some((item) => item.key === scanScope)) {
      setScanScope(availableScopes[0].key);
    }
  }, [market, scanScope, scopeCatalog]);

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
      return validation.valid;
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

    if (isCustomPool && effectiveCodes.length === 0) {
      setPageError(createParsedApiError({
        title: '股票池不能为空',
        message: `当前已切换到“自定义股票池”，请先填写${market === 'cn' ? 'A 股' : market === 'hk' ? '港股' : '美股'}代码`,
        category: 'missing_params',
      }));
      return;
    }

    if (isDynamicBoardScope && !selectedBoardName.trim()) {
      setPageError(createParsedApiError({
        title: '板块未选择',
        message: `当前扫描范围需要先选择一个${getMarketLabel(market)}板块，才能开始扫描。`,
        category: 'missing_params',
      }));
      return;
    }

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
        scope: activeScope?.key,
        boardName: isDynamicBoardScope ? selectedBoardName.trim() : undefined,
        boardType: isDynamicBoardScope ? activeBoardType || undefined : undefined,
        volumeHeatRatio: heat ? Number(heat) : undefined,
        exportCsv: true,
        sortBy,
        sortDir,
        limit: 200,
        scanLimit: scanLimit ? Number(scanLimit) : undefined,
        codes: effectiveCodes.length > 0 ? effectiveCodes : undefined,
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

  const scopeOptions = useMemo(() => scopeCatalog[market] || [], [market, scopeCatalog]);

  const activeScope = useMemo(
    () => scopeOptions.find((item) => item.key === scanScope) ?? scopeOptions[0],
    [scanScope, scopeOptions],
  );

  const activeBoardType = activeScope?.boardType || null;
  const activeBoardCatalogKey = activeBoardType ? `${market}:${activeBoardType}` : null;
  const isCustomPool = activeScope?.kind === 'custom_pool';
  const isDynamicBoardScope = activeScope?.kind === 'board_dynamic';
  const isPresetBoardScope = activeScope?.kind === 'board' && market === 'cn' && !!activeScope?.boardName && !!activeScope?.boardType;
  const previewBoardName = isDynamicBoardScope ? selectedBoardName : (isPresetBoardScope ? activeScope?.boardName || '' : '');
  const previewBoardType = isDynamicBoardScope || isPresetBoardScope ? activeBoardType : null;
  const boardOptions = useMemo(
    () => (activeBoardCatalogKey ? (boardCatalog[activeBoardCatalogKey] || []) : []),
    [activeBoardCatalogKey, boardCatalog],
  );
  const filteredBoardOptions = useMemo(() => {
    if (!boardSearchText.trim()) {
      return boardOptions.slice(0, 200);
    }
    const keyword = boardSearchText.trim().toLowerCase();
    return boardOptions.filter((item) => item.label.toLowerCase().includes(keyword)).slice(0, 200);
  }, [boardOptions, boardSearchText]);
  const selectedBoardOption = boardOptions.find((item) => item.boardName === selectedBoardName) || null;
  const previewCodes = isDynamicBoardScope || isPresetBoardScope
    ? (boardPreview?.previewCodes ?? activeScope?.previewCodes ?? [])
    : (activeScope?.previewCodes ?? []);
  const effectiveCodes = isCustomPool ? parseCodes(codesText) : [];
  const shouldRunAsync = market === 'cn' && activeScope?.kind === 'full_market';
  const effectiveEstimatedCount = isDynamicBoardScope || isPresetBoardScope
    ? (boardPreview?.estimatedCount ?? selectedBoardOption?.estimatedCount ?? null)
    : (activeScope?.estimatedCount ?? null);
  const dynamicBoardDescription = boardPreview?.description || selectedBoardOption?.description || activeScope?.description || '';
  const dynamicBoardTierSummary = boardPreview?.tierSummary || selectedBoardOption?.tierSummary || '';
  const dynamicBoardTiers: ScreenerBoardTier[] = boardPreview?.tiers?.length
    ? boardPreview.tiers
    : (selectedBoardOption?.tiers ?? []);
  const poolPreview = isCustomPool ? codesText : previewCodes.join(', ');
  const poolHint = isCustomPool
    ? MARKET_HINTS[market]
    : isDynamicBoardScope
      ? selectedBoardName
        ? `当前板块：${selectedBoardName}。${dynamicBoardDescription || '预览仅展示前若干只代码，实际扫描使用完整板块股票池。'}${dynamicBoardTierSummary ? ` 分层：${dynamicBoardTierSummary}。` : ''}`
        : `请先选择一个${getMarketLabel(market)}${activeBoardType === 'concept' ? '概念' : '行业'}板块，随后会展示成分股预览。`
      : isPresetBoardScope
        ? `当前范围：${activeScope?.label}。${dynamicBoardDescription || '会优先加载真实板块成分股预览；如果实时板块接口失败，则回退到维护清单。'}`
      : activeScope?.description || MARKET_HINTS[market];

  useEffect(() => {
    if (!isDynamicBoardScope || !activeBoardType || !activeBoardCatalogKey) {
      return;
    }
    if (boardCatalog[activeBoardCatalogKey]?.length) {
      return;
    }

    let cancelled = false;
    const loadBoards = async () => {
      try {
        const boards = await screenerApi.getBoards(market, activeBoardType);
        if (!cancelled) {
          setBoardCatalog((previous) => ({ ...previous, [activeBoardCatalogKey]: boards }));
        }
      } catch (error) {
        console.error('Failed to load screener boards:', error);
        if (!cancelled) {
          setMetadataWarning(`${getMarketLabel(market)}板块目录加载失败，已保留预置板块范围。`);
        }
      }
    };
    void loadBoards();

    return () => {
      cancelled = true;
    };
  }, [activeBoardCatalogKey, activeBoardType, boardCatalog, isDynamicBoardScope, market]);

  useEffect(() => {
    setSelectedBoardName('');
    setBoardSearchText('');
    setBoardPreview(null);
  }, [market, scanScope]);

  useEffect(() => {
    if (!previewBoardType || !previewBoardName) {
      setBoardPreview(null);
      return;
    }

    let cancelled = false;
    const loadBoardPreview = async () => {
      try {
        const preview = await screenerApi.getBoardPreview(market, previewBoardType, previewBoardName, 20);
        if (!cancelled) {
          setBoardPreview(preview);
        }
      } catch (error) {
        console.error('Failed to load screener board preview:', error);
        if (!cancelled) {
          setBoardPreview(null);
        }
      }
    };
    void loadBoardPreview();

    return () => {
      cancelled = true;
    };
  }, [market, previewBoardName, previewBoardType]);

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
              在主 Web 里直接按 A 股、港股、美股做条件选股或公式选股。现在支持按市场板块快速切换扫描范围，并可用扫描上限控制样本数量。
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

      <Card title="扫描配置" subtitle="配置市场、板块范围、股票池与扫描模式">
        <div className="grid gap-4 lg:grid-cols-[220px_220px_220px_minmax(0,1fr)]">
          <Select
            label="市场"
            value={market}
            labelSuffix={<HelpHint content="扫描范围选项由后端返回；A 股可用真实板块成分股，港股和美股可用后端维护的行业代表池。" />}
            onChange={(next) => {
              const nextMarket = next as MarketType;
              setMarket(nextMarket);
              setScanScope((scopeCatalog[nextMarket] || buildFallbackScopes(nextMarket))[0]?.key || 'custom_pool');
              setPageError(null);
            }}
            options={[
              { value: 'cn', label: 'A 股' },
              { value: 'hk', label: '港股' },
              { value: 'us', label: '美股' },
            ]}
          />
          <Select
            label="扫描范围"
            labelSuffix={<HelpHint content="扫描范围由后端维护；A 股支持真实行业/概念板块，港股和美股支持后端维护的行业板块代表池。" />}
            value={activeScope?.key || ''}
            onChange={(next) => {
              setScanScope(next);
              setPageError(null);
            }}
            options={scopeOptions.map((item) => ({ value: item.key, label: item.label }))}
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
            <label htmlFor="screener-codes" className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-foreground">
              <span>{isCustomPool ? '自定义股票池' : '范围预览'}</span>
              <HelpHint content={isCustomPool ? '支持逗号、空格、换行分隔股票代码。' : '这里只展示后端返回的前若干只预览代码；动态板块范围会按完整股票池扫描。'} />
            </label>
            <textarea
              id="screener-codes"
              value={poolPreview}
              onChange={(event) => setCodesText(event.target.value)}
              placeholder={
                isCustomPool
                  ? MARKET_PLACEHOLDERS[market]
                  : isDynamicBoardScope
                    ? '选择具体板块后，这里会展示成分股预览'
                    : '这里展示预览代码；实际范围由后端决定，无需手动填写'
              }
              rows={4}
              disabled={!isCustomPool}
              className="min-h-[120px] w-full rounded-xl border border-white/10 bg-card px-4 py-3 text-sm text-foreground shadow-soft-card transition-all placeholder:text-muted-text focus:border-cyan/40 focus:outline-none focus:ring-4 focus:ring-cyan/15 hover:border-white/18"
            />
            <p className="mt-2 text-xs text-secondary-text">{poolHint}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant={isCustomPool ? 'warning' : 'info'}>
                {isCustomPool
                  ? '手工输入股票池'
                  : effectiveEstimatedCount
                    ? `预计 ${effectiveEstimatedCount} 只成分股`
                    : `预览 ${previewCodes.length} 只股票`}
              </Badge>
              {shouldRunAsync ? <Badge variant="warning">A 股全市场会自动后台扫描</Badge> : null}
              {isDynamicBoardScope || isPresetBoardScope ? <Badge variant="info">{market === 'cn' ? '真实板块成分股' : '行业代表池'}</Badge> : null}
              {isDynamicBoardScope && dynamicBoardTierSummary ? <Badge variant="warning">{dynamicBoardTierSummary}</Badge> : null}
            </div>
            {isDynamicBoardScope && selectedBoardName && dynamicBoardTiers.length ? (
              <div className="mt-4 rounded-2xl border border-white/8 bg-elevated/30 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-white">板块分层明细</p>
                    <p className="mt-1 text-xs text-secondary-text">
                      当前板块按后端维护的代表池分为龙头 / 中军 / 弹性三层，便于快速理解扫描覆盖。
                    </p>
                  </div>
                  {dynamicBoardTierSummary ? <Badge variant="info">{dynamicBoardTierSummary}</Badge> : null}
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {dynamicBoardTiers.map((tier, index) => (
                    <div key={`${tier.key}-${tier.label}`} className="rounded-2xl border border-white/8 bg-card/60 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-white">{tier.label}</span>
                        <Badge variant={TIER_BADGE_VARIANTS[index % TIER_BADGE_VARIANTS.length]}>
                          {tier.count || tier.codes.length} 只
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-secondary-text">
                        {tier.codes.length ? tier.codes.join('、') : '暂无成分股'}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {isDynamicBoardScope ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
            <Input
              label="搜索板块"
              labelSuffix={<HelpHint content={`输入关键字快速过滤${getMarketLabel(market)}板块目录，例如 半导体、创新药、金融。`} />}
              value={boardSearchText}
              onChange={(event) => setBoardSearchText(event.target.value)}
              placeholder={activeBoardType === 'concept' ? '如 人工智能、算力租赁、创新药' : '如 半导体、金融、消费零售'}
              hint={market === 'cn' ? '目录来自实时板块接口。' : '目录来自后端维护的行业代表池，后续可继续扩展数据源。'}
            />
            <Select
              label={activeBoardType === 'industry' ? '具体行业板块' : '具体概念板块'}
              labelSuffix={<HelpHint content={market === 'cn' ? '选择后会自动加载该板块的真实成分股预览；实际扫描会使用完整名单。' : '选择后会自动加载该行业池预览；实际扫描会使用完整代表池。'} />}
              value={selectedBoardName}
              onChange={(next) => {
                setSelectedBoardName(next);
                setPageError(null);
              }}
              options={filteredBoardOptions.map((item) => ({
                value: item.boardName,
                label: item.estimatedCount ? `${item.label}（约 ${item.estimatedCount} 只）` : item.label,
              }))}
              placeholder={filteredBoardOptions.length ? '请选择具体板块' : '暂无匹配板块'}
            />
          </div>
        ) : null}

        <div className="mt-5 grid gap-4 lg:grid-cols-4">
          <Input
            label="量能热度 >="
            labelSuffix={<HelpHint content="热度 = 最新成交量 / 近 20 日均量；大于 1 表示近期成交量高于常态。" />}
            type="number"
            value={heat}
            onChange={(event) => setHeat(event.target.value)}
            placeholder="如 1.5"
            hint="最新成交量 / 近 20 日均量。"
          />
          <Input
            label="扫描上限"
            labelSuffix={<HelpHint content="限制参与扫描的股票数量，适合控制全市场扫描耗时；结果展示数量仍按 200 条返回。" />}
            type="number"
            min={1}
            max={2000}
            value={scanLimit}
            onChange={(event) => setScanLimit(event.target.value)}
            placeholder={shouldRunAsync ? '如 300' : '可选'}
            hint={shouldRunAsync ? 'A 股全市场建议设置一个上限，减少后台扫描耗时。' : '留空表示按当前范围全部扫描。'}
          />
          <Select
            label="排序字段"
            labelSuffix={<HelpHint content="决定命中结果最终展示顺序；热度字段为空时会按 0 处理。" />}
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
            labelSuffix={<HelpHint content="降序更适合先看价格/热度高的标的；升序适合找低位或代码顺序。" />}
            value={sortDir}
            onChange={(next) => setSortDir(next as 'asc' | 'desc')}
            options={[
              { value: 'desc', label: '降序' },
              { value: 'asc', label: '升序' },
            ]}
          />
        </div>

        <div className="mt-4 rounded-2xl border border-white/8 bg-elevated/30 px-4 py-3 text-sm text-secondary-text">
          当前范围：<span className="text-white">{activeScope?.label}</span>
          {' · '}
          {isCustomPool
            ? '将按你输入的自定义股票池扫描。'
            : isDynamicBoardScope
              ? selectedBoardName
                ? `将按 ${selectedBoardName} 的完整股票池扫描${effectiveEstimatedCount ? `（约 ${effectiveEstimatedCount} 只）` : ''}。`
                : '请先从板块目录中选择一个具体板块。'
            : isPresetBoardScope
              ? `将按 ${activeScope?.boardName} 的完整股票池扫描${effectiveEstimatedCount ? `（约 ${effectiveEstimatedCount} 只）` : ''}；实时板块接口失败时会回退到维护清单。`
            : shouldRunAsync
              ? '将扫描 A 股全市场，并自动转到后台任务显示进度。'
              : `当前仅预览前 ${previewCodes.length} 只代码，实际会按后端维护的完整范围扫描${effectiveEstimatedCount ? `（约 ${effectiveEstimatedCount} 只）` : ''}。`}
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

            {formulaValidation?.valid ? (
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

            {formulaValidation && !formulaValidation.valid ? (
              <Card className="border border-warning/20 bg-warning/10">
                <div className="space-y-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="warning">公式未通过</Badge>
                    <span className="text-white">{formulaValidation.message}</span>
                  </div>
                  {formulaValidation.normalizedFormula ? (
                    <div className="font-mono text-secondary-text">{formulaValidation.normalizedFormula}</div>
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
              <span className="text-sm font-medium text-white">按当前范围开始选股</span>
              <span className="text-xs text-secondary-text">
                当前 {conditions.length} 个条件，范围为 {activeScope?.label}{scanLimit ? `，扫描上限 ${scanLimit} 只` : ''}
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
              当前为公式模式，范围为 {activeScope?.label}{scanLimit ? `，扫描上限 ${scanLimit} 只` : ''}。
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
            <Badge variant={isCustomPool ? 'warning' : 'info'}>
              {isCustomPool ? '当前为自定义股票池扫描' : `当前范围：${activeScope?.label}`}
            </Badge>
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
