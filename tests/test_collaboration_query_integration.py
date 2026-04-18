"""Integration tests for parameterized collaboration Cypher query.

These tests require a live Neo4j instance and real project data.
Run with:
    pytest tests/test_collaboration_query_integration.py -v
"""

from pathlib import Path
import os
from typing import Any

import pytest

from app.analytics.collaboration.config import CollaborationNetworkConfig, LAYER_ORDER
from app.api.graph.v1.query import execute_cypher_query
from app.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.neo4j]


def _to_cypher_literal(value: Any) -> str:
    """Convert Python values to Cypher literal syntax for debug rendering."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_to_cypher_literal(item) for item in value) + "]"
    return repr(value)


def _render_query(query: str, parameters: dict[str, Any]) -> str:
    """Render a query with parameters inlined for human-readable debugging."""
    rendered = query
    # Replace longer parameter names first to avoid partial token collisions.
    for key in sorted(parameters.keys(), key=len, reverse=True):
        rendered = rendered.replace(f"${key}", _to_cypher_literal(parameters[key]))
    return rendered


@pytest.mark.skipif(
    (not settings.NEO4J_ENABLED) or (os.getenv("RUN_COLLAB_DB_VALIDATION", "0") != "1"),
    reason=(
        "Requires live Neo4j and explicit opt-in. "
        "Set NEO4J_ENABLED=true and RUN_COLLAB_DB_VALIDATION=1 to run."
    ),
)
@pytest.mark.parametrize("layer", LAYER_ORDER)
def test_each_layer_returns_data(layer: str):
    """Validate each collaboration layer has data in the current DB snapshot."""
    query_path = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "analytics"
        / "collaboration"
        / "queries"
        / "collaboration_score.cypher"
    )
    query = query_path.read_text(encoding="utf-8")

    config = CollaborationNetworkConfig.from_query_values(
        {
            "layers": layer,
            "lookback_days": 90,
            "min_pair_score": 1,
            "exclude_bots": True,
        }
    )

    parameters = config.to_cypher_parameters()
    rendered_query = _render_query(query, parameters)

    print("\n" + "=" * 90)
    print(f"[LAYER] {layer}")
    print("[QUERY - RENDERED]")
    print(rendered_query)
    print("=" * 90)

    records = execute_cypher_query(
        query,
        timeout=settings.NEO4J_QUERY_TIMEOUT,
        parameters=parameters,
    )

    assert records, (
        f"Single-layer query returned no rows for layer '{layer}'. "
        "This indicates either no activity exists in the last 90 days for that layer "
        "or data relationships/timestamps are missing for that signal."
    )
