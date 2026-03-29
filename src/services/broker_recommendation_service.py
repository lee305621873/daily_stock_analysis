# -*- coding: utf-8 -*-
"""Service layer for broker monthly gold stock recommendations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data.broker_recommend_cache import (
    load_broker_recommend_cache,
    save_broker_recommend_cache,
)
from src.services.tushare_client import create_tushare_pro_client


class BrokerRecommendationService:
    """Read broker monthly recommendation snapshots from local cache."""

    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = cache_path

    def _load_cache(self) -> Dict[str, Any]:
        return load_broker_recommend_cache(self.cache_path)

    def _save_cache(self, cache: Dict[str, Any]) -> Path:
        return save_broker_recommend_cache(cache, self.cache_path)

    @staticmethod
    def _recent_months(count: int) -> List[str]:
        current = datetime.now()
        year = current.year
        month = current.month
        values: List[str] = []
        for _ in range(max(1, count)):
            values.append(f"{year}{month:02d}")
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        return values

    @classmethod
    def _normalize_months(cls, raw: Optional[List[str]], fallback_count: int) -> List[str]:
        items: List[str] = []
        for part in list(raw or []):
            value = str(part or "").strip()
            if len(value) == 6 and value.isdigit() and value not in items:
                items.append(value)
        return items or cls._recent_months(fallback_count)

    @staticmethod
    def _infer_market(ts_code: str) -> str:
        code = str(ts_code or "").strip().upper()
        if code.endswith(".HK"):
            return "hk"
        if code.endswith(".SH") or code.endswith(".SZ") or code.endswith(".BJ"):
            return "cn"
        return "us"

    @staticmethod
    def _display_code(ts_code: str) -> str:
        code = str(ts_code or "").strip().upper()
        if "." in code:
            return code.split(".", 1)[0]
        return code

    @classmethod
    def _normalize_name(cls, row: Dict[str, Any]) -> str:
        for key in ("name", "stock_name", "ts_name"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return cls._display_code(str(row.get("ts_code") or ""))

    @classmethod
    def _aggregate_month(cls, df: Any, month: str, top_n: int) -> Dict[str, Any]:
        picks: Dict[str, Dict[str, Any]] = {}
        broker_names: set[str] = set()

        if df is None or df.empty:
            return {
                "month": month,
                "broker_total": 0,
                "total_picks": 0,
                "row_count": 0,
                "items": [],
            }

        for row in df.fillna("").to_dict(orient="records"):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            broker = str(row.get("broker") or row.get("broker_name") or "").strip()
            if not ts_code:
                continue
            if broker:
                broker_names.add(broker)
            item = picks.setdefault(
                ts_code,
                {
                    "ts_code": ts_code,
                    "code": cls._display_code(ts_code),
                    "name": cls._normalize_name(row),
                    "market": cls._infer_market(ts_code),
                    "brokers": set(),
                },
            )
            if broker:
                item["brokers"].add(broker)

        ranked_items: List[Dict[str, Any]] = []
        for ts_code, item in picks.items():
            brokers = sorted(str(name) for name in item["brokers"] if str(name).strip())
            ranked_items.append(
                {
                    "ts_code": ts_code,
                    "code": item["code"],
                    "name": item["name"],
                    "market": item["market"],
                    "broker_count": len(brokers),
                    "brokers": brokers,
                }
            )

        ranked_items.sort(key=lambda entry: (-int(entry["broker_count"]), str(entry["market"]), str(entry["code"])))
        for index, item in enumerate(ranked_items, start=1):
            item["rank"] = index

        return {
            "month": month,
            "broker_total": len(broker_names),
            "total_picks": len(ranked_items),
            "row_count": int(len(df)),
            "items": ranked_items,
        }

    @staticmethod
    def _build_broker_view(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        broker_map: Dict[str, Dict[str, Any]] = {}
        for item in items:
            for broker in list(item.get("brokers") or []):
                broker_name = str(broker or "").strip()
                if not broker_name:
                    continue
                entry = broker_map.setdefault(
                    broker_name,
                    {"broker": broker_name, "pick_count": 0, "picks": []},
                )
                entry["pick_count"] += 1
                entry["picks"].append(
                    {
                        "rank": int(item.get("rank") or 0),
                        "code": str(item.get("code") or ""),
                        "ts_code": str(item.get("ts_code") or ""),
                        "name": item.get("name"),
                        "market": str(item.get("market") or "cn"),
                        "broker_count": int(item.get("broker_count") or 0),
                    }
                )

        broker_items = list(broker_map.values())
        for entry in broker_items:
            entry["picks"].sort(
                key=lambda pick: (
                    int(pick.get("rank") or 0),
                    str(pick.get("market") or ""),
                    str(pick.get("code") or ""),
                )
            )
        broker_items.sort(
            key=lambda entry: (
                -int(entry.get("pick_count") or 0),
                str(entry.get("broker") or ""),
            )
        )
        for index, entry in enumerate(broker_items, start=1):
            entry["rank"] = index
            entry["picks"] = list(entry.get("picks") or [])
        return broker_items[:limit]

    def refresh_cache(
        self,
        months: Optional[List[str]] = None,
        history_months: int = 3,
        top_n: int = 50,
    ) -> Dict[str, Any]:
        normalized_months = self._normalize_months(months, history_months)
        pro = create_tushare_pro_client()
        items_by_month: Dict[str, Dict[str, Any]] = {}

        for month in normalized_months:
            df = pro.broker_recommend(month=month)
            items_by_month[month] = self._aggregate_month(df, month, top_n)

        cache = {
            "version": 1,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "months": normalized_months,
            "items_by_month": items_by_month,
            "meta": {
                "source": "tushare.broker_recommend",
                "top_per_month": max(1, int(top_n)),
                "history_months": len(normalized_months),
            },
        }
        self._save_cache(cache)
        return cache

    def get_monthly_recommendations(self, month: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
        cache = self._load_cache()
        months = [str(item).strip() for item in list(cache.get("months") or []) if str(item).strip()]
        items_by_month = cache.get("items_by_month") or {}

        target_month = str(month or "").strip()
        if not target_month:
            target_month = months[0] if months else ""

        snapshot = items_by_month.get(target_month) if target_month else None
        if not isinstance(snapshot, dict):
            return {
                "month": target_month or None,
                "updated_at": cache.get("updated_at"),
                "available_months": months,
                "broker_total": 0,
                "total_picks": 0,
                "items": [],
            }

        items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
        normalized_limit = max(1, min(int(limit or 12), 100))
        limited_items = list(items)[:normalized_limit]
        return {
            "month": snapshot.get("month") or target_month,
            "updated_at": cache.get("updated_at"),
            "available_months": months,
            "broker_total": int(snapshot.get("broker_total") or 0),
            "total_picks": int(snapshot.get("total_picks") or len(items)),
            "items": limited_items,
            "brokers": self._build_broker_view(list(items), normalized_limit),
        }
