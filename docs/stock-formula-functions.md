# Stock Formula Functions

## Trend

- `MA(series, period)`: simple moving average
- `EMA(series, period)`: exponential moving average
- `SMA(series, period, weight=1)`: Chinese-style smoothed moving average
- `WMA(series, period)`: weighted moving average

## Indicators

- `MACD(series, fast=12, slow=26, signal=9)`
  - outputs: `.macd`, `.signal`, `.hist`
- `RSI(series, period=14)`
- `KDJ(high, low, close, period=9, k_smooth=3, d_smooth=3)`
  - outputs: `.k`, `.d`, `.j`
- `BOLL(series, period=20, multiplier=2.0)`
  - outputs: `.upper`, `.mid`, `.lower`, `.bandwidth`, `.percent_b`
- `ATR(high, low, close, period=14)`
- `CCI(high, low, close, period=14)`
- `WR(high, low, close, period=14)`
- `OBV(close, vol)`
- `MFI(high, low, close, vol, period=14)`
- `ROC(series, period=12)`

## Utilities

- `REF(series, periods)`: shift series by `periods`
- `HHV(series, period)`: rolling max
- `LLV(series, period)`: rolling min
- `SUM(series, period)`: rolling sum
- `AVG(series, period)`: rolling average
- `STD(series, period)`: rolling standard deviation
- `ABS(value)`: absolute value
- `MAX(left, right)`: element-wise max
- `MIN(left, right)`: element-wise min
- `IF(condition, if_true, if_false)`: vectorized conditional

## Signal helpers

- `CROSS(left, right)`: cross-up signal
- `COUNT(condition, period)`: count true bars in window
- `EVERY(condition, period)`: all bars true in window
- `EXIST(condition, period)`: any bar true in window
- `BARSLAST(condition)`: bars since last true signal

## Runtime helpers (THS/TDX compatibility)

- `DYNAINFO(3/7)`: latest price
- `DYNAINFO(4/5/6)`: high / low / open
- `DYNAINFO(8/10)`: volume / amount
- `DYNAINFO(11/12)`: change amount / change percent
- `DYNAINFO(35/39)`: PB / dynamic PE
- `DYNAINFO(40/41)`: total / circulating market value (亿元)
- `FINANCE(1)`: total shares (亿股)
- `FINANCE(2/7)`: circulating shares (亿股)
- `FINANCE(6/34)`: BPS / net asset per share
- `FINANCE(30/46)`: revenue YoY (%)
- `FINANCE(33)`: EPS (with fallback derivation)
- `FINANCE(35)`: ROE (%)
- `FINANCE(40/47)`: net profit YoY (%)
- `FINANCE(37/38)`: total / circulating market value (亿元)
- `FINANCE(41/42)`: PE / PB
- `NAMELIKE(pattern)`: wildcard name match (`*`, `?`)

> Compatibility note:
> drawing/style statements (`DRAW*`, `COLOR*`) are accepted in pasted formulas but ignored for screener decisions.

## Example library

### MA cross

```txt
CROSS(MA(CLOSE,5), MA(CLOSE,20))
```

### Breakout with volume

```txt
CLOSE > HHV(HIGH,20) AND VOL > 2 * MA(VOL,5)
```

### Oversold rebound

```txt
RSI(CLOSE,14) < 30 AND CLOSE > REF(CLOSE,1)
```

### Trend continuation

```txt
EVERY(CLOSE > MA(CLOSE,20), 5) AND MACD(CLOSE,12,26,9).hist > 0
```

## Preset template notes

- Web 公式编辑器已内置 20+ 模板（当前 26 个），按四类组织：
  - 趋势跟随（MA/EMA/MACD/ROC）
  - 突破动量（HHV/Donchian/BOLL）
  - 均值回归（RSI/CCI/WR/MFI/KDJ）
  - 量价共振（VOL/OBV/ATR）
- “高胜率倾向”表示公开研究或公开回测中更常见的稳健规则组合，不代表未来收益保证；建议先做本地回测和参数微调。

## Public research and backtest references

- Meb Faber, *A Quantitative Approach to Tactical Asset Allocation* (10-month MA trend filter): [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)
- Brock, Lakonishok, LeBaron (1992), moving-average / breakout rule evidence: [Santa Fe Institute working paper page](https://www.santafe.edu/research/results/working-papers/simple-technical-trading-rules-and-the-stochastic)
- Moskowitz, Ooi, Pedersen (2012), time-series momentum: [Elsevier / JFE page](https://www.sciencedirect.com/science/article/abs/pii/S0304405X11002613)
- Jegadeesh & Titman (1993), medium-term momentum: [EconPapers](https://econpapers.repec.org/article/blajfinan/v_3a48_3ay_3a1993_3ai_3a1_3ap_3a65-91.htm)
- George & Hwang (2004), 52-week high effect: [Elsevier / JFE page](https://www.sciencedirect.com/science/article/abs/pii/S0304405X03002022)
- StockCharts, Connors RSI(2) strategy overview: [StockCharts article](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2)
- QuantifiedStrategies, RSI(2) backtest examples: [RSI 2 strategy](https://www.quantifiedstrategies.com/rsi-2-trading-strategy/)
- QuantifiedStrategies, Bollinger / MACD strategy backtests: [Bollinger](https://www.quantifiedstrategies.com/bollinger-bands-trading-strategy/) · [MACD](https://www.quantifiedstrategies.com/macd-trading-strategy/)
