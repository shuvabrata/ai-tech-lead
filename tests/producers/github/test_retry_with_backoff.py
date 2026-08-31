"""Unit tests for ``retry_with_backoff`` and its retryable-error guards.

The helper is shared by the GitHub producer (PyGithub ``rate limit`` string
messages, no ``response`` attribute) and the Jira producer (atlassian
``HTTPError`` carrying a ``response.status_code``). These tests lock in both
detection paths so neither producer silently drops data on a 429, and cover
the transient-network-error retry path added for temporary connectivity loss.
"""

from __future__ import annotations

from unittest import mock

import pytest
import requests

from connectors.producers.github.retry_with_backoff import (
    _is_network_error,
    _is_rate_limit,
    _is_retryable,
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
        response = mock.Mock()
        response.status_code = 429
        response.json.return_value = {}
        err = requests.HTTPError("", response=response)
        assert _is_rate_limit(err) is True

    def test_non_rate_limit_rejected(self):
        """404 / network errors are not treated as rate limiting."""
        response = mock.Mock()
        response.status_code = 404
        err = requests.HTTPError("not found", response=response)
        assert _is_rate_limit(err) is False
        assert _is_rate_limit(RuntimeError("connection reset")) is False


@pytest.mark.unit
class TestIsNetworkError:
    def test_connection_error(self):
        """requests ConnectionError (covers DNS NameResolutionError) is detected."""
        assert _is_network_error(requests.ConnectionError("Failed to resolve")) is True

    def test_timeout(self):
        assert _is_network_error(requests.Timeout("timed out")) is True
        assert _is_network_error(requests.ConnectTimeout("connect timed out")) is True
        assert _is_network_error(requests.ReadTimeout("read timed out")) is True

    def test_chunked_encoding_error(self):
        assert _is_network_error(requests.exceptions.ChunkedEncodingError("mid-stream")) is True

    def test_proxy_error(self):
        assert _is_network_error(requests.exceptions.ProxyError("proxy blip")) is True

    def test_urllib3_max_retry_error(self):
        import urllib3
        err = urllib3.exceptions.MaxRetryError(
            mock.Mock(), "https://api.github.com", reason=requests.ConnectionError("x")
        )
        assert _is_network_error(err) is True

    def test_socket_gaierror(self):
        import socket
        assert _is_network_error(socket.gaierror(-2, "Name or service not known")) is True

    def test_oserror_transient_errno(self):
        import errno
        assert _is_network_error(OSError(errno.ECONNRESET, "reset")) is True
        assert _is_network_error(OSError(errno.ECONNREFUSED, "refused")) is True

    def test_non_network_rejected(self):
        assert _is_network_error(ValueError("boom")) is False
        assert _is_network_error(RuntimeError("boom")) is False
        assert _is_network_error(OSError(2, "no such file")) is False


@pytest.mark.unit
class TestIsRetryable:
    def test_rate_limit_is_retryable(self):
        assert _is_retryable(_http_429()) is True

    def test_network_error_is_retryable(self):
        assert _is_retryable(requests.ConnectionError("Failed to resolve")) is True

    def test_non_retryable_rejected(self):
        assert _is_retryable(ValueError("boom")) is False
        assert _is_retryable(RuntimeError("boom")) is False


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

    def test_retries_then_recovers_on_network_error(self):
        """A transient network error fails once, then the call succeeds."""
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("Failed to resolve 'api.github.com'")
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

    def test_timeout_budget_exhausted_then_raises(self):
        """Persistent network error → raises after the time budget is exhausted."""
        def _always_network_error():
            raise requests.ConnectionError("Failed to resolve 'api.github.com'")

        # A tiny timeout forces immediate exhaustion; time.sleep is mocked so
        # the loop terminates deterministically.
        with mock.patch("time.sleep"), pytest.raises(Exception, match="Retry timeout"):
            retry_with_backoff(_always_network_error, timeout=0)

    def test_non_retryable_raises_immediately(self):
        """A non-retryable error is not retried."""
        def _boom():
            raise ValueError("boom")

        with mock.patch("time.sleep"), pytest.raises(ValueError, match="boom"):
            retry_with_backoff(_boom)


def _http_429():
    """Return an atlassian-style HTTPError carrying a 429 response."""
    response = mock.Mock()
    response.status_code = 429
    response.json.return_value = {"errorMessages": ["Too many requests"]}
    return requests.HTTPError("Too many requests", response=response)