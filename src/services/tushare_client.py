# -*- coding: utf-8 -*-
"""Shared helper for constructing a configured Tushare Pro client."""

from __future__ import annotations

from typing import Optional

from src.config import get_config


def create_tushare_pro_client(
    token: Optional[str] = None,
    api_url: Optional[str] = None,
):
    """Create a Tushare Pro client with explicit private token/base-url patching."""
    config = get_config()
    resolved_token = str(token or getattr(config, "tushare_token", "") or "").strip()
    resolved_api_url = str(
        api_url or getattr(config, "tushare_api_url", "") or "http://api.tushare.pro"
    ).strip().rstrip("/")

    if not resolved_token:
        raise ValueError("TUSHARE_TOKEN not configured")

    import tushare as ts

    ts.set_token(resolved_token)
    pro = ts.pro_api(resolved_token)
    setattr(pro, "_DataApi__token", resolved_token)
    setattr(pro, "_DataApi__http_url", resolved_api_url)
    return pro
