"""Unit tests for the shared RuntimeConfig model and RuntimeConfigCache.

These tests validate defaults, field bounds, timezone validation, type
enforcement on the cache accessors, and atomic snapshot replacement — all
without a DB connection or importing ``src.app``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.runtime_settings.cache import RuntimeConfigCache
from common.runtime_settings.config import RuntimeConfig


class TestRuntimeConfigDefaults:
    """Default values match the current ``Settings`` defaults."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "field,expected",
        [
            ("HTTP_REQUEST_TIMEOUT", 60),
            ("NEO4J_QUERY_TIMEOUT", 10),
            ("GRAPH_UI_MAX_NODES_TO_EXPAND", 20),
            ("GRAPH_UI_MAX_NODE_LABEL_CHARS", 10),
            ("CONNECTOR_SCAN_POLL_INTERVAL", 5000),
            ("RECENT_ACTIONS_LIMIT", 5),
            ("RETRY_BUDGET_SECONDS", 3600),
            ("RETRY_BACKOFF_CAP_SECONDS", 30),
            ("RETRY_BASE_DELAY_SECONDS", 1),
            ("TIMEZONE", "UTC"),
            ("UI_DATETIME_FORMAT", "%b %d, %Y %I:%M %p"),
            ("UI_DATE_FORMAT", "%b %d, %Y"),
            ("AUGMENTATION_HISTORY_TURNS", 5),
            ("ES_CHAIN_MAX_RESULTS", 5),
            ("MAX_MCP_ITERATIONS", 3),
            ("FF_NEO4J_USE_PROVIDER_PIPELINE", False),
            # ── AI / LLM ──────────────────────────────────────────────
            ("LLM_PROVIDER", "openai"),
            ("LLM_MODEL", "gpt-5"),
            ("MAX_TOKENS", 16000),
            ("GITHUB_MCP_ENABLED", False),
            ("ATLASSIAN_MCP_ENABLED", False),
            # ── System ────────────────────────────────────────────────
            ("NEO4J_ENABLED", False),
            # ── Connectors ────────────────────────────────────────────
            ("COMMIT_DAYS_LIMIT", 60),
            ("PULL_REQUEST_DAYS_LIMIT", 60),
            ("ISSUE_DAYS_LIMIT", 60),
            ("IDENTITY_REFRESH_DAYS", 7),
            ("MAX_TEAM_SIZE", 100),
            ("JIRA_LOOKBACK_DAYS", 90),
            ("JIRA_MAX_RESULTS_PER_PAGE", 100),
            ("CONFLUENCE_LOOKBACK_DAYS", 60),
            ("JIRA_EPIC_TEAM_FIELD", "Team"),
            ("JIRA_ISSUE_TEAM_FIELD", "Team"),
            ("JIRA_EPIC_START_DATE_FIELD", "created"),
            ("JIRA_EPIC_DUE_DATE_FIELD", "duedate"),
            ("API_SERVER", "http://app:8000/"),
            ("CONFIGURATION_SOURCE", "SERVER"),
            # ── Logging ───────────────────────────────────────────────
            ("LOG_LEVEL", "INFO"),
            ("LOG_FORMAT", "JSON"),
            ("ENABLE_FILE_LOGGING", False),
            ("LOG_DIR", "logs"),
            ("LOG_SIGNAL_DUMPS", False),
        ],
    )
    def test_default_value(self, field: str, expected: object) -> None:
        """Each field has the expected default value."""
        config = RuntimeConfig()
        assert getattr(config, field) == expected

    @pytest.mark.unit
    def test_all_fields_present(self) -> None:
        """The model exposes the expected number of runtime-configurable fields."""
        assert len(RuntimeConfig.model_fields) == 41


