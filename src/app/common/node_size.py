"""Node sizing utilities shared between the analytics pipeline and the Dash UI.

Kept in app/common to avoid circular imports: both the collaboration algorithm
(app/analytics/...) and the Dash data-transform (app/dash_app/...) need these
helpers, but the analytics layer must not import from the Dash layer.
"""

# Default node dimensions in pixels, keyed by nodeType string.
# Used as the base for _node_size multiplier calculations so dynamic sizing
# preserves each type's width:height ratio.
# Keep in sync with fixed width/height values in
# app/dash_app/pages/graph/styles.py :: build_cytoscape_stylesheet.
BASE_NODE_DIMENSIONS: dict[str, tuple[float, float]] = {
    "Project": (70.0, 35.0),
    "Person": (66.0, 56.0),
    "Branch": (58.0, 50.0),
    "Epic": (66.0, 56.0),
    "Issue": (58.0, 50.0),
    "Repository": (68.0, 34.0),
    "Team": (64.0, 54.0),
    "IdentityMapping": (62.0, 50.0),
    "Initiative": (66.0, 54.0),
    "Sprint": (60.0, 48.0),
    "Commit": (62.0, 50.0),
    "File": (64.0, 32.0),
    "PullRequest": (66.0, 33.0),
    "default": (60.0, 50.0),
}


def apply_node_size(element: dict) -> dict:
    """Pre-compute render dimensions from the _node_size multiplier on a node.

    If the element's data dict contains a ``_node_size`` float, this function
    writes ``_render_width_px`` and ``_render_height_px`` using per-type base
    dimensions multiplied by ``_node_size``. A legacy ``_render_size_px`` key is
    also written for compatibility with any external consumers expecting it.

    If ``_node_size`` is absent the element is returned unchanged, keeping the
    fixed nodeType sizing intact for all generic graph nodes.

    Args:
        element: A Cytoscape element dict with a ``data`` sub-dict.

    Returns:
        The same element dict, possibly with render dimension fields added.
    """
    data = element.get("data", {})
    node_size = data.get("_node_size")
    if node_size is None:
        return element
    node_type = data.get("nodeType", "default")
    base_width, base_height = BASE_NODE_DIMENSIONS.get(
        node_type,
        BASE_NODE_DIMENSIONS["default"],
    )
    data["_render_width_px"] = round(base_width * node_size, 2)
    data["_render_height_px"] = round(base_height * node_size, 2)
    data["_render_size_px"] = data["_render_width_px"]
    return element
