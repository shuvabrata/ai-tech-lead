"""Shared graph operation utilities for callback modules.

These helpers centralize API URL resolution and expansion merge logic to
keep callback functions focused on UI state updates.
"""

import os
from datetime import datetime

import requests

from .data_transform import neo4j_to_cytoscape


def get_graph_api_base_url() -> str:
    """Return configured Graph API base URL.

    Falls back to localhost for local development.
    """
    return os.getenv("API_BASE_URL", "http://localhost:8000")


def get_graph_expand_url() -> str:
    """Return full expansion endpoint URL."""
    return f"{get_graph_api_base_url()}/api/v1/graph/expand"


def execute_expansion_and_merge(
    *,
    node_id: str,
    direction: str,
    limit: int,
    loaded_node_ids: list[str] | None,
    expanded_nodes: dict | None,
    current_elements: list[dict],
    timeout_seconds: int,
) -> dict:
    """Execute expansion API call and merge returned elements.

    Returns a result dict with either:
    - {"ok": True, ...merged state...}
    - {"ok": False, "error_message": str}
    """
    exclude_ids = loaded_node_ids if loaded_node_ids else []
    payload = {
        "node_id": node_id,
        "direction": direction,
        "limit": limit,
        "offset": 0,
        "exclude_node_ids": exclude_ids,
        "relationship_types": None,
    }

    response = requests.post(
        get_graph_expand_url(),
        json=payload,
        timeout=timeout_seconds,
    )

    if response.status_code != 200:
        error_data = response.json() if response.content else {}
        error_message = error_data.get("detail", {}).get("message", "Unknown error")
        return {
            "ok": False,
            "error_message": error_message,
        }

    data = response.json()
    new_nodes = data.get("nodes", [])
    new_relationships = data.get("relationships", [])
    pagination = data.get("pagination", {})

    new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})

    existing_ids = {elem["data"]["id"] for elem in current_elements}
    merged_elements = current_elements.copy()

    for elem in new_elements:
        elem_id = elem["data"]["id"]
        if elem_id not in existing_ids:
            merged_elements.append(elem)
            existing_ids.add(elem_id)

    new_node_ids = [node["id"] for node in new_nodes]
    updated_loaded_ids = list(set((loaded_node_ids or []) + new_node_ids))

    updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
    updated_expanded[node_id] = {
        "direction": direction,
        "count": len(new_nodes),
        "timestamp": datetime.now().isoformat(),
    }

    return {
        "ok": True,
        "merged_elements": merged_elements,
        "updated_loaded_ids": updated_loaded_ids,
        "updated_expanded": updated_expanded,
        "new_nodes_count": len(new_nodes),
        "new_relationships_count": len(new_relationships),
        "has_more": pagination.get("has_more", False),
    }
