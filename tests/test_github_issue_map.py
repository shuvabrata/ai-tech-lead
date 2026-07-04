"""Unit tests for GitHub issue mapping and parsing helpers (Phase 2).

Tests cover:
- ``map_issue`` — raw PyGithub issue → normalized dict.
- ``extract_mentions`` — @login parsing with/without code blocks, dedup.
- ``extract_github_issue_refs`` — same-repo (#42) and cross-repo (org/repo#99) refs, dedup.
- ``extract_issue_keys`` — Jira key extraction reuse (already tested elsewhere, smoke test here).
- ``_strip_code_blocks`` — fenced and inline code stripping.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from connectors.producers.github.map_github import (
    _strip_code_blocks,
    extract_github_issue_refs,
    extract_issue_keys,
    extract_mentions,
    map_issue,
)


_REPO_FULL_NAME = "owner/repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    number: int = 42,
    title: str = "Fix login bug",
    state: str = "open",
    body: str = "",
    assignee_login: Optional[str] = None,
    reporter_login: str = "alice",
    labels: Optional[List[str]] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    html_url: str = "https://github.com/owner/repo/issues/42",
    comments_count: int = 0,
) -> MagicMock:
    """Build a mock PyGithub Issue object."""
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.state = state
    issue.body = body
    issue.html_url = html_url
    issue.comments = comments_count

    # Assignee
    if assignee_login:
        issue.assignee = MagicMock()
        issue.assignee.login = assignee_login
    else:
        issue.assignee = None

    # Reporter / user
    issue.user = MagicMock()
    issue.user.login = reporter_login

    # Labels
    label_objs = []
    for label_name in (labels or []):
        label = MagicMock()
        label.name = label_name
        label_objs.append(label)
    issue.labels = label_objs

    # Timestamps
    issue.created_at = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    issue.updated_at = updated_at or datetime(2026, 1, 2, tzinfo=timezone.utc)

    return issue


# ---------------------------------------------------------------------------
# map_issue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_map_issue_returns_correct_key():
    """The ``key`` should be ``<repo_full_name>#<number>``."""
    issue = _make_issue(number=42)
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["key"] == "owner/repo#42"


@pytest.mark.unit
def test_map_issue_returns_correct_summary():
    """The ``summary`` should be the issue title."""
    issue = _make_issue(title="Add dark mode")
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["summary"] == "Add dark mode"


@pytest.mark.unit
def test_map_issue_priority_is_none():
    """GitHub issues have no native priority — always 'None'."""
    issue = _make_issue()
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["priority"] == "None"


@pytest.mark.unit
def test_map_issue_type_is_issue():
    """GitHub issues have no native type — always 'Issue'."""
    issue = _make_issue()
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["type"] == "Issue"


@pytest.mark.unit
def test_map_issue_status_reflects_state():
    """The ``status`` should be the issue state ('open' or 'closed')."""
    issue = _make_issue(state="closed")
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["status"] == "closed"


@pytest.mark.unit
def test_map_issue_assignee_is_primary_login():
    """The ``assignee`` should be the assignee's login."""
    issue = _make_issue(assignee_login="bob")
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["assignee"] == "bob"


@pytest.mark.unit
def test_map_issue_assignee_none_when_no_assignee():
    """The ``assignee`` should be None when no assignee is set."""
    issue = _make_issue(assignee_login=None)
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["assignee"] is None


@pytest.mark.unit
def test_map_issue_reporter_is_author_login():
    """The ``reporter`` should be the issue author's login."""
    issue = _make_issue(reporter_login="alice")
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["reporter"] == "alice"


@pytest.mark.unit
def test_map_issue_labels_extracted_as_name_list():
    """Labels should be a list of label name strings."""
    issue = _make_issue(labels=["bug", "enhancement", "priority:high"])
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["labels"] == ["bug", "enhancement", "priority:high"]


@pytest.mark.unit
def test_map_issue_labels_empty_when_no_labels():
    """Labels should be an empty list when no labels are set."""
    issue = _make_issue(labels=None)
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["labels"] == []


@pytest.mark.unit
def test_map_issue_created_at_is_iso_string():
    """``created_at`` should be an ISO format string."""
    issue = _make_issue(created_at=datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc))
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["created_at"] == "2026-03-15T10:30:00+00:00"


@pytest.mark.unit
def test_map_issue_updated_at_is_iso_string():
    """``updated_at`` should be an ISO format string."""
    issue = _make_issue(updated_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc))
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["updated_at"] == "2026-03-16T12:00:00+00:00"


