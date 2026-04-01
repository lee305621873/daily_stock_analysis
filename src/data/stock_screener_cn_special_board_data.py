# -*- coding: utf-8 -*-
"""Built-in CN special board data for screener preset scopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[2]
CN_SPECIAL_BOARD_DATA_PATH = ROOT_DIR / "data" / "stock_screener" / "cn_special_board_data.json"


def _load_payload() -> Dict[str, Any]:
    if not CN_SPECIAL_BOARD_DATA_PATH.exists():
        return {"summary": {}, "boards": {}}
    try:
        payload = json.loads(CN_SPECIAL_BOARD_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"summary": {}, "boards": {}}
    if not isinstance(payload, dict):
        return {"summary": {}, "boards": {}}
    summary = payload.get("summary")
    boards = payload.get("boards")
    return {
        "summary": summary if isinstance(summary, dict) else {},
        "boards": boards if isinstance(boards, dict) else {},
    }


_PAYLOAD = _load_payload()
CN_SPECIAL_BOARD_SUMMARY: Dict[str, Any] = dict(_PAYLOAD.get("summary") or {})
CN_SPECIAL_BOARD_ITEMS: Dict[str, List[Dict[str, str]]] = {
    str(board_name): [
        {
            "code": str(item.get("code") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "source": str(item.get("source") or "").strip(),
        }
        for item in list(items or [])
        if isinstance(item, dict) and str(item.get("code") or "").strip()
    ]
    for board_name, items in dict(_PAYLOAD.get("boards") or {}).items()
}

CN_CPO_FALLBACK_CODES = [item["code"] for item in CN_SPECIAL_BOARD_ITEMS.get("CPO", [])]
CN_PCB_FALLBACK_CODES = [item["code"] for item in CN_SPECIAL_BOARD_ITEMS.get("PCB", [])]
CN_OPTICAL_CHIP_FALLBACK_CODES = [item["code"] for item in CN_SPECIAL_BOARD_ITEMS.get("光芯片", [])]
