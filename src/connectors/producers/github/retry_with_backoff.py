import errno
import socket
import time
from typing import Callable, TypeVar

import requests
import urllib3

from common.logger import logger

T = TypeVar('T')

# Default retry budget: a background scan can tolerate up to an hour of
# intermittent connectivity before giving up on a single call.
#
# These are the ultimate fallback defaults, used only when the runtime
# settings cache is unavailable (e.g. standalone CLI/test).  In a normal scan
# the effective values come from the shared ``daemon_common.runtime_cache``
# (populated from the app API snapshot, which resolves DB override → env →
# code default).
DEFAULT_RETRY_BUDGET = 3600  # total budget in seconds (1 hour)
DEFAULT_BACKOFF_CAP = 30     # per-sleep cap in seconds
DEFAULT_BASE_DELAY = 1       # initial delay in seconds (doubles each retry)

# Resolved retry settings, cached once per process.  A scan runs in a fresh
# process spawned by the daemon, so the settings cannot change mid-scan —
# resolving them once (lazily on first use) and reusing them for every API
# call avoids re-reading the runtime cache on each call.
# pylint: disable=invalid-name  # mutable caches, not constants
_retry_budget: int | None = None
_backoff_cap: int | None = None
_base_delay: int | None = None
# pylint: enable=invalid-name


def _ensure_retry_settings() -> None:
    """Resolve the three retry settings once per process and cache them.

    The runtime settings cache (``daemon_common.runtime_cache``) is the single
    read boundary for runtime-configurable settings.  It is populated from the
    app API snapshot, which already resolves the canonical precedence
    (DB override → env → code default), so no env-var or default handling is
    repeated here.

    Resolution is lazy (on first use) rather than at import time so the daemon
    has refreshed the cache at scan startup before we read it.
    ``daemon_common`` is imported lazily to keep this low-level utility usable
    standalone (e.g. in tests).
    """
    global _retry_budget, _backoff_cap, _base_delay  # noqa: PLW0603
    if _retry_budget is not None:
        return
    try:
        # pylint: disable=import-outside-toplevel
        from connectors.producers.daemon_common import runtime_cache
        _retry_budget = int(runtime_cache.get_int("RETRY_BUDGET_SECONDS"))
        _backoff_cap = int(runtime_cache.get_int("RETRY_BACKOFF_CAP_SECONDS"))
        _base_delay = int(runtime_cache.get_int("RETRY_BASE_DELAY_SECONDS"))
    except Exception:  # pylint: disable=broad-except
        # Cache unavailable (e.g. standalone CLI/test) — fall back to defaults.
        _retry_budget = DEFAULT_RETRY_BUDGET
        _backoff_cap = DEFAULT_BACKOFF_CAP
        _base_delay = DEFAULT_BASE_DELAY

    logger.info("Resolved retry settings: budget=%s, backoff_cap=%s, base_delay=%s", _retry_budget, _backoff_cap, _base_delay)
    


class WbaRetryTimeoutError(Exception):
    """Raised when ``retry_with_backoff`` exhausts its time budget.

    This is a distinct, catchable signal so producers can distinguish a
    transient-but-persistent connectivity failure (which should be retried on
    the next scan without advancing the sync cursor) from a non-retryable API
    error (e.g. 404/403).

    Attributes:
        timeout: The total retry budget in seconds that was exhausted.
        original: The last underlying exception that triggered the retries.
    """

    def __init__(self, timeout: int, original: Exception) -> None:
        self.timeout = timeout
        self.original = original
        super().__init__(f"Retry timeout ({timeout}s) exceeded: {original}")

