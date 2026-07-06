"""Tests for GraphNode ABC and computed display/time properties.

Verifies that all 15 concrete node dataclasses:
- compute _display_name / _on_hover_name / _last_updated_at
  correctly from their fields
- include those 3 keys in to_neo4j_properties() output (when applicable)
- enforce mandatory ``url`` at construction
- support per-type overrides (Commit, PullRequest, File, IdentityMapping)
"""

from __future__ import annotations

import pytest
from connectors.neo4j_db.models import (
    Person,
    Team,
    IdentityMapping,
    Project,
    Epic,
    Issue,
    Sprint,
    Repository,
    Commit,
    File,
    PullRequest,
    Space,
    Page,
    Blogpost,
)


# ── Constructor helpers ───────────────────────────────────────────────────────


def _minimal_url_kwargs(**overrides) -> dict:
    """Return a kwargs dict ensuring ``url`` is always set, defaulting to ``""``."""
    kwargs = {"url": ""}
    kwargs.update(overrides)
    return kwargs


# ── Node type test matrix ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_person_display_name():
    """Person uses 'name' field."""
    p = Person(id="p1", name="Alice", **_minimal_url_kwargs(url="https://example.com/alice"))
    assert p.display_name() == "Alice"
    assert p.on_hover_name() == "Alice"
    assert p.last_seen_at() is None
    assert p._calc_last_updated_at() is None
    props = p.to_neo4j_properties()
    assert props["_display_name"] == "Alice"
    assert props["_on_hover_name"] == "Alice"
    assert "_last_updated_at" not in props
    # id and url from the ABC should be included in the asdict output
    assert props["id"] == "p1"
    assert props["url"] == "https://example.com/alice"


@pytest.mark.unit
def test_person_display_name_fallback():
    """Person falls back to '' as name then defaults to id."""
    p = Person(id="p_fallback", name="", url="")
    assert p.display_name() == "p_fallback"


@pytest.mark.unit
def test_team_display_name():
    t = Team(id="t1", name="Platform", url="")
    assert t.display_name() == "Platform"
    props = t.to_neo4j_properties()
    assert props["_display_name"] == "Platform"


@pytest.mark.unit
def test_identity_mapping_display_name():
    """IdentityMapping uses username (override)."""
    im = IdentityMapping(id="im1", provider="GitHub", username="alice", url="")
    assert im.display_name() == "alice"
    props = im.to_neo4j_properties()
    assert props["_display_name"] == "alice"
    assert "_last_updated_at" not in props  # field is None


@pytest.mark.unit
def test_identity_mapping_last_updated_at():
    """IdentityMapping has last_updated_at field."""
    im = IdentityMapping(
        id="im1", provider="GitHub", username="bob", url="",
        last_updated_at="2026-01-01T00:00:00Z",
    )
    assert im._calc_last_updated_at() == "2026-01-01T00:00:00Z"
    props = im.to_neo4j_properties()
    assert props["_last_updated_at"] == "2026-01-01T00:00:00Z"


@pytest.mark.unit
def test_project_display_name():
    proj = Project(id="pj1", key="PROJ", name="My Project")
    assert proj.display_name() == "My Project"
    props = proj.to_neo4j_properties()
    assert props["_display_name"] == "My Project"


@pytest.mark.unit
def test_epic_display_name():
    epic = Epic(
        id="e1", key="EPIC-1", summary="My Epic", priority="High", status="IP",
        start_date="2026-01-01", due_date="2026-06-30", created_at="2026-01-01",
    )
    assert epic.display_name() == "My Epic"
    props = epic.to_neo4j_properties()
    assert props["_display_name"] == "My Epic"


@pytest.mark.unit
def test_issue_display_name():
    issue = Issue(
        id="i1", key="ISS-1", type="Story", summary="My Story", priority="Med",
        status="Open", story_points=3, created_at="2026-01-01",
    )
    assert issue.display_name() == "My Story"
    props = issue.to_neo4j_properties()
    assert props["_display_name"] == "My Story"


@pytest.mark.unit
def test_sprint_display_name():
    sprint = Sprint(id="s1", name="Sprint 1", goal="Goal", start_date="2026-01-01",
                    end_date="2026-02-01", status="Active")
    assert sprint.display_name() == "Sprint 1"


@pytest.mark.unit
def test_repository_display_name():
    repo = Repository(
        id="r1", name="my/repo", url="https://github.com/my/repo",
        language="Python", is_private=False, topics=[], created_at="2026-01-01",
    )
    assert repo.display_name() == "my/repo"


@pytest.mark.unit
def test_commit_last_updated_at_override():
    """Commit overrides _calc_last_updated_at to return created_at."""
    c = Commit(
        id="c1", sha="abc123", message="msg", created_at="2026-01-15T14:30:00",
        additions=10, deletions=2, files_changed=1, url="",
    )
    assert c._calc_last_updated_at() == "2026-01-15T14:30:00"
    props = c.to_neo4j_properties()
    assert props["_last_updated_at"] == "2026-01-15T14:30:00"
    assert props["_display_name"] == c.id  # no name/title/summary/key fields


@pytest.mark.unit
def test_file_display_name_override():
    """File uses path as display name."""
    f = File(id="f1", path="src/main.py", repo_name="repo", url="")
    assert f.display_name() == "src/main.py"
    props = f.to_neo4j_properties()
    assert props["_display_name"] == "src/main.py"


@pytest.mark.unit
def test_file_filtered_none_values():
    """File.to_neo4j_properties() excludes None values but includes computed keys."""
    f = File(id="f1", path="src/main.py", repo_name="repo", url="")
    props = f.to_neo4j_properties()
    assert "id" in props
    assert "path" in props
    assert "name" not in props  # None, filtered out
    assert "extension" not in props
    assert "_display_name" in props
    assert "_on_hover_name" in props


