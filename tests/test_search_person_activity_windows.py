"""Unit test — Person "activity" time-window deep-links on the Search page.

Requirement: when a search result is a ``Person``, the result card renders
three extra buttons ("24 hrs", "7 days", "30 days") below "View in Graph".
Clicking each deep-links to the Graph page with a time-windowed Cypher query
that surfaces the Person's "hot neighbourhood". Non-Person results must not
render these buttons.

The Cypher must:
- anchor on the Person (``MATCH (n {id: '...'})``),
- keep the anchor even when no neighbour falls in the window
  (``OPTIONAL MATCH``),
- filter on neighbour ``_last_updated_at`` OR ``_created_at`` OR the
  interaction edge ``last_interaction_at``,
- use the correct rolling duration per window,
- cap results at ``LIMIT 50``.

These tests are marked ``unit`` and have no external dependencies.
"""

from __future__ import annotations

import pytest

from dash import html
import dash_bootstrap_components as dbc

import app.dash_app.pages.search as search_module
from app.dash_app.pages.search import (
    _PERSON_ACTIVITY_WINDOWS,
    _build_person_activity_cypher,
)


_WBA_ID = "github::Person::shuvabrata"


# ---------------------------------------------------------------------------
# Cypher builder
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_person_activity_cypher_anchors_person():
    q = _build_person_activity_cypher(_WBA_ID, "P7D")
    assert f"MATCH (n {{id: '{_WBA_ID}'}})" in q


@pytest.mark.unit
def test_build_person_activity_cypher_uses_optional_match():
    q = _build_person_activity_cypher(_WBA_ID, "P7D")
    assert "OPTIONAL MATCH (n)-[r]-(m)" in q


@pytest.mark.unit
def test_build_person_activity_cypher_filters_node_and_edge_timestamps():
    q = _build_person_activity_cypher(_WBA_ID, "P7D")
    assert "m._last_updated_at >= datetime() - duration('P7D')" in q
    assert "m._created_at >= datetime() - duration('P7D')" in q
    assert "r.last_interaction_at >= datetime() - duration('P7D')" in q


@pytest.mark.unit
def test_build_person_activity_cypher_caps_limit():
    q = _build_person_activity_cypher(_WBA_ID, "P30D")
    assert "LIMIT 50" in q


@pytest.mark.unit
def test_activity_windows_are_exactly_three_in_order():
    labels = [label for label, _ in _PERSON_ACTIVITY_WINDOWS]
    durations = [duration for _, duration in _PERSON_ACTIVITY_WINDOWS]
    assert labels == ["24 hrs", "7 days", "30 days"]
    assert durations == ["PT24H", "P7D", "P30D"]


@pytest.mark.unit
def test_each_window_produces_distinct_duration_literal():
    for _label, duration in _PERSON_ACTIVITY_WINDOWS:
        q = _build_person_activity_cypher(_WBA_ID, duration)
        assert f"duration('{duration}')" in q


# ---------------------------------------------------------------------------
# Result card rendering
# ---------------------------------------------------------------------------

def _render_card(wba_id: str) -> html.Div:
    """Render a search result card for the given wba_id as a Person/other."""
    return search_module._build_result_card(
        {"wba_id": wba_id, "attributes": {"full_name": "Shuva"}}, full=False
    )


def _collect_buttons(card: html.Div) -> list[dbc.Button]:
    """Recursively collect dbc.Button instances from a Dash component tree."""
    buttons: list[dbc.Button] = []

    def walk(component):
        if isinstance(component, dbc.Button):
            buttons.append(component)
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif children is not None:
            walk(children)

    walk(card)
    return buttons


def _button_label(button: dbc.Button) -> str | None:
    """Extract a button's textual label (its first child, if a string)."""
    if isinstance(button.children, str):
        return button.children
    if isinstance(button.children, (list, tuple)) and button.children:
        first = button.children[0]
        return first if isinstance(first, str) else None
    return None


@pytest.mark.unit
def test_person_card_renders_three_activity_buttons():
    card = _render_card(_WBA_ID)
    labels = {_button_label(b) for b in _collect_buttons(card)}
    assert {"24 hrs", "7 days", "30 days"} <= labels


@pytest.mark.unit
def test_non_person_card_renders_no_activity_buttons():
    card = _render_card("github::Issue::123")
    labels = {_button_label(b) for b in _collect_buttons(card)}
    assert labels.isdisjoint({"24 hrs", "7 days", "30 days"})


@pytest.mark.unit
def test_activity_button_links_to_graph_with_cypher_param():
    card = _render_card(_WBA_ID)
    activity_buttons = [
        b for b in _collect_buttons(card)
        if _button_label(b) in ("24 hrs", "7 days", "30 days")
    ]
    assert len(activity_buttons) == 3
    for button in activity_buttons:
        assert button.href is not None
        assert button.href.startswith("/app/graph?cypher=")
        assert "MATCH" in button.href  # URL-encoded query is present