@pytest.mark.unit
def test_map_issue_url_is_html_url():
    """The ``url`` should be the issue's HTML URL."""
    issue = _make_issue(html_url="https://github.com/owner/repo/issues/99")
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["url"] == "https://github.com/owner/repo/issues/99"


@pytest.mark.unit
def test_map_issue_includes_repo_full_name():
    """The result should include ``repo_full_name`` for downstream use."""
    issue = _make_issue()
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["repo_full_name"] == "owner/repo"


@pytest.mark.unit
def test_map_issue_summary_empty_when_no_title():
    """The ``summary`` should be empty string when title is None."""
    issue = _make_issue(title=None)
    result = map_issue(issue, _REPO_FULL_NAME)
    assert result["summary"] == ""


# ---------------------------------------------------------------------------
# _strip_code_blocks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_strip_code_blocks_removes_fenced_code_block():
    """Fenced code blocks (```...```) should be removed."""
    text = "Before\n```python\nprint('hello')\n```\nAfter"
    result = _strip_code_blocks(text)
    assert "print" not in result
    assert "Before" in result
    assert "After" in result


@pytest.mark.unit
def test_strip_code_blocks_removes_inline_code():
    """Inline code spans (`...`) should be removed."""
    text = "Use `rtk` to run commands"
    result = _strip_code_blocks(text)
    assert "rtk" not in result
    assert "Use" in result
    assert "to run commands" in result


@pytest.mark.unit
def test_strip_code_blocks_preserves_normal_text():
    """Normal text without code blocks should be unchanged."""
    text = "This is a normal issue body with @mentions and #42 refs"
    result = _strip_code_blocks(text)
    assert result == text


@pytest.mark.unit
def test_strip_code_blocks_handles_empty_string():
    """Empty string input should return empty string."""
    assert _strip_code_blocks("") == ""


@pytest.mark.unit
def test_strip_code_blocks_handles_none_like_input():
    """None input should return empty string."""
    assert _strip_code_blocks(None) == ""  # type: ignore[arg-type]


@pytest.mark.unit
def test_strip_code_blocks_removes_multiple_fenced_blocks():
    """Multiple fenced code blocks should all be removed."""
    text = "```\ncode1\n```\nmiddle\n```js\ncode2\n```"
    result = _strip_code_blocks(text)
    assert "code1" not in result
    assert "code2" not in result
    assert "middle" in result


# ---------------------------------------------------------------------------
# extract_mentions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_mentions_finds_single_mention():
    """A single @mention should be extracted."""
    result = extract_mentions("Hey @alice can you review?")
    assert result == ["alice"]


@pytest.mark.unit
def test_extract_mentions_finds_multiple_mentions():
    """Multiple @mentions should all be extracted."""
    result = extract_mentions("Hey @alice and @bob please review")
    assert set(result) == {"alice", "bob"}


@pytest.mark.unit
def test_extract_mentions_deduplicates():
    """Duplicate @mentions should be deduplicated."""
    result = extract_mentions("@alice @alice @alice")
    assert result == ["alice"]


@pytest.mark.unit
def test_extract_mentions_returns_empty_when_no_mentions():
    """No @mentions should return an empty list."""
    result = extract_mentions("This is a normal comment with no mentions")
    assert result == []


@pytest.mark.unit
def test_extract_mentions_returns_empty_for_empty_string():
    """Empty string input should return an empty list."""
    assert extract_mentions("") == []


@pytest.mark.unit
def test_extract_mentions_ignores_mentions_in_code_blocks():
    """@mentions inside fenced code blocks should NOT be extracted."""
    text = "Hey @alice\n```python\n# @bob is mentioned in code\nprint('@charlie')\n```"
    result = extract_mentions(text)
    assert "alice" in result
    assert "bob" not in result
    assert "charlie" not in result


@pytest.mark.unit
def test_extract_mentions_ignores_mentions_in_inline_code():
    """@mentions inside inline code spans should NOT be extracted."""
    text = "Use `@bot` to trigger the bot, but ask @alice for help"
    result = extract_mentions(text)
    assert "alice" in result
    assert "bot" not in result


@pytest.mark.unit
def test_extract_mentions_handles_complex_login_names():
    """@mentions with hyphens in login names should be extracted."""
    result = extract_mentions("Hey @alice-smith and @bob-jones")
    assert set(result) == {"alice-smith", "bob-jones"}


