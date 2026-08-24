import time
from typing import Callable, TypeVar
from common.logger import logger

T = TypeVar('T')


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


def retry_with_backoff(func: Callable[[], T], max_retries: int = 5, initial_delay: int = 1) -> T:
    """
    Retry a function with exponential backoff for rate limiting.

    Args:
        func: Function to execute (should be a lambda or callable)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        Result of the function call

    Raises:
        Exception: If all retries are exhausted
    """
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if _is_rate_limit(e):
                if attempt < max_retries - 1:
                    logger.info(f"      Rate limit hit. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    raise Exception(f"Max retries exceeded due to rate limiting: {str(e)}") from e
            else:
                # Not a rate limit error, raise immediately
                raise

    raise Exception(f"Failed after {max_retries} attempts")