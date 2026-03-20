# -*- coding: utf-8 -*-
"""Unit tests for the stock screener service."""

from __future__ import annotations

import unittest

import pandas as pd

from api.v1.schemas.stocks import (
    CompareTo,
    CompareType,
    IndicatorCondition,
    IndicatorKey,
    MarketType,
    Operator,
    ScreenerScanRequest,
)
from src.services.stock_screener_service import StockScreenerService


class _FakeManager:
    def __init__(self) -> None:
        self.calls = []

    _fetchers = []

    def get_stock_name(self, code: str) -> str:
        return code

    def get_daily_data(self, code: str, days: int = 250):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=60, freq="D"),
                "open": [10 + i * 0.1 for i in range(60)],
                "high": [10.3 + i * 0.1 for i in range(60)],
                "low": [9.7 + i * 0.1 for i in range(60)],
                "close": [10 + i * 0.15 for i in range(60)],
                "volume": [1000 + i * 100 for i in range(60)],
                "amount": [10000 + i * 1200 for i in range(60)],
            }
        )
        return df.tail(days), "mock"

    def get_belong_boards(self, code: str):
        return [{"name": "白酒"}]


def _request(**kwargs) -> ScreenerScanRequest:
    return ScreenerScanRequest(
        conditions=[
            IndicatorCondition(
                indicator=IndicatorKey.RSI,
                params={"period": 14},
                output="rsi",
                operator=Operator.LT,
                compare_to=CompareTo(type=CompareType.VALUE, value=30),
            )
        ],
        **kwargs,
    )


class StockScreenerServiceTestCase(unittest.TestCase):
    def test_build_universe_requires_codes_for_us(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with self.assertRaisesRegex(ValueError, "requires explicit codes"):
            service._build_universe(_request(market=MarketType.US))  # pylint: disable=protected-access

    def test_build_custom_universe_normalizes_hk_codes(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_custom_universe(["hk00700", "09988"], MarketType.HK)  # pylint: disable=protected-access

        self.assertEqual([item.code for item in result], ["00700", "09988"])

    def test_build_custom_universe_rejects_invalid_us_code(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with self.assertRaisesRegex(ValueError, "invalid us codes"):
            service._build_custom_universe(["AAPL", "700"], MarketType.US)  # pylint: disable=protected-access

    def test_validate_formula(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.validate_formula("CLOSE > MA(CLOSE, 5)")

        self.assertTrue(result.valid)
        self.assertIn("MA", result.functions)

    def test_scan_formula_mode_returns_result(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.scan(
            ScreenerScanRequest(
                mode="formula",
                formula="CLOSE > MA(CLOSE, 5)",
                market="us",
                codes=["AAPL"],
                export_csv=False,
            )
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(result.results[0].code, "AAPL")


if __name__ == "__main__":
    unittest.main()
