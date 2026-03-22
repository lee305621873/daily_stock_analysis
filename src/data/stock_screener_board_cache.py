# -*- coding: utf-8 -*-
"""Persistent board cache helpers for stock screener."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_CACHE_PATH = ROOT_DIR / "data" / "stock_screener" / "board_cache.json"


def _empty_cache() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "catalogs": {},
        "constituents": {},
        "profiles": {},
    }


def _catalog_key(market: str, board_type: str) -> str:
    return f"{market}:{board_type}"


def _constituent_key(market: str, board_type: str, board_name: str) -> str:
    return f"{market}:{board_type}:{board_name}"


def _profile_key(market: str, code: str) -> str:
    return f"{market}:{code}"


def load_board_cache(path: Optional[Path] = None) -> Dict[str, Any]:
    target = path or DEFAULT_BOARD_CACHE_PATH
    if not target.exists():
        return _empty_cache()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return _empty_cache()

    cache = _empty_cache()
    if isinstance(payload, dict):
        cache.update(payload)
    if not isinstance(cache.get("catalogs"), dict):
        cache["catalogs"] = {}
    if not isinstance(cache.get("constituents"), dict):
        cache["constituents"] = {}
    if not isinstance(cache.get("profiles"), dict):
        cache["profiles"] = {}
    return cache


def save_board_cache(cache: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or DEFAULT_BOARD_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(cache or {})
    payload["version"] = int(payload.get("version") or 1)
    payload["updated_at"] = payload.get("updated_at") or datetime.now(timezone.utc).isoformat()
    payload.setdefault("catalogs", {})
    payload.setdefault("constituents", {})
    payload.setdefault("profiles", {})
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def get_catalog_entries(cache: Dict[str, Any], market: str, board_type: str) -> List[Dict[str, Any]]:
    catalogs = cache.get("catalogs") if isinstance(cache, dict) else {}
    entries = catalogs.get(_catalog_key(market, board_type), [])
    return list(entries) if isinstance(entries, list) else []


def set_catalog_entries(cache: Dict[str, Any], market: str, board_type: str, entries: List[Dict[str, Any]]) -> None:
    cache.setdefault("catalogs", {})
    cache["catalogs"][_catalog_key(market, board_type)] = entries


def get_constituent_entry(cache: Dict[str, Any], market: str, board_type: str, board_name: str) -> Optional[Dict[str, Any]]:
    constituents = cache.get("constituents") if isinstance(cache, dict) else {}
    entry = constituents.get(_constituent_key(market, board_type, board_name))
    return dict(entry) if isinstance(entry, dict) else None


def set_constituent_entry(
    cache: Dict[str, Any],
    market: str,
    board_type: str,
    board_name: str,
    entry: Dict[str, Any],
) -> None:
    cache.setdefault("constituents", {})
    cache["constituents"][_constituent_key(market, board_type, board_name)] = entry


def get_profile_entry(cache: Dict[str, Any], market: str, code: str) -> Optional[Dict[str, Any]]:
    profiles = cache.get("profiles") if isinstance(cache, dict) else {}
    entry = profiles.get(_profile_key(market, code))
    return dict(entry) if isinstance(entry, dict) else None


def set_profile_entry(cache: Dict[str, Any], market: str, code: str, entry: Dict[str, Any]) -> None:
    cache.setdefault("profiles", {})
    cache["profiles"][_profile_key(market, code)] = entry
