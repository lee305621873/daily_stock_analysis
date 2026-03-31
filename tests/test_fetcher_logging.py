import logging
import os
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager
from data_provider.efinance_fetcher import EfinanceFetcher


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-03-06", "2026-03-07"],
            "open": [10.0, 10.2],
            "high": [10.5, 10.4],
            "low": [9.8, 10.1],
            "close": [10.3, 10.35],
            "volume": [1000, 1200],
            "amount": [10300, 12420],
            "pct_chg": [1.0, 0.49],
        }
    )


class _SuccessFetcher(BaseFetcher):
    name = "SuccessFetcher"
    priority = 1

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return _sample_df()

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


class _FailureFetcher(BaseFetcher):
    name = "FailureFetcher"
    priority = 0

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError(
            "Eastmoney 历史K线接口失败: "
            "endpoint=push2his.eastmoney.com/api/qt/stock/kline/get, "
            "category=remote_disconnect"
        )

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


class _TushareServerErrorFetcher(BaseFetcher):
    name = "TushareFetcher"
    priority = 0

    def __init__(self) -> None:
        self.calls = 0

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls += 1
        raise DataFetchError(
            "Tushare 获取数据失败: Tushare API HTTP 504, "
            "url=http://jiaoch.site/daily, response_body=<html>504 Gateway Time-out</html>"
        )

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


class _EastmoneyDisconnectFetcher(BaseFetcher):
    name = "EfinanceFetcher"
    priority = 0

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError(
            "efinance 获取数据失败: Eastmoney 历史K线接口失败: "
            "endpoint=push2his.eastmoney.com/api/qt/stock/kline/get, "
            "category=remote_disconnect"
        )

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


class _HintAwareAkshareFetcher(BaseFetcher):
    name = "AkshareFetcher"
    priority = 1

    def __init__(self) -> None:
        self.received_hints = []
        self._active_hint = None

    @contextmanager
    def daily_data_hint(self, hint=None):
        self._active_hint = hint
        try:
            yield
        finally:
            self._active_hint = None

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.received_hints.append(self._active_hint)
        return _sample_df()

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


class TestFetcherLogging(unittest.TestCase):
    def test_base_fetcher_logs_start_and_success(self):
        fetcher = _SuccessFetcher()

        with self.assertLogs("data_provider.base", level="INFO") as captured:
            df = fetcher.get_daily_data("600519", start_date="2026-03-01", end_date="2026-03-08")

        log_text = "\n".join(captured.output)
        self.assertFalse(df.empty)
        self.assertIn("[SuccessFetcher] 开始获取 600519 日线数据", log_text)
        self.assertIn("[SuccessFetcher] 600519 获取成功:", log_text)
        self.assertIn("rows=2", log_text)

    def test_manager_logs_fallback_and_final_success(self):
        manager = DataFetcherManager(fetchers=[_FailureFetcher(), _SuccessFetcher()])

        with self.assertLogs("data_provider.base", level="INFO") as captured:
            df, source = manager.get_daily_data("601006", start_date="2026-01-07", end_date="2026-03-08")

        log_text = "\n".join(captured.output)
        self.assertFalse(df.empty)
        self.assertEqual(source, "SuccessFetcher")
        self.assertIn("[数据源尝试 1/2] [FailureFetcher] 获取 601006...", log_text)
        self.assertIn("[数据源失败 1/2] [FailureFetcher] 601006:", log_text)
        self.assertIn("[数据源切换] 601006: [FailureFetcher] -> [SuccessFetcher]", log_text)
        self.assertIn("[数据源完成] 601006 使用 [SuccessFetcher] 获取成功:", log_text)

    def test_manager_skips_tushare_during_daily_server_error_cooldown(self):
        tushare = _TushareServerErrorFetcher()
        success = _SuccessFetcher()
        manager = DataFetcherManager(fetchers=[tushare, success])

        first_df, first_source = manager.get_daily_data("605050", start_date="2026-01-07", end_date="2026-03-08")
        with self.assertLogs("data_provider.base", level="INFO") as captured:
            second_df, second_source = manager.get_daily_data("605333", start_date="2026-01-07", end_date="2026-03-08")

        log_text = "\n".join(captured.output)
        self.assertFalse(first_df.empty)
        self.assertFalse(second_df.empty)
        self.assertEqual(first_source, "SuccessFetcher")
        self.assertEqual(second_source, "SuccessFetcher")
        self.assertEqual(tushare.calls, 1)
        self.assertIn("[数据源跳过] 605333: [TushareFetcher] 冷却中", log_text)

    def test_manager_hints_akshare_to_skip_em_after_efinance_eastmoney_disconnect(self):
        efinance = _EastmoneyDisconnectFetcher()
        akshare = _HintAwareAkshareFetcher()
        manager = DataFetcherManager(fetchers=[efinance, akshare])

        df, source = manager.get_daily_data("605050", start_date="2026-01-07", end_date="2026-03-08")

        self.assertFalse(df.empty)
        self.assertEqual(source, "AkshareFetcher")
        self.assertEqual(len(akshare.received_hints), 1)
        self.assertEqual(akshare.received_hints[0], {
            "skip_sources": ["em"],
            "reason": "previous Eastmoney daily failure from EfinanceFetcher",
        })

    def test_efinance_logs_eastmoney_endpoint_on_remote_disconnect(self):
        fetcher = EfinanceFetcher()
        fake_efinance = types.SimpleNamespace(
            stock=types.SimpleNamespace(
                get_quote_history=lambda **kwargs: (_ for _ in ()).throw(
                    requests.exceptions.ConnectionError("Remote end closed connection without response")
                )
            )
        )

        with patch.dict(sys.modules, {"efinance": fake_efinance}):
            with patch.object(fetcher, "_set_random_user_agent", return_value=None), patch.object(
                fetcher, "_enforce_rate_limit", return_value=None
            ):
                with self.assertLogs(level="INFO") as captured:
                    with self.assertRaises(DataFetchError):
                        fetcher.get_daily_data("601006", start_date="2026-01-07", end_date="2026-03-08")

        log_text = "\n".join(captured.output)
        self.assertIn("Eastmoney 历史K线接口失败:", log_text)
        self.assertIn("endpoint=push2his.eastmoney.com/api/qt/stock/kline/get", log_text)
        self.assertIn("category=remote_disconnect", log_text)
        self.assertIn("[EfinanceFetcher] 601006 获取失败:", log_text)


if __name__ == "__main__":
    unittest.main()
