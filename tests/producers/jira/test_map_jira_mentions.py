"""Unit tests for ADF @mention extraction.

Tests ``src/connectors/producers/jira/map_jira.py``:

- ``extract_mentions_from_adf`` — recursively walks ADF JSON.
- ``extract_mentions_from_texts`` — combines a description + comment bodies.
"""

import pytest

from connectors.producers.jira.map_jira import (
    extract_mentions_from_adf,
    extract_mentions_from_texts,
)


def _mention(account_id: str) -> dict:
    return {"type": "mention", "attrs": {"id": f"accountId:{account_id}"}}


@pytest.mark.unit
class TestExtractMentionsFromAdf:
    def test_simple(self):
        """Single mention in a paragraph."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hey "},
                        _mention("alice"),
                    ],
                }
            ],
        }
        assert extract_mentions_from_adf(adf) == ["alice"]

    def test_multiple(self):
        """Multiple mentions are returned in document order."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "a"}]},
                _mention("bob"),
                {"type": "paragraph", "content": [_mention("carol")]},
            ],
        }
        assert extract_mentions_from_adf(adf) == ["bob", "carol"]

    def test_dedup(self):
        """Same person mentioned twice → one entry."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [_mention("alice"), _mention("alice")]},
            ],
        }
        assert extract_mentions_from_adf(adf) == ["alice"]

    def test_no_mentions(self):
        """Text with no mentions → empty list."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "hi"}]},
            ],
        }
        assert extract_mentions_from_adf(adf) == []

    def test_nested_adf(self):
        """Mentions inside nested structures (lists, tables, code blocks)."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [_mention("deep")]}
                            ],
                        }
                    ],
                },
                {
                    "type": "table",
                    "content": [
                        {"type": "tableRow", "content": [{"type": "tableCell"}]},
                        {"type": "tableRow", "content": [_mention("table_user")]},
                    ],
                },
            ],
        }
        result = extract_mentions_from_adf(adf)
        assert "deep" in result
        assert "table_user" in result

    def test_strips_accountid_prefix(self):
        """``accountId:abc123`` → ``abc123``."""
        adf = {"type": "doc", "content": [_mention("abc123")]}
        assert extract_mentions_from_adf(adf) == ["abc123"]

    def test_none_doc_returns_empty(self):
        """None argument → empty list."""
        assert extract_mentions_from_adf(None) == []

    def test_mention_without_attrs(self):
        """A mention node with no ``attrs`` does not crash."""
        adf = {"type": "doc", "content": [{"type": "mention"}]}
        assert extract_mentions_from_adf(adf) == []

    def test_empty_id_is_skipped(self):
        """A mention with an empty id is skipped."""
        adf = {
            "type": "doc",
            "content": [{"type": "mention", "attrs": {"id": ""}}],
        }
        assert extract_mentions_from_adf(adf) == []


@pytest.mark.unit
class TestExtractMentionsFromTexts:
    def test_combines_description_and_comments(self):
        """Mentions from both description and comment bodies are combined."""
        description = {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [_mention("alice")]}],
        }
        comment_bodies = [
            {"type": "doc", "content": [_mention("bob")]},
            {"type": "doc", "content": [_mention("carol")]},
        ]
        result = extract_mentions_from_texts(description, comment_bodies)
        assert sorted(result) == ["alice", "bob", "carol"]

    def test_dedup_across_sources(self):
        """Same person mentioned in description and a comment → one entry."""
        description = {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [_mention("alice")]}],
        }
        comment_bodies = [
            {"type": "doc", "content": [_mention("alice")]},
        ]
        assert extract_mentions_from_texts(description, comment_bodies) == ["alice"]

    def test_empty_sources(self):
        """No description and no comments → empty list."""
        assert extract_mentions_from_texts(None, []) == []