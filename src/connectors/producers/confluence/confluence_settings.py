"""Shared Confluence producer settings sourced from environment variables."""

from __future__ import annotations

import os

_DEFAULT_MAX_RESULTS_PER_PAGE = 100000
_DEFAULT_LOOKBACK_DAYS = 60


def _read_positive_int(env_name: str, default: int) -> int:
    raw_value = os.getenv(env_name, str(default)).strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def get_max_results_per_page() -> int:
    return _read_positive_int("CONFLUENCE_MAX_RESULTS_PER_PAGE", _DEFAULT_MAX_RESULTS_PER_PAGE)


def get_lookback_days() -> int:
    return _read_positive_int("CONFLUENCE_LOOKBACK_DAYS", _DEFAULT_LOOKBACK_DAYS)
