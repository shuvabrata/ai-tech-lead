"""Graph Visualization Page

This page allows users to:
- Enter and execute Cypher queries
- View graph results (nodes and relationships)
- Display tabular results for non-graph queries
"""

import dash_bootstrap_components as dbc
from dash import html, dcc


def get_layout():
    """Return the graph page layout"""
    return html.Div([
        # Page Header
        html.H2("Graph Visualization", className="mb-4", style={"fontWeight": "600", "color": "#1a1a1a"}),
        
        html.P(
            "Execute Cypher queries against your Neo4j database and visualize the results.", 
            className="mb-4",
            style={"color": "#666", "fontSize": "15px"}
        ),
        
        # Query Input Section
        html.Div([
            html.H5("Cypher Query", className="mb-3", style={"fontWeight": "500", "color": "#333"}),
            
            dbc.Textarea(
                id="graph-query-input",
                placeholder="MATCH (n:Project)-[r]->(m)\nRETURN n, r, m\nLIMIT 10",
                style={
                    "height": "150px",
                    "borderRadius": "12px",
                    "border": "2px solid #e0e0e0",
                    "padding": "12px 16px",
                    "fontSize": "14px",
                    "fontFamily": "Consolas, Monaco, 'Courier New', monospace",
                    "resize": "vertical",
                    "transition": "border-color 0.2s"
                },
                className="mb-3"
            ),
            
            html.Div([
                dbc.Button(
                    [html.I(className="fas fa-play me-2"), "Execute Query"],
                    id="graph-execute-btn",
                    color="primary",
                    style={
                        "borderRadius": "8px",
                        "fontWeight": "500",
                        "fontSize": "15px",
                        "padding": "10px 24px",
                        "boxShadow": "0 2px 6px rgba(13, 110, 253, 0.25)"
                    }
                ),
                html.Small(
                    "Note: Only read-only queries (MATCH, RETURN) are allowed for security.",
                    className="ms-3 text-muted",
                    style={"fontSize": "13px"}
                )
            ], className="d-flex align-items-center mb-4")
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "12px",
            "border": "1px solid #e0e0e0",
            "padding": "24px",
            "marginBottom": "24px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
        }),
        
        # Results Section
        html.Div([
            html.H5("Results", className="mb-3", style={"fontWeight": "500", "color": "#333"}),
            
            dcc.Loading(
                id="graph-loading",
                type="circle",
                color="#0d6efd",
                children=[
                    html.Div(
                        id="graph-results-container",
                        style={
                            "minHeight": "400px",
                            "padding": "20px"
                        },
                        children=[
                            html.Div(
                                [
                                    html.I(className="fas fa-project-diagram fa-3x mb-3", style={"color": "#ccc"}),
                                    html.P(
                                        "No results yet. Enter a Cypher query above and click 'Execute Query' to visualize data.",
                                        style={"color": "#999", "fontSize": "15px"}
                                    )
                                ],
                                className="text-center",
                                style={"marginTop": "80px"}
                            )
                        ]
                    )
                ]
            )
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "12px",
            "border": "1px solid #e0e0e0",
            "padding": "24px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
        }),
        
        # Hidden data store for graph data
        dcc.Store(id="graph-data-store", data=None),
        
        # Session store for query history (optional, for future use)
        dcc.Store(id="graph-query-history", data=[]),
        
    ], className="mt-4")
