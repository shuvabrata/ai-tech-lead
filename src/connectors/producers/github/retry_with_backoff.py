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
DEFAULT_TIMEOUT = 3600  # total budget in seconds (1 hour)
DEFAULT_MAX_DELAY = 30  # per-sleep cap in seconds
DEFAULT_INITIAL_DELAY = 1

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
    timeout: int = DEFAULT_TIMEOUT,
    max_delay: int = DEFAULT_MAX_DELAY,
    initial_delay: int = DEFAULT_INITIAL_DELAY,
) -> T:
    """
    Retry a function with exponential backoff for transient failures.

    Retries rate-limit (HTTP 429) and transient network errors (DNS, connection
    reset/refused, timeout) until a total time budget (``timeout``) is
    exhausted. Backoff doubles each attempt, capped at ``max_delay`` seconds,
    and never sleeps past the deadline.

    Args:
        func: Function to execute (should be a lambda or callable).
        timeout: Total retry budget in seconds. Defaults to 1 hour.
        max_delay: Maximum per-sleep delay in seconds.
        initial_delay: Initial delay in seconds (doubles each retry).

    Returns:
        Result of the function call.

    Raises:
        Exception: If the retry budget is exhausted or a non-retryable error
            occurs.
    """
    deadline = time.time() + timeout
    delay = initial_delay
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
                raise Exception(f"Retry timeout ({timeout}s) exceeded: {str(e)}") from e

            sleep_for = min(delay, max_delay, remaining)
            logger.info(
                "Retryable error. Retrying in %.0fs... (attempt %d): %s",
                sleep_for,
                attempt,
                e,
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)