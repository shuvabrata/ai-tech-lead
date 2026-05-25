"""Unit tests for the Elasticsearch augmentation chain.

Tests cover:
- _format_history: correct formatting and empty-history handling
- check_es_relevance: YES/NO gate for search vs. traversal questions
- generate_search_request: valid JSON, {"relevant": false}, malformed JSON,
  schema validation failure, markdown-fenced output, no raw-query fallback
- _format_results: truncation, highlight stripping, empty response
- augment_message_with_es_stream: full flow, each failure path
"""

from __future__ import annotations

import pytest

from app.ai_agent.chains.elasticsearch_chain import (
    _format_history,
    _format_results,
    _truncate_attribute,
    _strip_em_tags,
    check_es_relevance,
    generate_search_request,
)
from app.api.search.v1.model import SearchRequest, SearchResponse, SearchResult
from app.settings import settings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _format_history
# ---------------------------------------------------------------------------

class TestFormatHistory:
    def test_returns_empty_string_for_none(self):
        assert _format_history(None) == ""

    def test_returns_empty_string_for_empty_list(self):
        assert _format_history([]) == ""

    def test_formats_single_turn(self):
        history = [
            {"role": "user", "content": "Tell me about Alice"},
            {"role": "assistant", "content": "Alice is a developer."},
        ]
        result = _format_history(history)
        assert "User: Tell me about Alice" in result
        assert "Assistant: Alice is a developer." in result
        assert "## Conversation History" in result

    def test_respects_max_turns(self):
        history = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "reply3"},
        ]
        result = _format_history(history, max_turns=1)
        # Only the last 1 turn (2 messages) should appear
        assert "msg3" in result
        assert "reply3" in result
        assert "msg1" not in result
        assert "msg2" not in result

    def test_ends_with_newline(self):
        history = [{"role": "user", "content": "hello"}]
        result = _format_history(history)
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# _truncate_attribute
# ---------------------------------------------------------------------------

class TestTruncateAttribute:
    def test_short_string_unchanged(self):
        assert _truncate_attribute("short") == "short"

    def test_long_string_truncated(self):
        long_val = "x" * 300
        result = _truncate_attribute(long_val)
        assert len(result) <= 201  # 200 chars + ellipsis char
        assert result.endswith("\u2026")

    def test_non_string_converted(self):
        assert _truncate_attribute(42) == "42"
        assert _truncate_attribute(3.14) == "3.14"


# ---------------------------------------------------------------------------
# _strip_em_tags
# ---------------------------------------------------------------------------

class TestStripEmTags:
    def test_removes_open_and_close_em_tags(self):
        assert _strip_em_tags("<em>hello</em> world") == "hello world"

    def test_no_tags_unchanged(self):
        assert _strip_em_tags("plain text") == "plain text"

    def test_multiple_em_tags(self):
        assert _strip_em_tags("<em>a</em> and <em>b</em>") == "a and b"


# ---------------------------------------------------------------------------
# _format_results
# ---------------------------------------------------------------------------

class TestFormatResults:
    def _make_result(self, wba_id: str, highlight: str | None = None, **attrs) -> SearchResult:
        return SearchResult(
            wba_id=wba_id,
            highlight=highlight,
            attributes=attrs if attrs else None,
        )

    def test_empty_response_returns_empty_string(self):
        empty = SearchResponse(total=0, page=1, page_size=5, results=[])
        assert _format_results(empty) == ""

    def test_header_contains_total_and_count(self):
        result = self._make_result("jira::Issue::PROJ-1", summary="Bug fix")
        response = SearchResponse(total=47, page=1, page_size=5, results=[result])
        output = _format_results(response)
        assert "Total matches: 47 (showing top 1)" in output

    def test_parses_entity_type_and_source_from_wba_id(self):
        result = self._make_result("github::PullRequest::123")
        response = SearchResponse(total=1, page=1, page_size=5, results=[result])
        output = _format_results(response)
        assert "Type: PullRequest | Source: github" in output

    def test_highlight_em_tags_stripped(self):
        result = self._make_result(
            "jira::Issue::PROJ-1",
            highlight="Fix <em>login</em> bug",
        )
        response = SearchResponse(total=1, page=1, page_size=5, results=[result])
        output = _format_results(response)
        assert "Fix login bug" in output
        assert "<em>" not in output

    def test_long_attribute_truncated(self):
        long_desc = "x" * 300
        result = self._make_result("jira::Issue::PROJ-1", description=long_desc)
        response = SearchResponse(total=1, page=1, page_size=5, results=[result])
        output = _format_results(response)
        assert "\u2026" in output

    def test_short_attribute_not_truncated(self):
        result = self._make_result("jira::Issue::PROJ-1", status="In Progress")
        response = SearchResponse(total=1, page=1, page_size=5, results=[result])
        output = _format_results(response)
        assert "status: In Progress" in output

    def test_none_attribute_values_excluded(self):
        result = self._make_result("jira::Issue::PROJ-1", status=None, summary="Bug fix")
        response = SearchResponse(total=1, page=1, page_size=5, results=[result])
        output = _format_results(response)
        # None values should not appear as "status: None"
        assert "status: None" not in output
        assert "summary: Bug fix" in output

    def test_multiple_results_numbered(self):
        results = [
            self._make_result("jira::Issue::PROJ-1"),
            self._make_result("jira::Issue::PROJ-2"),
        ]
        response = SearchResponse(total=2, page=1, page_size=5, results=results)
        output = _format_results(response)
        assert "### 1." in output
        assert "### 2." in output


