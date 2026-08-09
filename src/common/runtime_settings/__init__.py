"""Runtime-configurable application settings — shared module.

This package provides the ``RuntimeConfig`` Pydantic model, the
``RuntimeConfigCache`` thread-safe in-memory cache, and a REST snapshot
client for non-app processes.  It lives in ``src/common/`` so both app
and non-app processes can import it without pulling in ``src.app`` or
requiring a database connection.
"""

from common.runtime_settings.cache import RuntimeConfigCache
from common.runtime_settings.client import fetch_runtime_snapshot
from common.runtime_settings.config import RuntimeConfig

__all__ = [
    "RuntimeConfig",
    "RuntimeConfigCache",
    "fetch_runtime_snapshot",
]