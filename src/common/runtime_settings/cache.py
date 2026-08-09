"""Synchronous in-memory cache of the effective runtime settings snapshot.

The cache is thread-safe via ``threading.Lock`` and initialises with all
defaults (no DB or env overrides) so it is safe to import before any
refresh has occurred.
"""

from __future__ import annotations

import threading
from typing import Any

from common.runtime_settings.config import RuntimeConfig


class RuntimeConfigCache:
    """Thread-safe synchronous snapshot reader for runtime settings.

    Usage::

        cache = RuntimeConfigCache()
        cache.get("HTTP_REQUEST_TIMEOUT")       # 60
        cache.get_int("RECENT_ACTIONS_LIMIT")    # 5
        cache.get_bool("FF_NEO4J_USE_PROVIDER_PIPELINE")  # False

        cache.refresh(RuntimeConfig(HTTP_REQUEST_TIMEOUT=90))
        cache.get_int("HTTP_REQUEST_TIMEOUT")   # 90
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config: RuntimeConfig = RuntimeConfig()

    # ── Public read accessors ────────────────────────────────────────────

    def get(self, key: str) -> Any:
        """Return the raw value for *key* from the current snapshot."""
        with self._lock:
            return getattr(self._config, key)

    def get_int(self, key: str) -> int:
        """Return the value for *key* as an integer.

        Raises ``TypeError`` if the value is a ``bool`` (since ``bool`` is a
        subclass of ``int`` in Python) to prevent accidental misuse.
        """
        with self._lock:
            value = getattr(self._config, key)
        if isinstance(value, bool):
            raise TypeError(
                f"Setting {key!r} is a boolean; use get_bool() instead"
            )
        if not isinstance(value, int):
            raise TypeError(
                f"Setting {key!r} is not an integer (got {type(value).__name__})"
            )
        return value

    def get_bool(self, key: str) -> bool:
        """Return the value for *key* as a boolean.

        Raises ``TypeError`` if the value is not a ``bool``.
        """
        with self._lock:
            value = getattr(self._config, key)
        if not isinstance(value, bool):
            raise TypeError(
                f"Setting {key!r} is not a boolean (got {type(value).__name__})"
            )
        return value

    # ── Snapshot management ──────────────────────────────────────────────

    def current(self) -> RuntimeConfig:
        """Return the current snapshot as a ``RuntimeConfig`` instance."""
        with self._lock:
            return self._config.model_copy(deep=True)

    def refresh(self, config: RuntimeConfig) -> None:
        """Atomically replace the current snapshot with *config*."""
        with self._lock:
            self._config = config.model_copy(deep=True)