#!/usr/bin/env python
"""
Minimal LLM connectivity check.

Reads environment variables (after loading .env) and sends a tiny chat completion
to verify the configured model/base_url/api_key can return content.

Defaults (in优先顺序):
- model:   --model > LITELLM_MODEL > OPENAI_MODEL > openai/gpt-4o-mini
- base:    --base-url > OPENAI_BASE_URL > LLM_MY_PROXY_BASE_URL
- api_key: --api-key > OPENAI_API_KEY > LLM_MY_PROXY_API_KEY
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from litellm import completion


def resolve_env(*names: str) -> str:
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return ""


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Test LLM connectivity")
    parser.add_argument("--model", default=None, help="Model name, e.g. openai/gpt-4o-mini")
    parser.add_argument("--base-url", default=None, help="LLM base URL")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--message", default="ping", help="User message to send")
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("LLM_TEST_TIMEOUT", "60")),
        help="Request timeout seconds (env LLM_TEST_TIMEOUT overrides default 60)",
    )
    args = parser.parse_args()

    model = args.model or resolve_env("LITELLM_MODEL", "OPENAI_MODEL") or "openai/gpt-4o-mini"
    base_url = args.base_url or resolve_env("OPENAI_BASE_URL", "LLM_MY_PROXY_BASE_URL")
    api_key = args.api_key or resolve_env("OPENAI_API_KEY", "LLM_MY_PROXY_API_KEY")

    if not api_key:
        print("ERR: API key is missing. Set OPENAI_API_KEY or LLM_MY_PROXY_API_KEY.", file=sys.stderr)
        return 1
    if not base_url:
        print("WARN: base_url not set, will rely on provider default.")

    print(f"model={model}")
    print(f"base_url={base_url or '<provider default>'}")

    try:
        resp = completion(
            model=model,
            messages=[{"role": "user", "content": args.message}],
            base_url=base_url or None,
            api_key=api_key,
            timeout=args.timeout,
        )
        msg = resp["choices"][0]["message"]["content"] or ""
        print("SUCCESS: received content" if msg else "FAIL: empty content")
        print(msg[:400])
        return 0 if msg else 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
