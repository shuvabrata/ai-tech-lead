"""Cytoscape style definitions for graph visualization

This module contains all visual styling for the graph visualization,
including node colors, sizes, edge styles, and selection states.
"""

import re

from app.common.graph_theme import merge_theme_overrides, overrides_to_cytoscape_rules
from app.dash_app.styles import (
    ACTIVE_THEME,
    get_theme_tokens,
    FONT_SANS,
    FONT_SIZE_TINY,
    FONT_SIZE_XXSMALL,
    FONT_WEIGHT_MEDIUM,
)

# 20 distinct, accessible fill/border colour pairs for community detection.
#
# Palette management note:
# - In use for entity node styles: Person, Project, Branch, Epic, Issue, Repository
# - Reserved for future entity node styles: Team, IdentityMapping, Initiative,
#   Sprint, Commit, File, PullRequest
# - Extension rule: prefer assigning an explicit nodeType shape + color pair for
#   new entity types instead of leaving them on the default fallback style.
COMMUNITY_COLORS = [
    ("#3B82F6", "#2563EB"),   #  0 – blue          (cool)
    ("#EF4444", "#DC2626"),   #  1 – red            (warm)
    ("#10B981", "#059669"),   #  2 – emerald        (cool)
    ("#F59E0B", "#D97706"),   #  3 – amber          (warm)
    ("#8B5CF6", "#7C3AED"),   #  4 – violet         (cool)
    ("#F97316", "#EA580C"),   #  5 – orange         (warm)
    ("#14B8A6", "#0D9488"),   #  6 – teal           (cool)
    ("#EC4899", "#DB2777"),   #  7 – pink           (warm)
    ("#84CC16", "#65A30D"),   #  8 – lime           (mid)
    ("#6366F1", "#4F46E5"),   #  9 – indigo         (cool)
    ("#06B6D4", "#0891B2"),   # 10 – cyan           (cool)
    ("#F43F5E", "#E11D48"),   # 11 – rose           (warm)
    ("#0EA5E9", "#0284C7"),   # 12 – sky            (cool)
    ("#EAB308", "#CA8A04"),   # 13 – yellow         (warm)
    ("#A855F7", "#9333EA"),   # 14 – purple         (cool)
    ("#D946EF", "#C026D3"),   # 15 – fuchsia        (warm)
    ("#22C55E", "#16A34A"),   # 16 – green          (mid)
    ("#64748B", "#475569"),   # 17 – slate          (neutral)
    ("#B45309", "#92400E"),   # 18 – brown-amber    (warm)
    ("#0F766E", "#115E59"),   # 19 – dark-teal      (cool)
]


