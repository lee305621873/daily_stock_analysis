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
  ScreenerFormulaTemplate,
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
  { key: 'HEAT', name: '市场热度（个股量比热度）', category: '热度', summary: '当前成交量 / 近 20 日平均成交量，值越大说明短期交易更活跃。', params: [], outputs: [{ key: 'value', label: 'Heat' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'PE', name: '市盈率 PE', category: '估值', summary: '基于实时行情估值字段，适合做估值高低筛选。', params: [], outputs: [{ key: 'value', label: 'PE' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'PB', name: '市净率 PB', category: '估值', summary: '基于实时行情估值字段，适合和 ROE 组合做估值质量筛选。', params: [], outputs: [{ key: 'value', label: 'PB' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'PEG', name: 'PEG（估算）', category: '估值', summary: '按 PEG=PE/净利润同比(%) 估算，净利润同比<=0 或缺失时记为不可用。', params: [], outputs: [{ key: 'value', label: 'PEG' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'ROE', name: '净资产收益率 ROE', category: '基本面', summary: '来源于基本面聚合中的 growth 数据块，当前以 A 股可用性最佳。', params: [], outputs: [{ key: 'value', label: 'ROE' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'REVENUE_YOY', name: '营收同比增长率', category: '基本面', summary: '来源于基本面聚合中的 revenue_yoy 字段（同比%）。', params: [], outputs: [{ key: 'value', label: 'Revenue YoY' }], operators: ['>', '>=', '<', '<=', '='] },
  { key: 'NET_PROFIT_YOY', name: '净利润同比增长率', category: '基本面', summary: '来源于基本面聚合中的 net_profit_yoy 字段（同比%）。', params: [], outputs: [{ key: 'value', label: 'Net Profit YoY' }], operators: ['>', '>=', '<', '<=', '='] },
];

const FORMULA_TEMPLATES = [
  { label: '均线金叉（5/20）', value: 'CROSS(MA(CLOSE,5), MA(CLOSE,20))' },
  { label: '中期趋势金叉（20/60）', value: 'CROSS(MA(CLOSE,20), MA(CLOSE,60))' },
  { label: 'EMA 动量金叉（12/26）', value: 'CROSS(EMA(CLOSE,12), EMA(CLOSE,26))' },
  { label: '多头排列启动', value: 'MA(CLOSE,20) > MA(CLOSE,60) AND MA(CLOSE,60) > MA(CLOSE,120) AND CLOSE > MA(CLOSE,20)' },
  { label: '回踩 20 日线再走强', value: 'MA(CLOSE,20) > MA(CLOSE,60) AND CLOSE > MA(CLOSE,20) AND REF(CLOSE,1) <= REF(MA(CLOSE,20),1)' },
  { label: 'MACD 零轴上方转强', value: 'MACD(CLOSE,12,26,9).macd > 0 AND CROSS(MACD(CLOSE,12,26,9).hist, 0)' },
  { label: 'MACD 柱体连续走强', value: 'EVERY(MACD(CLOSE,12,26,9).hist > REF(MACD(CLOSE,12,26,9).hist,1), 3) AND MACD(CLOSE,12,26,9).hist > 0' },
  { label: '12 月动量为正', value: 'ROC(CLOSE,252) > 0 AND CLOSE > MA(CLOSE,120)' },
  { label: '双周期动量确认（63/126）', value: 'ROC(CLOSE,63) > 0 AND ROC(CLOSE,126) > 0 AND CLOSE > MA(CLOSE,60)' },
  { label: '52 周新高突破', value: 'CLOSE >= HHV(HIGH,252) * 0.995 AND VOL > MA(VOL,20)' },
  { label: '放量突破 20 日新高', value: 'CLOSE > HHV(HIGH,20) AND VOL > 2 * MA(VOL,5)' },
  { label: '55 日唐奇安突破', value: 'CLOSE > HHV(HIGH,55) AND ATR(HIGH,LOW,CLOSE,14) > MA(ATR(HIGH,LOW,CLOSE,14),20)' },
  { label: '布林上轨突破 + 带宽放大', value: 'CLOSE > BOLL(CLOSE,20,2).upper AND BOLL(CLOSE,20,2).bandwidth > REF(BOLL(CLOSE,20,2).bandwidth,1)' },
  { label: '布林挤压后突破', value: 'BOLL(CLOSE,20,2).bandwidth < LLV(BOLL(CLOSE,20,2).bandwidth,60) * 1.2 AND CLOSE > BOLL(CLOSE,20,2).upper' },
  { label: 'RSI(2) 超卖反弹（强均值回归）', value: 'RSI(CLOSE,2) < 10 AND CLOSE > MA(CLOSE,200)' },
  { label: 'RSI(14) 超卖拐头', value: 'RSI(CLOSE,14) < 30 AND CLOSE > REF(CLOSE,1)' },
  { label: 'CCI 超卖反弹', value: 'CCI(HIGH,LOW,CLOSE,20) < -100 AND CLOSE > REF(CLOSE,1)' },
  { label: 'WR 超卖反弹', value: 'WR(HIGH,LOW,CLOSE,14) > 80 AND CLOSE > REF(CLOSE,1)' },
  { label: 'MFI 超卖反弹', value: 'MFI(HIGH,LOW,CLOSE,VOL,14) < 20 AND CLOSE > REF(CLOSE,1)' },
  { label: 'KDJ 超卖金叉', value: 'KDJ(HIGH,LOW,CLOSE,9,3,3).j < 20 AND CROSS(KDJ(HIGH,LOW,CLOSE,9,3,3).k, KDJ(HIGH,LOW,CLOSE,9,3,3).d)' },
  { label: '下轨均值回归', value: 'CLOSE < BOLL(CLOSE,20,2).lower AND RSI(CLOSE,6) < 25' },
  { label: 'OBV 资金确认突破', value: 'CLOSE > MA(CLOSE,20) AND OBV(CLOSE,VOL) > MA(OBV(CLOSE,VOL),20)' },
  { label: '缩量蓄势后突破', value: 'COUNT(VOL < MA(VOL,20), 10) >= 7 AND CLOSE > HHV(HIGH,10)' },
  { label: 'ATR 收缩后放量启动', value: 'ATR(HIGH,LOW,CLOSE,14) < MA(ATR(HIGH,LOW,CLOSE,14),20) AND VOL > 1.5 * MA(VOL,20) AND CLOSE > MA(CLOSE,20)' },
  { label: '金叉后二次确认', value: 'EXIST(CROSS(MA(CLOSE,5), MA(CLOSE,20)), 5) AND CLOSE > MA(CLOSE,20)' },
  { label: '短线超跌反转（3 日 RSI）', value: 'CLOSE < LLV(LOW,5) * 1.02 AND RSI(CLOSE,3) < 15 AND CLOSE > REF(CLOSE,1)' },
];

const LEGACY_CUSTOM_FORMULA_STORAGE_KEY = 'dsa.screener.custom-formulas.v1';
const MAX_CUSTOM_FORMULA_TEMPLATES = 200;
type CustomFormulaTemplate = ScreenerFormulaTemplate;

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

function normalizeCustomTemplates(items: CustomFormulaTemplate[]): CustomFormulaTemplate[] {
  return items
    .filter((item) => item && typeof item.id === 'string' && typeof item.label === 'string' && typeof item.value === 'string')
    .slice(0, MAX_CUSTOM_FORMULA_TEMPLATES);
}

function loadLegacyCustomFormulaTemplates(): CustomFormulaTemplate[] {
  try {
    const raw = window.localStorage.getItem(LEGACY_CUSTOM_FORMULA_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as CustomFormulaTemplate[];
    if (!Array.isArray(parsed)) return [];
    return normalizeCustomTemplates(parsed);
  } catch (error) {
    console.error('Failed to load legacy custom formula templates:', error);
    return [];
  }
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
  const compareIndicator = value.compareTo.indicator || metaList[0]?.key || meta?.key || '';
  const compareMeta = metaList.find((item) => item.key === compareIndicator);
  const isCrossOperator = value.operator === 'cross_up' || value.operator === 'cross_down';
  const compareType = isCrossOperator ? 'indicator' : value.compareTo.type;

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

        {meta?.outputs.length && meta.outputs.length > 1 ? (
          <Select
            className="xl:w-40"
            label="输出"
            labelSuffix={<HelpHint content={HINT_TEXT.conditionOutput} />}
            value={value.output || meta.outputs[0].key}
            onChange={(next) => update({ output: next })}
            options={meta.outputs.map((output) => ({ value: output.key, label: output.label }))}
          />
        ) : null}

        <Select
          className="xl:w-40"
          label="比较"
          labelSuffix={<HelpHint content={HINT_TEXT.conditionOperator} />}
          value={value.operator}
          onChange={(next) => {
            const nextOperator = next as Operator;
            if ((nextOperator === 'cross_up' || nextOperator === 'cross_down') && value.compareTo.type !== 'indicator') {
              update({
                operator: nextOperator,
                compareTo: {
                  ...value.compareTo,
                  type: 'indicator',
                  indicator: value.compareTo.indicator || metaList[0]?.key,
                },
              });
              return;
            }
            update({ operator: nextOperator });
          }}
          options={(meta?.operators || []).map((operator) => ({ value: operator, label: operator }))}
        />

        {isCrossOperator ? (
          <div className="xl:w-40">
            <label className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-foreground">
              <span>右侧</span>
              <HelpHint content={HINT_TEXT.conditionCrossRight} />
            </label>
            <div className="h-11 rounded-xl border border-white/10 bg-elevated/35 px-3 text-sm text-secondary-text flex items-center">
              另一指标
            </div>
          </div>
        ) : (
          <Select
            className="xl:w-40"
            label="右侧"
            labelSuffix={<HelpHint content={HINT_TEXT.conditionRightSide} />}
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
        )}

        {compareType === 'indicator' ? (
          <>
            <Select
              className="xl:w-52"
              label="对比指标"
              labelSuffix={compareMeta?.summary ? <HelpHint content={compareMeta.summary} /> : undefined}
              value={compareIndicator}
              onChange={(next) => update({ compareTo: { ...value.compareTo, indicator: next as IndicatorKey } })}
              options={metaList.map((item) => ({ value: item.key, label: item.name }))}
            />
            {compareMeta?.outputs.length && compareMeta.outputs.length > 1 ? (
              <Select
                className="xl:w-40"
                label="对比输出"
                value={value.compareTo.output || compareMeta.outputs[0].key}
                onChange={(next) => update({ compareTo: { ...value.compareTo, output: next } })}
                options={compareMeta.outputs.map((output) => ({ value: output.key, label: output.label }))}
              />
            ) : null}
          </>
        ) : (
          <Input
            className="xl:w-40"
            label="阈值"
            labelSuffix={<HelpHint content={HINT_TEXT.conditionThreshold} />}
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

const HINT_TEXT = {
  conditionOutput: '仅多输出指标显示该项。例：MACD 可选 Diff/Dea/柱子；RSI 单输出时会自动使用默认输出。',
  conditionOperator: '支持数值比较与金叉/死叉。选择 cross_up/cross_down 时会自动切换为“指标对指标”。',
  conditionCrossRight: '金叉/死叉必须比较两条指标序列，不能与固定阈值比较。',
  conditionRightSide: '阈值：与固定数字比较；另一指标：两条指标（或输出）之间比较。',
  conditionThreshold: '示例：RSI < 30、PE < 25、热度 > 1.5。建议先用宽条件，再逐步收紧。',
  market: '先选市场再选范围。A 股支持真实行业/概念板块；港股/美股优先使用维护行业池并持续扩充。',
  scope: '范围决定候选股票池。全市场适合摸排，板块适合主题扫描，自定义适合小样本快速验证。',
  mode: '条件模式=可视化条件；公式模式=DSL 规则；组合模式=公式+条件同时生效，结果取交集。',
  pool: '自定义股票池支持逗号、空格、换行。范围预览是候选代码展示，扫描时按完整范围执行。',
  boardSearch: '输入关键字过滤板块，如：半导体、创新药、金融、算力、AI。',
  boardSelect: '选择后会加载预览；开始扫描时使用该板块完整成分股，不受预览条数限制。',
  heat: '热度=最新成交量/近20日均量。常用阈值：1.2（温和放量）、1.5（明显放量）、2.0（强放量）。',
  scanLimit: '限制参与扫描的股票数量以控制耗时。调试建议 100-300，正式跑全市场可留空。',
  sortBy: '决定命中结果优先级。按热度适合找活跃标的；按价格/代码适合列表巡检。',
  sortDir: '降序优先看高值，升序优先看低值或代码顺序。',
} as const;

function buildFallbackScopes(market: MarketType): ScreenerScopeOption[] {
  if (market === 'cn') {
    return [{ key: 'all_market', market, label: 'A 股全市场', description: MARKET_HINTS.cn, kind: 'full_market', estimatedCount: null, previewCodes: [] }];
  }
  return [{ key: 'custom_pool', market, label: '自定义股票池', description: MARKET_HINTS[market], kind: 'custom_pool', estimatedCount: null, previewCodes: [] }];
}

function pickPreferredScopeKey(scopes: ScreenerScopeOption[]): string {
  const customPool = scopes.find((item) => item.key === 'custom_pool');
  return customPool?.key || scopes[0]?.key || 'custom_pool';
}

function getMarketLabel(market: MarketType): string {
  if (market === 'cn') return 'A股';
  if (market === 'hk') return '港股';
  return '美股';
}

const HelpHint: React.FC<{ content: string }> = ({ content }) => (
  <span className="group relative inline-flex">
    <span
      tabIndex={0}
      aria-label={content}
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/12 bg-white/6 text-[11px] font-semibold text-secondary-text cursor-help outline-none"
    >
      ?
    </span>
    <span
      role="tooltip"
      className="pointer-events-none absolute left-1/2 top-full z-[80] mt-2 w-72 -translate-x-1/2 rounded-lg border border-white/15 bg-slate-950/95 px-3 py-2 text-xs leading-5 text-slate-100 shadow-xl shadow-black/40 opacity-0 invisible transition-opacity duration-150 group-hover:opacity-100 group-hover:visible group-focus-within:opacity-100 group-focus-within:visible"
    >
      {content}
    </span>
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
  const [scanMode, setScanMode] = useState<ScreenerMode>('hybrid');
  const [formulaName, setFormulaName] = useState(FORMULA_TEMPLATES[0].label);
  const [formulaText, setFormulaText] = useState(FORMULA_TEMPLATES[0].value);
  const [selectedOfficialTemplate, setSelectedOfficialTemplate] = useState('');
  const [customFormulaTemplates, setCustomFormulaTemplates] = useState<CustomFormulaTemplate[]>([]);
  const [selectedCustomTemplateId, setSelectedCustomTemplateId] = useState('');
  const [formulaEditorNotice, setFormulaEditorNotice] = useState<string | null>(null);
  const [formulaValidation, setFormulaValidation] = useState<FormulaValidationResponse | null>(null);
  const [formulaValidationError, setFormulaValidationError] = useState<ParsedApiError | null>(null);
  const [market, setMarket] = useState<MarketType>('cn');
  const [scanScope, setScanScope] = useState('custom_pool');
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
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isExportingXlsx, setIsExportingXlsx] = useState(false);
  const [pageError, setPageError] = useState<ParsedApiError | null>(null);
  const [metadataWarning, setMetadataWarning] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const loadMetadata = async () => {
      const [indicatorResult, functionResult, scopeResult] = await Promise.allSettled([
        screenerApi.getIndicators(),
        screenerApi.getFormulaFunctions(),
        screenerApi.getScopes(),
      ]);

      let hasError = false;
      if (indicatorResult.status === 'fulfilled' && indicatorResult.value.length > 0) {
        setIndicators(indicatorResult.value);
        setConditions([createDefaultCondition(indicatorResult.value[0].key)]);
      } else if (indicatorResult.status === 'rejected') {
        console.error('Failed to load screener indicators:', indicatorResult.reason);
        hasError = true;
      }

      if (functionResult.status === 'fulfilled') {
        setFormulaFunctions(functionResult.value);
      } else {
        console.error('Failed to load screener formula functions:', functionResult.reason);
        hasError = true;
      }

      if (scopeResult.status === 'fulfilled') {
        const groupedScopes: Record<MarketType, ScreenerScopeOption[]> = {
          cn: scopeResult.value.filter((item) => item.market === 'cn'),
          hk: scopeResult.value.filter((item) => item.market === 'hk'),
          us: scopeResult.value.filter((item) => item.market === 'us'),
        };
        setScopeCatalog({
          cn: groupedScopes.cn.length ? groupedScopes.cn : buildFallbackScopes('cn'),
          hk: groupedScopes.hk.length ? groupedScopes.hk : buildFallbackScopes('hk'),
          us: groupedScopes.us.length ? groupedScopes.us : buildFallbackScopes('us'),
        });
      } else {
        console.error('Failed to load screener scopes:', scopeResult.reason);
        hasError = true;
      }

      if (hasError) {
        setMetadataWarning('部分选股元数据加载失败，已对失败部分使用本地兜底。');
      } else {
        setMetadataWarning(null);
      }
    };
    void loadMetadata();
  }, []);

  useEffect(() => {
    const availableScopes = scopeCatalog[market] || [];
    if (!availableScopes.length) return;
    if (!availableScopes.some((item) => item.key === scanScope)) {
      setScanScope(pickPreferredScopeKey(availableScopes));
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

  useEffect(() => {
    let cancelled = false;
    const loadTemplates = async () => {
      try {
        const remoteTemplates = normalizeCustomTemplates(await screenerApi.listFormulaTemplates());
        if (cancelled) return;
        const legacyTemplates = loadLegacyCustomFormulaTemplates();
        if (legacyTemplates.length === 0) {
          setCustomFormulaTemplates(remoteTemplates);
          return;
        }

        const missingLegacyTemplates = legacyTemplates.filter(
          (legacy) =>
            !remoteTemplates.some(
              (remote) => remote.id === legacy.id || (remote.label === legacy.label && remote.value === legacy.value),
            ),
        );
        if (missingLegacyTemplates.length === 0) {
          setCustomFormulaTemplates(remoteTemplates.length ? remoteTemplates : legacyTemplates);
          window.localStorage.removeItem(LEGACY_CUSTOM_FORMULA_STORAGE_KEY);
          return;
        }

        try {
          const migrated = await Promise.all(
            missingLegacyTemplates.map((item) => screenerApi.upsertFormulaTemplate({ id: item.id, label: item.label, value: item.value })),
          );
          if (cancelled) return;
          const mergedMap = new Map<string, CustomFormulaTemplate>();
          for (const item of [...migrated, ...remoteTemplates]) {
            mergedMap.set(item.id, item);
          }
          const mergedTemplates = normalizeCustomTemplates(Array.from(mergedMap.values()));
          setCustomFormulaTemplates(mergedTemplates);
          window.localStorage.removeItem(LEGACY_CUSTOM_FORMULA_STORAGE_KEY);
          setFormulaEditorNotice(`已自动迁移 ${migrated.length} 条“我的公式”到服务端`);
        } catch (migrationError) {
          console.error('Failed to migrate legacy custom formula templates:', migrationError);
          setCustomFormulaTemplates(remoteTemplates.length ? remoteTemplates : legacyTemplates);
        }
      } catch (error) {
        console.error('Failed to load custom formula templates from backend:', error);
        if (cancelled) return;
        setCustomFormulaTemplates(loadLegacyCustomFormulaTemplates());
      }
    };
    void loadTemplates();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSaveCustomFormulaTemplate = async () => {
    const normalizedFormula = formulaText.trim();
    const normalizedName = formulaName.trim();
    if (!normalizedFormula) {
      setFormulaValidationError(createParsedApiError({
        title: '公式不能为空',
        message: '请先输入自定义公式，再保存到“我的公式”。',
        category: 'missing_params',
      }));
      return;
    }

    try {
      const saved = await screenerApi.upsertFormulaTemplate({
        id: selectedCustomTemplateId || undefined,
        label: normalizedName || `自定义公式 ${customFormulaTemplates.length + 1}`,
        value: normalizedFormula,
      });
      setCustomFormulaTemplates((previous) =>
        [saved, ...previous.filter((item) => item.id !== saved.id)].slice(0, MAX_CUSTOM_FORMULA_TEMPLATES),
      );
      setSelectedCustomTemplateId(saved.id);
      setSelectedOfficialTemplate('');
      setFormulaEditorNotice(`已保存到“我的公式”：${saved.label}`);
      setFormulaValidationError(null);
    } catch (error) {
      setFormulaValidationError(getParsedApiError(error));
    }
  };

  const handleDeleteCustomFormulaTemplate = async () => {
    if (!selectedCustomTemplateId) return;
    const deleting = customFormulaTemplates.find((item) => item.id === selectedCustomTemplateId);
    try {
      const result = await screenerApi.deleteFormulaTemplate(selectedCustomTemplateId);
      setCustomFormulaTemplates((previous) => previous.filter((item) => item.id !== selectedCustomTemplateId));
      setSelectedCustomTemplateId('');
      if (!result.deleted) {
        setFormulaEditorNotice('当前模板已不存在，列表已刷新。');
        return;
      }
      setFormulaEditorNotice(deleting ? `已删除“我的公式”：${deleting.label}` : '已删除当前自定义公式');
    } catch (error) {
      setFormulaValidationError(getParsedApiError(error));
    }
  };

  const applyOfficialTemplate = (templateValue: string) => {
    setSelectedOfficialTemplate(templateValue);
    setSelectedCustomTemplateId('');
    const selected = FORMULA_TEMPLATES.find((item) => item.value === templateValue);
    if (!selected) return;
    setFormulaText(selected.value);
    setFormulaName(selected.label);
    setFormulaValidation(null);
    setFormulaValidationError(null);
    setFormulaEditorNotice(`已套用模板：${selected.label}`);
  };

  const applyCustomTemplate = (templateId: string) => {
    setSelectedCustomTemplateId(templateId);
    setSelectedOfficialTemplate('');
    const selected = customFormulaTemplates.find((item) => item.id === templateId);
    if (!selected) return;
    setFormulaText(selected.value);
    setFormulaName(selected.label);
    setFormulaValidation(null);
    setFormulaValidationError(null);
    setFormulaEditorNotice(`已加载“我的公式”：${selected.label}`);
  };

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

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleExport = async (format: 'csv' | 'xlsx') => {
    const activeTaskIdForExport = taskInfo?.status === 'completed' ? taskInfo.taskId : null;
    const hasVisibleRows = Boolean(results?.results?.length);
    if (!activeTaskIdForExport && !hasVisibleRows) {
      return;
    }

    const setLoading = format === 'csv' ? setIsExportingCsv : setIsExportingXlsx;
    setLoading(true);
    try {
      let blob: Blob;
      if (activeTaskIdForExport) {
        blob = await screenerApi.exportTaskResults(activeTaskIdForExport, format, 'all');
      } else if (format === 'csv' && results?.csv) {
        blob = new Blob([results.csv], { type: 'text/csv;charset=utf-8' });
      } else {
        blob = await screenerApi.exportRows(
          results?.results || [],
          format,
          `stock-screener-${market}-visible`,
        );
      }
      const suffix = format === 'csv' ? 'csv' : 'xlsx';
      const taskToken = activeTaskIdForExport ? `-${activeTaskIdForExport.slice(0, 8)}` : '';
      triggerDownload(blob, `stock-screener-${market}${taskToken}.${suffix}`);
    } catch (error) {
      setPageError(getParsedApiError(error));
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    const trimmedFormula = formulaText.trim();
    const formulaModeActive = scanMode === 'formula' || scanMode === 'hybrid';
    const conditionModeActive = scanMode === 'condition' || scanMode === 'hybrid';
    if (activeTaskId && taskInfo && (taskInfo.status === 'pending' || taskInfo.status === 'processing')) {
      setPageError(createParsedApiError({
        title: '后台任务进行中',
        message: '当前已有后台选股任务在执行，请等待完成后再发起新的扫描。',
        category: 'http_error',
      }));
      return;
    }

    if (formulaModeActive && !trimmedFormula) {
      const error = createParsedApiError({
        title: '公式不能为空',
        message: '当前模式包含公式条件，请先填写公式。',
        category: 'missing_params',
      });
      setFormulaValidation(null);
      setFormulaValidationError(error);
      return;
    }

    if (formulaModeActive) {
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

    const effectiveBoardName = isDynamicBoardScope
      ? selectedBoardName.trim()
      : (isPresetBoardScope ? (activeScope?.boardName || '').trim() : '');
    const effectiveBoardType = isDynamicBoardScope || isPresetBoardScope
      ? activeBoardType || undefined
      : undefined;

    if (isDynamicBoardScope && !effectiveBoardName) {
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
        conditions: conditionModeActive ? conditions : undefined,
        formula: formulaModeActive ? trimmedFormula : undefined,
        formulaName: formulaModeActive ? formulaName.trim() || undefined : undefined,
        market,
        scope: activeScope?.key,
        boardName: effectiveBoardName || undefined,
        boardType: effectiveBoardType,
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
        setIsLoading(false);
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
  const shouldRunAsync = effectiveCodes.length === 0 || effectiveCodes.length > 50;
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
        const preview = await screenerApi.getBoardPreview(market, previewBoardType, previewBoardName, 0);
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
  const formulaComplexity = useMemo(() => {
    if (!formulaValidation?.complexityLevel) return null;
    const level = String(formulaValidation.complexityLevel).toLowerCase();
    if (level === 'low') return { label: '低复杂度', variant: 'success' as const };
    if (level === 'high') return { label: '高复杂度', variant: 'warning' as const };
    return { label: '中复杂度', variant: 'info' as const };
  }, [formulaValidation]);
  const formulaFunctionUsageEntries = useMemo(() => {
    if (!formulaValidation?.functionUsage) return [] as Array<[string, number]>;
    return Object.entries(formulaValidation.functionUsage).sort((a, b) => b[1] - a[1]);
  }, [formulaValidation]);
  const isFormulaEnabled = scanMode === 'formula' || scanMode === 'hybrid';
  const isConditionEnabled = scanMode === 'condition' || scanMode === 'hybrid';

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
            <Badge variant="success">组合模式</Badge>
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
            labelSuffix={<HelpHint content={HINT_TEXT.market} />}
            onChange={(next) => {
              const nextMarket = next as MarketType;
              setMarket(nextMarket);
              setScanScope(pickPreferredScopeKey(scopeCatalog[nextMarket] || buildFallbackScopes(nextMarket)));
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
            labelSuffix={<HelpHint content={HINT_TEXT.scope} />}
            value={activeScope?.key || ''}
            onChange={(next) => {
              setScanScope(next);
              setPageError(null);
            }}
            options={scopeOptions.map((item) => ({ value: item.key, label: item.label }))}
          />
          <Select
            label="选股模式"
            labelSuffix={<HelpHint content={HINT_TEXT.mode} />}
            value={scanMode}
            onChange={(next) => {
              setScanMode(next as ScreenerMode);
              setFormulaValidation(null);
              setFormulaValidationError(null);
            }}
            options={[
              { value: 'condition', label: '条件模式' },
              { value: 'formula', label: '公式模式' },
              { value: 'hybrid', label: '组合模式（公式 + 条件）' },
            ]}
          />

          <div className="flex flex-col">
            <label htmlFor="screener-codes" className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-foreground">
              <span>{isCustomPool ? '自定义股票池' : '范围预览'}</span>
              <HelpHint content={HINT_TEXT.pool} />
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
              {shouldRunAsync ? <Badge variant="warning">当前范围会自动后台扫描</Badge> : null}
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
              labelSuffix={<HelpHint content={HINT_TEXT.boardSearch} />}
              value={boardSearchText}
              onChange={(event) => setBoardSearchText(event.target.value)}
              placeholder={activeBoardType === 'concept' ? '如 人工智能、算力租赁、创新药' : '如 半导体、金融、消费零售'}
              hint={market === 'cn' ? '目录来自实时板块接口。' : '目录来自后端维护的行业代表池，后续可继续扩展数据源。'}
            />
            <Select
              label={activeBoardType === 'industry' ? '具体行业板块' : '具体概念板块'}
              labelSuffix={<HelpHint content={HINT_TEXT.boardSelect} />}
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
            labelSuffix={<HelpHint content={HINT_TEXT.heat} />}
            type="number"
            value={heat}
            onChange={(event) => setHeat(event.target.value)}
            placeholder="如 1.5"
            hint="最新成交量 / 近 20 日均量。"
          />
          <Input
            label="扫描上限"
            labelSuffix={<HelpHint content={HINT_TEXT.scanLimit} />}
            type="number"
            min={1}
            max={2000}
            value={scanLimit}
            onChange={(event) => setScanLimit(event.target.value)}
            placeholder={shouldRunAsync ? '如 300' : '可选'}
            hint={shouldRunAsync ? '后台扫描建议设置一个上限，减少任务耗时。' : '留空表示按当前范围全部扫描。'}
          />
          <Select
            label="排序字段"
            labelSuffix={<HelpHint content={HINT_TEXT.sortBy} />}
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
            labelSuffix={<HelpHint content={HINT_TEXT.sortDir} />}
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

      {isFormulaEnabled ? (
        <Card title="公式编辑器" subtitle="统一公式 DSL，可复用到 A 股、港股、美股">
          <div className="space-y-4">
            <div className="grid gap-4 xl:grid-cols-[240px_240px_minmax(0,1fr)]">
              <Select
                label="官方模板"
                value={selectedOfficialTemplate}
                onChange={applyOfficialTemplate}
                placeholder=""
                options={[
                  { value: '', label: '选择一个模板' },
                  ...FORMULA_TEMPLATES.map((item) => ({ value: item.value, label: item.label })),
                ]}
              />
              <Select
                label="我的公式"
                value={selectedCustomTemplateId}
                onChange={(next) => {
                  if (!next) {
                    setSelectedCustomTemplateId('');
                    return;
                  }
                  applyCustomTemplate(next);
                }}
                placeholder=""
                options={[
                  { value: '', label: customFormulaTemplates.length ? '选择已保存公式' : '暂无已保存公式' },
                  ...customFormulaTemplates.map((item) => ({ value: item.id, label: item.label })),
                ]}
              />
              <Input
                label="公式名称"
                value={formulaName}
                onChange={(event) => {
                  setFormulaName(event.target.value);
                  setFormulaEditorNotice(null);
                }}
                placeholder="如 趋势延续 / 放量突破"
                hint="名称会显示在结果列表中；加载“我的公式”后可直接覆盖保存。"
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
                  if (selectedOfficialTemplate) {
                    setSelectedOfficialTemplate('');
                  }
                  setFormulaEditorNotice(null);
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
              <Button type="button" variant="outline" onClick={handleSaveCustomFormulaTemplate}>
                保存到我的公式
              </Button>
              <Button type="button" variant="outline" onClick={handleDeleteCustomFormulaTemplate} disabled={!selectedCustomTemplateId}>
                删除当前我的公式
              </Button>
              <Badge variant="info">支持 OHLCV / MA / EMA / MACD / RSI / KDJ / BOLL / ATR / COUNT / EVERY / CROSS</Badge>
            </div>

            {formulaEditorNotice ? (
              <Card className="border border-cyan/20 bg-cyan/5">
                <div className="text-sm text-cyan">{formulaEditorNotice}</div>
              </Card>
            ) : null}

            {formulaValidation?.valid ? (
              <Card className="border border-cyan/20 bg-cyan/5">
                <div className="space-y-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="success">校验通过</Badge>
                    <span className="text-secondary-text">{formulaSummary}</span>
                  </div>
                  <div className="font-mono text-white">{formulaValidation.normalizedFormula}</div>
                  <div className="flex flex-wrap gap-2">
                    {formulaComplexity ? <Badge variant={formulaComplexity.variant}>{formulaComplexity.label}</Badge> : null}
                    {typeof formulaValidation.complexityScore === 'number' ? (
                      <Badge variant="info">复杂度评分 {formulaValidation.complexityScore}</Badge>
                    ) : null}
                    {typeof formulaValidation.expressionNodes === 'number' ? (
                      <Badge variant="info">表达式节点 {formulaValidation.expressionNodes}</Badge>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {formulaValidation.functions.map((item) => (
                      <Badge key={item} variant="info">{item}</Badge>
                    ))}
                  </div>
                  {formulaFunctionUsageEntries.length ? (
                    <div className="space-y-1">
                      <div className="text-secondary-text">函数调用分布</div>
                      <div className="flex flex-wrap gap-2">
                        {formulaFunctionUsageEntries.map(([name, count]) => (
                          <Badge key={name} variant="warning">{name} x{count}</Badge>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {formulaValidation.warnings.length ? (
                    <div className="space-y-1 text-secondary-text">
                      {formulaValidation.warnings.map((warning) => (
                        <div key={warning}>- {warning}</div>
                      ))}
                    </div>
                  ) : null}
                  {formulaValidation.suggestions?.length ? (
                    <div className="space-y-1 text-secondary-text">
                      <div className="text-white">优化建议</div>
                      {formulaValidation.suggestions.map((suggestion) => (
                        <div key={suggestion}>- {suggestion}</div>
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

      {isConditionEnabled ? (
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
      ) : null}

      <StickyActionBar>
        <div className="mr-auto flex flex-col gap-1 px-1">
          <span className="text-sm font-medium text-white">按当前范围开始选股</span>
          <span className="text-xs text-secondary-text">
            {scanMode === 'hybrid'
              ? `当前为组合模式（公式 + ${conditions.length} 条条件），范围为 ${activeScope?.label}${scanLimit ? `，扫描上限 ${scanLimit} 只` : ''}。`
              : scanMode === 'formula'
                ? `当前为公式模式，范围为 ${activeScope?.label}${scanLimit ? `，扫描上限 ${scanLimit} 只` : ''}。`
                : `当前 ${conditions.length} 个条件，范围为 ${activeScope?.label}${scanLimit ? `，扫描上限 ${scanLimit} 只` : ''}。`}
          </span>
        </div>
        {isConditionEnabled ? (
          <Button type="button" variant="secondary" onClick={handleAddCondition}>
            添加条件
          </Button>
        ) : null}
        {isFormulaEnabled ? (
          <Button type="button" variant="secondary" onClick={handleValidateFormula} isLoading={isValidatingFormula} loadingText="校验中...">
            校验公式
          </Button>
        ) : null}
        <Button type="button" onClick={handleScan} isLoading={isLoading} loadingText="扫描中..." glow>
          开始选股
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleExport('xlsx')}
          disabled={!(results?.results?.length || taskInfo?.status === 'completed')}
          isLoading={isExportingXlsx}
          loadingText="导出中..."
        >
          导出 Excel
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleExport('csv')}
          disabled={!(results?.results?.length || taskInfo?.status === 'completed')}
          isLoading={isExportingCsv}
          loadingText="导出中..."
        >
          导出 CSV
        </Button>
      </StickyActionBar>

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
            <Badge variant={scanMode === 'hybrid' ? 'success' : scanMode === 'formula' ? 'info' : 'warning'}>
              {scanMode === 'hybrid' ? '当前为组合模式' : scanMode === 'formula' ? '当前为公式模式' : '当前为条件模式'}
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
