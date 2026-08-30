"""Unit tests for the compact page header component (create_page_header)."""

from __future__ import annotations

import pytest

from dash import dcc, html

from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    COLOR_NAVY,
    COMPACT_PAGE_HEADER_STYLE,
)


def _flatten_children(node) -> list:
    """Recursively collect all child nodes into a flat list."""
    seen: list = []

    def walk(item) -> None:
        seen.append(item)
        children = getattr(item, "children", None)
        if children is None:
            return
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        else:
            walk(children)

    walk(node)
    return seen


@pytest.mark.unit
def test_returns_div_with_compact_style() -> None:
    """The header is an html.Div using the compact page header style."""
    header = create_page_header([("Settings", None)])
    assert isinstance(header, html.Div)
    assert header.style == COMPACT_PAGE_HEADER_STYLE


@pytest.mark.unit
def test_clickable_segment_renders_as_link() -> None:
    """Segments with an href render as clickable dcc.Link in navy."""
    header = create_page_header(
        [("Settings", "/app/settings"), ("Graph Styling", None)]
    )
    nodes = _flatten_children(header)
    links = [n for n in nodes if isinstance(n, dcc.Link)]
    assert len(links) == 1
    assert links[0].children == "Settings"
    assert links[0].href == "/app/settings"
    assert links[0].style["color"] == COLOR_NAVY


@pytest.mark.unit
def test_current_page_segment_renders_as_span() -> None:
    """Segments with href=None render as non-clickable spans in charcoal."""
    header = create_page_header(
        [("Settings", "/app/settings"), ("Graph Styling", None)]
    )
    nodes = _flatten_children(header)
    spans = [n for n in nodes if isinstance(n, html.Span)]
    current = [s for s in spans if s.children == "Graph Styling"]
    assert len(current) == 1
    assert current[0].style["color"] == COLOR_CHARCOAL_MEDIUM


@pytest.mark.unit
def test_description_renders_with_separator() -> None:
    """A description is appended after a '|' separator in gray."""
    header = create_page_header(
        [("Settings", None)], "Customize graph colors."
    )
    nodes = _flatten_children(header)
    spans = [n for n in nodes if isinstance(n, html.Span)]
    separators = [s for s in spans if s.children == " | "]
    assert len(separators) == 1
    description = [s for s in spans if s.children == "Customize graph colors."]
    assert len(description) == 1
    assert description[0].style["color"] == COLOR_GRAY_MEDIUM


@pytest.mark.unit
def test_no_description_omits_separator() -> None:
    """When description is None, no '|' separator is rendered."""
    header = create_page_header([("Settings", None)])
    nodes = _flatten_children(header)
    spans = [n for n in nodes if isinstance(n, html.Span)]
    separators = [s for s in spans if s.children == " | "]
    assert separators == []


@pytest.mark.unit
def test_empty_breadcrumb_renders_description_only() -> None:
    """An empty breadcrumb list renders just the description."""
    header = create_page_header([], "Just a description.")
    nodes = _flatten_children(header)
    spans = [n for n in nodes if isinstance(n, html.Span)]
    description = [s for s in spans if s.children == "Just a description."]
    assert len(description) == 1
    # No breadcrumb segments and no '|' separator.
    separators = [s for s in spans if s.children == " | "]
    assert separators == []