"""Shared graph operation utilities for callback modules.

These helpers centralize API URL resolution and expansion merge logic to
keep callback functions focused on UI state updates.
"""

import os
import math
from datetime import datetime

import requests

from app.common.logger import logger
from .data_transform import neo4j_to_cytoscape
from .element_types import is_edge_element, is_node_element


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
    current_node_positions: dict | None,
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

    logger.info(
        "[GRAPH-DEBUG][expand.merge] request "
        f"node_id={node_id} direction={direction} limit={limit} "
        f"exclude_count={len(exclude_ids)} current_elements={len(current_elements)}"
    )

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

    logger.info(
        "[GRAPH-DEBUG][expand.merge] response "
        f"new_nodes={len(new_nodes)} new_relationships={len(new_relationships)} "
        f"has_more={pagination.get('has_more', False)}"
    )

    new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})
    new_nodes_elements = [e for e in new_elements if not is_edge_element(e)]
    new_edge_elements = [e for e in new_elements if is_edge_element(e)]

    logger.info(
        "[GRAPH-DEBUG][expand.merge] transformed "
        f"new_elements={len(new_elements)} node_elements={len(new_nodes_elements)} "
        f"edge_elements={len(new_edge_elements)}"
    )

    existing_ids = {elem["data"]["id"] for elem in current_elements}
    merged_elements = current_elements.copy()
    skipped_existing = 0

    for elem in new_elements:
        elem_id = elem["data"]["id"]
        if elem_id not in existing_ids:
            merged_elements.append(elem)
            existing_ids.add(elem_id)
        else:
            skipped_existing += 1

    # Preserve visible node positions (only when the captured map is valid) and
    # place newly added nodes near the expansion anchor.
    current_node_positions = current_node_positions or {}
    new_node_ids = {node["id"] for node in new_nodes if "id" in node}

    position_items = [
        (node_key, pos)
        for node_key, pos in current_node_positions.items()
        if isinstance(pos, dict) and "x" in pos and "y" in pos
    ]
    unique_positions = {
        (round(float(pos["x"]), 2), round(float(pos["y"]), 2))
        for _, pos in position_items
    }
    has_valid_position_map = len(position_items) >= 2 and len(unique_positions) >= 2

    anchor = current_node_positions.get(node_id)
    if not anchor:
        anchor_elem = next(
            (
                elem for elem in current_elements
                if elem.get("data", {}).get("id") == node_id and isinstance(elem.get("position"), dict)
            ),
            None,
        )
        anchor = anchor_elem.get("position") if anchor_elem else None

    anchor_x = float(anchor.get("x", 0)) if isinstance(anchor, dict) else 0.0
    anchor_y = float(anchor.get("y", 0)) if isinstance(anchor, dict) else 0.0

    radial_positions = {}
    if new_node_ids:
        radius = 180
        step = (2 * math.pi) / max(len(new_node_ids), 1)
        for idx, new_id in enumerate(sorted(new_node_ids)):
            angle = idx * step
            radial_positions[new_id] = {
                "x": anchor_x + (radius * math.cos(angle)),
                "y": anchor_y + (radius * math.sin(angle)),
            }

    for elem in merged_elements:
        if not is_node_element(elem):
            continue

        node_id_value = elem.get("data", {}).get("id")
        if not node_id_value:
            continue

        # Only preserve existing positions when capture quality looks sane.
        if has_valid_position_map and node_id_value in current_node_positions:
            elem["position"] = current_node_positions[node_id_value]
        elif node_id_value in radial_positions:
            elem["position"] = radial_positions[node_id_value]

    new_node_ids = [node["id"] for node in new_nodes]
    updated_loaded_ids = list(set((loaded_node_ids or []) + new_node_ids))

    updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
    updated_expanded[node_id] = {
        "direction": direction,
        "count": len(new_nodes),
        "timestamp": datetime.now().isoformat(),
    }

    merged_nodes = [e for e in merged_elements if not is_edge_element(e)]
    merged_edges = [e for e in merged_elements if is_edge_element(e)]

    logger.info(
        "[GRAPH-DEBUG][expand.merge] merged "
        f"merged_total={len(merged_elements)} merged_nodes={len(merged_nodes)} "
        f"merged_edges={len(merged_edges)} skipped_existing={skipped_existing} "
        f"loaded_node_ids={len(updated_loaded_ids)} preserved_positions={len(position_items)} "
        f"unique_positions={len(unique_positions)} has_valid_position_map={has_valid_position_map}"
    )

    return {
        "ok": True,
        "merged_elements": merged_elements,
        "updated_loaded_ids": updated_loaded_ids,
        "updated_expanded": updated_expanded,
        "new_nodes_count": len(new_nodes),
        "new_relationships_count": len(new_relationships),
        "has_more": pagination.get("has_more", False),
    }
