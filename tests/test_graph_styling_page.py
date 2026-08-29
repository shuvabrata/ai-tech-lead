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


# ── Phase 4.2 — editor layout ──────────────────────────────────────────


def _collect(node):
    """Flatten a Dash component tree into a list of all nested components."""
    results = [node]
    children = getattr(node, "children", None)
    if children is None:
        return results
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "id"):
                results.extend(_collect(child))
    elif hasattr(children, "children") or hasattr(children, "id"):
        results.extend(_collect(children))
    return results


@pytest.mark.unit
def test_layout_has_two_base_mode_tabs() -> None:
    """The editor renders base modes as tabs (Light + Dark)."""
    layout = get_layout()
    sections = [
        n for n in _collect(layout)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "gs-base-section"
    ]
    themes = {n.id["base_theme"] for n in sections}
    assert themes == {"executive-light", "executive-dark"}


@pytest.mark.unit
def test_layout_has_node_type_rows_per_section() -> None:
    """Each base-mode section renders a node-type row per type (excluding default)."""
    from app.common.graph_theme import NODE_TYPES

    expected = {nt for nt in NODE_TYPES if nt != "default"}
    layout = get_layout()
    rows = [
        n for n in _collect(layout)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "gs-node-row"
    ]
    for base_theme in ("executive-light", "executive-dark"):
        per_theme = {
            n.id["node_type"] for n in rows if n.id["base_theme"] == base_theme
        }
        assert per_theme == expected


@pytest.mark.unit
def test_layout_has_edges_and_global_cards() -> None:
    """Each base-mode section includes an Edges card and a Global card."""
    layout = get_layout()
    cards = [
        n for n in _collect(layout)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") in ("gs-edges-card", "gs-global-card")
    ]
    for base_theme in ("executive-light", "executive-dark"):
        kinds = {
            n.id["type"]
            for n in cards
            if n.id["base_theme"] == base_theme
        }
        assert kinds == {"gs-edges-card", "gs-global-card"}


@pytest.mark.unit
def test_node_row_has_all_six_fields() -> None:
    """Each node-type row exposes fill/border/border-width/shape/width/height."""
    from app.dash_app.pages.settings.graph_styling.components import (
        build_node_type_row,
    )

    row = build_node_type_row("executive-light", "Person")
    fields = [
        n for n in _collect(row)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "gs-node-field"
    ]
    assert {n.id["field"] for n in fields} == {
        "color",
        "border",
        "border_width",
        "shape",
        "width",
        "height",
    }


# ── Phase 4.3 — per-row live preview glyph ─────────────────────────────


@pytest.mark.unit
def test_each_row_has_glyph() -> None:
    """Each node-type row carries an inline preview glyph."""
    from app.common.graph_theme import NODE_TYPES

    expected = {nt for nt in NODE_TYPES if nt != "default"}
    layout = get_layout()
    glyphs = [
        n for n in _collect(layout)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "gs-node-glyph"
    ]
    for base_theme in ("executive-light", "executive-dark"):
        per_theme = {
            n.id["node_type"] for n in glyphs if n.id["base_theme"] == base_theme
        }
        assert per_theme == expected


@pytest.mark.unit
def test_glyph_style_reflects_override() -> None:
    """The glyph style reflects fill/border/shape/size."""
    from app.dash_app.pages.settings.graph_styling.callbacks import (
        build_glyph_style,
    )

    style = build_glyph_style(
        fill="#00FF00",
        border="#008800",
        border_width=3,
        shape="diamond",
        width=80,
        height=60,
    )
    assert style["backgroundColor"] == "#00FF00"
    assert "3px solid #008800" in style["border"]
    assert "clipPath" in style  # diamond uses clip-path


@pytest.mark.unit
def test_glyph_style_preserves_aspect_ratio() -> None:
    """Wide nodes render wider; tall nodes render taller (aspect preserved)."""
    from app.dash_app.pages.settings.graph_styling.callbacks import (
        build_glyph_style,
    )

    wide = build_glyph_style("#000000", None, 0, "rectangle", 120, 60)
    tall = build_glyph_style("#000000", None, 0, "rectangle", 60, 120)

    wide_w, wide_h = float(wide["width"].rstrip("px")), float(wide["height"].rstrip("px"))
    tall_w, tall_h = float(tall["width"].rstrip("px")), float(tall["height"].rstrip("px"))

    assert wide_w > wide_h  # wide node is wider than tall
    assert tall_h > tall_w  # tall node is taller than wide
    # Aspect ratios match the input ratio (120:60 == 2:1, 60:120 == 1:2).
    assert abs((wide_w / wide_h) - 2.0) < 0.05
    assert abs((tall_h / tall_w) - 2.0) < 0.05


@pytest.mark.unit
def test_glyph_style_uses_defaults_when_unset() -> None:
    """Unset fields fall back to defaults and never error."""
    from app.dash_app.pages.settings.graph_styling.callbacks import (
        build_glyph_style,
    )

    style = build_glyph_style(None, None, None, None, None, None)
    assert style["backgroundColor"] == "#B8B8B8"
    assert style["width"]  # non-empty string


@pytest.mark.unit
def test_each_row_has_reset_button() -> None:
    """Each node-type row carries a reset button."""
    from app.common.graph_theme import NODE_TYPES

    expected = {nt for nt in NODE_TYPES if nt != "default"}
    layout = get_layout()
    resets = [
        n for n in _collect(layout)
        if isinstance(getattr(n, "id", None), dict)
        and n.id.get("type") == "gs-node-reset"
    ]
    for base_theme in ("executive-light", "executive-dark"):
        per_theme = {
            n.id["node_type"] for n in resets if n.id["base_theme"] == base_theme
        }
        assert per_theme == expected


@pytest.mark.unit
def test_reset_clears_all_fields() -> None:
    """The reset callback returns None (unset) for all six fields."""
    from app.dash_app.pages.settings.graph_styling.callbacks import (
        reset_node_row,
    )

    result = reset_node_row(1)
    assert result == (None, None, None, None, None, None)
