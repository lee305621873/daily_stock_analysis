# -*- coding: utf-8 -*-
"""API tests for stock endpoints."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class StocksApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "stocks_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            ) + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.client = TestClient(create_app(static_dir=self.data_dir / "empty-static"))

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_broker_recommendations_endpoint(self) -> None:
        with patch("api.v1.endpoints.stocks.BrokerRecommendationService") as service_cls:
            service_cls.return_value.get_monthly_recommendations.return_value = {
                "month": "202603",
                "updated_at": "2026-03-29T00:00:00Z",
                "available_months": ["202603"],
                "broker_total": 2,
                "total_picks": 2,
                "items": [
                    {
                        "rank": 1,
                        "code": "600519",
                        "ts_code": "600519.SH",
                        "name": "贵州茅台",
                        "market": "cn",
                        "broker_count": 2,
                        "brokers": ["中信证券", "华泰证券"],
                    }
                ],
                "brokers": [
                    {
                        "rank": 1,
                        "broker": "中信证券",
                        "pick_count": 1,
                        "picks": [
                            {
                                "rank": 1,
                                "code": "600519",
                                "ts_code": "600519.SH",
                                "name": "贵州茅台",
                                "market": "cn",
                                "broker_count": 2,
                            }
                        ],
                    }
                ],
            }

            response = self.client.get("/api/v1/stocks/broker-recommendations", params={"limit": 8})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["code"], "600519")
        self.assertEqual(payload["brokers"][0]["broker"], "中信证券")

    def test_refresh_broker_recommendations_endpoint(self) -> None:
        with patch("api.v1.endpoints.stocks.BrokerRecommendationService") as service_cls:
            service = service_cls.return_value
            service.refresh_cache.return_value = {"months": ["202603"]}
            service.get_monthly_recommendations.return_value = {
                "month": "202603",
                "updated_at": "2026-03-29T00:00:00Z",
                "available_months": ["202603"],
                "broker_total": 2,
                "total_picks": 2,
                "items": [],
                "brokers": [],
            }

            response = self.client.post(
                "/api/v1/stocks/broker-recommendations/refresh",
                params={"history_months": 3, "top": 50, "limit": 8},
            )

        self.assertEqual(response.status_code, 200)
        service.refresh_cache.assert_called_once()
        self.assertEqual(response.json()["month"], "202603")


if __name__ == "__main__":
    unittest.main()
