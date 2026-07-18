"""Per-layer validation of the collaboration score Cypher query against live Neo4j.

Runs automatically whenever NEO4J_ENABLED=true. No extra opt-in flag required.

Each test isolates one collaboration layer by enabling only that layer, runs the
full query against the live graph, and asserts at least one person-pair is
returned. Results are collected and written to tests/collab_validation/results/
as timestamped HTML and JSON reports via the conftest.py session hook.

Run:
    pytest tests/collab_validation/ -v
"""

import time
from pathlib import Path
from typing import Any

import pytest

from app.analytics.collaboration.config import CollaborationNetworkConfig, LAYER_ORDER
from app.api.graph.v1.query import execute_cypher_query
from app.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.neo4j]

_QUERY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "app"
    / "analytics"
    / "collaboration"
    / "queries"
    / "collaboration_score.cypher"
)


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
    for key in sorted(parameters.keys(), key=len, reverse=True):
        rendered = rendered.replace(f"${key}", _to_cypher_literal(parameters[key]))
    return rendered


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Requires live Neo4j. Set NEO4J_ENABLED=true to run.",
)
@pytest.mark.parametrize("layer", LAYER_ORDER)
def test_each_layer_returns_data(layer: str, track_result):
    """Validate each collaboration layer returns at least one person-pair from Neo4j."""
    query = _QUERY_PATH.read_text(encoding="utf-8")

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

    t0 = time.time()
    records = execute_cypher_query(
        query,
        timeout=settings.NEO4J_QUERY_TIMEOUT,
        parameters=parameters,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    passed = bool(records)
    track_result({
        "layer": layer,
        "status": "PASS" if passed else "FAIL",
        "row_count": len(records),
        "elapsed_ms": elapsed_ms,
        "message": f"{len(records)} pairs found" if passed else "No rows returned",
    })

    assert passed, (
        f"Single-layer query returned no rows for layer '{layer}'. "
        "This indicates either no activity exists in the last 90 days for that layer "
        "or data relationships/timestamps are missing for that signal."
    )
