"""Unit tests for collaboration network configuration parsing."""

import pytest

from app.analytics.collaboration.config import (
    CollaborationNetworkConfig,
    DEFAULT_COMMUNITY_GAP_X,
    DEFAULT_COMMUNITY_GAP_Y,
    DEFAULT_LAYER_WEIGHTS,
    LAYER_ORDER,
)


pytestmark = pytest.mark.unit


def test_default_config_enables_all_layers_and_default_weights():
    config = CollaborationNetworkConfig()

    assert config.enabled_layers == LAYER_ORDER
    assert config.weights == DEFAULT_LAYER_WEIGHTS
    assert config.community_gap_x == DEFAULT_COMMUNITY_GAP_X
    assert config.community_gap_y == DEFAULT_COMMUNITY_GAP_Y


def test_from_query_values_parses_layers_and_overrides_weights():
    config = CollaborationNetworkConfig.from_query_values(
        {
            "layers": "reporter_assignee,pr_reviews",
            "w_reporter_assignee": "4.5",
            "lookback_days": "60",
            "min_pair_score": "2",
            "top_n_edges_per_node": "3",
            "community_gap_x": "2000",
            "community_gap_y": "1500",
            "exclude_bots": "false",
        }
    )

    assert config.enabled_layers == ["reporter_assignee", "pr_reviews"]
    assert config.weights["reporter_assignee"] == 4.5
    assert config.lookback_days == 60
    assert config.min_pair_score == 2
    assert config.top_n_edges_per_node == 3
    assert config.community_gap_x == 2000
    assert config.community_gap_y == 1500
    assert config.exclude_bots is False


def test_to_cypher_parameters_contains_include_and_weight_keys():
    config = CollaborationNetworkConfig.from_query_values({"layers": "epic_overlap"})
    params = config.to_cypher_parameters()

    assert params["include_epic_overlap"] is True
    assert params["include_pr_reviews"] is False
    assert params["weight_epic_overlap"] == config.weights["epic_overlap"]


def test_invalid_layer_name_is_rejected():
    with pytest.raises(ValueError):
        CollaborationNetworkConfig.from_query_values({"layers": "unknown_layer"})


def test_confluence_layers_present_in_layer_order():
    confluence_layers = [
        "confluence_co_authorship",
        "confluence_comment_engagement",
        "confluence_co_commenters",
        "confluence_mentions",
    ]
    for layer in confluence_layers:
        assert layer in LAYER_ORDER, f"Expected '{layer}' in LAYER_ORDER"


def test_confluence_layers_have_correct_default_weights():
    assert DEFAULT_LAYER_WEIGHTS["confluence_co_authorship"] == 3.0
    assert DEFAULT_LAYER_WEIGHTS["confluence_comment_engagement"] == 2.0
    assert DEFAULT_LAYER_WEIGHTS["confluence_co_commenters"] == 1.0
    assert DEFAULT_LAYER_WEIGHTS["confluence_mentions"] == 2.0


def test_confluence_layers_enabled_by_default():
    config = CollaborationNetworkConfig()
    for layer in ["confluence_co_authorship", "confluence_comment_engagement",
                  "confluence_co_commenters", "confluence_mentions"]:
        assert layer in config.enabled_layers, f"Expected '{layer}' enabled by default"


def test_to_cypher_parameters_includes_confluence_keys():
    config = CollaborationNetworkConfig()
    params = config.to_cypher_parameters()

    assert params["include_confluence_co_authorship"] is True
    assert params["weight_confluence_co_authorship"] == 3.0
    assert params["include_confluence_comment_engagement"] is True
    assert params["weight_confluence_comment_engagement"] == 2.0
    assert params["include_confluence_co_commenters"] is True
    assert params["weight_confluence_co_commenters"] == 1.0
    assert params["include_confluence_mentions"] is True
    assert params["weight_confluence_mentions"] == 2.0


def test_confluence_layers_can_be_selectively_disabled():
    config = CollaborationNetworkConfig.from_query_values(
        {"layers": "reporter_assignee,pr_reviews,epic_overlap"}
    )
    params = config.to_cypher_parameters()

    assert params["include_confluence_co_authorship"] is False
    assert params["include_confluence_comment_engagement"] is False
    assert params["include_confluence_co_commenters"] is False
    assert params["include_confluence_mentions"] is False


# ---------------------------------------------------------------------------
# GitHub Issue Layer Tests (Phase 5)
# ---------------------------------------------------------------------------


def test_github_issue_layers_present_in_layer_order():
    """GitHub issue layers are registered in LAYER_ORDER."""
    assert "github_issue_comment_engagement" in LAYER_ORDER
    assert "github_issue_co_commenters" in LAYER_ORDER


