#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export board constituents for CN/HK/US markets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.v1.schemas.stocks import MarketType, ScreenerBoardType
from src.services.stock_screener_service import StockScreenerService


BoardRow = Tuple[str, str]


def _payload_to_rows(payload) -> List[BoardRow]:
    rows: List[BoardRow] = []
    seen: set[str] = set()
    for item in payload.items:
        code = str(getattr(item, "code", "") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append((code, str(getattr(item, "name", "") or "").strip()))
    return rows


def load_rows(market: str, board_type: str, board_name: str, allow_fallback: bool) -> tuple[List[BoardRow], str]:
    normalized_market = market.strip().lower()
    normalized_type = board_type.strip().lower()
    normalized_name = board_name.strip()
    service = StockScreenerService()
    payload = service.board_constituents(
        market=MarketType(normalized_market),
        board_type=ScreenerBoardType(normalized_type),
        board_name=normalized_name,
        allow_fallback=allow_fallback,
    )
    rows = _payload_to_rows(payload)
    if not rows:
        raise RuntimeError(f"board has no constituents for {normalized_name}")
    return rows, payload.source


def rows_to_text(rows: Iterable[BoardRow], with_names: bool) -> str:
    lines: List[str] = []
    for code, name in rows:
        if with_names and name:
            lines.append(f"{code}\t{name}")
        else:
            lines.append(code)
    return "\n".join(lines) + "\n"


def rows_to_json(rows: Iterable[BoardRow]) -> str:
    return json.dumps([{"code": code, "name": name} for code, name in rows], ensure_ascii=False, indent=2) + "\n"


def rows_to_csv(rows: Iterable[BoardRow]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["code", "name"])
    for code, name in rows:
        writer.writerow([code, name])
    return buffer.getvalue()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export board constituents for CN/HK/US markets")
    parser.add_argument("--market", default="cn", choices=["cn", "hk", "us"], help="target market")
    parser.add_argument("--board-type", default="industry", choices=["industry", "concept"], help="board type")
    parser.add_argument("--board-name", required=True, help="board name, e.g. 半导体 / 人工智能 / 科技互联网")
    parser.add_argument("--format", default="text", choices=["text", "json", "csv"], help="output format")
    parser.add_argument("--output", help="optional output file path")
    parser.add_argument("--codes-only", action="store_true", help="text format only: output codes without names")
    parser.add_argument("--no-fallback", action="store_true", help="CN only: fail fast when AkShare is unavailable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rows, source = load_rows(
            market=args.market,
            board_type=args.board_type,
            board_name=args.board_name,
            allow_fallback=not args.no_fallback,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        output = rows_to_json(rows)
    elif args.format == "csv":
        output = rows_to_csv(rows)
    else:
        output = rows_to_text(rows, with_names=not args.codes_only)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[OK] exported {len(rows)} rows from {source} to {args.output}")
    else:
        print(f"# source={source} count={len(rows)}", file=sys.stderr)
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