def build_cytoscape_stylesheet(theme_name: str = ACTIVE_THEME, effective=None):
    """Build Cytoscape stylesheet for a specific theme.

    Node shape/size/colour are driven by the *effective* theme (base tokens ⊕
    overrides) so user-configured graph themes propagate to the stylesheet.
    ``effective`` is an optional pre-merged theme document (the output of
    :func:`app.common.graph_theme.merge_theme_overrides`); when omitted, the
    base tokens are merged with empty overrides — identical to the previous
    hardcoded output.
    """
    tokens = get_theme_tokens(theme_name)
    if effective is None:
        effective = merge_theme_overrides(tokens, {})
    cyto_font_family = re.sub(r"[\"']", "", FONT_SANS)

    node_label_color = tokens["text.primary"] if theme_name == "executive-light" else "#f4f7fb"
    typed_node_label_color = tokens["graph.node.label"]
    edge_label_bg = tokens["surface.base"]

    edges = effective["edges"]
    globals_ = effective["global"]

    # Theme-derived rules come from the single shared translation layer
    # (app.common.graph_theme.overrides_to_cytoscape_rules). The generic node,
    # per-nodeType, edge, and selected rules are all produced there.
    theme_rules = overrides_to_cytoscape_rules(effective)

    # Enrich the generic (untyped) node rule with the font/label styling that
    # is a stylesheet concern, not a theme concern. ``shape`` is intentionally
    # omitted (ellipse is the Cytoscape default), preserving parity with the
    # previous output.
    generic_node_rule = theme_rules[0]
    generic_node_rule["style"].update({
        'label': 'data(displayLabel)',
        'color': node_label_color,
        'text-valign': 'center',
        'text-halign': 'center',
        'font-family': cyto_font_family,
        'font-size': FONT_SIZE_TINY,
        'font-weight': FONT_WEIGHT_MEDIUM,
        'border-width': '0px',
        'text-wrap': 'wrap',
        'text-max-width': '56px'
    })
    # The shared function sets the generic node's ``color`` from the theme's
    # node_label_color; the stylesheet overrides it with the page's label
    # colour (light mode uses text.primary). This preserves the pre-existing
    # behaviour exactly.
    generic_node_rule["style"]["color"] = node_label_color
    # ``shape`` is intentionally omitted from the generic node rule (ellipse is
    # the Cytoscape default), preserving parity with the previous output.
    generic_node_rule["style"].pop("shape", None)

    # Enrich each per-nodeType rule with the typed label colour.
    for rule in theme_rules[1:]:
        if rule["selector"].startswith("node[nodeType"):
            rule["style"]["color"] = typed_node_label_color

    # Enrich the edge rule with the full edge styling (fonts, arrows, labels).
    edge_rule = next(r for r in theme_rules if r["selector"] == "edge")
    edge_rule["style"].update({
        'target-arrow-color': edges.get("line-color", tokens["graph.edge.default"]),
        'arrow-scale': 1.0,
        'curve-style': 'bezier',
        'control-point-step-size': 40,
        'label': 'data(label)',
        'font-family': cyto_font_family,
        'font-size': FONT_SIZE_XXSMALL,
        'font-weight': FONT_WEIGHT_MEDIUM,
        'text-rotation': 'autorotate',
        'text-margin-y': -10,
        'text-background-color': globals_.get(
            "edge_label_background", edge_label_bg
        ),
        'text-background-opacity': 0.85,
        'text-background-padding': '3px',
        'text-outline-color': globals_.get(
            "edge_label_background", edge_label_bg
        ),
        'text-outline-width': 1
    })

    # Enrich the node:selected rule with the selection border styling.
    selected_rule = next(r for r in theme_rules if r["selector"] == "node:selected")
    selected_rule["style"].update({
        'border-width': '2px',
        'border-style': 'solid',
        'z-index': 9999
    })

    return [
        *theme_rules,
        {
            'selector': '.selected-highlight',
            'style': {
                'opacity': 1.0,
                'z-index': 9997,
            }
        },
        {
            'selector': 'node.selected-highlight',
            'style': {
                'text-opacity': 1.0,
            }
        },
        {
            'selector': 'edge.selected-highlight',
            'style': {
                'text-opacity': 1.0,
            }
        },
        {
            'selector': '.selected-dim',
            'style': {
                'opacity': 0.3,
            }
        },
        {
            'selector': 'node.selected-dim',
            'style': {
                'text-opacity': 0.35,
                'z-index': 1,
            }
        },
        {
            'selector': 'edge.selected-dim',
            'style': {
                'text-opacity': 0.0,
                'z-index': 1,
            }
        },
        {
            'selector': '.highlighted',
            'style': {
                'opacity': 1.0,
                'z-index': 9998
            }
        },
        {
            'selector': '.dimmed',
            'style': {
                'opacity': 0.3
            }
        },
        {
            'selector': 'node.dimmed',
            'style': {
                'text-opacity': 0.35,
                'z-index': 1,
            }
        },
        {
            'selector': 'edge.dimmed',
            'style': {
                'text-opacity': 0.0,
                'z-index': 1,
            }
        },
        # Community colour rules for collaboration network mode.
        # These appear last so they override nodeType background colours while
        # preserving shape and size set by the nodeType selectors above.
        *[
            {
                'selector': f'.community-{i}',
                'style': {
                    'background-color': fill,
                    'border-color': border,
                    'border-width': '2px',
                }
            }
            for i, (fill, border) in enumerate(COMMUNITY_COLORS)
        ],
        # --- C3: Node Spotlight (comes last — highest specificity) ---
        {
            'selector': 'node.spotlight-dim',
            'style': {
                'opacity': 0.12,
                'z-index': 1,
            }
        },
        {
            'selector': 'node.spotlight-match',
            'style': {
                'border-width': '3px',
                'border-color': '#F59E0B',
                'opacity': 1.0,
                'z-index': 9997,
                'transition-property': 'opacity border-width border-color',
                'transition-duration': '0.35s',
                'transition-timing-function': 'ease-out',
            }
        },
        {
            'selector': 'edge.spotlight-dim',
            'style': {
                'opacity': 0.06,
                'z-index': 1,
            }
        },
        {
            'selector': 'edge.spotlight-match',
            'style': {
                'opacity': 0.8,
                'z-index': 9996,
            }
        },
    ]


CYTOSCAPE_STYLESHEET = build_cytoscape_stylesheet()


def get_node_type_styles(theme_name: str = ACTIVE_THEME, stylesheet=None):
    """Extract node type styling information from the stylesheet.

    Parses CYTOSCAPE_STYLESHEET to extract node types and their colors.
    Returns a dictionary mapping node types to their styling information.

    Returns:
        dict: Mapping of node type to style info, e.g.,
              {
                  "Project": {"color": ..., "border": ..., "shape": "round-rectangle"},
                  "Person":  {"color": ..., "border": ..., "shape": "octagon"},
                  ...
              }
              Also includes "default" for nodes without specific types.
    """
    node_styles = {}

    node_type_pattern = re.compile(r'node\[nodeType\s*=\s*"([^"]+)"\]')

    stylesheet_to_parse = stylesheet or build_cytoscape_stylesheet(theme_name)
    tokens = get_theme_tokens(theme_name)

    for style_item in stylesheet_to_parse:
        selector = style_item.get('selector', '')
        style = style_item.get('style', {})

        match = node_type_pattern.search(selector)
        if match:
            node_type = match.group(1)
            node_styles[node_type] = {
                'color': style.get('background-color', tokens["graph.node.default"]),
                'border': style.get('border-color', tokens["graph.node.default.border"]),
                'shape': style.get('shape', 'ellipse')
            }
        elif selector == 'node':
            node_styles['default'] = {
                'color': style.get('background-color', tokens["graph.node.default"]),
                'border': style.get('border-color', tokens["graph.node.default.border"]),
                'shape': style.get('shape', 'ellipse')
            }

    return node_styles
