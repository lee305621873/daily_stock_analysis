# -*- coding: utf-8 -*-
"""Unit tests for the stock screener service."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from api.v1.schemas.stocks import (
    CompareTo,
    CompareType,
    IndicatorCondition,
    ScreenerBoardType,
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

    def test_build_universe_applies_scan_limit(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_universe(  # pylint: disable=protected-access
            _request(market=MarketType.US, codes=["AAPL", "MSFT", "NVDA"], scan_limit=2)
        )

        self.assertEqual([item.code for item in result], ["AAPL", "MSFT"])

    def test_scope_catalog_uses_config_preview_for_cn_board_scope(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            scopes = service.scope_catalog(MarketType.CN)

        fetch_constituents.assert_not_called()

        semiconductor = next(item for item in scopes if item.key == "cn_semiconductor")
        self.assertEqual(semiconductor.preview_codes[:2], ["603986", "688041"])
        self.assertGreaterEqual(semiconductor.estimated_count or 0, 10)

    def test_board_catalog_returns_cn_board_options(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_catalog") as fetch_catalog:
            fetch_catalog.return_value = (
                [
                    {"board_name": "半导体", "label": "半导体", "estimated_count": 132},
                    {"board_name": "白酒", "label": "白酒", "estimated_count": 21},
                ],
                "akshare",
            )

            boards = service.board_catalog(MarketType.CN, ScreenerBoardType.INDUSTRY)

        self.assertEqual([item.board_name for item in boards], ["半导体", "白酒"])
        self.assertEqual(boards[0].estimated_count, 132)

    def test_board_preview_uses_real_constituents(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.return_value = ([("603986", "兆易创新"), ("688981", "中芯国际")], "akshare")

            preview = service.board_preview(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体", limit=1)

        self.assertEqual(preview.board_name, "半导体")
        self.assertEqual(preview.estimated_count, 2)
        self.assertEqual(preview.preview_codes, ["603986"])

    def test_board_preview_falls_back_to_scope_codes_for_cn_board(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.side_effect = RuntimeError("akshare unavailable")

            preview = service.board_preview(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体", limit=2)

        self.assertEqual(preview.board_name, "半导体")
        self.assertEqual(preview.preview_codes, ["603986", "688041"])
        self.assertGreaterEqual(preview.estimated_count or 0, 10)
        self.assertIn("半导体", preview.description or "")

    def test_build_cn_board_universe_falls_back_to_tushare(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        basics = service._build_custom_universe(["603986", "688981"], MarketType.CN)  # pylint: disable=protected-access

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.side_effect = RuntimeError("akshare unavailable")
            with patch.object(
                service,
                "_fetch_tushare_cn_board_universe",
                return_value=(basics, "tushare"),
            ):
                result = service._build_cn_board_universe("industry", "半导体", [])

        self.assertEqual([item.code for item in result], ["603986", "688981"])

    def test_board_constituents_returns_full_payload(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        basics = service._build_custom_universe(["603986", "688981"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(
            service,
            "_load_cn_board_basics",
            return_value=(basics, "tushare"),
        ):
            payload = service.board_constituents(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体")

        self.assertEqual(payload.board_name, "半导体")
        self.assertEqual(payload.source, "tushare")
        self.assertEqual(payload.total, 2)
        self.assertEqual(payload.items[0].code, "603986")

    def test_board_constituents_supports_concept_tushare_fallback(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        basics = service._build_custom_universe(["300308", "002230"], MarketType.CN)  # pylint: disable=protected-access

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.side_effect = RuntimeError("akshare unavailable")
            with patch.object(
                service,
                "_fetch_tushare_cn_board_universe",
                return_value=(basics, "tushare"),
            ):
                payload = service.board_constituents(
                    MarketType.CN,
                    ScreenerBoardType.CONCEPT,
                    "人工智能",
                    allow_fallback=False,
                )

        self.assertEqual(payload.board_type, ScreenerBoardType.CONCEPT)
        self.assertEqual(payload.source, "tushare")
        self.assertEqual(payload.total, 2)
        self.assertEqual([item.code for item in payload.items], ["300308", "002230"])

    def test_board_constituents_without_fallback_raises_when_all_sources_fail(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.side_effect = RuntimeError("akshare unavailable")
            with patch.object(service, "_fetch_tushare_cn_board_universe", side_effect=RuntimeError("tushare unavailable")):
                with self.assertRaisesRegex(RuntimeError, "tushare unavailable"):
                    service.board_constituents(
                        MarketType.CN,
                        ScreenerBoardType.INDUSTRY,
                        "半导体",
                        allow_fallback=False,
                    )

    def test_board_constituents_returns_config_source_for_overseas_boards(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        for market, board_name, first_code in (
            (MarketType.HK, "科技互联网", "00700"),
            (MarketType.US, "半导体", "NVDA"),
        ):
            with self.subTest(market=market.value, board_name=board_name):
                payload = service.board_constituents(market, ScreenerBoardType.INDUSTRY, board_name)
                self.assertEqual(payload.source, "config")
                self.assertGreaterEqual(payload.total, 5)
                self.assertEqual(payload.items[0].code, first_code)

    def test_build_universe_uses_scope_definition(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_universe(  # pylint: disable=protected-access
            _request(market=MarketType.US, scope="us_semiconductor")
        )

        self.assertGreaterEqual(len(result), 5)
        self.assertEqual(result[0].code, "NVDA")

    def test_build_universe_uses_dynamic_cn_board_scope(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.return_value = ([("603986", "兆易创新"), ("688981", "中芯国际")], "akshare")

            result = service._build_universe(  # pylint: disable=protected-access
                _request(
                    market=MarketType.CN,
                    scope="cn_board_industry_dynamic",
                    board_type=ScreenerBoardType.INDUSTRY,
                    board_name="半导体",
                )
            )

        self.assertEqual([item.code for item in result], ["603986", "688981"])

    def test_board_catalog_returns_us_configured_boards(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        boards = service.board_catalog(MarketType.US, ScreenerBoardType.INDUSTRY)

        self.assertGreaterEqual(len(boards), 3)
        self.assertEqual(boards[0].market, MarketType.US)
        self.assertEqual(boards[0].board_type, ScreenerBoardType.INDUSTRY)
        self.assertTrue(boards[0].tier_summary)
        self.assertGreaterEqual(len(boards[0].tiers), 3)
        self.assertEqual(boards[0].tiers[0].label, "龙头")

    def test_board_preview_uses_us_configured_pool(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        preview = service.board_preview(MarketType.US, ScreenerBoardType.INDUSTRY, "半导体", limit=2)

        self.assertEqual(preview.board_name, "半导体")
        self.assertEqual(preview.preview_codes, ["NVDA", "AMD"])
        self.assertGreaterEqual(preview.estimated_count or 0, 10)
        self.assertIn("龙头", preview.tier_summary or "")
        self.assertGreaterEqual(len(preview.tiers), 3)
        self.assertIn("NVDA", preview.tiers[0].codes)

    def test_build_universe_uses_dynamic_us_board_scope(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_universe(  # pylint: disable=protected-access
            _request(
                market=MarketType.US,
                scope="us_board_industry_dynamic",
                board_type=ScreenerBoardType.INDUSTRY,
                board_name="半导体",
            )
        )

        self.assertEqual([item.code for item in result[:3]], ["NVDA", "AMD", "AVGO"])

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
