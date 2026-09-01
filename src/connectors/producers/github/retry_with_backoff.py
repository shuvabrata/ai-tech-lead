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
DEFAULT_RETRY_BUDGET = 3600  # total budget in seconds (1 hour)
DEFAULT_BACKOFF_CAP = 30     # per-sleep cap in seconds
DEFAULT_BASE_DELAY = 1       # initial delay in seconds (doubles each retry)


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
    retry_budget: int = DEFAULT_RETRY_BUDGET,
    backoff_cap: int = DEFAULT_BACKOFF_CAP,
    base_delay: int = DEFAULT_BASE_DELAY,
) -> T:
    """
    Retry a function with exponential backoff for transient failures.

    Retries rate-limit (HTTP 429) and transient network errors (DNS, connection
    reset/refused, timeout) until a total time budget (``retry_budget``) is
    exhausted. Backoff doubles each attempt, capped at ``backoff_cap`` seconds,
    and never sleeps past the deadline.

    Args:
        func: Function to execute (should be a lambda or callable).
        retry_budget: Total retry budget in seconds. Defaults to 1 hour.
        backoff_cap: Maximum per-sleep delay in seconds.
        base_delay: Initial delay in seconds (doubles each retry).

    Returns:
        Result of the function call.

    Raises:
        WbaRetryTimeoutError: If the retry budget is exhausted.
        Exception: If a non-retryable error occurs (re-raised as-is).
    """
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