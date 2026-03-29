# -*- coding: utf-8 -*-
"""Unit tests for the stock screener service."""

from __future__ import annotations

import unittest
import types
from unittest.mock import MagicMock, patch

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
import src.services.stock_screener_service as screener_service_module
from src.services.stock_screener_service import StockBasic, StockScreenerService


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

    def get_realtime_quote(self, code: str):
        return types.SimpleNamespace(pe_ratio=18.0, pb_ratio=2.1)

    def get_fundamental_context(self, code: str, budget_seconds: float | None = None):
        return {
            "valuation": {"data": {"pe_ratio": 18.0, "pb_ratio": 2.1}},
            "growth": {"data": {"roe": 15.2, "revenue_yoy": 22.5, "net_profit_yoy": 30.0}},
        }


class _HintAwareManager(_FakeManager):
    def __init__(self) -> None:
        super().__init__()
        self.preferred_fetchers: list[str | None] = []

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 250,
        preferred_fetcher: str | None = None,
    ):
        self.preferred_fetchers.append(preferred_fetcher)
        return super().get_daily_data(stock_code, days=days)


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
    def setUp(self) -> None:
        self._board_cache = {"version": 1, "updated_at": None, "catalogs": {}, "constituents": {}, "profiles": {}}
        self._load_cache_patcher = patch(
            "src.services.stock_screener_service.load_board_cache",
            side_effect=lambda *args, **kwargs: self._board_cache,
        )
        self._save_cache_patcher = patch(
            "src.services.stock_screener_service.save_board_cache",
            side_effect=lambda cache, *args, **kwargs: cache,
        )
        self._load_cache_patcher.start()
        self._save_cache_patcher.start()

    def tearDown(self) -> None:
        self._save_cache_patcher.stop()
        self._load_cache_patcher.stop()

    def test_call_akshare_with_resilience_retries_transient_error(self) -> None:
        screener_service_module._AKSHARE_SOURCE_CIRCUIT.clear()
        attempts = {"count": 0}

        def flaky_call():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ConnectionError("Remote end closed connection without response")
            return "ok"

        with patch("src.services.stock_screener_service.time.sleep", return_value=None):
            result = screener_service_module._call_akshare_with_resilience(
                "akshare_test_retry",
                "AkShare retry test",
                flaky_call,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)

    def test_call_akshare_with_resilience_opens_circuit_after_consecutive_failures(self) -> None:
        screener_service_module._AKSHARE_SOURCE_CIRCUIT.clear()

        def always_fail():
            raise ConnectionError("Connection aborted")

        with patch.object(screener_service_module, "_AKSHARE_RETRY_MAX_ATTEMPTS", 1):
            with patch.object(screener_service_module, "_AKSHARE_CIRCUIT_FAILURE_THRESHOLD", 2):
                with patch.object(screener_service_module, "_AKSHARE_CIRCUIT_COOLDOWN_SECONDS", 60.0):
                    with patch("src.services.stock_screener_service.time.sleep", return_value=None):
                        with self.assertRaises(RuntimeError):
                            screener_service_module._call_akshare_with_resilience(
                                "akshare_test_circuit",
                                "AkShare circuit test",
                                always_fail,
                            )
                        with self.assertRaises(RuntimeError):
                            screener_service_module._call_akshare_with_resilience(
                                "akshare_test_circuit",
                                "AkShare circuit test",
                                always_fail,
                            )
                        with self.assertRaisesRegex(RuntimeError, "circuit open"):
                            screener_service_module._call_akshare_with_resilience(
                                "akshare_test_circuit",
                                "AkShare circuit test",
                                always_fail,
                            )

    def test_persist_board_basics_keeps_existing_when_new_result_is_empty(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        service._persist_board_basics(  # pylint: disable=protected-access
            MarketType.CN,
            "industry",
            "半导体",
            [StockBasic(code="603986", name="兆易创新"), StockBasic(code="688981", name="中芯国际")],
            "cache_seed",
        )
        service._persist_board_basics(  # pylint: disable=protected-access
            MarketType.CN,
            "industry",
            "半导体",
            [],
            "akshare",
        )

        entry = self._board_cache["constituents"].get("cn:industry:半导体") or {}
        items = entry.get("items") or []
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["code"], "603986")

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

    def test_build_custom_universe_splits_compound_cn_codes(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_custom_universe(["002218.300528"], MarketType.CN)  # pylint: disable=protected-access

        self.assertEqual([item.code for item in result], ["002218", "300528"])

    def test_build_universe_applies_scan_limit(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service._build_universe(  # pylint: disable=protected-access
            _request(market=MarketType.US, codes=["AAPL", "MSFT", "NVDA"], scan_limit=2)
        )

        self.assertEqual([item.code for item in result], ["AAPL", "MSFT"])

    def test_tushare_query_uses_configured_api_url(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "code": 0,
            "data": {
                "fields": ["ts_code", "name"],
                "items": [["000001.SZ", "平安银行"]],
            },
        }

        with patch("src.services.stock_screener_service.get_config") as mock_get_config:
            with patch("src.services.stock_screener_service.requests.post", return_value=fake_response) as mock_post:
                mock_get_config.return_value = types.SimpleNamespace(
                    tushare_token="test-token",
                    tushare_api_url="http://jiaoch.site",
                )
                result = service._tushare_query(  # pylint: disable=protected-access
                    "daily",
                    {"ts_code": "000001.SZ"},
                    "ts_code,name",
                )

        self.assertEqual(result.iloc[0]["ts_code"], "000001.SZ")
        self.assertEqual(result.iloc[0]["name"], "平安银行")
        mock_post.assert_called_once_with(
            "http://jiaoch.site",
            json={
                "api_name": "daily",
                "token": "test-token",
                "params": {"ts_code": "000001.SZ"},
                "fields": "ts_code,name",
            },
            timeout=20,
        )

    def test_scope_catalog_uses_config_preview_for_cn_board_scope(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            scopes = service.scope_catalog(MarketType.CN)

        fetch_constituents.assert_not_called()

        semiconductor = next(item for item in scopes if item.key == "cn_semiconductor")
        self.assertEqual(semiconductor.preview_codes[:2], ["603986", "688041"])
        self.assertGreaterEqual(semiconductor.estimated_count or 0, 10)

    def test_scope_catalog_prefers_cached_cn_board_constituents(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        self._board_cache["constituents"]["cn:industry:半导体"] = {
            "items": [
                {"code": "603986", "name": "兆易创新"},
                {"code": "688981", "name": "中芯国际"},
                {"code": "002371", "name": "北方华创"},
            ],
            "source": "sohu:5558+akshare",
        }

        scopes = service.scope_catalog(MarketType.CN)
        semiconductor = next(item for item in scopes if item.key == "cn_semiconductor")

        self.assertEqual(semiconductor.estimated_count, 3)
        self.assertEqual(semiconductor.preview_codes[:3], ["603986", "688981", "002371"])

    def test_scope_catalog_expands_cn_auto_board_scopes_from_cache(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        industry_rows = []
        concept_rows = []
        for idx in range(1, 13):
            board_name = f"测试行业{idx}"
            industry_rows.append({"board_name": board_name, "label": board_name, "description": "auto industry", "source": "sohu"})
            self._board_cache["constituents"][f"cn:industry:{board_name}"] = {
                "items": [{"code": f"{600000 + idx * 100 + seq}", "name": f"行业股{idx}-{seq}"} for seq in range(25 - idx)],
                "source": "sohu:test",
            }
        for idx in range(1, 8):
            board_name = f"测试概念{idx}"
            concept_rows.append({"board_name": board_name, "label": board_name, "description": "auto concept", "source": "sohu"})
            self._board_cache["constituents"][f"cn:concept:{board_name}"] = {
                "items": [{"code": f"{300000 + idx * 100 + seq}", "name": f"概念股{idx}-{seq}"} for seq in range(20 - idx)],
                "source": "sohu:test",
            }
        self._board_cache["catalogs"]["cn:industry"] = industry_rows
        self._board_cache["catalogs"]["cn:concept"] = concept_rows

        scopes = service.scope_catalog(MarketType.CN)

        self.assertGreaterEqual(len(scopes), 16)
        self.assertTrue(any(item.key.startswith("cn_auto_industry_") for item in scopes))
        self.assertTrue(any(item.key.startswith("cn_auto_concept_") for item in scopes))
        top_auto = next(item for item in scopes if item.key.startswith("cn_auto_industry_"))
        self.assertGreaterEqual(top_auto.estimated_count or 0, 10)

    def test_build_universe_supports_cn_auto_scope_key(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        self._board_cache["catalogs"]["cn:industry"] = [
            {"board_name": "测试行业", "label": "测试行业", "description": "auto industry", "source": "sohu"},
        ]
        self._board_cache["constituents"]["cn:industry:测试行业"] = {
            "items": [{"code": "600001", "name": "测试A"}, {"code": "600002", "name": "测试B"}],
            "source": "sohu:test",
        }

        basics = service._build_custom_universe(["600001", "600002"], MarketType.CN)  # pylint: disable=protected-access
        with patch.object(service, "_build_cn_board_universe", return_value=basics) as build_board:
            result = service._build_universe(  # pylint: disable=protected-access
                _request(market=MarketType.CN, scope="cn_auto_industry_1")
            )

        build_board.assert_called_once_with("industry", "测试行业", ["600001", "600002"])
        self.assertEqual([item.code for item in result], ["600001", "600002"])

    def test_build_universe_raises_when_scope_unknown(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with self.assertRaisesRegex(ValueError, "unknown scope"):
            service._build_universe(_request(market=MarketType.CN, scope="cn_scope_not_exists"))  # pylint: disable=protected-access

    def test_build_universe_prefers_board_filters_over_cn_full_market_scope(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        basics = service._build_custom_universe(["600001", "600002"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(service, "_build_board_universe", return_value=basics) as build_board:
            with patch.object(service, "_list_a_share") as list_a_share:
                result = service._build_universe(  # pylint: disable=protected-access
                    _request(market=MarketType.CN, scope="all_market", board_filters=["半导体"])
                )

        self.assertEqual([item.code for item in result], ["600001", "600002"])
        list_a_share.assert_not_called()
        build_board.assert_called_once()
        build_args = build_board.call_args[0]
        self.assertEqual(build_args[0], MarketType.CN)
        self.assertEqual(build_args[2], "半导体")

    def test_scope_catalog_expands_overseas_scopes_to_at_least_twenty(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        hk_scopes = service.scope_catalog(MarketType.HK)
        us_scopes = service.scope_catalog(MarketType.US)

        self.assertGreaterEqual(len(hk_scopes), 20)
        self.assertGreaterEqual(len(us_scopes), 20)

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

    def test_board_catalog_prefers_cached_constituent_count_for_estimated_count(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        self._board_cache["catalogs"]["cn:industry"] = [
            {"board_name": "半导体", "label": "半导体", "estimated_count": 20},
        ]
        self._board_cache["constituents"]["cn:industry:半导体"] = {
            "items": [{"code": "603986", "name": "兆易创新"}, {"code": "688981", "name": "中芯国际"}],
            "source": "sohu:5558",
        }

        boards = service.board_catalog(MarketType.CN, ScreenerBoardType.INDUSTRY)

        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0].estimated_count, 2)

    def test_board_preview_uses_real_constituents(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.return_value = ([("603986", "兆易创新"), ("688981", "中芯国际")], "akshare")

            preview = service.board_preview(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体", limit=1)

        self.assertEqual(preview.board_name, "半导体")
        self.assertGreaterEqual(preview.estimated_count or 0, 2)
        self.assertEqual(preview.preview_codes[:2], ["603986", "688981"])

    def test_board_preview_returns_full_codes_when_limit_is_zero(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        basics = service._build_custom_universe(["603986", "688981", "002371"], MarketType.CN)  # pylint: disable=protected-access
        self._board_cache["constituents"]["cn:industry:半导体"] = {
            "items": [{"code": item.code, "name": item.name} for item in basics],
            "source": "sohu:5558",
        }

        preview = service.board_preview(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体", limit=0)

        self.assertEqual(preview.estimated_count, 3)
        self.assertEqual(preview.preview_codes, ["603986", "688981", "002371"])

    def test_board_preview_falls_back_to_scope_codes_for_cn_board(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        with patch("src.services.stock_screener_service._fetch_cn_board_constituents") as fetch_constituents:
            fetch_constituents.side_effect = RuntimeError("akshare unavailable")

            preview = service.board_preview(MarketType.CN, ScreenerBoardType.INDUSTRY, "半导体", limit=2)

        self.assertEqual(preview.board_name, "半导体")
        self.assertEqual(preview.preview_codes[:2], ["603986", "688041"])
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
                self.assertTrue(payload.source.startswith("config"))
                self.assertGreaterEqual(payload.total, 5)
                self.assertEqual(payload.items[0].code, first_code)

    def test_load_cn_board_basics_enriches_small_live_result_with_sohu(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        live_basics = service._build_custom_universe(["603986", "688981"], MarketType.CN)  # pylint: disable=protected-access
        sohu_basics = service._build_custom_universe(["603986", "688981", "002371", "300223"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(service, "_fetch_cn_board_universe", return_value=(live_basics, "akshare")):
            with patch.object(service, "_fetch_sohu_cn_board_universe", return_value=(sohu_basics, "sohu:5558")):
                basics, source = service._load_cn_board_basics("industry", "半导体", [])

        self.assertEqual([item.code for item in basics], ["603986", "688981", "002371", "300223"])
        self.assertEqual(source, "sohu:5558+akshare")

    def test_load_cn_board_basics_prefers_sohu_order_even_without_extra_symbols(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        live_basics = service._build_custom_universe(["603986", "688981", "002371"], MarketType.CN)  # pylint: disable=protected-access
        sohu_basics = service._build_custom_universe(["002371", "603986", "688981"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(service, "_fetch_cn_board_universe", return_value=(live_basics, "akshare")):
            with patch.object(service, "_fetch_sohu_cn_board_universe", return_value=(sohu_basics, "sohu:5558")):
                basics, source = service._load_cn_board_basics("industry", "半导体", [])

        self.assertEqual([item.code for item in basics], ["002371", "603986", "688981"])
        self.assertEqual(source, "sohu:5558+akshare")

    def test_load_cn_board_basics_unions_multiple_sources(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        ak_basics = service._build_custom_universe(["603986", "688981"], MarketType.CN)  # pylint: disable=protected-access
        ts_basics = service._build_custom_universe(["688981", "300223"], MarketType.CN)  # pylint: disable=protected-access
        sohu_basics = service._build_custom_universe(["002371", "603986"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(service, "_fetch_cn_board_universe", return_value=(ak_basics, "akshare")):
            with patch.object(service, "_fetch_tushare_cn_board_universe", return_value=(ts_basics, "tushare")):
                with patch.object(service, "_fetch_sohu_cn_board_universe", return_value=(sohu_basics, "sohu:5558")):
                    basics, source = service._load_cn_board_basics("industry", "半导体", [])

        self.assertEqual([item.code for item in basics], ["002371", "603986", "688981", "300223"])
        self.assertEqual(source, "sohu:5558+akshare+tushare")

    def test_load_cn_board_basics_uses_sohu_when_live_sources_fail(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        sohu_basics = service._build_custom_universe(["603986", "688981", "002371"], MarketType.CN)  # pylint: disable=protected-access

        with patch.object(service, "_fetch_cn_board_universe", side_effect=RuntimeError("akshare unavailable")):
            with patch.object(service, "_fetch_tushare_cn_board_universe", side_effect=RuntimeError("tushare unavailable")):
                with patch.object(service, "_fetch_sohu_cn_board_universe", return_value=(sohu_basics, "sohu:5558")):
                    basics, source = service._load_cn_board_basics("industry", "半导体", ["603986"])

        self.assertEqual([item.code for item in basics], ["603986", "688981", "002371"])
        self.assertEqual(source, "sohu:5558")

    def test_fetch_overseas_market_symbols_uses_hk_spot_when_em_fails(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        fake_akshare = types.SimpleNamespace(
            stock_hk_spot_em=lambda: (_ for _ in ()).throw(RuntimeError("em unavailable")),
            stock_hk_spot=lambda: pd.DataFrame(
                {
                    "代码": ["00700", "09988", "00700"],
                    "名称": ["腾讯控股", "阿里巴巴-W", "腾讯控股"],
                }
            ),
        )

        with patch.dict("sys.modules", {"akshare": fake_akshare}):
            basics, source = service._fetch_overseas_market_symbols(MarketType.HK)  # pylint: disable=protected-access

        self.assertEqual(source, "akshare_hk_spot")
        self.assertEqual([item.code for item in basics[:2]], ["00700", "09988"])

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

        self.assertEqual([item.code for item in result[:2]], ["603986", "688981"])
        self.assertGreaterEqual(len(result), 2)

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
        self.assertEqual(preview.preview_codes[:2], ["NVDA", "AMD"])
        self.assertGreaterEqual(preview.estimated_count or 0, 20)
        self.assertIn("龙头", preview.tier_summary or "")
        self.assertGreaterEqual(len(preview.tiers), 3)
        self.assertIn("NVDA", preview.tiers[0].codes)

    def test_board_preview_uses_hk_boosted_pool(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        preview = service.board_preview(MarketType.HK, ScreenerBoardType.INDUSTRY, "科技互联网", limit=3)

        self.assertEqual(preview.board_name, "科技互联网")
        self.assertEqual(preview.preview_codes[:2], ["00700", "09988"])
        self.assertGreaterEqual(preview.estimated_count or 0, 20)

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

    def test_validate_formula_returns_invalid_payload_instead_of_raising(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.validate_formula("__import__('os').system('pwd')")

        self.assertFalse(result.valid)
        self.assertIn("supported", result.message.lower())

    def test_build_overseas_market_board_snapshots_prefers_live_matches_and_keeps_seed_codes(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        cache = {"version": 1, "updated_at": None, "catalogs": {}, "constituents": {}, "profiles": {}}

        with patch.object(
            service,
            "_fetch_overseas_market_symbols",
            return_value=(
                [
                    service._build_custom_universe(["NVDA", "AMD", "JPM"], MarketType.US)[0],
                    service._build_custom_universe(["AMD"], MarketType.US)[0],
                    service._build_custom_universe(["JPM"], MarketType.US)[0],
                ],
                "akshare_us_spot_em",
            ),
        ):
            with patch.object(service, "_fetch_overseas_famous_symbols", return_value=([], "empty")):
                with patch.object(
                    service,
                    "_fetch_yfinance_profile",
                    side_effect=lambda market, basic: {
                        "NVDA": {"code": "NVDA", "name": "NVIDIA", "sector": "Technology", "industry": "Semiconductors", "source": "yfinance"},
                        "AMD": {"code": "AMD", "name": "AMD", "sector": "Technology", "industry": "Semiconductors", "source": "yfinance"},
                        "JPM": {"code": "JPM", "name": "JPMorgan", "sector": "Financial Services", "industry": "Banks - Diversified", "source": "yfinance"},
                    }[basic.code],
                ):
                    snapshots, source = service.build_overseas_market_board_snapshots(MarketType.US, cache=cache, profile_limit=3)

        self.assertEqual(source, "akshare_us_spot_em")
        semiconductor = snapshots["半导体"]
        self.assertTrue(semiconductor["source"].startswith("akshare_us_spot_em+yfinance"))
        self.assertIn("NVDA", [item["code"] for item in semiconductor["items"][:3]])
        self.assertIn("AMD", [item["code"] for item in semiconductor["items"][:3]])
        self.assertIn("profiles", cache)

    def test_build_overseas_market_board_snapshots_uses_famous_pool_when_primary_unavailable(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        cache = {"version": 1, "updated_at": None, "catalogs": {}, "constituents": {}, "profiles": {}}
        famous_basics = service._build_custom_universe(["NVDA", "AMD"], MarketType.US)  # pylint: disable=protected-access

        with patch.object(service, "_fetch_overseas_market_symbols", side_effect=RuntimeError("primary unavailable")):
            with patch.object(service, "_fetch_overseas_famous_symbols", return_value=(famous_basics, "akshare_us_famous_spot_em")):
                with patch.object(
                    service,
                    "_fetch_yfinance_profile",
                    side_effect=lambda market, basic: {
                        "NVDA": {"code": "NVDA", "name": "NVIDIA", "sector": "Technology", "industry": "Semiconductors", "source": "yfinance"},
                        "AMD": {"code": "AMD", "name": "AMD", "sector": "Technology", "industry": "Semiconductors", "source": "yfinance"},
                    }[basic.code],
                ):
                    snapshots, source = service.build_overseas_market_board_snapshots(MarketType.US, cache=cache, profile_limit=2)

        self.assertEqual(source, "akshare_us_famous_spot_em")
        semiconductor = snapshots["半导体"]
        self.assertTrue(semiconductor["source"].startswith("akshare_us_famous_spot_em+yfinance"))
        self.assertIn("NVDA", [item["code"] for item in semiconductor["items"]])

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

    def test_scan_hybrid_mode_requires_formula_and_conditions_together(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.scan(
            ScreenerScanRequest(
                mode="hybrid",
                formula="CLOSE > MA(CLOSE, 5)",
                market="cn",
                codes=["600519"],
                conditions=[
                    IndicatorCondition(
                        indicator=IndicatorKey.PE,
                        operator=Operator.GT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=10),
                    ),
                ],
                export_csv=False,
            )
        )

        self.assertEqual(result.total, 1)
        self.assertIn("CLOSE > MA(CLOSE, 5)", result.results[0].matched_conditions)
        self.assertTrue(any("PE >" in item for item in result.results[0].matched_conditions))

    def test_scan_reuses_history_source_hint(self) -> None:
        manager = _HintAwareManager()
        service = StockScreenerService(manager=manager)
        service._max_workers = 1  # pylint: disable=protected-access

        result = service.scan(
            ScreenerScanRequest(
                mode="formula",
                formula="CLOSE > MA(CLOSE, 5)",
                market="us",
                codes=["AAPL", "MSFT"],
                export_csv=False,
            )
        )

        self.assertEqual(result.total, 2)
        self.assertEqual(manager.preferred_fetchers[0], None)
        self.assertEqual(manager.preferred_fetchers[1], "mock")

    def test_scan_progress_callback_is_throttled(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        service._progress_update_step = 10  # pylint: disable=protected-access

        progress_snapshots: list[int] = []
        result = service.scan(
            ScreenerScanRequest(
                mode="formula",
                formula="CLOSE > MA(CLOSE, 5)",
                market="us",
                codes=[
                    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "NFLX", "INTC", "CSCO",
                    "ORCL", "IBM", "QCOM", "AVGO", "MU", "ADBE", "CRM", "UBER", "PYPL", "SHOP", "SNOW", "PLTR",
                ],
                export_csv=False,
            ),
            progress_callback=lambda scanned, total, matched, message: progress_snapshots.append(scanned),
        )

        self.assertEqual(result.total, 23)
        self.assertIn(23, progress_snapshots)
        self.assertLess(len(progress_snapshots), 12)

    def test_resolve_scan_workers_respects_limits(self) -> None:
        service = StockScreenerService(manager=_FakeManager())
        service._max_workers = 16  # pylint: disable=protected-access

        self.assertEqual(service._resolve_scan_workers(0), 1)   # pylint: disable=protected-access
        self.assertEqual(service._resolve_scan_workers(3), 3)   # pylint: disable=protected-access
        self.assertEqual(service._resolve_scan_workers(100), 16)  # pylint: disable=protected-access

    def test_indicator_catalog_contains_scalar_fundamental_indicators(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        keys = {item.key for item in service.indicator_catalog()}

        self.assertIn(IndicatorKey.HEAT, keys)
        self.assertIn(IndicatorKey.PE, keys)
        self.assertIn(IndicatorKey.PB, keys)
        self.assertIn(IndicatorKey.PEG, keys)
        self.assertIn(IndicatorKey.ROE, keys)
        self.assertIn(IndicatorKey.REVENUE_YOY, keys)
        self.assertIn(IndicatorKey.NET_PROFIT_YOY, keys)

    def test_scan_supports_pe_pb_scalar_conditions(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.scan(
            ScreenerScanRequest(
                market="cn",
                codes=["600519"],
                conditions=[
                    IndicatorCondition(
                        indicator=IndicatorKey.PE,
                        operator=Operator.GT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=10),
                    ),
                    IndicatorCondition(
                        indicator=IndicatorKey.PB,
                        operator=Operator.LT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=3),
                        logic_with_previous="AND",
                    ),
                ],
            )
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(result.results[0].code, "600519")

    def test_scan_supports_growth_and_peg_conditions(self) -> None:
        service = StockScreenerService(manager=_FakeManager())

        result = service.scan(
            ScreenerScanRequest(
                market="cn",
                codes=["600519"],
                conditions=[
                    IndicatorCondition(
                        indicator=IndicatorKey.ROE,
                        operator=Operator.GT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=10),
                    ),
                    IndicatorCondition(
                        indicator=IndicatorKey.NET_PROFIT_YOY,
                        operator=Operator.GT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=20),
                        logic_with_previous="AND",
                    ),
                    IndicatorCondition(
                        indicator=IndicatorKey.PEG,
                        operator=Operator.LT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=1),
                        logic_with_previous="AND",
                    ),
                ],
            )
        )

        self.assertEqual(result.total, 1)

    def test_scan_skips_when_growth_data_missing(self) -> None:
        class _MissingGrowthManager(_FakeManager):
            def get_fundamental_context(self, code: str, budget_seconds: float | None = None):
                return {"valuation": {"data": {"pe_ratio": 12.0, "pb_ratio": 1.8}}, "growth": {"data": {}}}

        service = StockScreenerService(manager=_MissingGrowthManager())
        result = service.scan(
            ScreenerScanRequest(
                market="cn",
                codes=["600519"],
                conditions=[
                    IndicatorCondition(
                        indicator=IndicatorKey.ROE,
                        operator=Operator.GT,
                        compare_to=CompareTo(type=CompareType.VALUE, value=10),
                    )
                ],
            )
        )

        self.assertEqual(result.total, 0)


if __name__ == "__main__":
    unittest.main()
