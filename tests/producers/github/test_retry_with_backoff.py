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
    WbaRetryTimeoutError,
    _ensure_retry_settings,
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

    def test_exhausts_timeout_then_raises(self):
        """Persistent 429 → raises WbaRetryTimeoutError after the budget."""
        def _always_429():
            raise _http_429()

        with mock.patch("time.sleep"), pytest.raises(WbaRetryTimeoutError):
            retry_with_backoff(_always_429, retry_budget=0)

    def test_timeout_budget_exhausted_then_raises(self):
        """Persistent network error → raises WbaRetryTimeoutError."""
        def _always_network_error():
            raise requests.ConnectionError("Failed to resolve 'api.github.com'")

        # A tiny timeout forces immediate exhaustion; time.sleep is mocked so
        # the loop terminates deterministically.
        with mock.patch("time.sleep"), pytest.raises(WbaRetryTimeoutError):
            retry_with_backoff(_always_network_error, retry_budget=0)

    def test_timeout_error_carries_original_and_timeout(self):
        """WbaRetryTimeoutError exposes the timeout and original exception."""
        original = requests.ConnectionError("Failed to resolve 'api.github.com'")

        def _always_network_error():
            raise original

        with mock.patch("time.sleep"):
            with pytest.raises(WbaRetryTimeoutError) as exc_info:
                retry_with_backoff(_always_network_error, retry_budget=0)

        assert exc_info.value.timeout == 0
        assert exc_info.value.original is original
        assert "Retry timeout" in str(exc_info.value)

    def test_non_retryable_raises_immediately(self):
        """A non-retryable error is not retried."""
        def _boom():
            raise ValueError("boom")

        with mock.patch("time.sleep"), pytest.raises(ValueError, match="boom"):
            retry_with_backoff(_boom)


@pytest.mark.unit
class TestRetrySettingsResolution:
    """Retry settings are resolved once per process and cached in globals."""

    def _reset_globals(self):
        """Reset the module-level cached settings to their unset state."""
        import connectors.producers.github.retry_with_backoff as mod
        mod._retry_budget = None
        mod._backoff_cap = None
        mod._base_delay = None

    def test_reads_from_runtime_cache_once(self):
        """Values are read from the runtime cache and cached in globals."""
        import connectors.producers.github.retry_with_backoff as mod
        self._reset_globals()
        with mock.patch(
            "connectors.producers.daemon_common.runtime_cache"
        ) as mock_cache:
            mock_cache.get_int.side_effect = [3600, 30, 1]
            _ensure_retry_settings()
            # Second call must not re-read the cache.
            _ensure_retry_settings()
            assert mock_cache.get_int.call_count == 3
        assert mod._retry_budget == 3600
        assert mod._backoff_cap == 30
        assert mod._base_delay == 1

    def test_default_when_cache_unavailable(self):
        """If the runtime cache read fails, the code defaults are used."""
        import connectors.producers.github.retry_with_backoff as mod
        self._reset_globals()
        with mock.patch(
            "connectors.producers.daemon_common.runtime_cache"
        ) as mock_cache:
            mock_cache.get_int.side_effect = RuntimeError("cache unavailable")
            _ensure_retry_settings()
        assert mod._retry_budget == 3600
        assert mod._backoff_cap == 30
        assert mod._base_delay == 1

    def test_retry_with_backoff_uses_cached_values(self):
        """retry_with_backoff resolves once and reuses the cached values."""
        self._reset_globals()
        with mock.patch(
            "connectors.producers.daemon_common.runtime_cache"
        ) as mock_cache:
            mock_cache.get_int.side_effect = [3600, 30, 1]
            with mock.patch("time.sleep"):
                assert retry_with_backoff(lambda: 42) == 42
                assert retry_with_backoff(lambda: 43) == 43
            # Only one resolution for both calls.
            assert mock_cache.get_int.call_count == 3


def _http_429():
    """Return an atlassian-style HTTPError carrying a 429 response."""
    response = mock.Mock()
    response.status_code = 429
    response.json.return_value = {"errorMessages": ["Too many requests"]}
    return requests.HTTPError("Too many requests", response=response)