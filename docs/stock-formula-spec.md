# Stock Formula Spec

## Goal

This document defines the unified screener formula DSL used by the Web/API stock screener.
The same formula syntax is designed to work across CN/HK/US markets after OHLCV data is normalized.

## Supported fields

- `OPEN`
- `HIGH`
- `LOW`
- `CLOSE`
- `VOL`
- `AMOUNT`

Short aliases are also supported and normalized automatically:

- `O -> OPEN`
- `H -> HIGH`
- `L -> LOW`
- `C -> CLOSE`
- `V -> VOL`

## Runtime compatibility helpers (THS/TDX style)

- `DYNAINFO(n)`:
  - currently supports:
    - `3/7`: latest price
    - `4`: high
    - `5`: low
    - `6`: open
    - `8`: volume
    - `10`: amount
    - `11`: change amount
    - `12`: change percent
    - `35`: PB
    - `39`: dynamic PE
    - `40`: total market value (亿元)
    - `41`: circulating market value (亿元)
- `FINANCE(n)`:
  - currently supports:
    - `1`: total shares (亿股)
    - `2/7`: circulating shares (亿股)
    - `6/34`: BPS / net asset per share
    - `30/46`: revenue YoY (%)
    - `33`: EPS
    - `35`: ROE (%)
    - `40/47`: net profit YoY (%)
    - `37`: total market value (亿元)
    - `38`: circulating market value (亿元)
    - `41`: PE
    - `42`: PB
- `NAMELIKE(pattern)`:
  - wildcard stock-name matching (`*`/`?`)
- Drawing/style statements are ignored during screener execution:
  - `DRAWICON(...)`, `DRAWTEXT(...)`, `DRAWTEXT_FIX(...)`, `DRAWNUMBER(...)`, `STICKLINE(...)`, `PLOYLINE/POLYLINE(...)`, `DRAWLINE(...)`, `DRAWRECTREL(...)`, `DRAWBAND(...)`, standalone `COLOR*`

## Operators

- Arithmetic: `+`, `-`, `*`, `/`, `%`, `**`
- Comparison: `>`, `>=`, `<`, `<=`, `=`, `==`, `!=`
- Boolean: `AND`, `OR`, `NOT`
- Grouping: `(`
`)`

## Expression rules

- Final formula should evaluate to a boolean series or a numeric series.
- When a numeric series is returned, non-zero is treated as `true`.
- The screener uses the latest available bar as the final match decision.
- Formula names are optional metadata and only affect result display.

## Multi-output functions

Some functions return multiple outputs and require attribute access:

- `MACD(...).macd`
- `MACD(...).signal`
- `MACD(...).hist`
- `KDJ(...).k`
- `KDJ(...).d`
- `KDJ(...).j`
- `BOLL(...).upper`
- `BOLL(...).mid`
- `BOLL(...).lower`
- `BOLL(...).bandwidth`
- `BOLL(...).percent_b`

## Examples

```txt
CROSS(MA(CLOSE,5), MA(CLOSE,20))
```

```txt
CLOSE > HHV(HIGH,20) AND VOL > 2 * MA(VOL,5)
```

```txt
EVERY(CLOSE > MA(CLOSE,20), 5) AND MACD(CLOSE,12,26,9).hist > 0
```

```txt
RSI(CLOSE,14) < 30 AND CLOSE > REF(CLOSE,1)
```

## Validation and safety

- Only whitelisted fields and functions are allowed.
- No script execution, imports, loops, comprehensions, lambdas, or arbitrary attribute access are allowed.
- Function calls must be direct calls to supported DSL functions.

## Market behavior

- Formula syntax is market-agnostic.
- Market differences such as stock code normalization, stock universe loading, and board/sector metadata are handled by the screener service and market adapters, not by the formula syntax itself.
