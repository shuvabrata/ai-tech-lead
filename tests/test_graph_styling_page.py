"""Tests for the Graph Styling settings page (Plan 017, Phase 4.1)."""

from __future__ import annotations

import pytest

from dash import html

from app.dash_app.pages.settings.graph_styling import get_layout
from app.dash_app.pages.settings.graph_styling import callbacks  # noqa: F401


@pytest.mark.unit
def test_layout_returns_div_shell() -> None:
    """The placeholder layout returns a valid html.Div shell."""
    layout = get_layout()
    assert isinstance(layout, html.Div)


@pytest.mark.unit
def test_layout_contains_header_and_breadcrumb() -> None:
    """The placeholder layout includes a breadcrumb link and page header."""
    layout = get_layout()

    # Traverse all component nodes generically.
    seen: list = []

    def walk(node) -> None:
        seen.append(node)
        children = getattr(node, "children", None)
        if children is None:
            return
        if isinstance(children, (list, tuple)):
            for child in children:
                if hasattr(child, "children") or hasattr(child, "href"):
                    walk(child)
        elif hasattr(children, "children") or hasattr(children, "href"):
            walk(children)

    walk(layout)

    # Breadcrumb "Settings" link present with expected href.
    links = [n for n in seen if getattr(n, "href", None) == "/app/settings"]
    assert len(links) >= 1

    # Page header text "Graph Styling" present.
    texts = [
        getattr(n, "children", "")
        for n in seen
        if isinstance(getattr(n, "children", None), str)
    ]
    assert "Graph Styling" in texts


@pytest.mark.unit
def test_package_import_registers_callbacks_without_error() -> None:
    """Importing the package does not raise and exposes get_layout."""
    from app.dash_app.pages.settings import graph_styling

    assert callable(graph_styling.get_layout)
    assert callable(callbacks) or callbacks is not None
