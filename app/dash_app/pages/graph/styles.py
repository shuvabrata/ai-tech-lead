"""Cytoscape style definitions for graph visualization

This module contains all visual styling for the graph visualization,
including node colors, sizes, edge styles, and selection states.
"""

import re

from app.dash_app.styles import (
    FONT_SANS,
    FONT_SIZE_TINY,
    FONT_SIZE_XXSMALL,
    FONT_WEIGHT_MEDIUM,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_BACKGROUND_WHITE,
    COLOR_GRAPH_NODE_DEFAULT,
    COLOR_GRAPH_NODE_DEFAULT_BORDER,
    COLOR_GRAPH_NODE_PROJECT,
    COLOR_GRAPH_NODE_PROJECT_BORDER,
    COLOR_GRAPH_NODE_PERSON,
    COLOR_GRAPH_NODE_PERSON_BORDER,
    COLOR_GRAPH_NODE_BRANCH,
    COLOR_GRAPH_NODE_BRANCH_BORDER,
    COLOR_GRAPH_NODE_EPIC,
    COLOR_GRAPH_NODE_EPIC_BORDER,
    COLOR_GRAPH_NODE_ISSUE,
    COLOR_GRAPH_NODE_ISSUE_BORDER,
    COLOR_GRAPH_NODE_REPOSITORY,
    COLOR_GRAPH_NODE_REPOSITORY_BORDER,
    COLOR_GRAPH_EDGE_DEFAULT,
    COLOR_GRAPH_SELECTION,
)


