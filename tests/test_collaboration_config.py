"""Unit tests for collaboration network configuration parsing."""

import pytest

from app.analytics.collaboration.config import (
    CollaborationNetworkConfig,
    DEFAULT_LAYER_WEIGHTS,
    LAYER_ORDER,
)


def test_default_config_enables_all_layers_and_default_weights():
    config = CollaborationNetworkConfig()

    assert config.enabled_layers == LAYER_ORDER
    assert config.weights == DEFAULT_LAYER_WEIGHTS


def test_from_query_values_parses_layers_and_overrides_weights():
    config = CollaborationNetworkConfig.from_query_values(
        {
            "layers": "reporter_assignee,pr_reviews",
            "w_reporter_assignee": "4.5",
            "lookback_days": "60",
            "min_pair_score": "2",
            "top_n_edges_per_node": "3",
            "exclude_bots": "false",
        }
    )

    assert config.enabled_layers == ["reporter_assignee", "pr_reviews"]
    assert config.weights["reporter_assignee"] == 4.5
    assert config.lookback_days == 60
    assert config.min_pair_score == 2
    assert config.top_n_edges_per_node == 3
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