# ---------------------------------------------------------------------------
# check_es_relevance
# ---------------------------------------------------------------------------

class _MockProvider:
    """Minimal mock LLM provider for unit tests."""
    def __init__(self, response: str):
        self._response = response
        self.last_messages: list = []

    def chat_completion(self, messages: list) -> str:
        self.last_messages = messages
        return self._response

    def chat_completion_with_tools(self, **_kwargs):
        raise NotImplementedError


class TestCheckEsRelevance:
    def test_returns_true_for_yes_response(self):
        provider = _MockProvider("YES")
        assert check_es_relevance("Find all high priority bugs", provider) is True

    def test_returns_true_for_yes_with_trailing_text(self):
        provider = _MockProvider("YES, this is relevant")
        assert check_es_relevance("Find issues", provider) is True

    def test_returns_false_for_no_response(self):
        provider = _MockProvider("NO")
        assert check_es_relevance("Who reviewed Alice's PRs?", provider) is False

    def test_returns_false_on_exception(self):
        class _FailProvider:
            def chat_completion(self, _messages):
                raise RuntimeError("LLM is down")
        assert check_es_relevance("find bugs", _FailProvider()) is False

    def test_history_included_in_prompt(self):
        provider = _MockProvider("YES")
        history = [
            {"role": "user", "content": "Tell me about Alice"},
            {"role": "assistant", "content": "Alice is a developer."},
        ]
        check_es_relevance("What issues is she assigned to?", provider, history)
        prompt_text = provider.last_messages[0]["content"]
        assert "Tell me about Alice" in prompt_text
        assert "Alice is a developer." in prompt_text

    def test_no_history_no_history_block(self):
        provider = _MockProvider("NO")
        check_es_relevance("hello", provider, None)
        prompt_text = provider.last_messages[0]["content"]
        assert "Conversation History" not in prompt_text


# ---------------------------------------------------------------------------
# generate_search_request
# ---------------------------------------------------------------------------

class TestGenerateSearchRequest:
    def test_valid_json_returns_search_request(self):
        provider = _MockProvider('{"q": "login bug", "entity_type": "Issue", "source": "jira"}')
        result = generate_search_request("Find login bugs in Jira", provider)
        assert result is not None
        assert result.q == "login bug"
        assert result.entity_type == "Issue"
        assert result.source == "jira"

    def test_sets_full_true(self):
        provider = _MockProvider('{"q": "test"}')
        result = generate_search_request("find test issues", provider)
        assert result is not None
        assert result.full is True

    def test_sets_page_size_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "ES_CHAIN_MAX_RESULTS", 3)
        provider = _MockProvider('{"q": "test"}')
        result = generate_search_request("find test issues", provider)
        assert result is not None
        assert result.page_size == 3

    def test_relevant_false_returns_none(self):
        provider = _MockProvider('{"relevant": false}')
        result = generate_search_request("Who collaborated with Alice?", provider)
        assert result is None

    def test_malformed_json_returns_none(self):
        provider = _MockProvider("Sorry, I cannot help with that.")
        result = generate_search_request("find bugs", provider)
        assert result is None

    def test_non_dict_json_returns_none(self):
        provider = _MockProvider('["q", "bugs"]')
        result = generate_search_request("find bugs", provider)
        assert result is None

    def test_markdown_fenced_json_parsed_correctly(self):
        provider = _MockProvider('```json\n{"q": "payment refactor"}\n```')
        result = generate_search_request("find payment refactor commits", provider)
        assert result is not None
        assert result.q == "payment refactor"

    def test_unknown_keys_silently_dropped(self):
        provider = _MockProvider('{"q": "test", "unknown_field": "ignored"}')
        result = generate_search_request("find test", provider)
        assert result is not None
        assert result.q == "test"

    def test_null_fields_not_set(self):
        provider = _MockProvider('{"q": "bugs", "entity_type": null, "source": null}')
        result = generate_search_request("find bugs", provider)
        assert result is not None
        assert result.entity_type is None
        assert result.source is None

    def test_llm_exception_returns_none(self):
        class _FailProvider:
            def chat_completion(self, _messages):
                raise RuntimeError("timeout")
        result = generate_search_request("find bugs", _FailProvider())
        assert result is None

    def test_history_included_in_prompt(self):
        provider = _MockProvider('{"q": "Alice"}')
        history = [{"role": "user", "content": "Tell me about Alice Chen"}]
        generate_search_request("What Jira issues is she working on?", provider, history)
        prompt_text = provider.last_messages[0]["content"]
        assert "Alice Chen" in prompt_text

    def test_raw_message_never_used_as_fallback(self):
        """Ensure that even on total LLM failure, the raw user message is not sent to ES."""
        class _FailProvider:
            def chat_completion(self, _messages):
                raise RuntimeError("LLM error")
        result = generate_search_request("Fetch me non-security related issues", _FailProvider())
        # Must return None, not a SearchRequest with q="Fetch me non-security related issues"
        assert result is None


