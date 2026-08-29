"""Unit tests for the pure graph-theme merge and translation helpers.

Covers:
* ``ALLOWED_SHAPES`` — full Cytoscape set contains the in-use shapes.
* ``merge_theme_overrides`` — override wins; missing keys fall through;
  empty overrides leave the base unchanged.
* ``overrides_to_cytoscape_rules`` — semantic key translation, numeric px,
  shape pass-through.
"""

import pytest

from app.common.graph_theme import (
    ALLOWED_SHAPES,
    EdgeOverride,
    GlobalOverride,
    NodeOverride,
    ThemeOverrides,
    effective_semantic_theme,
    merge_theme_overrides,
    overrides_to_cytoscape_rules,
)
from app.dash_app.pages.graph.styles import build_cytoscape_stylesheet

pytestmark = pytest.mark.unit

# A minimal but representative base token dict, mirroring the structure of the
# hardcoded ``THEME_TOKENS`` graph palette (see dash_app/styles.py).
BASE_LIGHT = {
    "graph.node.default": "#B8B8B8",
    "graph.node.default.border": "#9E9E9E",
    "graph.node.label": "#f4f7fb",
    "graph.node.person": "#3B82F6",
    "graph.node.person.border": "#2563EB",
    "graph.node.project": "#F59E0B",
    "graph.node.project.border": "#D97706",
    "graph.edge.default": "#C0C0C0",
    "graph.selection": "#424242",
    "text.secondary": "#2d3748",
    "surface.base": "#ffffff",
}


def test_allowed_shapes_include_in_use():
    """Every shape referenced by the actual stylesheet is in ALLOWED_SHAPES.

    Derives the in-use shapes from ``build_cytoscape_stylesheet()`` at test
    time rather than maintaining a separate constant, so the check cannot
    drift from the real stylesheet.
    """
    stylesheet = build_cytoscape_stylesheet()
    in_use = {
        rule["style"]["shape"]
        for rule in stylesheet
        if rule.get("selector", "").startswith("node")
        and "shape" in rule.get("style", {})
    }
    assert in_use
    assert in_use <= set(ALLOWED_SHAPES)


def test_allowed_shapes_full_cyto_set():
    """The allowed set is the full Cytoscape vocabulary."""
    expected = {
        "ellipse", "triangle", "round-triangle", "rectangle", "round-rectangle",
        "bottom-round-rectangle", "cut-rectangle", "barrel", "rhomboid",
        "diamond", "round-diamond", "pentagon", "round-pentagon", "hexagon",
        "round-hexagon", "concave-hexagon", "heptagon", "round-heptagon",
        "octagon", "round-octagon", "star", "tag", "round-tag", "vee",
    }
    assert set(ALLOWED_SHAPES) == expected


def test_legend_glyph_parity_all_shapes():
    """Every non-ellipse ALLOWED_SHAPES entry has a distinct glyph.

    ``get_shape_css`` falls back to a plain ellipse (``borderRadius: 50%``) for
    unknown shapes. ``ellipse`` and ``circle`` intentionally share that
    fallback, so they are excluded; every other shape must produce a glyph
    with a ``clip-path`` (or a non-ellipse ``borderRadius``), guarding against
    silently regressing when a shape is added without a legend glyph.
    """
    from app.dash_app.pages.graph.utils.ui_components import get_shape_css

    for shape in ALLOWED_SHAPES:
        if shape in ("ellipse", "circle"):
            continue
        glyph = get_shape_css(shape)
        has_clip = "clipPath" in glyph
        has_rounding = glyph.get("borderRadius") not in (None, "50%")
        assert has_clip or has_rounding, f"Missing legend glyph for shape '{shape}'"


def test_merge_empty_overrides_returns_base():
    """Empty overrides must leave the effective theme equal to the base."""
    merged = merge_theme_overrides(BASE_LIGHT, ThemeOverrides())
    assert merged["nodes"]["Person"]["background-color"] == "#3B82F6"
    assert merged["nodes"]["Person"]["shape"] == "ellipse"  # base fallback
    assert merged["nodes"]["default"]["background-color"] == "#B8B8B8"


def test_merge_override_wins_over_base():
    """An explicit override replaces the base value."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(color="#00FF00", shape="diamond")}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    person = merged["nodes"]["Person"]
    assert person["background-color"] == "#00FF00"
    assert person["shape"] == "diamond"
    # Unoverridden props fall through to base.
    assert person["border-color"] == "#2563EB"


def test_merge_missing_keys_fall_through():
    """Unspecified node types / properties inherit the base."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(width=80, height=60)}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    person = merged["nodes"]["Person"]
    assert person["width"] == "80px"
    assert person["height"] == "60px"
    assert person["background-color"] == "#3B82F6"  # untouched
    # A node type with no override maps to base entirely.
    project = merged["nodes"]["Project"]
    assert project["background-color"] == "#F59E0B"


