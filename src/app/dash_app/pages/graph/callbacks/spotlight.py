"""Graph Node Spotlight Callbacks (C3)

Live spotlight search: debounce the input (400 ms, min 3 chars), call the
ES search API via the service layer, intersect results with the loaded graph
nodes via wba_id, then apply spotlight-match / spotlight-dim
CSS classes to all Cytoscape elements.
"""

from dash import Input, Output, State, callback, clientside_callback
from dash.exceptions import PreventUpdate

from app.api.search.v1 import service as search_service
from app.api.search.v1.model import SearchRequest
from common.logger import logger
from ..utils import is_node_data

_MIN_QUERY_LENGTH = 3

# ---------------------------------------------------------------------------
# Clientside debounce: raw input value → debounced store (400 ms)
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(value) {
        if (window._spotlightTimer) {
            clearTimeout(window._spotlightTimer);
        }
        return new Promise(function(resolve) {
            window._spotlightTimer = setTimeout(function() {
                resolve(value !== undefined ? value : '');
            }, 400);
        });
    }
    """,
    Output("spotlight-debounced-store", "data"),
    Input("graph-spotlight-input", "value"),
    prevent_initial_call=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_spotlight_classes(elements, match_wba_ids):
    """Add spotlight-match / spotlight-dim classes to Cytoscape elements.

    When match_wba_ids is None, all spotlight-* classes are stripped (clear mode).
    For edges: spotlight-match when both endpoints match, otherwise spotlight-dim.
    """
    # Pass 1 (nodes only): collect Cytoscape element ids that match
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
        # Preserve all non-spotlight classes (filter, community, etc.)
        classes = {c for c in existing.split() if c and not c.startswith("spotlight-")}

        if match_wba_ids is not None:
            if is_node_data(data):
                if data.get("wba_id", "") in match_wba_ids:
                    classes.add("spotlight-match")
                else:
                    classes.add("spotlight-dim")
            else:
                # Edge: match only when both endpoints match
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
    Output("graph-cytoscape", "elements", allow_duplicate=True),
    Output("graph-spotlight-count", "children"),
    Input("spotlight-debounced-store", "data"),
    State("graph-cytoscape", "elements"),
    prevent_initial_call=True,
)
def update_spotlight(query: str | None, elements: list | None):
    """Apply spotlight highlighting to graph nodes based on ES search results."""
    if not elements:
        raise PreventUpdate

    # Clear spotlight when query is below the minimum length
    if not query or len(query.strip()) < _MIN_QUERY_LENGTH:
        cleared = _apply_spotlight_classes(elements, None)
        return cleared, ""

    q = query.strip()

    try:
        response = search_service.search(SearchRequest(q=q, page_size=100))
    except Exception as exc:
        logger.warning(f"[Spotlight] Search failed for query {q!r}: {exc}")
        raise PreventUpdate

    match_wba_ids = {r.wba_id for r in response.results}

    node_count = sum(1 for elem in elements if is_node_data(elem.get("data", {})))
    match_count = sum(
        1
        for elem in elements
        if is_node_data(elem.get("data", {}))
        and elem["data"].get("wba_id", "") in match_wba_ids
    )

    updated = _apply_spotlight_classes(elements, match_wba_ids)
    count_text = f"{match_count} of {node_count} nodes match" if node_count > 0 else ""
    return updated, count_text
