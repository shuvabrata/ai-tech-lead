"""Unit test — search badge colours must match graph node colours.

Requirement: every entity type rendered as a typed node in the Cytoscape graph
(i.e., has an explicit ``node[nodeType = "X"]`` selector in the graph
stylesheet) must have an identical background colour in the search page's
``_ENTITY_TYPE_BADGE_COLORS`` dict.

This test catches drift caused by:
- Adding a new node type to ``graph/styles.py`` without updating ``search.py``
- Editing a token value in ``styles.py`` and forgetting one of the consumers
- Hardcoding a colour in one place instead of referencing ``TOKENS``

The test is marked ``unit`` and has no external dependencies.
"""

from __future__ import annotations

import re

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from app.dash_app.pages.graph.styles import build_cytoscape_stylesheet
import app.dash_app.pages.search as search_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NODE_TYPE_RE = re.compile(r'node\[nodeType\s*=\s*"([^"]+)"\]')


def _extract_graph_type_colors() -> dict[str, str]:
    """Parse the Cytoscape stylesheet and return {nodeType: background-color}.

    Only selectors that exactly target a single ``nodeType`` value are
    included (i.e. ``node[nodeType = "Page"]`` qualifies; generic ``node``
    or edge selectors are ignored).
    """
    stylesheet = build_cytoscape_stylesheet()
    result: dict[str, str] = {}
    for entry in stylesheet:
        selector = entry.get("selector", "")
        match = _NODE_TYPE_RE.fullmatch(selector.strip())
        if match:
            node_type = match.group(1)
            bg_color = entry.get("style", {}).get("background-color")
            if bg_color:
                result[node_type] = bg_color
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_all_graph_node_types_have_search_badge_color():
    """Every typed graph node must appear in the search badge color map."""
    graph_colors = _extract_graph_type_colors()
    badge_colors = search_module._ENTITY_TYPE_BADGE_COLORS

    missing = [t for t in graph_colors if t not in badge_colors]
    assert not missing, (
        f"These node types have a graph colour but no search badge colour: {missing}. "
        "Add them to _ENTITY_TYPE_BADGE_COLORS in src/app/dash_app/pages/search.py."
    )


@pytest.mark.unit
def test_search_badge_colors_match_graph_colors():
    """For every typed graph node, the search badge colour must be identical."""
    graph_colors = _extract_graph_type_colors()
    badge_colors = search_module._ENTITY_TYPE_BADGE_COLORS

    mismatches = {
        node_type: {"graph": graph_colors[node_type], "search": badge_colors[node_type]}
        for node_type in graph_colors
        if node_type in badge_colors and badge_colors[node_type] != graph_colors[node_type]
    }
    assert not mismatches, (
        "Search badge colours deviate from graph node colours for these types:\n"
        + "\n".join(
            f"  {t}: graph={v['graph']!r}, search={v['search']!r}"
            for t, v in mismatches.items()
        )
        + "\nUpdate _ENTITY_TYPE_BADGE_COLORS in src/app/dash_app/pages/search.py "
        "or the TOKENS in src/app/dash_app/styles.py so both sides match."
    )


@pytest.mark.unit
def test_no_extra_search_badge_colors_use_wrong_token():
    """Search badge colours that are not in the graph stylesheet must still
    come from TOKENS (not arbitrary hardcoded hex strings) — verified by
    checking they are present somewhere in the TOKENS dict values."""
    from app.dash_app.styles import TOKENS

    badge_colors = search_module._ENTITY_TYPE_BADGE_COLORS
    token_values = set(TOKENS.values())

    not_from_tokens = {
        node_type: color
        for node_type, color in badge_colors.items()
        if color not in token_values
    }
    assert not not_from_tokens, (
        "These search badge colours are not derived from TOKENS in styles.py: "
        f"{not_from_tokens}. Use TOKENS['graph.node.*'] keys instead of "
        "hardcoded hex strings."
    )
