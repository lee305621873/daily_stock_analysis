#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh persistent board cache for stock screener."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.v1.schemas.stocks import MarketType
from src.data.stock_screener_board_cache import (
    DEFAULT_BOARD_CACHE_PATH,
    load_board_cache,
    save_board_cache,
    set_catalog_entries,
    set_constituent_entry,
)
from src.data.stock_screener_scope_config import STOCK_SCREENER_DYNAMIC_BOARD_CONFIG, STOCK_SCREENER_SCOPE_CONFIG
from src.services.stock_screener_service import (
    StockBasic,
    StockScreenerService,
    _build_board_tier_summary,
    _build_board_tiers,
    _extract_board_codes,
    _fallback_cn_board_catalog,
    _fetch_cn_board_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh persistent screener board cache")
    parser.add_argument(
        "--markets",
        default="cn,hk,us",
        help="comma-separated markets to refresh, default: cn,hk,us",
    )
    parser.add_argument(
        "--cn-all-dynamic",
        action="store_true",
        help="for CN, refresh all dynamic industry/concept boards from live catalog when available",
    )
    parser.add_argument(
        "--cn-limit",
        type=int,
        default=None,
        help="when --cn-all-dynamic is enabled, limit the number of CN boards per board type for testing",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_BOARD_CACHE_PATH),
        help="output cache path",
    )
    parser.add_argument(
        "--skip-overseas-live",
        action="store_true",
        help="for HK/US, skip live AkShare + YFinance enrichment and only persist configured seed pools",
    )
    parser.add_argument(
        "--overseas-limit",
        type=int,
        default=None,
        help="optional cap for HK/US market symbol probing during live enrichment, useful for debugging",
    )
    return parser.parse_args()


def _scope_board_fallback_codes(board_type: str, board_name: str) -> List[str]:
    for scope in STOCK_SCREENER_SCOPE_CONFIG.get("cn", []):
        if str(scope.get("kind") or "") != "board":
            continue
        if str(scope.get("board_type") or "") != board_type:
            continue
        if str(scope.get("board_name") or "").strip() != board_name:
            continue
        return [str(code).strip() for code in list(scope.get("fallback_codes") or []) if str(code).strip()]
    return []


