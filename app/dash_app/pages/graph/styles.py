"""Cytoscape style definitions for graph visualization

This module contains all visual styling for the graph visualization,
including node colors, sizes, edge styles, and selection states.
"""

import re


CYTOSCAPE_STYLESHEET = [
    # Default node style
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'background-color': '#B8B8B8',  # Pastel Neutral: Soft gray
            'color': '#333',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '11px',
            'font-weight': '500',
            'width': '60px',
            'height': '60px',
            'border-width': '0px',
            'border-color': '#9E9E9E',  # Darker soft gray
            'text-wrap': 'wrap',
            'text-max-width': '80px'
        }
    },
    # Project nodes - Soft Blue
    {
        'selector': 'node[nodeType = "Project"]',
        'style': {
            'shape': 'round-rectangle',
            'background-color': '#AEC6CF',  # Pastel Neutral: Soft blue
            'border-color': '#8FA8B5',
            'width': '70px',
            'height': '70px'
        }
    },
    # Person nodes - Soft Lavender
    {
        'selector': 'node[nodeType = "Person"]',
        'style': {
            'shape': 'octagon',
            'background-color': '#C5B4E3',  # Pastel Neutral: Soft lavender
            'border-color': '#A798C7',
            'width': '65px',
            'height': '65px'
        }
    },
    # Branch nodes - Soft Mint
    {
        'selector': 'node[nodeType = "Branch"]',
        'style': {
            'shape': 'diamond',
            'background-color': '#B5E7E3',  # Pastel Neutral: Soft mint
            'border-color': '#96C9C5',
            'width': '55px',
            'height': '55px'
        }
    },
    # Epic nodes - Soft Peach
    {
        'selector': 'node[nodeType = "Epic"]',
        'style': {
            'shape': 'hexagon',
            'background-color': '#F4C2B0',  # Pastel Neutral: Soft peach
            'border-color': '#D9A892',
            'width': '65px',
            'height': '65px'
        }
    },
    # Issue nodes - Soft Cream
    {
        'selector': 'node[nodeType = "Issue"]',
        'style': {
            'shape': 'triangle',
            'background-color': '#F5E6D3',  # Pastel Neutral: Soft cream
            'border-color': '#D9C8B5',
            'color': '#333',
            'width': '55px',
            'height': '55px'
        }
    },
    # Repository nodes - Soft Sage
    {
        'selector': 'node[nodeType = "Repository"]',
        'style': {
            'shape': 'rectangle',
            'background-color': '#C8D5B9',  # Pastel Neutral: Soft sage
            'border-color': '#AAB89B',
            'width': '65px',
            'height': '65px'
        }
    },
    # Edge styles
    {
        'selector': 'edge',
        'style': {
            'width': 2,
            'line-color': '#C0C0C0',  # Pastel Neutral: Lighter neutral gray
            'target-arrow-color': '#C0C0C0',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '9px',
            'text-rotation': 'autorotate',
            'text-margin-y': -10,
            'text-background-color': '#fff',
            'text-background-opacity': 0.8,
            'text-background-padding': '3px'
        }
    },
    # Node selected state (click to select)
    {
        'selector': 'node:selected',
        'style': {
            'border-width': '2px',
            'border-color': '#424242',  # Dark Charcoal: Professional selection highlight
            'border-style': 'solid',
            'z-index': 9999
        }
    },
    # Edge selected state (click to select)
    {
        'selector': 'edge:selected',
        'style': {
            'width': 4,
            'line-color': '#424242',  # Dark Charcoal: Professional selection highlight
            'target-arrow-color': '#424242',
            'z-index': 9999
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
                  "Project": {"color": "#AEC6CF", "border": "#8FA8B5", "shape": "round-rectangle"},
                  "Person": {"color": "#C5B4E3", "border": "#A798C7", "shape": "octagon"},
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
                'color': style.get('background-color', '#B8B8B8'),
                'border': style.get('border-color', '#9E9E9E'),
                'shape': style.get('shape', 'ellipse')
            }
        # Check for default node style
        elif selector == 'node':
            node_styles['default'] = {
                'color': style.get('background-color', '#B8B8B8'),
                'border': style.get('border-color', '#9E9E9E'),
                'shape': style.get('shape', 'ellipse')
            }
    
    return node_styles