# ---------------------------------------------------------------------------
# augment_message_with_es_stream (async flow tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_returns_not_applied_when_es_disabled(monkeypatch):
    """Chain is a no-op when ELASTICSEARCH_ENABLED=false."""
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)
    from app.ai_agent.chains import elasticsearch_chain as ec

    events = []
    async for event in ec.augment_message_with_es_stream("find bugs", provider=None):
        events.append(event)

    augmented = next(e for e in events if e["type"] == "augmented_message")
    assert augmented["content"]["applied"] is False


@pytest.mark.asyncio
async def test_stream_not_applied_when_not_relevant(monkeypatch):
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)
    from app.ai_agent.chains import elasticsearch_chain as ec

    monkeypatch.setattr(ec, "check_es_relevance", lambda *_a, **_kw: False)

    events = []
    async for event in ec.augment_message_with_es_stream("Who reviewed Alice's PR?", provider=object()):
        events.append(event)

    augmented = next(e for e in events if e["type"] == "augmented_message")
    assert augmented["content"]["applied"] is False
    thinking_texts = [e["content"] for e in events if e["type"] == "thinking_chunk"]
    assert any("does not require entity search" in t for t in thinking_texts)


@pytest.mark.asyncio
async def test_stream_not_applied_when_query_generation_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)
    from app.ai_agent.chains import elasticsearch_chain as ec

    monkeypatch.setattr(ec, "check_es_relevance", lambda *_a, **_kw: True)
    monkeypatch.setattr(ec, "generate_search_request", lambda *_a, **_kw: None)

    events = []
    async for event in ec.augment_message_with_es_stream("find bugs", provider=object()):
        events.append(event)

    augmented = next(e for e in events if e["type"] == "augmented_message")
    assert augmented["content"]["applied"] is False
    thinking_texts = [e["content"] for e in events if e["type"] == "thinking_chunk"]
    assert any("valid search request" in t for t in thinking_texts)


@pytest.mark.asyncio
async def test_stream_not_applied_when_zero_results(monkeypatch):
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)
    from app.ai_agent.chains import elasticsearch_chain as ec

    monkeypatch.setattr(ec, "check_es_relevance", lambda *_a, **_kw: True)
    monkeypatch.setattr(ec, "generate_search_request", lambda *_a, **_kw: SearchRequest(q="test"))
    empty_response = SearchResponse(total=0, page=1, page_size=5, results=[])
    monkeypatch.setattr(ec, "es_search", lambda _req: empty_response)

    events = []
    async for event in ec.augment_message_with_es_stream("find bugs", provider=object()):
        events.append(event)

    augmented = next(e for e in events if e["type"] == "augmented_message")
    assert augmented["content"]["applied"] is False
    thinking_texts = [e["content"] for e in events if e["type"] == "thinking_chunk"]
    assert any("No matching entities" in t for t in thinking_texts)


@pytest.mark.asyncio
async def test_stream_applied_with_results(monkeypatch):
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)
    from app.ai_agent.chains import elasticsearch_chain as ec

    monkeypatch.setattr(ec, "check_es_relevance", lambda *_a, **_kw: True)
    monkeypatch.setattr(ec, "generate_search_request", lambda *_a, **_kw: SearchRequest(q="login bug"))
    mock_result = SearchResult(
        wba_id="jira::Issue::PROJ-1",
        highlight="Fix <em>login</em> bug",
        attributes={"summary": "Login bug fix", "status": "In Progress"},
    )
    mock_response = SearchResponse(total=1, page=1, page_size=5, results=[mock_result])
    monkeypatch.setattr(ec, "es_search", lambda _req: mock_response)

    events = []
    async for event in ec.augment_message_with_es_stream("find login bugs", provider=object()):
        events.append(event)

    augmented = next(e for e in events if e["type"] == "augmented_message")
    content = augmented["content"]
    assert content["applied"] is True
    assert content["source"] == "elasticsearch"
    assert "total_hits" in content
    assert "PROJ-1" in content["context"]
    assert content["total_hits"] == 1


@pytest.mark.asyncio
async def test_stream_always_emits_thinking_end(monkeypatch):
    """thinking_end must be emitted on every code path."""
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)
    from app.ai_agent.chains import elasticsearch_chain as ec

    monkeypatch.setattr(ec, "check_es_relevance", lambda *_a, **_kw: False)

    events = []
    async for event in ec.augment_message_with_es_stream("hello", provider=object()):
        events.append(event)

    assert any(e["type"] == "thinking_end" for e in events)