# Raw socket errno values that indicate a transient network failure.
_NETWORK_ERRNOS = {
    errno.ECONNRESET,
    errno.ECONNREFUSED,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    errno.ETIMEDOUT,
}


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if *exc* represents a rate-limit (HTTP 429) failure.

    Two signals are checked so the helper works across the two API clients in
    this project:

    - ``e.response.status_code == 429`` — the ``atlassian`` Jira client raises
      ``requests.HTTPError`` carrying the response on the instance. Jira 429
      bodies are not guaranteed to contain the words "rate limit", so the
      status code is the only reliable signal there.
    - A substring match on the message — the PyGithub ``GithubException`` used
      by the GitHub producer has no ``response`` attribute and its message is
      always "API rate limit exceeded ...".

    Non-rate-limit errors (e.g. 404, 400, network) fall through and are
    re-raised immediately.
    """
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    error_str = str(exc).lower()
    return "rate limit" in error_str or "api rate limit exceeded" in error_str


def _is_network_error(exc: Exception) -> bool:
    """Return True if *exc* represents a transient network failure.

    These are the errors raised when the network drops mid-request (DNS
    resolution failure, connection reset/refused, timeout, proxy blip, or a
    mid-stream disconnect). They are recoverable once connectivity returns, so
    they should be retried rather than treated as fatal.

    Detection is type-based (``isinstance``) against the ``requests`` /
    ``urllib3`` / ``socket`` exception classes, which is more robust than
    string matching. A raw ``OSError`` with a transient ``errno`` is also
    treated as a network error.
    """
    if isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ProxyError,
            urllib3.exceptions.MaxRetryError,
            socket.gaierror,
        ),
    ):
        return True
    return isinstance(exc, OSError) and exc.errno in _NETWORK_ERRNOS


def _is_retryable(exc: Exception) -> bool:
    """Return True if *exc* is a transient, retryable failure.

    Combines two signals:

    1. Rate-limit (HTTP 429) — via status code or message substring.
    2. Transient network errors — via ``isinstance`` checks against the
       ``requests`` / ``urllib3`` / ``socket`` exception classes.

    Non-retryable errors (e.g. 404, 400, 403, deterministic 5xx) fall through
    and are re-raised immediately.
    """
    return _is_rate_limit(exc) or _is_network_error(exc)


def retry_with_backoff(
    func: Callable[[], T],
    retry_budget: int | None = None,
    backoff_cap: int | None = None,
    base_delay: int | None = None,
) -> T:
    """
    Retry a function with exponential backoff for transient failures.

    Retries rate-limit (HTTP 429) and transient network errors (DNS, connection
    reset/refused, timeout) until a total time budget (``retry_budget``) is
    exhausted. Backoff doubles each attempt, capped at ``backoff_cap`` seconds,
    and never sleeps past the deadline.

    When an argument is ``None`` (the default), the effective value is read
    from the shared runtime settings cache.  The values are resolved once per
    process (a scan runs in a fresh process, so they cannot change mid-scan)
    and reused for every API call.  This lets the values be configured
    dynamically via the runtime settings system without changing call sites.

    Args:
        func: Function to execute (should be a lambda or callable).
        retry_budget: Total retry budget in seconds. Defaults to the resolved
            ``RETRY_BUDGET_SECONDS`` (1 hour).
        backoff_cap: Maximum per-sleep delay in seconds. Defaults to the
            resolved ``RETRY_BACKOFF_CAP_SECONDS`` (30s).
        base_delay: Initial delay in seconds (doubles each retry). Defaults to
            the resolved ``RETRY_BASE_DELAY_SECONDS`` (1s).

    Returns:
        Result of the function call.

    Raises:
        WbaRetryTimeoutError: If the retry budget is exhausted.
        Exception: If a non-retryable error occurs (re-raised as-is).
    """
    if retry_budget is None or backoff_cap is None or base_delay is None:
        _ensure_retry_settings()
        assert _retry_budget is not None
        assert _backoff_cap is not None
        assert _base_delay is not None
        if retry_budget is None:
            retry_budget = _retry_budget
        if backoff_cap is None:
            backoff_cap = _backoff_cap
        if base_delay is None:
            base_delay = _base_delay

    deadline = time.time() + retry_budget
    delay = base_delay
    attempt = 0

    while True:
        try:
            return func()
        except Exception as e:
            if not _is_retryable(e):
                raise

            attempt += 1
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.warning(
                    "Retry budget exhausted after %d attempts and %.0fs: %s Raising WbaRetryTimeoutError.",
                    attempt,
                    retry_budget,
                    e,
                )
                raise WbaRetryTimeoutError(retry_budget, e) from e

            sleep_for = min(delay, backoff_cap, remaining)
            logger.info(
                "Retryable error. Retrying in %.0fs... (attempt %d): %s. Time remaining: %.0fs",
                sleep_for,
                attempt,
                e,
                remaining
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, backoff_cap)