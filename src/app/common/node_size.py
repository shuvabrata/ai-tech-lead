"""Node sizing utilities shared between the analytics pipeline and the Dash UI.

Kept in app/common to avoid circular imports: both the collaboration algorithm
(app/analytics/...) and the Dash data-transform (app/dash_app/...) need these
helpers, but the analytics layer must not import from the Dash layer.
"""

# Default node sizes in pixels, keyed by nodeType string.
# Used as the base for _node_size multiplier calculations so that
# dynamic sizing respects each type's proportional baseline.
# Keep in sync with the fixed width/height values in
# app/dash_app/pages/graph/styles.py :: build_cytoscape_stylesheet.
BASE_NODE_SIZES: dict[str, float] = {
    "Person":     65.0,
    "Project":    70.0,
    "Branch":     55.0,
    "Epic":       65.0,
    "Issue":      55.0,
    "Repository": 65.0,
    "default":    60.0,
}


def apply_node_size(element: dict) -> dict:
    """Pre-compute _render_size_px from the _node_size multiplier on a node element.

    If the element's data dict contains a ``_node_size`` float, this function
    writes ``_render_size_px = BASE_NODE_SIZES[nodeType] * _node_size`` back into
    the data dict so the Cytoscape stylesheet can apply it via a plain data accessor
    (``width: 'data(_render_size_px)'``) without any in-stylesheet arithmetic.

    If ``_node_size`` is absent the element is returned unchanged, keeping the
    fixed nodeType sizing intact for all generic graph nodes.

    Args:
        element: A Cytoscape element dict with a ``data`` sub-dict.

    Returns:
        The same element dict, possibly with ``_render_size_px`` added to data.
    """
    data = element.get("data", {})
    node_size = data.get("_node_size")
    if node_size is None:
        return element
    node_type = data.get("nodeType", "default")
    base = BASE_NODE_SIZES.get(node_type, BASE_NODE_SIZES["default"])
    data["_render_size_px"] = round(base * node_size, 2)
    return element
