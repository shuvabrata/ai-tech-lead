"""Shared Confluence producer settings sourced from environment variables."""

from __future__ import annotations

import os
from common.logger import logger

_DEFAULT_LOOKBACK_DAYS = 60

def _read_positive_int(env_name: str, default: int) -> int:
    raw_value = os.getenv(env_name, str(default)).strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def get_lookback_days() -> int:
    lookback_days = _read_positive_int("CONFLUENCE_LOOKBACK_DAYS", _DEFAULT_LOOKBACK_DAYS)
    logger.debug("Using Confluence lookback window of %d days", lookback_days)
    return lookback_days
