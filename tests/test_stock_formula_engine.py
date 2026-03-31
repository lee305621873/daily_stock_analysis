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
        self.assertIn("公式会在最新一个交易日", result.meaning)
        self.assertTrue(any("上穿" in item for item in result.meaning_breakdown))

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

    def test_validate_formula_supports_common_ths_boolean_symbols(self) -> None:
        formula = "XG: C<>REF(C,1) && !NAMELIKE('*ST*');"
        result = self.engine.validate(formula)

        self.assertTrue(result.valid)
        self.assertIn("!=", result.normalized_formula)
        self.assertIn("not", result.normalized_formula.lower())

    def test_validate_formula_supports_ths_runtime_functions_and_ignores_draw_statements(self) -> None:
        formula = """
        {THS style script}
        PE:=DYNAINFO(39);
        PB:=DYNAINFO(35);
        XG: PE < 15 AND PB < 2 AND NOT NAMELIKE('*ST*');
        DRAWICON(XG, LOW*0.95, 1);
        DRAWTEXT(XG, HIGH*1.05, '低估高ROE'), COLORRED;
        XG;
        """
        result = self.engine.validate(formula)

        self.assertTrue(result.valid)
        self.assertIn("DYNAINFO", result.functions)
        self.assertIn("NAMELIKE", result.functions)
        self.assertNotIn("DRAWICON", result.normalized_formula.upper())

    def test_evaluate_formula_supports_runtime_context_for_finance_dynainfo_namelike(self) -> None:
        formula = (
            "PE:=DYNAINFO(39);"
            "PB:=DYNAINFO(35);"
            "ROE:=FINANCE(33)/FINANCE(34)*100;"
            "XG: PE<15 AND PB<2 AND ROE>10 AND NOT NAMELIKE('*ST*');"
        )
        result = self.engine.evaluate(
            formula,
            self.df,
            runtime_context={
                "DYNAINFO_39": 12.0,
                "DYNAINFO_35": 1.2,
                "FINANCE_33": 2.0,
                "FINANCE_34": 10.0,
                "STOCK_NAME": "测试股份",
            },
        )

        self.assertTrue(result.matched)

    def test_evaluate_formula_aligns_runtime_series_index_before_comparison(self) -> None:
        df = self.df.copy()
        df.index = pd.Index(range(100, 140))
        runtime_series = pd.Series([9.0] * len(df), index=pd.Index(list(reversed(df.index))))

        result = self.engine.evaluate(
            "CLOSE > DYNAINFO(39)",
            df,
            runtime_context={"DYNAINFO_39": runtime_series},
        )

        self.assertTrue(result.matched)

    def test_validate_formula_supports_multiline_xg_with_draw_and_color_statements(self) -> None:
        formula = """
        {低估值高ROE高成长选股公式}
        PE:=DYNAINFO(39);
        PB:=DYNAINFO(35);
        ROE:=FINANCE(33)/FINANCE(34)*100;
        MA20:=MA(CLOSE,20);
        VOL5:=MA(VOL,5);
        XG:
            PE<15
            AND PB<1.5
            AND ROE>15
            AND CLOSE>MA20
            AND VOL>VOL5*1.2
            AND NOT(NAMELIKE('*ST') OR NAMELIKE('退*'));
        DRAWICON(XG, LOW*0.95, 1);
        DRAWTEXT(XG, HIGH*1.05, '低估高ROE'), COLORRED;
        XG
        """
        result = self.engine.validate(formula)

        self.assertTrue(result.valid)
        self.assertIn("NAMELIKE", result.functions)
        self.assertNotIn("DRAWICON", result.normalized_formula.upper())


if __name__ == "__main__":
    unittest.main()