class TestRuntimeConfigValidation:
    """Bounds and type validation."""

    @pytest.mark.unit
    @pytest.mark.parametrize("bad", [0, -1, 51, 100])
    def test_recent_actions_limit_rejects_out_of_range(self, bad: int) -> None:
        """RECENT_ACTIONS_LIMIT must be between 1 and 50."""
        with pytest.raises(ValidationError):
            RuntimeConfig(RECENT_ACTIONS_LIMIT=bad)

    @pytest.mark.unit
    @pytest.mark.parametrize("good", [1, 25, 50])
    def test_recent_actions_limit_accepts_valid(self, good: int) -> None:
        """RECENT_ACTIONS_LIMIT accepts 1..50 inclusive."""
        assert RuntimeConfig(RECENT_ACTIONS_LIMIT=good).RECENT_ACTIONS_LIMIT == good

    @pytest.mark.unit
    @pytest.mark.parametrize("bad", [0, -5])
    def test_neo4j_query_timeout_rejects_lt_one(self, bad: int) -> None:
        """NEO4J_QUERY_TIMEOUT must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(NEO4J_QUERY_TIMEOUT=bad)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "field",
        ["RETRY_BUDGET_SECONDS", "RETRY_BACKOFF_CAP_SECONDS", "RETRY_BASE_DELAY_SECONDS"],
    )
    @pytest.mark.parametrize("bad", [0, -1])
    def test_retry_settings_reject_lt_one(self, field: str, bad: int) -> None:
        """Retry settings must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(**{field: bad})

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "field,good",
        [
            ("RETRY_BUDGET_SECONDS", 3600),
            ("RETRY_BACKOFF_CAP_SECONDS", 30),
            ("RETRY_BASE_DELAY_SECONDS", 1),
        ],
    )
    def test_retry_settings_accept_valid(self, field: str, good: int) -> None:
        """Retry settings accept valid positive integers."""
        assert getattr(RuntimeConfig(**{field: good}), field) == good

    @pytest.mark.unit
    @pytest.mark.parametrize("bad", ["Not/AZone", "", "UTC/Something"])
    def test_timezone_rejects_invalid(self, bad: str) -> None:
        """TIMEZONE must be a valid IANA zone name."""
        with pytest.raises(ValidationError):
            RuntimeConfig(TIMEZONE=bad)

    @pytest.mark.unit
    def test_timezone_accepts_valid(self) -> None:
        """TIMEZONE accepts a valid IANA zone name."""
        assert RuntimeConfig(TIMEZONE="America/New_York").TIMEZONE == "America/New_York"

    @pytest.mark.unit
    def test_flag_accepts_only_bool_true(self) -> None:
        """FF_NEO4J_USE_PROVIDER_PIPELINE accepts ``True``."""
        config = RuntimeConfig(FF_NEO4J_USE_PROVIDER_PIPELINE=True)
        assert config.FF_NEO4J_USE_PROVIDER_PIPELINE is True

    @pytest.mark.unit
    def test_flag_accepts_only_bool_false(self) -> None:
        """FF_NEO4J_USE_PROVIDER_PIPELINE accepts ``False``."""
        config = RuntimeConfig(FF_NEO4J_USE_PROVIDER_PIPELINE=False)
        assert config.FF_NEO4J_USE_PROVIDER_PIPELINE is False

    @pytest.mark.unit
    def test_flag_rejects_non_bool(self) -> None:
        """FF_NEO4J_USE_PROVIDER_PIPELINE rejects non-boolean values."""
        with pytest.raises(ValidationError):
            RuntimeConfig(FF_NEO4J_USE_PROVIDER_PIPELINE="yes")  # type: ignore[arg-type]

    # ── New field validation tests ───────────────────────────────────────

    @pytest.mark.unit
    @pytest.mark.parametrize("bad", [0, -1, 999])
    def test_max_tokens_rejects_out_of_range(self, bad: int) -> None:
        """MAX_TOKENS must be >= 1000."""
        with pytest.raises(ValidationError):
            RuntimeConfig(MAX_TOKENS=bad)

    @pytest.mark.unit
    @pytest.mark.parametrize("good", [1000, 16000, 128000])
    def test_max_tokens_accepts_valid(self, good: int) -> None:
        """MAX_TOKENS accepts values >= 1000."""
        assert RuntimeConfig(MAX_TOKENS=good).MAX_TOKENS == good

    @pytest.mark.unit
    @pytest.mark.parametrize("bad", [0, -1, 501, 1000])
    def test_jira_max_results_rejects_out_of_range(self, bad: int) -> None:
        """JIRA_MAX_RESULTS_PER_PAGE must be between 1 and 500."""
        with pytest.raises(ValidationError):
            RuntimeConfig(JIRA_MAX_RESULTS_PER_PAGE=bad)

    @pytest.mark.unit
    @pytest.mark.parametrize("good", [1, 100, 500])
    def test_jira_max_results_accepts_valid(self, good: int) -> None:
        """JIRA_MAX_RESULTS_PER_PAGE accepts 1..500 inclusive."""
        assert RuntimeConfig(JIRA_MAX_RESULTS_PER_PAGE=good).JIRA_MAX_RESULTS_PER_PAGE == good

    @pytest.mark.unit
    def test_commit_days_limit_rejects_lt_one(self) -> None:
        """COMMIT_DAYS_LIMIT must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(COMMIT_DAYS_LIMIT=0)

    @pytest.mark.unit
    def test_pull_request_days_limit_rejects_lt_one(self) -> None:
        """PULL_REQUEST_DAYS_LIMIT must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(PULL_REQUEST_DAYS_LIMIT=0)

    @pytest.mark.unit
    def test_max_team_size_rejects_lt_one(self) -> None:
        """MAX_TEAM_SIZE must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(MAX_TEAM_SIZE=0)

    @pytest.mark.unit
    def test_jira_lookback_days_rejects_lt_one(self) -> None:
        """JIRA_LOOKBACK_DAYS must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(JIRA_LOOKBACK_DAYS=0)

    @pytest.mark.unit
    def test_confluence_lookback_days_rejects_lt_one(self) -> None:
        """CONFLUENCE_LOOKBACK_DAYS must be >= 1."""
        with pytest.raises(ValidationError):
            RuntimeConfig(CONFLUENCE_LOOKBACK_DAYS=0)

    @pytest.mark.unit
    def test_identity_refresh_days_accepts_zero(self) -> None:
        """IDENTITY_REFRESH_DAYS accepts 0 (disabled)."""
        assert RuntimeConfig(IDENTITY_REFRESH_DAYS=0).IDENTITY_REFRESH_DAYS == 0


