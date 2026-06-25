import pytest
from datetime import datetime
from common.activity_signal.models import ActivitySignal
from connectors.producers.github.build_pull_request_signal import build_pull_request_signal

@pytest.mark.unit
def test_build_pull_request_signal_with_commenters():
    pr_data = {
        "number": 123,
        "title": "Test PR",
        "state": "open",
        "created_at": "2026-06-20T10:00:00+00:00",
        "updated_at": "2026-06-20T12:00:00+00:00",
        "commits_count": 2,
        "additions": 10,
        "deletions": 5,
        "changed_files": 1,
        "comments": 2,
        "review_comments": 1,
        "head_branch_name": "feature-branch",
        "base_branch_name": "main",
        "mergeable_state": "clean",
        "labels": ["bug"],
        "url": "https://github.com/org/repo/pull/123",
        "base_branch_id": "repo::main",
        "head_branch_id": "repo::feature-branch",
    }
    author_data = {"login": "author_user"}
    reviewer_logins = ["reviewer_1"]
    repo_data = {"name": "repo"}
    requested_reviewer_logins = ["req_reviewer_1"]
    merger_login = None
    commit_shas = ["sha123"]
    comments_data = [
        {"login": "commenter_1", "timestamp": "2026-06-20T11:00:00+00:00"},
        {"login": "commenter_2", "timestamp": "2026-06-20T11:30:00+00:00"},
    ]

    signal = build_pull_request_signal(
        pr_data=pr_data,
        author_data=author_data,
        reviewer_logins=reviewer_logins,
        repo_data=repo_data,
        requested_reviewer_logins=requested_reviewer_logins,
        merger_login=merger_login,
        commit_shas=commit_shas,
        comments_data=comments_data,
    )

    assert signal is not None
    assert isinstance(signal, ActivitySignal)
    
    # Check relationships
    rel_types = [r.type for r in signal.relationships]
    assert "CREATED_BY" in rel_types
    assert "REVIEWED_BY" in rel_types
    assert "REQUESTED_REVIEWER" in rel_types
    assert "INCLUDES" in rel_types
    
    # Check COMMENTED_ON relationships
    comment_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert len(comment_rels) == 2
    
    targets = [r.target.id for r in comment_rels]
    assert "commenter_1" in targets
    assert "commenter_2" in targets
    
    # Ensure direction is IN
    for r in comment_rels:
        assert r.direction == "IN"
