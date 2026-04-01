# -*- coding: utf-8 -*-
"""Tests for tolerant env parsing in Config._load_from_env()."""

import os
import unittest
from unittest.mock import patch

from src.config import Config


class ConfigEnvParsingTestCase(unittest.TestCase):
    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_invalid_or_empty_int_env_values_fallback_to_defaults(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "TUSHARE_RATE_LIMIT_PER_MINUTE": "",
            "STOCK_SCREENER_MAX_WORKERS": "'",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.tushare_rate_limit_per_minute, 80)
        self.assertEqual(config.stock_screener_max_workers, 16)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_quoted_int_env_values_are_parsed(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "TUSHARE_RATE_LIMIT_PER_MINUTE": "'120'",
            "STOCK_SCREENER_MAX_WORKERS": "2",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.tushare_rate_limit_per_minute, 120)
        self.assertEqual(config.stock_screener_max_workers, 2)


if __name__ == "__main__":
    unittest.main()