class TestRuntimeConfigCache:
    """Cache accessor behavior and snapshot replacement."""

    @pytest.mark.unit
    def test_returns_defaults_before_refresh(self) -> None:
        """Cache returns defaults before any refresh call."""
        cache = RuntimeConfigCache()
        assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 60
        assert cache.get_int("RECENT_ACTIONS_LIMIT") == 5
        assert cache.get_bool("FF_NEO4J_USE_PROVIDER_PIPELINE") is False
        assert cache.get("TIMEZONE") == "UTC"

    @pytest.mark.unit
    def test_refresh_replaces_snapshot(self) -> None:
        """refresh() atomically replaces the current snapshot."""
        cache = RuntimeConfigCache()
        cache.refresh(RuntimeConfig(HTTP_REQUEST_TIMEOUT=90, TIMEZONE="Asia/Kolkata"))
        assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 90
        assert cache.get("TIMEZONE") == "Asia/Kolkata"
        # Unset fields keep their defaults.
        assert cache.get_int("RECENT_ACTIONS_LIMIT") == 5

    @pytest.mark.unit
    def test_current_returns_deep_copy(self) -> None:
        """current() returns a copy that cannot mutate the cache."""
        cache = RuntimeConfigCache()
        snapshot = cache.current()
        snapshot.HTTP_REQUEST_TIMEOUT = 999
        assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 60

    @pytest.mark.unit
    def test_get_int_rejects_bool(self) -> None:
        """get_int() raises TypeError for boolean fields."""
        cache = RuntimeConfigCache()
        with pytest.raises(TypeError):
            cache.get_int("FF_NEO4J_USE_PROVIDER_PIPELINE")

    @pytest.mark.unit
    def test_get_bool_rejects_non_bool(self) -> None:
        """get_bool() raises TypeError for non-boolean fields."""
        cache = RuntimeConfigCache()
        with pytest.raises(TypeError):
            cache.get_bool("HTTP_REQUEST_TIMEOUT")

    @pytest.mark.unit
    def test_get_unknown_key_raises_attribute(self) -> None:
        """get() on an unknown key raises AttributeError."""
        cache = RuntimeConfigCache()
        with pytest.raises(AttributeError):
            cache.get("NOT_A_REAL_KEY")

    @pytest.mark.unit
    def test_refresh_after_prior_refresh(self) -> None:
        """A second refresh replaces the previous snapshot entirely."""
        cache = RuntimeConfigCache()
        cache.refresh(RuntimeConfig(HTTP_REQUEST_TIMEOUT=90))
        assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 90
        cache.refresh(RuntimeConfig(HTTP_REQUEST_TIMEOUT=120))
        assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 120