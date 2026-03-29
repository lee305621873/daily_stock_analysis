# -*- coding: utf-8 -*-
"""Unit tests for broker recommendation cache service."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.broker_recommendation_service import BrokerRecommendationService


class BrokerRecommendationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.temp_dir.name) / "broker_recommendations.json"
        self.cache_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": "2026-03-29T00:00:00Z",
                    "months": ["202603", "202602"],
                    "items_by_month": {
                        "202603": {
                            "month": "202603",
                            "broker_total": 12,
                            "total_picks": 3,
                            "items": [
                                {
                                    "rank": 1,
                                    "code": "600519",
                                    "ts_code": "600519.SH",
                                    "name": "贵州茅台",
                                    "market": "cn",
                                    "broker_count": 5,
                                    "brokers": ["中信证券", "华泰证券"],
                                },
                                {
                                    "rank": 2,
                                    "code": "AAPL",
                                    "ts_code": "AAPL",
                                    "name": "Apple",
                                    "market": "us",
                                    "broker_count": 4,
                                    "brokers": ["高盛"],
                                },
                            ],
                        },
                        "202602": {
                            "month": "202602",
                            "broker_total": 8,
                            "total_picks": 1,
                            "items": [
                                {
                                    "rank": 1,
                                    "code": "00700",
                                    "ts_code": "00700.HK",
                                    "name": "腾讯控股",
                                    "market": "hk",
                                    "broker_count": 3,
                                    "brokers": ["中金公司"],
                                }
                            ],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.service = BrokerRecommendationService(cache_path=self.cache_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_returns_latest_month_when_month_not_specified(self) -> None:
        payload = self.service.get_monthly_recommendations(limit=10)

        self.assertEqual(payload["month"], "202603")
        self.assertEqual(payload["broker_total"], 12)
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["ts_code"], "600519.SH")

    def test_returns_specific_month_and_applies_limit(self) -> None:
        payload = self.service.get_monthly_recommendations(month="202603", limit=1)

        self.assertEqual(payload["month"], "202603")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["code"], "600519")
        self.assertEqual(len(payload["brokers"]), 1)
        self.assertEqual(payload["brokers"][0]["broker"], "中信证券")

    def test_refresh_cache_rewrites_local_snapshot(self) -> None:
        class _FakeFrame:
            empty = False

            def fillna(self, _value):
                return self

            def to_dict(self, orient="records"):
                return [
                    {"ts_code": "600519.SH", "name": "贵州茅台", "broker": "中信证券"},
                    {"ts_code": "600519.SH", "name": "贵州茅台", "broker": "华泰证券"},
                    {"ts_code": "AAPL", "name": "Apple", "broker": "高盛"},
                ]

            def __len__(self):
                return 3

        class _FakePro:
            def broker_recommend(self, month: str):
                self.last_month = month
                return _FakeFrame()

        with patch("src.services.broker_recommendation_service.create_tushare_pro_client", return_value=_FakePro()):
            cache = self.service.refresh_cache(months=["202604"], top_n=10)

        self.assertEqual(cache["months"], ["202604"])
        payload = self.service.get_monthly_recommendations(month="202604", limit=5)
        self.assertEqual(payload["broker_total"], 3)
        self.assertEqual(payload["items"][0]["code"], "600519")
        self.assertEqual(payload["items"][0]["broker_count"], 2)
        self.assertTrue(any(item["broker"] == "中信证券" for item in payload["brokers"]))

    def test_broker_view_keeps_all_picks_for_expansion(self) -> None:
        items = []
        for index in range(1, 10):
            items.append(
                {
                    "rank": index,
                    "code": f"6005{index:02d}",
                    "ts_code": f"6005{index:02d}.SH",
                    "name": f"样例{index}",
                    "market": "cn",
                    "broker_count": 1,
                    "brokers": ["光大证券"],
                }
            )

        broker_view = self.service._build_broker_view(items, limit=10)  # pylint: disable=protected-access

        self.assertEqual(len(broker_view), 1)
        self.assertEqual(broker_view[0]["broker"], "光大证券")
        self.assertEqual(broker_view[0]["pick_count"], 9)
        self.assertEqual(len(broker_view[0]["picks"]), 9)


if __name__ == "__main__":
    unittest.main()
