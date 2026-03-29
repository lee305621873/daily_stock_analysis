# -*- coding: utf-8 -*-
"""Persistent cache helpers for Tushare broker monthly recommendations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BROKER_RECOMMEND_CACHE_PATH = ROOT_DIR / "data" / "tushare" / "broker_recommendations.json"


def _empty_cache() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "months": [],
        "items_by_month": {},
        "meta": {},
    }


def load_broker_recommend_cache(path: Optional[Path] = None) -> Dict[str, Any]:
    target = path or DEFAULT_BROKER_RECOMMEND_CACHE_PATH
    if not target.exists():
        return _empty_cache()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return _empty_cache()

    cache = _empty_cache()
    if isinstance(payload, dict):
        cache.update(payload)
    if not isinstance(cache.get("months"), list):
        cache["months"] = []
    if not isinstance(cache.get("items_by_month"), dict):
        cache["items_by_month"] = {}
    if not isinstance(cache.get("meta"), dict):
        cache["meta"] = {}
    return cache


def save_broker_recommend_cache(cache: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or DEFAULT_BROKER_RECOMMEND_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(cache or {})
    payload["version"] = int(payload.get("version") or 1)
    payload["updated_at"] = payload.get("updated_at") or datetime.now(timezone.utc).isoformat()
    payload.setdefault("months", [])
    payload.setdefault("items_by_month", {})
    payload.setdefault("meta", {})
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
