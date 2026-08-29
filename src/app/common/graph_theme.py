"""Graph theme overrides: pure merge + translation helpers.

This module is the single source of truth for how user-configurable graph
theme overrides (stored in the ``graph_themes`` table) are combined with the
hardcoded base tokens defined in ``app.dash_app.styles`` (``THEME_TOKENS``)
and turned into Cytoscape rules.

**Pure by design.** Nothing in this module imports from ``dash_app`` (or any
other UI layer). Base tokens are passed in as arguments so the module can run
in isolation (unit tests, API layer, connectors) and so the hardcoded base
palette can evolve independently.

Key concepts:

* **Deltas only** — a theme row stores only the properties it changes. The
  base tokens remain the single source of truth; the effective theme is
  always ``base_tokens ⊕ overrides``.
* **Semantic keys** — e.g. ``color`` ↔ Cytoscape ``background-color``. The
  translation from semantic key to Cytoscape property happens once, here.
* **Numeric px** — dimensions are stored as plain ints (no ``"px"`` suffix)
  and rendered as e.g. ``"80px"`` strings by :func:`overrides_to_cytoscape_rules`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The override-aware nodeType keys mirror the existing nodeType values used by
# the graph page (see ``build_cytoscape_stylesheet`` in
# ``app.dash_app.pages.graph.styles``), plus ``default`` for untyped nodes.
NODE_TYPES: tuple[str, ...] = (
    "Person",
    "Project",
    "Issue",
    "Epic",
    "Repository",
    "Branch",
    "Team",
    "IdentityMapping",
    "Initiative",
    "Sprint",
    "Commit",
    "File",
    "PullRequest",
    "Space",
    "Page",
    "Blogpost",
    "default",
)

# Full Cytoscape node shape set. See
# https://js.cytoscape.org/#style/node-body. This is the complete vocabulary a
# user may select for a node type in a graph theme.
ALLOWED_SHAPES: tuple[str, ...] = (
    "ellipse",
    "triangle",
    "round-triangle",
    "rectangle",
    "round-rectangle",
    "bottom-round-rectangle",
    "cut-rectangle",
    "barrel",
    "rhomboid",
    "diamond",
    "round-diamond",
    "pentagon",
    "round-pentagon",
    "hexagon",
    "round-hexagon",
    "concave-hexagon",
    "heptagon",
    "round-heptagon",
    "octagon",
    "round-octagon",
    "star",
    "tag",
    "round-tag",
    "vee",
)

# Semantic → Cytoscape property mapping for node overrides.
# ``color`` is the semantic name; the mapped value is the Cytoscape style key.
NODE_SEMANTIC_TO_CYTO: dict[str, str] = {
    "color": "background-color",
    "border": "border-color",
    "border_width": "border-width",
    "shape": "shape",
    "width": "width",
    "height": "height",
}

# Edge override keys → Cytoscape style keys.
EDGE_SEMANTIC_TO_CYTO: dict[str, str] = {
    "line_color": "line-color",
    "width": "width",
    "arrow_shape": "target-arrow-shape",
    "label_color": "color",
}

# Global override keys → Cytoscape style keys. ``node_label_color`` is the
# text colour applied to node labels; ``edge_label_background`` backs the edge
# label text. ``selection_color`` colors the :selected border.
GLOBAL_SEMANTIC_TO_CYTO: dict[str, str] = {
    "node_label_color": "color",
    "selection_color": "border-color",
    "edge_label_background": "text-background-color",
}


@dataclass(frozen=True)
class NodeOverride:
    """Per-nodeType visual override.

    All fields are optional; only present fields are merged over the base.
    ``width`` and ``height`` are plain numeric pixels.
    """

    color: str | None = None
    border: str | None = None
    border_width: int | None = None
    shape: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class EdgeOverride:
    """Edge-level visual override (applies to all edges)."""

    line_color: str | None = None
    width: int | None = None
    arrow_shape: str | None = None
    label_color: str | None = None


@dataclass(frozen=True)
class GlobalOverride:
    """Global (across node/edge) visual overrides."""

    node_label_color: str | None = None
    selection_color: str | None = None
    edge_label_background: str | None = None


@dataclass(frozen=True)
class ThemeOverrides:
    """Parsed, validated override document for a single theme.

    Mirrors the JSONB ``overrides`` column contract:

    .. code-block:: json

        {
          "nodes": {"Person": {"color": "#00FF00", ...}, "default": {...}},
          "edges": {"line_color": "#999999", ...},
          "global": {...}
        }
    """

    nodes: dict[str, NodeOverride] = field(default_factory=dict)
    edges: EdgeOverride = field(default_factory=EdgeOverride)
    global_: GlobalOverride = field(default_factory=GlobalOverride)


def _is_valid_hex(color: str) -> bool:
    """Return True if ``color`` is ``#RGB`` or ``#RRGGBB`` hexadecimal."""
    text = color[1:] if color.startswith("#") else color
    if len(text) not in (3, 6):
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


