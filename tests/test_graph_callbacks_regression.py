"""Regression tests for Graph page callback state synchronization.

These tests focus on frontend callback state contracts that previously allowed
stale graph data to reappear after repeated Execute actions.
"""

from dataclasses import dataclass

from app.dash_app.pages.graph.callbacks import query as query_callbacks


@dataclass
class _FakeResponse:
    """Minimal requests.Response stand-in for callback tests."""

    payload: dict
    status_code: int = 200

    @property
    def headers(self):
        return {"content-type": "application/json"}

    @property
    def content(self):
        return b"{}"

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class _PostSequence:
    """Sequential fake for requests.post returning predefined responses."""

    def __init__(self, responses):
        self._responses = responses
        self._idx = 0

    def __call__(self, _url, json, timeout):
        _ = (json, timeout)
        if self._idx >= len(self._responses):
            raise AssertionError("Unexpected extra requests.post call")
        response = self._responses[self._idx]
        self._idx += 1
        return response


def test_execute_query_repeated_runs_refresh_baseline_and_filters(monkeypatch):
    """Executing Query A then Query B must leave Query B as active baseline.

    This guards against regressions where old unfiltered graph state could
    overwrite the latest execute result.
    """

    graph_a = {
        "isGraph": True,
        "nodes": [{"id": "A1"}],
        "relationships": [{"id": "R1"}],
        "resultCount": 2,
        "rawResults": [],
    }
    graph_b = {
        "isGraph": True,
        "nodes": [{"id": "B1"}],
        "relationships": [],
        "resultCount": 1,
        "rawResults": [],
    }

    cyto_a = [{"data": {"id": "A1"}}, {"data": {"id": "R1", "source": "A1", "target": "A1"}}]
    cyto_b = [{"data": {"id": "B1"}}]

    post_fake = _PostSequence([_FakeResponse(graph_a), _FakeResponse(graph_b)])
    monkeypatch.setattr(query_callbacks.requests, "post", post_fake)

    def _fake_neo4j_to_cytoscape(payload):
        node_ids = {n["id"] for n in payload.get("nodes", [])}
        if node_ids == {"A1"}:
            return cyto_a
        if node_ids == {"B1"}:
            return cyto_b
        raise AssertionError("Unexpected graph payload")

    monkeypatch.setattr(query_callbacks, "neo4j_to_cytoscape", _fake_neo4j_to_cytoscape)

    # First execute (Query A)
    result_a = query_callbacks.execute_query(1, "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10")

    # Second execute (Query B)
    result_b = query_callbacks.execute_query(2, "MATCH (n) RETURN n LIMIT 1")

    # Output indices from execute_query callback contract
    ELEMENTS = 1
    UNFILTERED_STORE = 13
    NODE_FILTER = 14
    REL_FILTER = 15
    WEIGHT_FILTER = 16
    TOP_N_FILTER = 17

    # Baseline and rendered elements should match each run
    assert result_a[ELEMENTS] == cyto_a
    assert result_a[UNFILTERED_STORE] == cyto_a

    assert result_b[ELEMENTS] == cyto_b
    assert result_b[UNFILTERED_STORE] == cyto_b

    # Critical regression assertion: second execute must overwrite first baseline
    assert result_b[UNFILTERED_STORE] != result_a[UNFILTERED_STORE]

    # Execute should always reset filter controls to defaults
    assert result_b[NODE_FILTER] == []
    assert result_b[REL_FILTER] == []
    assert result_b[WEIGHT_FILTER] == 0
    assert result_b[TOP_N_FILTER] == "all"
