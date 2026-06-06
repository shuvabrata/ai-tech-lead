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