def validate_hex_color(color: str) -> None:
    """Raise ``ValueError`` if ``color`` is not a valid hex colour."""
    if not _is_valid_hex(color):
        raise ValueError(
            f"Invalid hex color {color!r}: expected #RGB or #RRGGBB."
        )


def _node_type_key(node_type: str) -> str:
    """Lowercase a node type for lookup against token names.

    Base tokens use snake_case keys derived from the nodeType (e.g. the
    ``Person`` nodeType maps to ``graph.node.person``).
    """
    node_type = node_type.strip()
    if not node_type:
        raise ValueError("Node type must not be empty.")
    if node_type not in NODE_TYPES:
        raise ValueError(
            f"Unknown node type {node_type!r}. "
            f"Allowed: {', '.join(NODE_TYPES)}"
        )
    if node_type == "default":
        return "default"
    snake = "".join(
        f"_{ch.lower()}" if ch.isupper() else ch for ch in node_type
    ).lstrip("_")
    return snake


def merge_node_override(base: dict[str, Any], override: NodeOverride) -> dict[str, Any]:
    """Merge a single node type's override onto its base properties.

    Only fields explicitly set on ``override`` (non-``None``) replace values in
    ``base``. Returns a new dict; ``base`` is not mutated.
    """
    merged = dict(base)
    if override.color is not None:
        merged["background-color"] = override.color
    if override.border is not None:
        merged["border-color"] = override.border
    if override.border_width is not None:
        merged["border-width"] = f"{override.border_width}px"
    if override.shape is not None:
        merged["shape"] = override.shape
    if override.width is not None:
        merged["width"] = f"{override.width}px"
    if override.height is not None:
        merged["height"] = f"{override.height}px"
    return merged


def _base_node_properties(
    node_type: str, base_tokens: dict[str, str]
) -> dict[str, Any]:
    """Extract the base-rule properties for ``node_type`` from token dict.

    Provides defaults for every configurable node property so that partial
    overrides compose cleanly even when a base rule omits a key.
    """
    if node_type == "default":
        color = base_tokens.get("graph.node.default", "#B8B8B8")
        border = base_tokens.get("graph.node.default.border", "#9E9E9E")
    else:
        token_key = _node_type_key(node_type)
        color = base_tokens.get(
            f"graph.node.{token_key}", base_tokens.get("graph.node.default", "#B8B8B8")
        )
        border = base_tokens.get(
            f"graph.node.{token_key}.border",
            base_tokens.get("graph.node.default.border", "#9E9E9E"),
        )

    # Default dimensions mirror the fallback rule in
    # ``build_cytoscape_stylesheet`` for untyped nodes.
    return {
        "width": "60px",
        "height": "50px",
        "shape": "ellipse",
        "background-color": color,
        "border-color": border,
    }


