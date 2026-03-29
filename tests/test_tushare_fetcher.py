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
            "http://jiaoch.site",
            json={
                "api_name": "daily",
                "token": "trial-token",
                "params": {"ts_code": "000001.SZ"},
                "fields": "ts_code,close",
            },
            timeout=15,
        )


if __name__ == "__main__":
    unittest.main()