@pytest.mark.unit
def test_extract_mentions_does_not_match_email_addresses():
    """@ in email addresses should NOT be treated as mentions."""
    result = extract_mentions("Contact alice@example.com for help")
    assert result == []


@pytest.mark.unit
def test_extract_mentions_does_not_match_url_fragments():
    """@ in URLs should NOT be treated as mentions."""
    result = extract_mentions("See https://github.com/owner/repo/@alice")
    assert result == []


# ---------------------------------------------------------------------------
# extract_github_issue_refs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_refs_finds_same_repo_ref():
    """Same-repo #42 should be resolved to <repo_full_name>#42."""
    result = extract_github_issue_refs("Fixes #42", _REPO_FULL_NAME)
    assert result == ["owner/repo#42"]


@pytest.mark.unit
def test_extract_refs_finds_cross_repo_ref():
    """Cross-repo org/repo#99 should be extracted as-is."""
    result = extract_github_issue_refs("Related to otherorg/otherrepo#99", _REPO_FULL_NAME)
    assert result == ["otherorg/otherrepo#99"]


@pytest.mark.unit
def test_extract_refs_finds_both_same_and_cross_repo():
    """Both same-repo and cross-repo refs should be extracted."""
    text = "Fixes #42 and relates to otherorg/otherrepo#99"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    assert set(result) == {"owner/repo#42", "otherorg/otherrepo#99"}


@pytest.mark.unit
def test_extract_refs_deduplicates():
    """Duplicate refs should be deduplicated."""
    text = "Fixes #42, see also #42"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    assert result == ["owner/repo#42"]


@pytest.mark.unit
def test_extract_refs_returns_empty_when_no_refs():
    """No issue refs should return an empty list."""
    result = extract_github_issue_refs("Just a normal comment", _REPO_FULL_NAME)
    assert result == []


@pytest.mark.unit
def test_extract_refs_returns_empty_for_empty_string():
    """Empty string input should return an empty list."""
    assert extract_github_issue_refs("", _REPO_FULL_NAME) == []


@pytest.mark.unit
def test_extract_refs_ignores_refs_in_code_blocks():
    """Issue refs inside fenced code blocks should NOT be extracted."""
    text = "Fixes #42\n```\n# this is not a ref #99\n```\nSee also #100"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    # #42 and #100 should be found (outside code block), #99 should NOT
    assert "owner/repo#42" in result
    assert "owner/repo#100" in result
    assert "owner/repo#99" not in result


@pytest.mark.unit
def test_extract_refs_ignores_refs_in_inline_code():
    """Issue refs inside inline code spans should NOT be extracted."""
    text = "Fixes #42, but `#99` is in code"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    assert "owner/repo#42" in result
    assert "owner/repo#99" not in result


@pytest.mark.unit
def test_extract_refs_finds_multiple_same_repo_refs():
    """Multiple same-repo refs should all be extracted and resolved."""
    text = "Fixes #42, closes #43, relates to #44"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    assert set(result) == {"owner/repo#42", "owner/repo#43", "owner/repo#44"}


@pytest.mark.unit
def test_extract_refs_finds_multiple_cross_repo_refs():
    """Multiple cross-repo refs should all be extracted."""
    text = "Relates to org1/repo1#10 and org2/repo2#20"
    result = extract_github_issue_refs(text, _REPO_FULL_NAME)
    assert set(result) == {"org1/repo1#10", "org2/repo2#20"}


@pytest.mark.unit
def test_extract_refs_does_not_match_plain_hash():
    """A bare # without a number should NOT be treated as a ref."""
    result = extract_github_issue_refs("This is # not a ref", _REPO_FULL_NAME)
    assert result == []


# ---------------------------------------------------------------------------
# extract_issue_keys (Jira keys — smoke test for reuse verification)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_issue_keys_finds_jira_keys():
    """Jira issue keys should be extracted (reuse verification)."""
    result = extract_issue_keys("Fixes PROJ-123 and AB-456")
    assert set(result) == {"PROJ-123", "AB-456"}


@pytest.mark.unit
def test_extract_issue_keys_deduplicates():
    """Duplicate Jira keys should be deduplicated."""
    result = extract_issue_keys("PROJ-123 PROJ-123")
    assert result == ["PROJ-123"]


@pytest.mark.unit
def test_extract_issue_keys_returns_empty_when_no_keys():
    """No Jira keys should return an empty list."""
    result = extract_issue_keys("Just a normal comment")
    assert result == []
