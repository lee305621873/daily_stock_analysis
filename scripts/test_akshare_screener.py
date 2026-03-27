#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Minimal AkShare connectivity check for stock screener board data.

Usage:
  .venv/bin/python scripts/test_akshare_screener.py
  .venv/bin/python scripts/test_akshare_screener.py --board "半导体" --board-type industry
  .venv/bin/python scripts/test_akshare_screener.py --board "人工智能" --board-type concept
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _classify_error_message(message: str) -> str:
    text = (message or "").lower()
    if "nameresolutionerror" in text or "failed to resolve" in text or "nodename nor servname" in text:
        return "dns"
    if "connecttimeout" in text or "read timeout" in text or "timed out" in text:
        return "timeout"
    if "remotedisconnected" in text:
        return "remote_disconnected"
    if "remote end closed connection without response" in text:
        return "remote_disconnected"
    if "max retries exceeded" in text or "newconnectionerror" in text or "connectionerror" in text:
        return "connection"
    if "connection aborted" in text or "connection reset" in text:
        return "connection"
    if "ssl" in text or "certificate" in text:
        return "ssl"
    return "unknown"


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Test AkShare availability for screener board endpoints")
    parser.add_argument("--board-type", choices=["industry", "concept"], default="industry", help="Board type to test")
    parser.add_argument("--board", default="半导体", help="Board name used to test constituents endpoint")
    parser.add_argument("--sample-size", type=int, default=3, help="How many sample rows to print")
    args = parser.parse_args()

    print("=== AkShare Screener Connectivity Check ===")
    print(f"board_type={args.board_type} board={args.board}")

    try:
        import akshare as ak  # type: ignore
    except Exception as exc:
        print(f"FAIL import: {type(exc).__name__}: {exc}")
        return 10

    version = getattr(ak, "__version__", "unknown")
    print(f"akshare_version={version}")

    start = time.perf_counter()
    try:
        if args.board_type == "industry":
            catalog_df = ak.stock_board_industry_name_em()
        else:
            catalog_df = ak.stock_board_concept_name_em()
        elapsed_catalog = time.perf_counter() - start
        catalog_count = 0 if catalog_df is None else len(catalog_df.index)
        print(f"catalog_ok=True elapsed={elapsed_catalog:.2f}s rows={catalog_count}")
    except Exception as exc:
        elapsed_catalog = time.perf_counter() - start
        message = str(exc)
        category = _classify_error_message(message)
        print(f"catalog_ok=False elapsed={elapsed_catalog:.2f}s category={category} error={type(exc).__name__}: {message}")
        return 20

    start = time.perf_counter()
    try:
        if args.board_type == "industry":
            cons_df = ak.stock_board_industry_cons_em(symbol=args.board)
        else:
            cons_df = ak.stock_board_concept_cons_em(symbol=args.board)
        elapsed_constituents = time.perf_counter() - start
        row_count = 0 if cons_df is None else len(cons_df.index)
        print(f"constituents_ok=True elapsed={elapsed_constituents:.2f}s rows={row_count}")
        if cons_df is not None and not cons_df.empty:
            preview = cons_df.head(max(1, args.sample_size))
            code_col = next((col for col in preview.columns if str(col) in {"代码", "code"}), None)
            name_col = next((col for col in preview.columns if str(col) in {"名称", "name"}), None)
            if code_col and name_col:
                print("sample_rows:")
                for _, row in preview.iterrows():
                    print(f"  - {row.get(code_col, '')} {row.get(name_col, '')}")
    except Exception as exc:
        elapsed_constituents = time.perf_counter() - start
        message = str(exc)
        category = _classify_error_message(message)
        print(
            f"constituents_ok=False elapsed={elapsed_constituents:.2f}s category={category} "
            f"error={type(exc).__name__}: {message}"
        )
        return 21

    print("RESULT=SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
