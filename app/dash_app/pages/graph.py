"""Graph Visualization Page

This page allows users to:
- Enter and execute Cypher queries
- View graph results (nodes and relationships)
- Display tabular results for non-graph queries
"""

import os
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback
import requests

from app.settings import settings

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


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


# Callback to execute Cypher query
@callback(
    [Output("graph-data-store", "data"),
     Output("graph-results-container", "children")],
    [Input("graph-execute-btn", "n_clicks")],
    [State("graph-query-input", "value")],
    prevent_initial_call=True
)
def execute_query(n_clicks, query_text):
    """Execute Cypher query and store results"""
    # Validate query not empty
    if not query_text or not query_text.strip():
        error_display = html.Div([
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                "Please enter a Cypher query before executing."
            ], color="warning", className="mb-0")
        ])
        return None, error_display
    
    # Get API base URL
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    try:
        # Send query to API
        response = requests.post(
            f"{api_base}/api/v1/graph/query",
            json={"query": query_text},
            timeout=TIMEOUT_SECONDS
        )
        
        # Handle error responses
        if response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            error_message = error_data.get("detail", {}).get("error", str(response.text))
            error_hint = error_data.get("detail", {}).get("hint", "")
            
            error_display = html.Div([
                dbc.Alert([
                    html.H5([
                        html.I(className="fas fa-times-circle me-2"),
                        "Query Execution Failed"
                    ], className="alert-heading mb-2"),
                    html.P(error_message, className="mb-1"),
                    html.Small(error_hint, className="text-muted") if error_hint else None
                ], color="danger")
            ])
            return None, error_display
        
        response.raise_for_status()
        data = response.json()
        
        # Display success message with result counts
        is_graph = data.get("isGraph", False)
        node_count = len(data.get("nodes", []))
        rel_count = len(data.get("relationships", []))
        result_count = data.get("resultCount", 0)
        
        if is_graph:
            success_display = html.Div([
                dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    f"Query executed successfully! Found {node_count} nodes and {rel_count} relationships."
                ], color="success", className="mb-3"),
                html.Div([
                    html.H6("Graph visualization will be available in Phase 3", className="text-muted mb-2"),
                    html.P("For now, here's the raw data:", className="mb-2"),
                    html.Pre(
                        str(data),
                        style={
                            "backgroundColor": "#f8f9fa",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "maxHeight": "400px",
                            "overflowY": "auto",
                            "fontSize": "12px"
                        }
                    )
                ])
            ])
        else:
            # Tabular results
            raw_results = data.get("rawResults", [])
            success_display = html.Div([
                dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    f"Query executed successfully! Retrieved {result_count} result(s)."
                ], color="success", className="mb-3"),
                html.Div([
                    html.H6("Tabular Results:", className="mb-2"),
                    html.Pre(
                        str(raw_results),
                        style={
                            "backgroundColor": "#f8f9fa",
                            "padding": "12px",
                            "borderRadius": "8px",
                            "maxHeight": "400px",
                            "overflowY": "auto",
                            "fontSize": "12px"
                        }
                    )
                ])
            ])
        
        return data, success_display
        
    except requests.exceptions.Timeout:
        error_display = html.Div([
            dbc.Alert([
                html.I(className="fas fa-clock me-2"),
                f"Query timeout: The query took longer than {TIMEOUT_SECONDS} seconds to execute."
            ], color="warning")
        ])
        return None, error_display
    except requests.exceptions.ConnectionError:
        error_display = html.Div([
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                "Connection error: Unable to connect to the backend API. Please ensure the server is running."
            ], color="danger")
        ])
        return None, error_display
    except requests.exceptions.HTTPError as e:
        error_display = html.Div([
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"HTTP Error: {str(e)}"
            ], color="danger")
        ])
        return None, error_display
    except Exception as e:
        error_display = html.Div([
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"Unexpected error: {str(e)}"
            ], color="danger")
        ])
        return None, error_display