def test_github_issue_layers_have_correct_default_weights():
    """GitHub issue layers have the expected default weights."""
    assert DEFAULT_LAYER_WEIGHTS["github_issue_comment_engagement"] == 3.0
    assert DEFAULT_LAYER_WEIGHTS["github_issue_co_commenters"] == 2.0


def test_github_issue_layers_enabled_by_default():
    """GitHub issue layers are enabled by default."""
    config = CollaborationNetworkConfig()
    assert "github_issue_comment_engagement" in config.enabled_layers
    assert "github_issue_co_commenters" in config.enabled_layers


def test_to_cypher_parameters_includes_github_issue_keys():
    """to_cypher_parameters() includes include_/weight_ keys for GitHub issue layers."""
    config = CollaborationNetworkConfig()
    params = config.to_cypher_parameters()

    assert params["include_github_issue_comment_engagement"] is True
    assert params["weight_github_issue_comment_engagement"] == 3.0
    assert params["include_github_issue_co_commenters"] is True
    assert params["weight_github_issue_co_commenters"] == 2.0


def test_github_issue_layers_can_be_selectively_disabled():
    """GitHub issue layers are disabled when not in the selected layers list."""
    config = CollaborationNetworkConfig.from_query_values(
        {"layers": "reporter_assignee,pr_reviews"}
    )
    params = config.to_cypher_parameters()

    assert params["include_github_issue_comment_engagement"] is False
    assert params["include_github_issue_co_commenters"] is False


def test_github_issue_layer_weights_have_correct_values():
    """Verify GitHub issue weights are set to the correct independent values."""
    config = CollaborationNetworkConfig()
    assert config.weights["github_issue_comment_engagement"] == 3.0
    assert config.weights["github_issue_co_commenters"] == 2.0


# ---------------------------------------------------------------------------
# Jira Comment/Mention Layer Tests (Plan 018, Phase 4)
# ---------------------------------------------------------------------------

JIRA_LAYERS = [
    "jira_issue_comment_engagement",
    "jira_issue_co_commenters",
    "jira_epic_initiative_comment_engagement",
    "jira_epic_initiative_co_commenters",
]

JIRA_WEIGHTS = {
    "jira_issue_comment_engagement": 3.0,
    "jira_issue_co_commenters": 2.0,
    "jira_epic_initiative_comment_engagement": 2.0,
    "jira_epic_initiative_co_commenters": 1.0,
}


def test_jira_comment_layers_registered():
    """All 4 Jira comment layers are present in LAYER_ORDER."""
    for layer in JIRA_LAYERS:
        assert layer in LAYER_ORDER, f"Expected '{layer}' in LAYER_ORDER"


def test_jira_mentions_layer_removed():
    """The fabricated-author jira_mentions layer is deliberately absent.

    Plan 020 removed layer #19 because the MENTIONS edge carries no true
    author (the producer emits it undirected with only the @mentioned
    accountId). Re-adding it without recording mention authorship would
    reintroduce fabricated person-to-person attribution.
    """
    assert "jira_mentions" not in LAYER_ORDER
    assert "jira_mentions" not in DEFAULT_LAYER_WEIGHTS


def test_jira_comment_layers_have_correct_weights():
    """Jira comment layers have the expected default weights."""
    for layer, weight in JIRA_WEIGHTS.items():
        assert DEFAULT_LAYER_WEIGHTS[layer] == weight, f"Unexpected weight for {layer}"


def test_jira_comment_layers_enabled_by_default():
    """Jira comment layers are enabled by default."""
    config = CollaborationNetworkConfig()
    for layer in JIRA_LAYERS:
        assert layer in config.enabled_layers, f"Expected '{layer}' enabled by default"


def test_to_cypher_parameters_includes_jira_comment_keys():
    """to_cypher_parameters() includes include_/weight_ keys for Jira layers."""
    config = CollaborationNetworkConfig()
    params = config.to_cypher_parameters()

    for layer in JIRA_LAYERS:
        assert params[f"include_{layer}"] is True
        assert params[f"weight_{layer}"] == JIRA_WEIGHTS[layer]


def test_jira_comment_layers_can_be_selectively_disabled():
    """Jira comment layers are disabled when not in the selected layers list."""
    config = CollaborationNetworkConfig.from_query_values(
        {"layers": "reporter_assignee,pr_reviews"}
    )
    params = config.to_cypher_parameters()

    for layer in JIRA_LAYERS:
        assert params[f"include_{layer}"] is False


def test_existing_layers_unchanged():
    """Adding Jira layers should not regress existing weights."""
    config = CollaborationNetworkConfig()
    assert config.weights["github_issue_comment_engagement"] == 3.0
    assert config.weights["confluence_comment_engagement"] == 2.0
    assert config.weights["pr_reviews"] == 3.0
    assert config.weights["reporter_assignee"] == 2.0