def merge_theme_overrides(
    base_tokens: dict[str, str], overrides: ThemeOverrides | dict[str, Any]
) -> dict[str, Any]:
    """Return an "effective theme" document from base tokens ⊕ overrides.

    ``base_tokens`` is the hardcoded token dict for a base mode (e.g. what
    :func:`get_theme_tokens` returns for ``executive-light``). ``overrides``
    may be a :class:`ThemeOverrides` instance or a raw override doc (as stored
    in the ``overrides`` JSONB column).

    The returned dict has the canonical override shape::

        {
          "nodes": {<Type>: {<semantic override keys>}, "default": {...}},
          "edges": { "line_color": ..., "width": ... },
          "global": { ... }
        }

    Effective per-nodeType values are resolved (semantic keys re-mapped to
    Cytoscape properties) so callers can build rules directly.
    """
    if not isinstance(overrides, ThemeOverrides):
        overrides = parse_overrides(overrides)

    nodes: dict[str, Any] = {}
    for node_type in NODE_TYPES:
        if node_type == "default":
            continue
        base_props = _base_node_properties(node_type, base_tokens)
        node_override = overrides.nodes.get(node_type)
        node_override = node_override or NodeOverride()
        nodes[node_type] = merge_node_override(base_props, node_override)

    # Untyped "default" node.
    base_props = _base_node_properties("default", base_tokens)
    default_override = overrides.nodes.get("default")
    try:
        nodes["default"] = merge_node_override(
            base_props, default_override or NodeOverride()
        )
    except ValueError:  # pragma: no cover - default always valid
        nodes["default"] = merge_node_override(
            base_props, NodeOverride()
        )

    edges = {
        "line-color": base_tokens.get("graph.edge.default", "#C0C0C0"),
        "width": base_tokens.get("graph.edge.width", 2),
        "target-arrow-shape": base_tokens.get("graph.edge.arrow", "triangle"),
        "color": base_tokens.get("text.secondary", "#2d3748"),
    }
    e = overrides.edges
    if e.line_color is not None:
        edges["line-color"] = e.line_color
    if e.width is not None:
        edges["width"] = e.width
    if e.arrow_shape is not None:
        edges["target-arrow-shape"] = e.arrow_shape
    if e.label_color is not None:
        edges["color"] = e.label_color

    g = overrides.global_
    global_ = {
        "node_label_color": base_tokens.get("graph.node.label", "#f4f7fb"),
        "selection_color": base_tokens.get("graph.selection", "#424242"),
        "edge_label_background": base_tokens.get("surface.base", "#ffffff"),
    }
    if g.node_label_color is not None:
        global_["node_label_color"] = g.node_label_color
    if g.selection_color is not None:
        global_["selection_color"] = g.selection_color
    if g.edge_label_background is not None:
        global_["edge_label_background"] = g.edge_label_background

    return {"nodes": nodes, "edges": edges, "global": global_}


