
import time
from typing import Callable, TypeVar, Any
from common.logger import logger

T = TypeVar('T')

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
            error_str = str(e).lower()
            # Check if it's a rate limit error
            if 'rate limit' in error_str or 'api rate limit exceeded' in error_str:
                if attempt < max_retries - 1:
                    logger.info(f"      Rate limit hit. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    raise Exception(f"Max retries exceeded due to rate limiting: {str(e)}")
            else:
                # Not a rate limit error, raise immediately
                raise

    raise Exception(f"Failed after {max_retries} attempts")