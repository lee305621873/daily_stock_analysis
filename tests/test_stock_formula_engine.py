# -*- coding: utf-8 -*-
"""Unit tests for the stock formula engine."""

from __future__ import annotations

import unittest

import pandas as pd

from src.services.stock_formula_engine import FormulaValidationError, StockFormulaEngine


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=40, freq="D"),
            "open": [10 + i * 0.2 for i in range(40)],
            "high": [10.3 + i * 0.2 for i in range(40)],
            "low": [9.8 + i * 0.2 for i in range(40)],
            "close": [10 + i * 0.25 for i in range(40)],
            "volume": [1000 + i * 100 for i in range(40)],
            "amount": [10000 + i * 1000 for i in range(40)],
        }
    )


class StockFormulaEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = StockFormulaEngine()
        self.df = _sample_df()

    def test_validate_formula_success(self) -> None:
        result = self.engine.validate("CROSS(MA(CLOSE,5), MA(CLOSE,20)) AND RSI(CLOSE,14) < 70")

        self.assertTrue(result.valid)
        self.assertIn("CLOSE", result.referenced_fields)
        self.assertIn("MA", result.functions)
        self.assertIn("RSI", result.functions)

    def test_validate_formula_rejects_unsafe_identifier(self) -> None:
        with self.assertRaises(FormulaValidationError):
            self.engine.validate("__import__('os').system('pwd')")

    def test_evaluate_formula_returns_match(self) -> None:
        result = self.engine.evaluate("CLOSE > MA(CLOSE, 5)", self.df)

        self.assertTrue(result.matched)
        self.assertIn("MA", result.description)

    def test_evaluate_formula_supports_multi_output_indicator(self) -> None:
        result = self.engine.evaluate("MACD(CLOSE,12,26,9).hist > 0", self.df)

        self.assertTrue(result.matched)

    def test_validate_formula_supports_tdx_assignments(self) -> None:
        formula = "VAR1:=COUNT(CLOSE/REF(CLOSE,1)<0.97,20)>=3;VAR2:=EXIST(CLOSE/REF(CLOSE,1)>1.095,5);XG:VAR1 AND VAR2;"
        result = self.engine.validate(formula)

        self.assertTrue(result.valid)
        self.assertIn("COUNT", result.functions)
        self.assertIn("EXIST", result.functions)

    def test_validate_formula_supports_split_field_identifier(self) -> None:
        formula = "VAR1:=COUNT(C\nLOSE/REF(CLOSE,1)<0.97,20)>=1;XG:VAR1;"
        result = self.engine.validate(formula)

        self.assertTrue(result.valid)
        self.assertIn("CLOSE", result.normalized_formula)


if __name__ == "__main__":
    unittest.main()