@pytest.mark.unit
def test_pull_request_on_hover_override():
    """PullRequest.on_hover_name() returns PR #number: title."""
    pr = PullRequest(
        id="pr1", number=42, title="Fix bug", state="open",
        created_at="2026-01-01", updated_at="2026-01-02",
        merged_at=None, closed_at=None,
        commits_count=1, additions=10, deletions=2, changed_files=1,
        comments=0, review_comments=0, head_branch_name="main",
        base_branch_name="dev", labels=[], mergeable_state="clean", url="",
    )
    assert pr.on_hover_name() == "PR #42: Fix bug"
    props = pr.to_neo4j_properties()
    assert props["_on_hover_name"] == "PR #42: Fix bug"
    assert props["_display_name"] == "Fix bug"  # default from title field


@pytest.mark.unit
def test_space_last_seen_at():
    """Space _last_seen_at is injected via set_last_observed_at()."""
    s = Space(id="s1", key="DEV", name="Development")
    s.set_last_observed_at("2026-06-01T00:00:00Z")
    assert s.last_seen_at() == "2026-06-01T00:00:00Z"
    props = s.to_neo4j_properties()
    assert props["_last_seen_at"] == "2026-06-01T00:00:00Z"


@pytest.mark.unit
def test_page_last_updated_at():
    page = Page(
        id="pg1", title="My Page", created_at="2026-01-01",
        last_updated_at="2026-06-01T00:00:00Z",
    )
    assert page._calc_last_updated_at() == "2026-06-01T00:00:00Z"
    props = page.to_neo4j_properties()
    assert props["_last_updated_at"] == "2026-06-01T00:00:00Z"
    assert props["_display_name"] == "My Page"


@pytest.mark.unit
def test_blogpost_display_name():
    bp = Blogpost(id="bp1", title="My Blog", created_at="2026-01-01")
    assert bp.display_name() == "My Blog"
    props = bp.to_neo4j_properties()
    assert props["_display_name"] == "My Blog"


@pytest.mark.unit
def test_last_seen_at_from_last_synced_at():
    """Classes with _last_seen_at return it from last_seen_at() (Python method, not dataclass field)."""
    for label, obj in [
        ("Space", Space(id="s1", key="DEV", name="Dev")),
        ("Page", Page(id="pg1", title="P", created_at="2026-01-01")),
        ("Blogpost", Blogpost(id="bp1", title="B", created_at="2026-01-01")),
    ]:
        obj.set_last_observed_at("2026-01-01T00:00:00Z")
        assert obj.last_seen_at() == "2026-01-01T00:00:00Z", f"{label} failed"


@pytest.mark.unit
def test_commit_no_last_seen():
    """Commit has no _last_seen_at → last_seen_at returns None."""
    c = Commit(id="c1", sha="abc", message="m", created_at="2026-01-01T00:00:00",
               additions=1, deletions=0, files_changed=1, url="")
    assert c.last_seen_at() is None


@pytest.mark.unit
def test_to_neo4j_properties_includes_all_computed_keys():
    """Sanity check that _display_name and _on_hover_name appear in to_neo4j_properties()."""
    p1 = Person(id="p1", name="A", url="")
    p2 = Person(id="p2", name="B", url="")
    for p in [p1, p2]:
        props = p.to_neo4j_properties()
        assert "_display_name" in props
        assert "_on_hover_name" in props


@pytest.mark.unit
def test_identity_mapping_mandatory_url():
    """IdentityMapping has url: str = \"\" — omitting url is allowed (gets default)."""
    im = IdentityMapping(id="im1", provider="GitHub", username="alice")
    assert im.url == ""


@pytest.mark.unit
def test_repository_has_mandatory_url():
    """Repository.url is required (str field without default)."""
    with pytest.raises(TypeError):
        Repository(
            id="r1", name="my/repo",
            language="Python", is_private=False, topics=[], created_at="2026-01-01",
        )


@pytest.mark.unit
def test_jira_issue_base_inheritance():
    """JiraIssueBase inherited GraphNode, Initiative gets display/time props."""
    from connectors.neo4j_db.models import Initiative
    init = Initiative(
        id="init1", key="INIT-1", summary="Platform Modernization",
        priority="High", status="In Progress", created_at="2026-01-01",
        updated_at="2026-01-15", duedate="2026-06-30",
    )
    assert init.display_name() == "Platform Modernization"
    props = init.to_neo4j_properties()
    assert props["_display_name"] == "Platform Modernization"
    assert "_last_updated_at" in props


@pytest.mark.unit
def test_graph_node_is_abstract():
    """GraphNode cannot be directly instantiated."""
    from connectors.neo4j_db.node_base import GraphNode
    with pytest.raises(TypeError):
        GraphNode()


@pytest.mark.unit
def test_epic_does_not_shadow_calc_last_updated_at():
    """Epic has a field named updated_at but no method override —
    _calc_last_updated_at on the base class should pick it up."""
    epic = Epic(
        id="e1", key="EPIC-1", summary="Epic", priority="High", status="IP",
        start_date="2026-01-01", due_date="2026-06-30",
        created_at="2026-01-01", updated_at="2026-01-15",
    )
    assert epic._calc_last_updated_at() == "2026-01-15"
    props = epic.to_neo4j_properties()
    assert props["_last_updated_at"] == "2026-01-15"


@pytest.mark.unit
def test_page_title_used_for_display():
    """Page has title but no name/summary/key — display_name picks title."""
    page = Page(id="pg1", title="Executive Summary", created_at="2026-01-01")
    assert page.display_name() == "Executive Summary"