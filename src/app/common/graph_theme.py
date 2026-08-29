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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Hex colour: #RGB or #RRGGBB.
HEX_COLOR = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"

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

# Pydantic ``Literal`` of the full shape set. Kept in sync with
# ``ALLOWED_SHAPES`` (mypy cannot unpack a runtime tuple inside ``Literal``).
ShapeLiteral = Literal[
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
]

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


class NodeOverride(BaseModel):
    """Per-nodeType visual override (semantic keys, optional fields).

    All fields are optional; only present fields are merged over the base.
    ``width`` / ``height`` / ``border_width`` are plain numeric pixels.
    ``border_width`` accepts ``0`` (no border) so that full-snapshot themes can
    explicitly freeze the base's borderless default and remain immune to
    future base-palette changes.
    """

    color: str | None = Field(default=None, pattern=HEX_COLOR)
    border: str | None = Field(default=None, pattern=HEX_COLOR)
    border_width: int | None = Field(default=None, ge=0)
    shape: ShapeLiteral | None = None
    width: int | None = Field(default=None, gt=0, le=400)
    height: int | None = Field(default=None, gt=0, le=400)


class EdgeOverride(BaseModel):
    """Edge-level visual override (applies to all edges)."""

    line_color: str | None = Field(default=None, pattern=HEX_COLOR)
    width: int | None = Field(default=None, gt=0, le=20)
    arrow_shape: str | None = None
    label_color: str | None = Field(default=None, pattern=HEX_COLOR)


class GlobalOverride(BaseModel):
    """Global (across node/edge) visual overrides."""

    node_label_color: str | None = Field(default=None, pattern=HEX_COLOR)
    selection_color: str | None = Field(default=None, pattern=HEX_COLOR)
    edge_label_background: str | None = Field(default=None, pattern=HEX_COLOR)


class ThemeOverrides(BaseModel):
    """Parsed, validated override document for a single theme.

    Mirrors the JSONB ``overrides`` column contract:

    .. code-block:: json

        {
          "nodes": {"Person": {"color": "#00FF00", ...}, "default": {...}},
          "edges": {"line_color": "#999999", ...},
          "global": {...}
        }
    """

    nodes: dict[str, NodeOverride] = Field(default_factory=dict)
    edges: EdgeOverride = Field(default_factory=EdgeOverride)
    global_: GlobalOverride = Field(
        default_factory=GlobalOverride, alias="global"
    )

    @field_validator("nodes")
    @classmethod
    def _validate_node_keys(
        cls, nodes: dict[str, NodeOverride]
    ) -> dict[str, NodeOverride]:
        """Reject unknown node-type keys."""
        unknown = sorted(set(nodes) - set(NODE_TYPES))
        if unknown:
            raise ValueError(
                f"Unknown node type(s): {', '.join(unknown)}. "
                f"Allowed: {', '.join(NODE_TYPES)}"
            )
        return nodes

    model_config = ConfigDict(populate_by_name=True)


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
    overrides compose cleanly even when a base rule omits a key. Shape and
    size come from the ``graph.node.<key>.shape/.width/.height`` tokens so
    the effective base matches the hardcoded stylesheet exactly (no drift).
    """
    if node_type == "default":
        token_key = "default"
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

    shape = base_tokens.get(f"graph.node.{token_key}.shape", "ellipse")
    width = base_tokens.get(f"graph.node.{token_key}.width", "60px")
    height = base_tokens.get(f"graph.node.{token_key}.height", "50px")

    return {
        "width": width,
        "height": height,
        "shape": shape,
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


def _px_to_int(value: Any, default: int = 0) -> int:
    """Parse a ``"Npx"`` / numeric dimension into an int (drop the suffix)."""
    if value is None:
        return default
    text = str(value).strip()
    if text.lower().endswith("px"):
        text = text[:-2]
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def effective_semantic_theme(
    base_tokens: dict[str, str], overrides: ThemeOverrides | dict[str, Any]
) -> dict[str, Any]:
    """Return the full effective theme in **semantic** space.

    This is the editor-facing counterpart to :func:`merge_theme_overrides`
    (which emits Cytoscape space for the consumer pages). Every node type
    (including the untyped ``default``), plus edges and global, carries
    **concrete** values — base tokens resolved and merged with any overrides —
    in the semantic key vocabulary used by the override contract
    (``color`` / ``border`` / ``border_width`` / ``shape`` / ``width`` /
    ``height`` for nodes; ``line_color`` / ``width`` / ``arrow_shape`` /
    ``label_color`` for edges; ``node_label_color`` / ``selection_color`` /
    ``edge_label_background`` for global).

    The result is a **full snapshot**: a custom theme stored from this output
    is frozen against future base-palette changes (all fields explicit, no
    deltas fall through to the base).

    Dimension fields are plain numeric px (no ``"px"`` suffix), matching the
    override contract.
    """
    if not isinstance(overrides, ThemeOverrides):
        overrides = parse_overrides(overrides)

    nodes: dict[str, Any] = {}
    for node_type in NODE_TYPES:
        base_props = _base_node_properties(node_type, base_tokens)
        node_override = overrides.nodes.get(node_type) or NodeOverride()
        merged = merge_node_override(base_props, node_override)
        nodes[node_type] = {
            "color": merged["background-color"],
            "border": merged["border-color"],
            "border_width": _px_to_int(merged.get("border-width"), 0),
            "shape": merged["shape"],
            "width": _px_to_int(merged.get("width"), 60),
            "height": _px_to_int(merged.get("height"), 50),
        }

    e = overrides.edges
    edges = {
        "line_color": (
            e.line_color
            if e.line_color is not None
            else base_tokens.get("graph.edge.default", "#C0C0C0")
        ),
        "width": (
            e.width if e.width is not None else _px_to_int(base_tokens.get("graph.edge.width", 2), 2)
        ),
        "arrow_shape": (
            e.arrow_shape
            if e.arrow_shape is not None
            else base_tokens.get("graph.edge.arrow", "triangle")
        ),
        "label_color": (
            e.label_color
            if e.label_color is not None
            else base_tokens.get("text.secondary", "#2d3748")
        ),
    }

    g = overrides.global_
    global_ = {
        "node_label_color": (
            g.node_label_color
            if g.node_label_color is not None
            else base_tokens.get("graph.node.label", "#f4f7fb")
        ),
        "selection_color": (
            g.selection_color
            if g.selection_color is not None
            else base_tokens.get("graph.selection", "#424242")
        ),
        "edge_label_background": (
            g.edge_label_background
            if g.edge_label_background is not None
            else base_tokens.get("surface.base", "#ffffff")
        ),
    }

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

    Validation (hex colours, shape names, numeric bounds, node-type keys) is
    enforced by the Pydantic models themselves. Raises ``ValueError`` /
    ``TypeError`` on invalid input.
    """
    return ThemeOverrides.model_validate(data or {})