def test_merge_default_node_override():
    """An override for the untyped default node applies to the generic node."""
    overrides = ThemeOverrides(
        nodes={"default": NodeOverride(color="#CCCCCC")}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    assert merged["nodes"]["default"]["background-color"] == "#CCCCCC"


def test_merge_edges_and_global():
    """Edge and global overrides compose over base values."""
    overrides = ThemeOverrides(
        edges=EdgeOverride(line_color="#999999", width=3),
        global_=GlobalOverride(selection_color="#FFAA00"),
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    assert merged["edges"]["line-color"] == "#999999"
    assert merged["edges"]["width"] == 3
    assert merged["global"]["selection_color"] == "#FFAA00"
    # Unoverridden edge/global values fall through.
    assert merged["edges"]["color"] == "#2d3748"
    assert merged["global"]["node_label_color"] == "#f4f7fb"


def test_merge_accepts_raw_dict():
    """merge_theme_overrides accepts a raw override doc (the JSONB shape)."""
    raw = {
        "nodes": {"Person": {"color": "#00FF00", "width": 70, "height": 60}},
        "edges": {"line_color": "#888888"},
        "global": {"node_label_color": "#111111"},
    }
    merged = merge_theme_overrides(BASE_LIGHT, raw)
    person = merged["nodes"]["Person"]
    assert person["background-color"] == "#00FF00"
    assert person["width"] == "70px"
    assert merged["edges"]["line-color"] == "#888888"
    assert merged["global"]["node_label_color"] == "#111111"


def _rules_for(merged):
    return {
        rule["selector"]: rule["style"]
        for rule in overrides_to_cytoscape_rules(merged)
    }


def test_rules_translate_semantic_key():
    """Semantic ``color`` maps to Cytoscape ``background-color``."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(color="#00FF00")}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    rules = _rules_for(merged)
    person_rule = rules['node[nodeType = "Person"]']
    assert person_rule["background-color"] == "#00FF00"


def test_rules_numeric_px_string():
    """Numeric widths become ``"NNpx"`` strings in the Cytoscape rule."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(width=80, height=60)}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    rules = _rules_for(merged)
    person_rule = rules['node[nodeType = "Person"]']
    assert person_rule["width"] == "80px"
    assert person_rule["height"] == "60px"


def test_rules_shape_passes_through():
    """``shape`` passes through unchanged."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(shape="diamond")}
    )
    merged = merge_theme_overrides(BASE_LIGHT, overrides)
    rules = _rules_for(merged)
    assert rules['node[nodeType = "Person"]']["shape"] == "diamond"


def test_rules_include_generic_edge_selected():
    """Rules contain the generic node, edge, and selected selectors."""
    merged = merge_theme_overrides(BASE_LIGHT, ThemeOverrides())
    rules = _rules_for(merged)
    assert "node" in rules
    assert "edge" in rules
    assert "node:selected" in rules
    assert rules["node"]["background-color"] == "#B8B8B8"


def test_rules_complete_for_all_types():
    """Every node type yields a rule after merge."""
    merged = merge_theme_overrides(BASE_LIGHT, ThemeOverrides())
    rules = _rules_for(merged)
    for node_type in ("Person", "Project", "Branch"):
        assert f'node[nodeType = "{node_type}"]' in rules


# ── effective_semantic_theme (editor-facing full snapshot) ────────────


def test_effective_semantic_empty_is_full_base():
    """Empty overrides still produce a full concrete doc (no blanks)."""
    eff = effective_semantic_theme(BASE_LIGHT, ThemeOverrides())
    person = eff["nodes"]["Person"]
    assert person["color"] == "#3B82F6"
    assert person["border"] == "#2563EB"
    assert person["border_width"] == 0  # base nodes are borderless
    assert person["shape"] == "ellipse"
    assert isinstance(person["width"], int)
    assert isinstance(person["height"], int)
    # Untyped default node present with concrete values.
    assert eff["nodes"]["default"]["color"] == "#B8B8B8"
    # Edges + global concrete.
    assert eff["edges"]["line_color"] == "#C0C0C0"
    assert eff["global"]["node_label_color"] == "#f4f7fb"


def test_effective_semantic_applies_override():
    """Overrides win and are reflected in semantic space."""
    overrides = ThemeOverrides(
        nodes={"Person": NodeOverride(color="#00FF00", shape="diamond", width=80)},
        edges=EdgeOverride(line_color="#888888"),
        global_=GlobalOverride(selection_color="#FFAA00"),
    )
    eff = effective_semantic_theme(BASE_LIGHT, overrides)
    person = eff["nodes"]["Person"]
    assert person["color"] == "#00FF00"
    assert person["shape"] == "diamond"
    assert person["width"] == 80
    assert eff["edges"]["line_color"] == "#888888"
    assert eff["global"]["selection_color"] == "#FFAA00"


def test_effective_semantic_includes_all_node_types():
    """The snapshot covers every node type (full immunity)."""
    eff = effective_semantic_theme(BASE_LIGHT, ThemeOverrides())
    from app.common.graph_theme import NODE_TYPES

    assert set(eff["nodes"].keys()) == set(NODE_TYPES)