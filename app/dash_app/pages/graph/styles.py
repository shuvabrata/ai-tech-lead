"""Cytoscape style definitions for graph visualization

This module contains all visual styling for the graph visualization,
including node colors, sizes, edge styles, and selection states.
"""

import re

from app.dash_app.styles import (
    ACTIVE_THEME,
    get_theme_tokens,
    FONT_SANS,
    FONT_SIZE_TINY,
    FONT_SIZE_XXSMALL,
    FONT_WEIGHT_MEDIUM,
)

# 20 distinct, accessible fill/border colour pairs for community detection.
# Ordering strategy: the first N entries are maximally hue-distinct so that
# graphs with few communities (2-5) still display clearly different colours.
# Pairs are interleaved across warm/cool/neutral hues rather than listed by
# hue family, so community-0 and community-1 are never similar-looking.
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


def build_cytoscape_stylesheet(theme_name: str = ACTIVE_THEME):
    """Build Cytoscape stylesheet for a specific theme."""
    tokens = get_theme_tokens(theme_name)
    # Cytoscape.js expects a comma-separated font list without quotes.
    cyto_font_family = re.sub(r"[\"']", "", FONT_SANS)

    # Keep graph labels readable on dark node fills.
    # Default (untyped) nodes use text.primary on light to contrast against the
    # neutral gray fill.  Vivid typed-node fills use the shared label token.
    node_label_color = tokens["text.primary"] if theme_name == "executive-light" else "#f4f7fb"
    typed_node_label_color = tokens["graph.node.label"]
    edge_label_bg = tokens["surface.base"]

    return [
        # Default node style
        {
            'selector': 'node',
            'style': {
                'label': 'data(displayLabel)',
                'background-color': tokens["graph.node.default"],
                'color': node_label_color,
                'text-valign': 'center',
                'text-halign': 'center',
                'font-family': cyto_font_family,
                'font-size': FONT_SIZE_TINY,
                'font-weight': FONT_WEIGHT_MEDIUM,
                'width': '60px',
                'height': '60px',
                'border-width': '0px',
                'border-color': tokens["graph.node.default.border"],
                'text-wrap': 'wrap',
                'text-max-width': '56px'
            }
        },
        {
            'selector': 'node[nodeType = "Project"]',
            'style': {
                'shape': 'round-rectangle',
                'background-color': tokens["graph.node.project"],
                'border-color': tokens["graph.node.project.border"],
                'color': typed_node_label_color,
                'width': '70px',
                'height': '70px'
            }
        },
        {
            'selector': 'node[nodeType = "Person"]',
            'style': {
                'shape': 'octagon',
                'background-color': tokens["graph.node.person"],
                'border-color': tokens["graph.node.person.border"],
                'color': typed_node_label_color,
                'width': '65px',
                'height': '65px'
            }
        },
        {
            'selector': 'node[nodeType = "Branch"]',
            'style': {
                'shape': 'diamond',
                'background-color': tokens["graph.node.branch"],
                'border-color': tokens["graph.node.branch.border"],
                'color': typed_node_label_color,
                'width': '55px',
                'height': '55px'
            }
        },
        {
            'selector': 'node[nodeType = "Epic"]',
            'style': {
                'shape': 'hexagon',
                'background-color': tokens["graph.node.epic"],
                'border-color': tokens["graph.node.epic.border"],
                'color': typed_node_label_color,
                'width': '65px',
                'height': '65px'
            }
        },
        {
            'selector': 'node[nodeType = "Issue"]',
            'style': {
                'shape': 'triangle',
                'background-color': tokens["graph.node.issue"],
                'border-color': tokens["graph.node.issue.border"],
                'color': typed_node_label_color,
                'width': '55px',
                'height': '55px'
            }
        },
        {
            'selector': 'node[nodeType = "Repository"]',
            'style': {
                'shape': 'rectangle',
                'background-color': tokens["graph.node.repository"],
                'border-color': tokens["graph.node.repository.border"],
                'color': typed_node_label_color,
                'width': '65px',
                'height': '65px'
            }
        },
        {
            'selector': 'edge',
            'style': {
                'width': 2,
                'line-color': tokens["graph.edge.default"],
                'target-arrow-color': tokens["graph.edge.default"],
                'target-arrow-shape': 'triangle',
                'arrow-scale': 1.0,
                'curve-style': 'bezier',
                'control-point-step-size': 40,
                'label': 'data(label)',
                'font-family': cyto_font_family,
                'font-size': FONT_SIZE_XXSMALL,
                'font-weight': FONT_WEIGHT_MEDIUM,
                'color': tokens["text.secondary"],
                'text-rotation': 'autorotate',
                'text-margin-y': -10,
                'text-background-color': edge_label_bg,
                'text-background-opacity': 0.85,
                'text-background-padding': '3px',
                'text-outline-color': edge_label_bg,
                'text-outline-width': 1
            }
        },
        {
            'selector': 'edge[weight]',
            'style': {
                'width': 'mapData(weight, 0, 100, 1, 8)',
                'arrow-scale': 'mapData(weight, 0, 100, 0.8, 2.0)',
            }
        },
        {
            'selector': 'node:selected',
            'style': {
                'border-width': '2px',
                'border-color': tokens["graph.selection"],
                'border-style': 'solid',
                'z-index': 9999
            }
        },
        {
            'selector': 'edge:selected',
            'style': {
                'width': 4,
                'line-color': tokens["graph.selection"],
                'target-arrow-color': tokens["graph.selection"],
                'z-index': 9999
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
    ]


CYTOSCAPE_STYLESHEET = build_cytoscape_stylesheet()


def get_node_type_styles(theme_name: str = ACTIVE_THEME, stylesheet=None):
    """Extract node type styling information from the stylesheet
    
    Parses CYTOSCAPE_STYLESHEET to extract node types and their colors.
    Returns a dictionary mapping node types to their styling information.
    
    Returns:
        dict: Mapping of node type to style info, e.g.,
              {
                  "Project": {"color": COLOR_GRAPH_NODE_PROJECT, "border": COLOR_GRAPH_NODE_PROJECT_BORDER, "shape": "round-rectangle"},
                  "Person": {"color": COLOR_GRAPH_NODE_PERSON, "border": COLOR_GRAPH_NODE_PERSON_BORDER, "shape": "octagon"},
                  ...
              }
              Also includes "default" for nodes without specific types.
    """
    node_styles = {}
    
    # Pattern to match node[nodeType = "TypeName"]
    node_type_pattern = re.compile(r'node\[nodeType\s*=\s*"([^"]+)"\]')
    
    stylesheet_to_parse = stylesheet or build_cytoscape_stylesheet(theme_name)

    tokens = get_theme_tokens(theme_name)

    for style_item in stylesheet_to_parse:
        selector = style_item.get('selector', '')
        style = style_item.get('style', {})
        
        # Check if this is a node type selector
        match = node_type_pattern.search(selector)
        if match:
            node_type = match.group(1)
            node_styles[node_type] = {
                'color': style.get('background-color', tokens["graph.node.default"]),
                'border': style.get('border-color', tokens["graph.node.default.border"]),
                'shape': style.get('shape', 'ellipse')
            }
        # Check for default node style
        elif selector == 'node':
            node_styles['default'] = {
                'color': style.get('background-color', tokens["graph.node.default"]),
                'border': style.get('border-color', tokens["graph.node.default.border"]),
                'shape': style.get('shape', 'ellipse')
            }
    
    return node_styles
