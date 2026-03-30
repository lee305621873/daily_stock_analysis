# -*- coding: utf-8 -*-
"""Unit tests for Tushare fetcher endpoint patching."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()
if "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from data_provider.tushare_fetcher import TushareFetcher


class TestTushareFetcherEndpointPatch(unittest.TestCase):
    def test_init_reads_rate_limit_from_config(self) -> None:
        fake_api = types.SimpleNamespace(_DataApi__timeout=15)
        fake_ts = types.SimpleNamespace(
            set_token=MagicMock(),
            pro_api=MagicMock(return_value=fake_api),
        )

        with patch.dict(sys.modules, {"tushare": fake_ts}):
            with patch("data_provider.tushare_fetcher.get_config") as mock_get_config:
                mock_get_config.return_value = types.SimpleNamespace(
                    tushare_token="trial-token",
                    tushare_api_url="http://jiaoch.site",
                    tushare_rate_limit_per_minute=0,
                )
                fetcher = TushareFetcher()

        self.assertEqual(fetcher.rate_limit_per_minute, 0)

    def test_init_sets_private_token_and_http_url(self) -> None:
        fake_api = types.SimpleNamespace(_DataApi__timeout=15)
        fake_ts = types.SimpleNamespace(
            set_token=MagicMock(),
            pro_api=MagicMock(return_value=fake_api),
        )

        with patch.dict(sys.modules, {"tushare": fake_ts}):
            with patch("data_provider.tushare_fetcher.get_config") as mock_get_config:
                mock_get_config.return_value = types.SimpleNamespace(
                    tushare_token="trial-token",
                    tushare_api_url="http://jiaoch.site",
                )
                fetcher = TushareFetcher()

        self.assertIs(fetcher._api, fake_api)
        self.assertEqual(getattr(fake_api, "_DataApi__token"), "trial-token")
        self.assertEqual(getattr(fake_api, "_DataApi__http_url"), "http://jiaoch.site")

    def test_patched_query_posts_to_configured_api_url(self) -> None:
        fake_api = types.SimpleNamespace(_DataApi__timeout=15)
        fake_ts = types.SimpleNamespace(
            set_token=MagicMock(),
            pro_api=MagicMock(return_value=fake_api),
        )
        fake_response = MagicMock(status_code=200)
        fake_response.text = '{"code":0,"data":{"fields":["ts_code","close"],"items":[["000001.SZ",12.34]]}}'

        with patch.dict(sys.modules, {"tushare": fake_ts}):
            with patch("data_provider.tushare_fetcher.get_config") as mock_get_config:
                with patch("data_provider.tushare_fetcher.requests.post", return_value=fake_response) as mock_post:
                    mock_get_config.return_value = types.SimpleNamespace(
                        tushare_token="trial-token",
                        tushare_api_url="http://jiaoch.site",
                    )
                    fetcher = TushareFetcher()
                    result = fetcher._api.query("daily", fields="ts_code,close", ts_code="000001.SZ")

        self.assertEqual(result.iloc[0]["ts_code"], "000001.SZ")
        self.assertEqual(result.iloc[0]["close"], 12.34)
        mock_post.assert_called_once_with(
            "http://jiaoch.site/daily",
            json={
                "api_name": "daily",
                "token": "trial-token",
                "params": {"ts_code": "000001.SZ"},
                "fields": "ts_code,close",
            },
            timeout=15,
        )

    def test_patched_query_includes_response_body_when_http_error(self) -> None:
        fake_api = types.SimpleNamespace(_DataApi__timeout=15)
        fake_ts = types.SimpleNamespace(
            set_token=MagicMock(),
            pro_api=MagicMock(return_value=fake_api),
        )
        fake_response = MagicMock(status_code=404, text="<html><title>404 Not Found</title></html>")

        with patch.dict(sys.modules, {"tushare": fake_ts}):
            with patch("data_provider.tushare_fetcher.get_config") as mock_get_config:
                with patch("data_provider.tushare_fetcher.requests.post", return_value=fake_response):
                    mock_get_config.return_value = types.SimpleNamespace(
                        tushare_token="trial-token",
                        tushare_api_url="http://jiaoch.site",
                    )
                    fetcher = TushareFetcher()
                    with self.assertRaises(Exception) as ctx:
                        fetcher._api.query("daily", ts_code="000001.SZ")

                    self.assertIn("Tushare API HTTP 404", str(ctx.exception))
                    self.assertIn("url=http://jiaoch.site/daily", str(ctx.exception))
                    self.assertIn("404 Not Found", str(ctx.exception))

    def test_check_rate_limit_skips_sleep_when_limit_disabled(self) -> None:
        fake_api = types.SimpleNamespace(_DataApi__timeout=15)
        fake_ts = types.SimpleNamespace(
            set_token=MagicMock(),
            pro_api=MagicMock(return_value=fake_api),
        )

        with patch.dict(sys.modules, {"tushare": fake_ts}):
            with patch("data_provider.tushare_fetcher.get_config") as mock_get_config:
                with patch("data_provider.tushare_fetcher.time.sleep") as mock_sleep:
                    mock_get_config.return_value = types.SimpleNamespace(
                        tushare_token="trial-token",
                        tushare_api_url="http://jiaoch.site",
                        tushare_rate_limit_per_minute=0,
                    )
                    fetcher = TushareFetcher()
                    fetcher._call_count = 999
                    fetcher._check_rate_limit()

        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
