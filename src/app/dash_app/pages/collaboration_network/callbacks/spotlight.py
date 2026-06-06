"""Collaboration Network spotlight callbacks.

Live spotlight search: debounce the input (400 ms, min 3 chars), perform a
client-side case-insensitive substring match against the person fields already
stored in the Cytoscape elements (label, full_name, name, email, login), then
apply spotlight-match / spotlight-dim CSS classes to all Cytoscape elements —
composing on top of any active filter classes.

Client-side matching is used instead of Elasticsearch because the collab
network loads 1000+ nodes and sending that many wba_ids in an ES terms filter
causes ES to return the total count but silently drop the hits array.  The
person fields required for spotlight (name, email) are already present in the
element data returned by the collaboration score query, so no ES round-trip is
needed.
"""

from dash import Input, Output, State, callback, clientside_callback
from dash.exceptions import PreventUpdate

from app.dash_app.pages.graph.utils import is_node_data
from common.logger import logger


_MIN_QUERY_LENGTH = 3

# Fields searched in priority order for each Person node.
_SEARCH_FIELDS = ("label", "full_name", "name", "login", "email")


# ---------------------------------------------------------------------------
# Clientside debounce: raw input value → debounced store (400 ms)
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(value) {
        if (window._collabSpotlightTimer) {
            clearTimeout(window._collabSpotlightTimer);
        }
        return new Promise(function(resolve) {
            window._collabSpotlightTimer = setTimeout(function() {
                resolve(value !== undefined ? value : '');
            }, 400);
        });
    }
    """,
    Output("collab-spotlight-debounced-store", "data"),
    Input("collab-spotlight-input", "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_node(data: dict, query_lower: str) -> bool:
    """Return True if any searchable field in node data contains query_lower."""
    for field in _SEARCH_FIELDS:
        val = data.get(field)
        if val and query_lower in str(val).lower():
            return True
    return False


def _apply_spotlight_classes(elements, match_wba_ids):
    """Add spotlight-match / spotlight-dim classes to Cytoscape elements.

    When match_wba_ids is None, all spotlight-* classes are stripped (clear mode).
    For edges: spotlight-match when both endpoints match, otherwise spotlight-dim.
    Non-spotlight classes (e.g. dimmed, community) are preserved.
    """
    # Pass 1 (nodes only): collect Cytoscape element ids of matching nodes
    matching_cyto_ids: set = set()
    if match_wba_ids is not None:
        for elem in (elements or []):
            data = elem.get("data", {})
            if is_node_data(data) and data.get("wba_id", "") in match_wba_ids:
                matching_cyto_ids.add(data.get("id", ""))

    modified = []
    for elem in (elements or []):
        data = elem.get("data", {})
        existing = elem.get("classes", "")
        # Preserve all non-spotlight classes (dimmed, community, filter, etc.)
        classes = {c for c in existing.split() if c and not c.startswith("spotlight-")}

        if match_wba_ids is not None:
            if is_node_data(data):
                if data.get("wba_id", "") in match_wba_ids:
                    classes.add("spotlight-match")
                else:
                    classes.add("spotlight-dim")
            else:
                # Edge: match only when both endpoints are in matching nodes
                src = data.get("source", "")
                tgt = data.get("target", "")
                if src in matching_cyto_ids and tgt in matching_cyto_ids:
                    classes.add("spotlight-match")
                else:
                    classes.add("spotlight-dim")

        modified.append({**elem, "classes": " ".join(sorted(classes))})
    return modified


# ---------------------------------------------------------------------------
# Server-side spotlight callback
# ---------------------------------------------------------------------------

@callback(
    Output("collab-cytoscape", "elements", allow_duplicate=True),
    Output("collab-spotlight-count", "children"),
    Input("collab-spotlight-debounced-store", "data"),
    State("collab-cytoscape", "elements"),
    prevent_initial_call=True,
)
def update_collab_spotlight(query: str | None, elements: list | None):
    """Apply spotlight highlighting to collab nodes using client-side field matching."""
    if not elements:
        raise PreventUpdate

    # Clear spotlight when query is below the minimum length
    if not query or len(query.strip()) < _MIN_QUERY_LENGTH:
        cleared = _apply_spotlight_classes(elements, None)
        return cleared, ""

    q = query.strip()
    q_lower = q.lower()

    node_elements = [e for e in elements if is_node_data(e.get("data", {}))]

    match_wba_ids = {
        e["data"]["wba_id"]
        for e in node_elements
        if e["data"].get("wba_id") and _match_node(e["data"], q_lower)
    }

    node_count = len(node_elements)
    match_count = len(match_wba_ids)

    logger.info(
        "[Collab Spotlight] query=%r  node_count=%d  match_count=%d",
        q,
        node_count,
        match_count,
    )

    updated = _apply_spotlight_classes(elements, match_wba_ids)
    count_text = f"{match_count} of {node_count} nodes match" if node_count > 0 else ""
    return updated, count_text


    updated = _apply_spotlight_classes(elements, match_wba_ids)
    count_text = f"{match_count} of {node_count} nodes match" if node_count > 0 else ""
    return updated, count_text
