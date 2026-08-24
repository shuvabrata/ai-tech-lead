"""Unit tests for ``retry_with_backoff`` and its ``_is_rate_limit`` guard.

The helper is shared by the GitHub producer (PyGithub ``rate limit`` string
messages, no ``response`` attribute) and the Jira producer (atlassian
``HTTPError`` carrying a ``response.status_code``). These tests lock in both
detection paths so neither producer silently drops data on a 429.
"""

from __future__ import annotations

from unittest import mock

import pytest

from connectors.producers.github.retry_with_backoff import (
    _is_rate_limit,
    retry_with_backoff,
)


@pytest.mark.unit
class TestIsRateLimit:
    def test_github_rate_limit_string(self):
        """PyGithub-style message (no response attr) is detected."""
        err = Exception("API rate limit exceeded for user")
        assert _is_rate_limit(err) is True

    def test_jira_status_429_generic_body(self):
        """Atlassian-style 429 with a generic body is detected via status."""
        err = _http_429()
        assert _is_rate_limit(err) is True

    def test_jira_status_429_without_rate_limit_words(self):
        """A bare HTTPError with response.status_code=429 is still detected."""
        import requests
        response = mock.Mock()
        response.status_code = 429
        response.json.return_value = {}
        err = requests.HTTPError("", response=response)
        assert _is_rate_limit(err) is True

    def test_non_rate_limit_rejected(self):
        """404 / network errors are not treated as rate limiting."""
        import requests
        response = mock.Mock()
        response.status_code = 404
        err = requests.HTTPError("not found", response=response)
        assert _is_rate_limit(err) is False
        assert _is_rate_limit(RuntimeError("connection reset")) is False


@pytest.mark.unit
class TestRetryWithBackoffBehavior:
    def test_succeeds_immediately(self):
        assert retry_with_backoff(lambda: 42) == 42

    def test_retries_then_recovers_on_429(self):
        """A 429 fails once, then the call succeeds on retry."""
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_429()
            return "ok"

        with mock.patch("time.sleep"):
            assert retry_with_backoff(_flaky) == "ok"
        assert calls["n"] == 2

    def test_exhausts_retries_then_raises(self):
        """Persistent 429 → raises after max_retries."""
        def _always_429():
            raise _http_429()

        with mock.patch("time.sleep"), pytest.raises(Exception, match="Max retries"):
            retry_with_backoff(_always_429, max_retries=3)

    def test_non_rate_limit_raises_immediately(self):
        """A non-rate-limit error is not retried."""
        def _boom():
            raise ValueError("boom")

        with mock.patch("time.sleep"), pytest.raises(ValueError, match="boom"):
            retry_with_backoff(_boom)


def _http_429():
    """Return an atlassian-style HTTPError carrying a 429 response."""
    import requests
    response = mock.Mock()
    response.status_code = 429
    response.json.return_value = {"errorMessages": ["Too many requests"]}
    return requests.HTTPError("Too many requests", response=response)