CYTOSCAPE_STYLESHEET = [
    # Default node style
    {
        'selector': 'node',
        'style': {
            'label': 'data(displayLabel)',
            'background-color': COLOR_GRAPH_NODE_DEFAULT,
            'color': COLOR_CHARCOAL_MEDIUM,
            'text-valign': 'center',
            'text-halign': 'center',
            'font-family': FONT_SANS,
            'font-size': FONT_SIZE_TINY,
            'font-weight': FONT_WEIGHT_MEDIUM,
            'width': '60px',
            'height': '60px',
            'border-width': '0px',
            'border-color': COLOR_GRAPH_NODE_DEFAULT_BORDER,
            'text-wrap': 'wrap',
            'text-max-width': '56px'
        }
    },
    # Project nodes - Soft Blue
    {
        'selector': 'node[nodeType = "Project"]',
        'style': {
            'shape': 'round-rectangle',
            'background-color': COLOR_GRAPH_NODE_PROJECT,
            'border-color': COLOR_GRAPH_NODE_PROJECT_BORDER,
            'width': '70px',
            'height': '70px'
        }
    },
    # Person nodes - Soft Lavender
    {
        'selector': 'node[nodeType = "Person"]',
        'style': {
            'shape': 'octagon',
            'background-color': COLOR_GRAPH_NODE_PERSON,
            'border-color': COLOR_GRAPH_NODE_PERSON_BORDER,
            'width': '65px',
            'height': '65px'
        }
    },
    # Branch nodes - Soft Mint
    {
        'selector': 'node[nodeType = "Branch"]',
        'style': {
            'shape': 'diamond',
            'background-color': COLOR_GRAPH_NODE_BRANCH,
            'border-color': COLOR_GRAPH_NODE_BRANCH_BORDER,
            'width': '55px',
            'height': '55px'
        }
    },
    # Epic nodes - Soft Peach
    {
        'selector': 'node[nodeType = "Epic"]',
        'style': {
            'shape': 'hexagon',
            'background-color': COLOR_GRAPH_NODE_EPIC,
            'border-color': COLOR_GRAPH_NODE_EPIC_BORDER,
            'width': '65px',
            'height': '65px'
        }
    },
    # Issue nodes - Soft Cream
    {
        'selector': 'node[nodeType = "Issue"]',
        'style': {
            'shape': 'triangle',
            'background-color': COLOR_GRAPH_NODE_ISSUE,
            'border-color': COLOR_GRAPH_NODE_ISSUE_BORDER,
            'color': COLOR_CHARCOAL_MEDIUM,
            'width': '55px',
            'height': '55px'
        }
    },
    # Repository nodes - Soft Sage
    {
        'selector': 'node[nodeType = "Repository"]',
        'style': {
            'shape': 'rectangle',
            'background-color': COLOR_GRAPH_NODE_REPOSITORY,
            'border-color': COLOR_GRAPH_NODE_REPOSITORY_BORDER,
            'width': '65px',
            'height': '65px'
        }
    },
    # Edge styles - Default (no weight property)
    {
        'selector': 'edge',
        'style': {
            'width': 2,
            'line-color': COLOR_GRAPH_EDGE_DEFAULT,
            'target-arrow-color': COLOR_GRAPH_EDGE_DEFAULT,
            'target-arrow-shape': 'triangle',
            'target-arrow-scale': 1.0,
            'curve-style': 'bezier',
            'control-point-step-size': 40,  # Better separation for parallel edges
            'label': 'data(label)',
            'font-family': FONT_SANS,
            'font-size': FONT_SIZE_XXSMALL,
            'font-weight': FONT_WEIGHT_MEDIUM,
            'color': COLOR_CHARCOAL_MEDIUM,
            'text-rotation': 'autorotate',
            'text-margin-y': -10,
            'text-background-color': COLOR_BACKGROUND_WHITE,
            'text-background-opacity': 0.85,
            'text-background-padding': '3px',
            'text-outline-color': COLOR_BACKGROUND_WHITE,
            'text-outline-width': 1
        }
    },
    # Edge styles - With weight property (dynamic thickness)
    {
        'selector': 'edge[weight]',
        'style': {
            'width': 'mapData(weight, 0, 100, 1, 8)',  # Map weight 0-100 to width 1-8px
            'target-arrow-scale': 'mapData(weight, 0, 100, 0.8, 2.0)',  # Scale arrows proportionally
        }
    },
    # Node selected state (click to select)
    {
        'selector': 'node:selected',
        'style': {
            'border-width': '2px',
            'border-color': COLOR_GRAPH_SELECTION,
            'border-style': 'solid',
            'z-index': 9999
        }
    },
    # Edge selected state (click to select)
    {
        'selector': 'edge:selected',
        'style': {
            'width': 4,
            'line-color': COLOR_GRAPH_SELECTION,
            'target-arrow-color': COLOR_GRAPH_SELECTION,
            'z-index': 9999
        }
    },
    # Highlighted elements (hover interaction - Phase 1.2.3)
    {
        'selector': '.highlighted',
        'style': {
            'opacity': 1.0,
            'z-index': 9998
        }
    },
    # Dimmed elements (hover interaction - Phase 1.2.3)
    {
        'selector': '.dimmed',
        'style': {
            'opacity': 0.3
        }
    }
]


def get_node_type_styles():
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
    
    for style_item in CYTOSCAPE_STYLESHEET:
        selector = style_item.get('selector', '')
        style = style_item.get('style', {})
        
        # Check if this is a node type selector
        match = node_type_pattern.search(selector)
        if match:
            node_type = match.group(1)
            node_styles[node_type] = {
                'color': style.get('background-color', COLOR_GRAPH_NODE_DEFAULT),
                'border': style.get('border-color', COLOR_GRAPH_NODE_DEFAULT_BORDER),
                'shape': style.get('shape', 'ellipse')
            }
        # Check for default node style
        elif selector == 'node':
            node_styles['default'] = {
                'color': style.get('background-color', COLOR_GRAPH_NODE_DEFAULT),
                'border': style.get('border-color', COLOR_GRAPH_NODE_DEFAULT_BORDER),
                'shape': style.get('shape', 'ellipse')
            }
    
    return node_styles
