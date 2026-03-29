#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch and cache Tushare broker monthly gold stock recommendations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.broker_recommend_cache import DEFAULT_BROKER_RECOMMEND_CACHE_PATH
from src.services.broker_recommendation_service import BrokerRecommendationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh broker monthly gold picks from Tushare")
    parser.add_argument(
        "--months",
        default="",
        help="comma-separated months like 202603,202602; default uses current and previous 2 months",
    )
    parser.add_argument("--history-months", type=int, default=3, help="number of recent months to fetch when --months is empty")
    parser.add_argument("--top", type=int, default=50, help="top N picks kept per month after aggregation")
    parser.add_argument("--output", default=str(DEFAULT_BROKER_RECOMMEND_CACHE_PATH), help="output json path")
    return parser.parse_args()

def _normalize_months(raw: str, fallback_count: int) -> List[str]:
    if not raw.strip():
        return []
    items: List[str] = []
    for part in raw.split(","):
        value = part.strip()
        if len(value) == 6 and value.isdigit() and value not in items:
            items.append(value)
    return items


def main() -> int:
    args = parse_args()
    months = _normalize_months(args.months, args.history_months)
    service = BrokerRecommendationService(cache_path=Path(args.output))
    cache = service.refresh_cache(months=months, history_months=args.history_months, top_n=args.top)

    for month in cache.get("months") or []:
        snapshot = (cache.get("items_by_month") or {}).get(month) or {}
        print(
            f"[OK] month={month} rows={snapshot['row_count']} brokers={snapshot['broker_total']} "
            f"picks={snapshot['total_picks']} kept={len(snapshot['items'])}"
        )

    print(f"[DONE] saved broker recommendations to {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
