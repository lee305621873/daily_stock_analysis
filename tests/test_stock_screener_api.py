# -*- coding: utf-8 -*-
"""API tests for stock screener endpoints."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from api.v1.schemas.stocks import ScreenerScanResultItem, ScreenerTaskAccepted, ScreenerTaskStatusEnum
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class StockScreenerApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "stock_screener_api_test.db"
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

    def test_indicator_catalog_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.indicator_catalog.return_value = [
                {
                    "key": "RSI",
                    "name": "RSI",
                    "category": "swing",
                    "summary": "衡量超买超卖",
                    "params": [],
                    "outputs": [{"key": "rsi", "label": "RSI"}],
                    "operators": [">", "<"],
                }
            ]

            response = self.client.get("/api/v1/stocks/screener/indicators")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["key"], "RSI")

    def test_scope_catalog_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.scope_catalog.return_value = [
                {
                    "key": "cn_semiconductor",
                    "market": "cn",
                    "label": "A 股半导体",
                    "description": "半导体板块成分股",
                    "kind": "board",
                    "estimated_count": 132,
                    "preview_codes": ["603986", "688981"],
                    "board_name": "半导体",
                    "board_type": "industry",
                }
            ]

            response = self.client.get("/api/v1/stocks/screener/scopes", params={"market": "cn"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["key"], "cn_semiconductor")

    def test_board_catalog_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.board_catalog.return_value = [
                {
                    "market": "cn",
                    "board_type": "industry",
                    "board_name": "半导体",
                    "label": "半导体",
                    "estimated_count": 132,
                    "tiers": [],
                }
            ]

            response = self.client.get(
                "/api/v1/stocks/screener/boards",
                params={"market": "cn", "board_type": "industry"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["board_name"], "半导体")

    def test_board_preview_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.board_preview.return_value = {
                "market": "cn",
                "board_type": "industry",
                "board_name": "半导体",
                "estimated_count": 132,
                "preview_codes": ["603986", "688981"],
                "tiers": [],
            }

            response = self.client.get(
                "/api/v1/stocks/screener/boards/preview",
                params={"market": "cn", "board_type": "industry", "board_name": "半导体", "limit": 20},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preview_codes"][0], "603986")

    def test_board_constituents_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.board_constituents.return_value = {
                "market": "cn",
                "board_type": "industry",
                "board_name": "半导体",
                "total": 2,
                "source": "tushare",
                "items": [
                    {"code": "603986", "name": "兆易创新"},
                    {"code": "688981", "name": "中芯国际"},
                ],
            }

            response = self.client.get(
                "/api/v1/stocks/screener/boards/constituents",
                params={"market": "cn", "board_type": "industry", "board_name": "半导体"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "tushare")
        self.assertEqual(response.json()["items"][0]["code"], "603986")

    def test_formula_function_catalog_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.formula_function_catalog.return_value = [
                {
                    "name": "MA",
                    "category": "trend",
                    "summary": "Moving average",
                    "signature": "MA(series, period)",
                    "returns": "series",
                    "examples": ["MA(CLOSE, 5)"],
                    "params": [],
                }
            ]

            response = self.client.get("/api/v1/stocks/screener/formula/functions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "MA")

    def test_formula_template_list_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.list_formula_templates.return_value = [
                {
                    "id": "custom-1",
                    "label": "我的突破策略",
                    "value": "CLOSE > MA(CLOSE, 10)",
                    "created_at": "2026-03-27T10:00:00",
                    "updated_at": "2026-03-27T10:00:00",
                }
            ]

            response = self.client.get("/api/v1/stocks/screener/formula/templates")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], "custom-1")

    def test_formula_template_upsert_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.upsert_formula_template.return_value = {
                "id": "custom-1",
                "label": "我的突破策略",
                "value": "CLOSE > MA(CLOSE, 10)",
                "created_at": "2026-03-27T10:00:00",
                "updated_at": "2026-03-27T11:00:00",
            }

            response = self.client.post(
                "/api/v1/stocks/screener/formula/templates",
                json={
                    "id": "custom-1",
                    "label": "我的突破策略",
                    "value": "CLOSE > MA(CLOSE, 10)",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "我的突破策略")

    def test_formula_template_delete_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.delete_formula_template.return_value = True
            response = self.client.delete("/api/v1/stocks/screener/formula/templates/custom-1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])

    def test_formula_validate_endpoint(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.validate_formula.return_value = {
                "valid": True,
                "normalized_formula": "CLOSE > MA(CLOSE, 5)",
                "referenced_fields": ["CLOSE"],
                "functions": ["MA"],
                "message": "公式校验通过",
                "estimated_lookback": 250,
                "warnings": [],
            }

            response = self.client.post(
                "/api/v1/stocks/screener/formula/validate",
                json={"formula": "CLOSE > MA(CLOSE, 5)"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["valid"])

    def test_scan_endpoint_success(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.scan.return_value = {
                "total": 1,
                "results": [
                    {
                        "code": "AAPL",
                        "name": "苹果",
                        "last_close": 188.12,
                        "data_source": "mock",
                        "matched_conditions": ["RSI < 30"],
                        "boards": [],
                        "heat": 1.32,
                    }
                ],
                "csv": None,
            }

            response = self.client.post(
                "/api/v1/stocks/screener/scan",
                json={
                    "market": "us",
                    "codes": ["AAPL"],
                    "conditions": [
                        {
                            "indicator": "RSI",
                            "params": {"period": 14},
                            "output": "rsi",
                            "operator": "<",
                            "compare_to": {"type": "value", "value": 30},
                            "logic_with_previous": "AND",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["code"], "AAPL")

    def test_scan_endpoint_formula_mode_success(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.scan.return_value = {
                "total": 1,
                "results": [
                    {
                        "code": "AAPL",
                        "name": "苹果",
                        "last_close": 188.12,
                        "data_source": "mock",
                        "matched_conditions": ["趋势延续"],
                        "boards": [],
                        "heat": 1.32,
                    }
                ],
                "csv": None,
            }

            response = self.client.post(
                "/api/v1/stocks/screener/scan",
                json={
                    "mode": "formula",
                    "formula": "CLOSE > MA(CLOSE, 5)",
                    "formula_name": "趋势延续",
                    "market": "us",
                    "codes": ["AAPL"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["matched_conditions"][0], "趋势延续")

    def test_scan_endpoint_validation_error(self) -> None:
        with patch("api.v1.endpoints.stock_screener.StockScreenerService") as service_cls:
            service_cls.return_value.scan.side_effect = ValueError("hk/us scan requires explicit codes")

            response = self.client.post(
                "/api/v1/stocks/screener/scan",
                json={
                    "market": "us",
                    "conditions": [
                        {
                            "indicator": "RSI",
                            "params": {"period": 14},
                            "output": "rsi",
                            "operator": "<",
                            "compare_to": {"type": "value", "value": 30},
                            "logic_with_previous": "AND",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 400)
        detail = response.json()
        self.assertEqual(detail.get("error"), "validation_error")

    def test_scan_endpoint_accepts_async_task(self) -> None:
        accepted = ScreenerTaskAccepted(task_id="task-001", message="选股任务已提交")

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.submit_task.return_value = accepted

            response = self.client.post(
                "/api/v1/stocks/screener/scan",
                json={
                    "market": "cn",
                    "async_mode": True,
                    "conditions": [
                        {
                            "indicator": "RSI",
                            "params": {"period": 14},
                            "output": "rsi",
                            "operator": "<",
                            "compare_to": {"type": "value", "value": 30},
                            "logic_with_previous": "AND",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["task_id"], "task-001")
        queue_factory.return_value.submit_task.assert_called_once()

    def test_scan_endpoint_scope_without_codes_defaults_to_async_task(self) -> None:
        accepted = ScreenerTaskAccepted(task_id="task-002", message="选股任务已提交")

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.submit_task.return_value = accepted

            response = self.client.post(
                "/api/v1/stocks/screener/scan",
                json={
                    "market": "us",
                    "scope": "us_semiconductor",
                    "conditions": [
                        {
                            "indicator": "RSI",
                            "params": {"period": 14},
                            "output": "rsi",
                            "operator": "<",
                            "compare_to": {"type": "value", "value": 30},
                            "logic_with_previous": "AND",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["task_id"], "task-002")
        queue_factory.return_value.submit_task.assert_called_once()

    def test_get_task_status_endpoint(self) -> None:
        task_payload = {
            "task_id": "task-001",
            "market": "cn",
            "status": ScreenerTaskStatusEnum.PROCESSING.value,
            "progress": 35,
            "scanned_count": 350,
            "total_count": 1000,
            "matched_count": 12,
            "message": "正在扫描 350/1000，当前命中 12 条",
            "created_at": "2026-03-20T10:00:00",
            "started_at": "2026-03-20T10:00:01",
            "completed_at": None,
            "error": None,
            "result": None,
        }
        task_record = SimpleNamespace(to_dict=lambda include_result=False: task_payload)

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.get_task.return_value = task_record

            response = self.client.get("/api/v1/stocks/screener/tasks/task-001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "task-001")
        self.assertEqual(response.json()["progress"], 35)

    def test_export_task_results_csv_endpoint(self) -> None:
        task_record = SimpleNamespace(status=ScreenerTaskStatusEnum.COMPLETED, result=SimpleNamespace(results=[]))
        export_rows = [
            ScreenerScanResultItem(
                code="600519",
                name="贵州茅台",
                last_close=1888.88,
                data_source="mock",
                matched_conditions=["RSI < 30"],
                boards=["白酒"],
                heat=1.23,
            )
        ]

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.get_task.return_value = task_record
            queue_factory.return_value.get_task_export_items.return_value = export_rows

            response = self.client.get("/api/v1/stocks/screener/tasks/task-001/export?format=csv&scope=all")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("attachment;", response.headers.get("content-disposition", ""))
        decoded = response.content.decode("utf-8-sig")
        self.assertIn("贵州茅台", decoded)
        self.assertIn("600519", decoded)

    def test_export_task_results_xlsx_endpoint(self) -> None:
        task_record = SimpleNamespace(status=ScreenerTaskStatusEnum.COMPLETED, result=SimpleNamespace(results=[]))
        export_rows = [
            ScreenerScanResultItem(
                code="AAPL",
                name="苹果",
                last_close=188.12,
                data_source="mock",
                matched_conditions=["趋势延续"],
                boards=["美股科技"],
                heat=1.11,
            )
        ]

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.get_task.return_value = task_record
            queue_factory.return_value.get_task_export_items.return_value = export_rows

            response = self.client.get("/api/v1/stocks/screener/tasks/task-002/export?format=xlsx&scope=all")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response.headers.get("content-type", ""),
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_export_task_results_rejects_incomplete_task(self) -> None:
        task_record = SimpleNamespace(status=ScreenerTaskStatusEnum.PROCESSING, result=None)

        with patch("api.v1.endpoints.stock_screener.get_stock_screener_task_queue") as queue_factory:
            queue_factory.return_value.get_task.return_value = task_record

            response = self.client.get("/api/v1/stocks/screener/tasks/task-003/export?format=xlsx&scope=all")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "task_not_completed")

    def test_export_rows_endpoint(self) -> None:
        response = self.client.post(
            "/api/v1/stocks/screener/export/rows",
            json={
                "format": "xlsx",
                "filename": "my-picked-stocks",
                "items": [
                    {
                        "code": "00700",
                        "name": "腾讯控股",
                        "last_close": 320.5,
                        "data_source": "mock",
                        "matched_conditions": ["趋势延续"],
                        "boards": ["港股互联网"],
                        "heat": 1.09,
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"PK"))
