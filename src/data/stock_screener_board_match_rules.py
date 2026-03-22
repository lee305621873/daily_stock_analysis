# -*- coding: utf-8 -*-
"""Keyword-based board match rules for HK/US live board enrichment."""

from __future__ import annotations

from typing import Any, Dict


BoardRule = Dict[str, Any]


OVERSEAS_BOARD_MATCH_RULES: Dict[str, Dict[str, Dict[str, BoardRule]]] = {
    "hk": {
        "industry": {
            "科技互联网": {
                "sector_keywords": ["technology", "communication services"],
                "industry_keywords": [
                    "internet",
                    "software",
                    "consumer electronics",
                    "electronic",
                    "communication equipment",
                    "semiconductor",
                ],
            },
            "半导体": {
                "sector_keywords": ["technology"],
                "industry_keywords": ["semiconductor", "electronic components", "electronics"],
                "name_keywords": ["semi", "chip"],
            },
            "新能源车": {
                "sector_keywords": ["consumer cyclical", "industrials", "basic materials", "energy"],
                "industry_keywords": [
                    "auto",
                    "vehicle",
                    "battery",
                    "lithium",
                    "new energy",
                    "ev",
                ],
            },
            "消费零售": {
                "sector_keywords": ["consumer cyclical", "consumer defensive"],
                "industry_keywords": [
                    "retail",
                    "restaurant",
                    "apparel",
                    "beverage",
                    "packaged foods",
                    "travel",
                    "internet retail",
                ],
            },
            "金融": {
                "sector_keywords": ["financial", "financial services"],
                "industry_keywords": ["bank", "insurance", "capital markets", "asset management", "exchange"],
            },
            "医药医疗": {
                "sector_keywords": ["healthcare"],
                "industry_keywords": ["drug", "biotech", "medical", "healthcare", "diagnostics", "pharma"],
            },
            "能源公用": {
                "sector_keywords": ["energy", "utilities"],
                "industry_keywords": ["oil", "gas", "coal", "electric", "utility", "power"],
            },
            "地产基建": {
                "sector_keywords": ["real estate", "industrials"],
                "industry_keywords": ["real estate", "property", "construction", "engineering", "infrastructure"],
            },
            "航运物流": {
                "sector_keywords": ["industrials"],
                "industry_keywords": ["shipping", "marine", "freight", "logistics", "transport"],
            },
            "博彩旅游": {
                "sector_keywords": ["consumer cyclical"],
                "industry_keywords": ["casino", "resort", "travel", "lodging", "hotel", "airline", "leisure"],
            },
            "通信设备与运营": {
                "sector_keywords": ["communication services", "technology"],
                "industry_keywords": ["telecom", "communication equipment", "wireless", "network"],
            },
        }
    },
    "us": {
        "industry": {
            "科技平台": {
                "sector_keywords": ["technology", "communication services"],
                "industry_keywords": [
                    "software",
                    "internet",
                    "consumer electronics",
                    "cloud",
                    "application",
                    "information technology",
                ],
            },
            "半导体": {
                "sector_keywords": ["technology"],
                "industry_keywords": ["semiconductor", "semiconductors", "semiconductor equipment"],
                "name_keywords": ["semi", "chip"],
            },
            "软件安全": {
                "sector_keywords": ["technology"],
                "industry_keywords": ["software", "security", "cyber", "application", "infrastructure"],
            },
            "AI 与算力基础设施": {
                "sector_keywords": ["technology", "utilities", "real estate"],
                "industry_keywords": [
                    "server",
                    "data center",
                    "network",
                    "communication equipment",
                    "semiconductor",
                    "computer hardware",
                    "power",
                ],
                "name_keywords": ["ai", "compute", "data center"],
            },
            "金融": {
                "sector_keywords": ["financial", "financial services"],
                "industry_keywords": ["bank", "insurance", "capital markets", "asset management", "credit services", "exchange"],
            },
            "消费零售": {
                "sector_keywords": ["consumer cyclical", "consumer defensive"],
                "industry_keywords": [
                    "retail",
                    "restaurant",
                    "travel",
                    "apparel",
                    "lodging",
                    "internet retail",
                    "specialty retail",
                ],
            },
            "医疗健康": {
                "sector_keywords": ["healthcare"],
                "industry_keywords": ["drug", "biotech", "medical", "healthcare", "diagnostics", "pharma"],
            },
            "能源工业": {
                "sector_keywords": ["energy", "industrials"],
                "industry_keywords": [
                    "oil",
                    "gas",
                    "industrial",
                    "aerospace",
                    "defense",
                    "machinery",
                    "railroad",
                    "transportation",
                ],
            },
            "公用事业": {
                "sector_keywords": ["utilities"],
                "industry_keywords": ["electric", "utility", "power", "renewable", "independent power"],
            },
            "REITs": {
                "sector_keywords": ["real estate"],
                "industry_keywords": ["reit", "real estate"],
            },
            "航空航天军工": {
                "sector_keywords": ["industrials"],
                "industry_keywords": ["aerospace", "defense", "aircraft", "military"],
            },
            "材料化工": {
                "sector_keywords": ["basic materials"],
                "industry_keywords": ["chemical", "materials", "metal", "mining", "steel", "copper", "gold"],
            },
            "汽车出行": {
                "sector_keywords": ["consumer cyclical", "industrials"],
                "industry_keywords": ["auto", "vehicle", "transportation", "mobility", "truck", "parts"],
            },
        }
    },
}