def _basics_to_items(basics: Iterable[StockBasic]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen: set[str] = set()
    for basic in basics:
        code = str(getattr(basic, "code", "") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        name = str(getattr(basic, "name", "") or "").strip()
        items.append({"code": code, "name": name or code})
    return items


def _config_board_items(codes: Iterable[str]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append({"code": normalized, "name": normalized})
    return items


def _load_cn_catalog_rows(board_type: str) -> Tuple[List[Dict[str, object]], str]:
    try:
        return _fetch_cn_board_catalog(board_type)
    except Exception:
        return _fallback_cn_board_catalog(board_type), "config_fallback"


def _refresh_cn_market(
    cache: Dict[str, object],
    service: StockScreenerService,
    include_all_dynamic: bool,
    limit: int | None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for board_type in ("industry", "concept"):
        catalog_rows, catalog_source = _load_cn_catalog_rows(board_type)
        if limit is not None:
            catalog_rows = catalog_rows[:limit]

        set_catalog_entries(cache, "cn", board_type, [
            {
                "board_name": str(row.get("board_name") or ""),
                "label": str(row.get("label") or row.get("board_name") or ""),
                "estimated_count": row.get("estimated_count"),
                "description": row.get("description"),
                "source": catalog_source,
                "updated_at": now,
            }
            for row in catalog_rows
            if str(row.get("board_name") or "").strip()
        ])

        target_boards: List[str] = []
        if include_all_dynamic:
            target_boards.extend(
                str(row.get("board_name") or "").strip()
                for row in catalog_rows
                if str(row.get("board_name") or "").strip()
            )

        for scope in STOCK_SCREENER_SCOPE_CONFIG.get("cn", []):
            if str(scope.get("kind") or "") != "board":
                continue
            if str(scope.get("board_type") or "") != board_type:
                continue
            board_name = str(scope.get("board_name") or "").strip()
            if board_name:
                target_boards.append(board_name)

        seen_board_names: set[str] = set()
        for board_name in target_boards:
            if not board_name or board_name in seen_board_names:
                continue
            seen_board_names.add(board_name)
            fallback_codes = _scope_board_fallback_codes(board_type, board_name)
            basics, source = service._load_cn_board_basics(board_type, board_name, fallback_codes)
            items = _basics_to_items(basics)
            if not items:
                continue
            set_constituent_entry(cache, "cn", board_type, board_name, {
                "market": "cn",
                "board_type": board_type,
                "board_name": board_name,
                "description": None,
                "tier_summary": None,
                "tiers": [],
                "items": items,
                "source": source,
                "updated_at": now,
            })


def _refresh_config_market(
    cache: Dict[str, object],
    service: StockScreenerService,
    market: str,
    enable_live_enrichment: bool,
    overseas_limit: int | None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    market_enum = MarketType(market)
    for board_type, boards in STOCK_SCREENER_DYNAMIC_BOARD_CONFIG.get(market, {}).items():
        live_snapshots: Dict[str, Dict[str, object]] = {}
        if enable_live_enrichment:
            try:
                live_snapshots, live_source = service.build_overseas_market_board_snapshots(
                    market=market_enum,
                    board_type=board_type,
                    cache=cache,
                    profile_limit=overseas_limit,
                )
                print(f"[INFO] refreshed {market.upper()} {board_type} snapshots from {live_source}, boards={len(live_snapshots)}")
            except Exception as exc:
                print(f"[WARN] failed to refresh {market.upper()} {board_type} live snapshots: {exc}")
                live_snapshots = {}
        catalog_rows: List[Dict[str, object]] = []
        for board in boards:
            board_name = str(board.get("board_name") or "").strip()
            if not board_name:
                continue
            snapshot = live_snapshots.get(board_name) or {}
            items = list(snapshot.get("items") or _config_board_items(_extract_board_codes(board)))
            source = str(snapshot.get("source") or "config")
            catalog_rows.append({
                "board_name": board_name,
                "label": str(board.get("label") or board_name),
                "estimated_count": len(items),
                "description": board.get("description"),
                "tier_summary": _build_board_tier_summary(board),
                "tiers": _build_board_tiers(board),
                "source": source,
                "updated_at": now,
            })
            set_constituent_entry(cache, market, board_type, board_name, {
                "market": market,
                "board_type": board_type,
                "board_name": board_name,
                "description": board.get("description"),
                "tier_summary": _build_board_tier_summary(board),
                "tiers": _build_board_tiers(board),
                "items": items,
                "source": source,
                "updated_at": now,
            })
        set_catalog_entries(cache, market, board_type, catalog_rows)


def main() -> int:
    args = parse_args()
    selected_markets = {part.strip().lower() for part in args.markets.split(",") if part.strip()}
    output_path = Path(args.output).expanduser().resolve()
    cache = load_board_cache(output_path)
    service = StockScreenerService()

    if "cn" in selected_markets:
        _refresh_cn_market(cache, service, include_all_dynamic=args.cn_all_dynamic, limit=args.cn_limit)
    if "hk" in selected_markets:
        _refresh_config_market(
            cache,
            service,
            "hk",
            enable_live_enrichment=not args.skip_overseas_live,
            overseas_limit=args.overseas_limit,
        )
    if "us" in selected_markets:
        _refresh_config_market(
            cache,
            service,
            "us",
            enable_live_enrichment=not args.skip_overseas_live,
            overseas_limit=args.overseas_limit,
        )

    saved_path = save_board_cache(cache, output_path)
    print(f"[OK] board cache refreshed: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
