#!/usr/bin/env python
"""
Minimal Tavily connectivity check using the project's existing config/search stack.

Usage:
  .venv/bin/python scripts/test_tavily.py
  .venv/bin/python scripts/test_tavily.py --query "比亚迪 股票 最新消息"
  .venv/bin/python scripts/test_tavily.py --stock-code 300750 --stock-name 宁德时代
"""

import argparse
from pathlib import Path
import sys

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config  # noqa: E402
from src.search_service import SearchService, TavilySearchProvider  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Test Tavily configuration and connectivity")
    parser.add_argument("--query", default=None, help="Direct query to search with Tavily")
    parser.add_argument("--stock-code", default="600519", help="Stock code for news search path")
    parser.add_argument("--stock-name", default="贵州茅台", help="Stock name for news search path")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum results to return")
    args = parser.parse_args()

    config = get_config()
    tavily_keys = config.tavily_api_keys
    print(f"TAVILY_API_KEYS loaded: {len(tavily_keys)}")
    print(f"NEWS_MAX_AGE_DAYS: {config.news_max_age_days}")

    if not tavily_keys:
        print("FAIL: TAVILY_API_KEYS is empty. Please fill it in .env first.")
        return 1

    provider = TavilySearchProvider(tavily_keys)
    print(f"Tavily provider available: {provider.is_available}")

    if args.query:
        print(f"Testing direct Tavily query: {args.query}")
        response = provider.search(args.query, args.max_results, days=config.news_max_age_days)
    else:
        service = SearchService(
            tavily_keys=tavily_keys,
            bocha_keys=[],
            brave_keys=[],
            serpapi_keys=[],
            minimax_keys=[],
            searxng_base_urls=[],
            news_max_age_days=config.news_max_age_days,
        )
        print(f"Testing search_stock_news: {args.stock_name}({args.stock_code})")
        response = service.search_stock_news(args.stock_code, args.stock_name, max_results=args.max_results)

    print(f"provider: {response.provider}")
    print(f"success: {response.success}")
    print(f"result_count: {len(response.results)}")

    if response.error_message:
        print(f"error: {response.error_message}")

    for idx, item in enumerate(response.results[:3], start=1):
        print(f"[{idx}] {item.title}")
        print(f"    source={item.source} url={item.url}")

    return 0 if response.success and bool(response.results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
