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
