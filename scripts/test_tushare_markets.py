#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sanity-check whether Tushare can fetch CN/HK/US market data."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.tushare_client import create_tushare_pro_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Tushare market coverage for CN/HK/US")
    parser.add_argument("--cn-code", default="000001.SZ", help="A-share sample ts_code, default: 000001.SZ")
    parser.add_argument("--hk-code", default="00700.HK", help="HK sample ts_code, default: 00700.HK")
    parser.add_argument("--us-code", default="AAPL", help="US sample ts_code, default: AAPL")
    parser.add_argument("--days", type=int, default=30, help="Lookback days, default: 30")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=max(1, days))
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _run_check(pro: Any, label: str, endpoint: str, **params: Any) -> Dict[str, Any]:
    try:
        func = getattr(pro, endpoint)
        df = func(**params)
        rows = 0 if df is None else int(len(df))
        latest_trade_date = None
        if rows > 0 and "trade_date" in df.columns:
            latest_trade_date = str(df.iloc[0]["trade_date"])
        return {
            "market": label,
            "endpoint": endpoint,
            "ok": rows > 0,
            "rows": rows,
            "latest_trade_date": latest_trade_date,
            "params": params,
            "error": None,
        }
    except Exception as exc:
        return {
            "market": label,
            "endpoint": endpoint,
            "ok": False,
            "rows": 0,
            "latest_trade_date": None,
            "params": params,
            "error": str(exc),
        }


def main() -> int:
    args = parse_args()
    start_date, end_date = _date_range(args.days)
    pro = create_tushare_pro_client()

    checks: List[Dict[str, Any]] = [
        _run_check(pro, "A股", "daily", ts_code=args.cn_code, start_date=start_date, end_date=end_date),
        _run_check(pro, "港股", "hk_daily", ts_code=args.hk_code, start_date=start_date, end_date=end_date),
        _run_check(pro, "美股", "us_daily", ts_code=args.us_code, start_date=start_date, end_date=end_date),
    ]

    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        print(f"{'市场':<6} {'接口':<14} {'状态':<6} {'行数':<6} {'最新日期':<12} 参数/错误")
        for item in checks:
            status = "OK" if item["ok"] else "FAIL"
            details = item["params"] if item["ok"] else item["error"]
            print(
                f"{item['market']:<6} {item['endpoint']:<14} {status:<6} "
                f"{item['rows']:<6} {str(item['latest_trade_date'] or '-'): <12} {details}"
            )

    return 0 if all(item["ok"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
