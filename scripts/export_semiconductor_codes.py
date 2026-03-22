#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convenience wrapper for exporting CN semiconductor board constituents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from export_board_codes import load_rows, rows_to_csv, rows_to_json, rows_to_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export A-share semiconductor board constituents")
    parser.add_argument("--board-name", default="半导体", help="CN board name, default: 半导体")
    parser.add_argument("--board-type", default="industry", choices=["industry", "concept"], help="board type")
    parser.add_argument("--format", default="text", choices=["text", "json", "csv"], help="output format")
    parser.add_argument("--output", help="optional output file path; print to stdout when omitted")
    parser.add_argument("--codes-only", action="store_true", help="text format only: output codes without names")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="fail fast when AkShare/Tushare are unavailable instead of using local fallback codes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rows, source = load_rows(
            market="cn",
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