def overrides_to_cytoscape_rules(merged_tokens: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate an effective-theme document into a Cytoscape stylesheet.

    ``merged_tokens`` is the output of :func:`merge_theme_overrides`. Returns
    a list of Cytoscape rule dicts (``{"selector": ..., "style": ...}``) for
    the node, default, edge, and selected/global rules that depend on the
    theme.

    Callers may prepend/append additional non-theme rules (fonts, community
    colours, spotlight states) as needed.
    """
    rules: list[dict[str, Any]] = []
    nodes = merged_tokens.get("nodes", {})
    default_props = nodes.get("default", {})
    global_ = merged_tokens.get("global", {})

    # Generic node rule (untyped) carries the default node's properties.
    base_node_style: dict[str, str] = {}
    for cyto_key in ("background-color", "border-color", "width", "height", "shape"):
        if cyto_key in default_props:
            base_node_style[cyto_key] = str(default_props[cyto_key])
    base_node_style.setdefault("color", str(global_.get("node_label_color", "#f4f7fb")))
    rules.append({"selector": "node", "style": base_node_style})

    # Per-nodeType rules.
    for node_type, props in nodes.items():
        if node_type == "default":
            continue
        style: dict[str, str] = {}
        if "background-color" in props:
            style["background-color"] = str(props["background-color"])
        if "border-color" in props:
            style["border-color"] = str(props["border-color"])
        if "shape" in props:
            style["shape"] = str(props["shape"])
        if "width" in props:
            style["width"] = str(props["width"])
        if "height" in props:
            style["height"] = str(props["height"])
        if not style:
            continue
        rules.append(
            {
                "selector": f'node[nodeType = "{node_type}"]',
                "style": style,
            }
        )

    # Edge rule.
    edges = merged_tokens.get("edges", {})
    edge_style: dict[str, Any] = {}
    for cyto_key, default in (
        ("width", 2),
        ("line-color", "#C0C0C0"),
        ("target-arrow-shape", "triangle"),
        ("color", "#2d3748"),
    ):
        edge_style[cyto_key] = edges.get(cyto_key, default)
    rules.append({"selector": "edge", "style": edge_style})

    # Selected node (theme selection colour).
    rules.append(
        {
            "selector": "node:selected",
            "style": {
                "border-color": str(global_.get("selection_color", "#424242")),
            },
        }
    )

    return rules


def parse_overrides(data: dict[str, Any] | None) -> ThemeOverrides:
    """Parse and validate a raw override document into :class:`ThemeOverrides`.

    ``data`` is the shape stored in the JSONB ``overrides`` column:

    .. code-block:: json

        {"nodes": {...}, "edges": {...}, "global": {...}}

    Unknown keys are ignored; known keys are validated (hex colours and shape
    names are range-checked against the allowed sets).
    """
    data = data or {}

    node_overrides: dict[str, NodeOverride] = {}
    raw_nodes = data.get("nodes") or {}
    for node_type, raw in raw_nodes.items():
        if node_type not in NODE_TYPES:
            raise ValueError(
                f"Unknown node type {node_type!r}. "
                f"Allowed: {', '.join(NODE_TYPES)}"
            )
        raw = raw or {}
        _validate_node_override(raw, node_type)
        node_overrides[node_type] = _build_node_override(raw)

    raw_edges = data.get("edges") or {}
    edges = EdgeOverride(
        **{k: v for k, v in {
            "line_color": raw_edges.get("line_color"),
            "width": raw_edges.get("width"),
            "arrow_shape": raw_edges.get("arrow_shape"),
            "label_color": raw_edges.get("label_color"),
        }.items() if v is not None}
    )
    if edges.line_color is not None:
        validate_hex_color(edges.line_color)
    if edges.label_color is not None:
        validate_hex_color(edges.label_color)

    raw_global = data.get("global") or {}
    global_ = GlobalOverride(
        **{k: v for k, v in {
            "node_label_color": raw_global.get("node_label_color"),
            "selection_color": raw_global.get("selection_color"),
            "edge_label_background": raw_global.get("edge_label_background"),
        }.items() if v is not None}
    )
    for key in ("node_label_color", "selection_color", "edge_label_background"):
        value = getattr(global_, key)
        if value is not None:
            validate_hex_color(value)

    return ThemeOverrides(nodes=node_overrides, edges=edges, global_=global_)


def _validate_node_override(raw: dict[str, Any], node_type: str) -> None:
    """Validate a single node's raw override dict."""
    if "color" in raw and raw["color"] is not None:
        validate_hex_color(raw["color"])
    if "border" in raw and raw["border"] is not None:
        validate_hex_color(raw["border"])
    if "shape" in raw and raw["shape"] is not None:
        if raw["shape"] not in ALLOWED_SHAPES:
            raise ValueError(
                f"Unknown shape {raw['shape']!r} for node {node_type!r}. "
                f"Allowed: {', '.join(ALLOWED_SHAPES)}"
            )
    for key in ("width", "height", "border_width"):
        if key in raw and raw[key] is not None:
            value = raw[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{key} for node {node_type!r} must be an integer.")
            if value <= 0:
                raise ValueError(f"{key} for node {node_type!r} must be positive.")


def _build_node_override(raw: dict[str, Any]) -> NodeOverride:
    """Construct a validated :class:`NodeOverride` from a raw dict."""
    return NodeOverride(
        color=raw.get("color"),
        border=raw.get("border"),
        border_width=raw.get("border_width"),
        shape=raw.get("shape"),
        width=raw.get("width"),
        height=raw.get("height"),
    )
