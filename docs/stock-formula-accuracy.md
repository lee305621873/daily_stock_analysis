# Stock Formula Accuracy

## Scope

This document records the accuracy baseline for the unified stock screener formula engine.

The goal is not to claim absolute superiority over any third-party platform.
The goal is to make formula semantics explicit, testable, reproducible, and stable across releases.

## Accuracy principles

- Same formula + same normalized OHLCV input should produce the same result.
- Formula semantics must be documented instead of implied.
- Changes to formula behavior must be covered by regression tests.
- Market differences should be isolated in data normalization and stock-universe handling.

## Current calculation baseline

- Price and volume fields are normalized to:
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`
  - `amount`
- Rows are sorted by `date` ascending before formula execution.
- Final match decision uses the latest available bar.
- Missing or insufficient data may produce `NaN`; the final boolean decision falls back to `false` when no valid latest signal exists.

## Known sources of discrepancy vs external platforms

- Different data vendors or delayed data snapshots
- Different adjusted-price policies
- Different suspended-bar handling
- Different universe definitions for CN/HK/US
- Different proprietary implementations of certain indicators

## Verification strategy

- Unit tests for core functions
- Regression tests for common formulas
- API tests for formula validation and scanning
- Frontend tests for formula-mode submission and async progress flows

## Recommended benchmarking workflow

For formulas that must closely match another platform:

1. Pick a fixed ticker and date range
2. Freeze the OHLCV sample data
3. Run the formula in both systems
4. Record any output or signal mismatch
5. Classify the mismatch:
   - data source mismatch
   - adjustment mismatch
   - implementation mismatch
   - interpretation mismatch

This workflow is the basis for improving parity over time.
