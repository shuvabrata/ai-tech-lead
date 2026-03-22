"""Query Execution Callbacks

Callbacks for query validation and execution.
"""

import time
import requests
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback

from app.settings import settings
from app.common.logger import logger
from app.dash_app.styles import (
    VALIDATION_ALERT_STYLE,
    VALIDATION_CODE_STYLE,
    GRAPH_DETAILS_PANEL_STYLE
)
from ..utils import (
    neo4j_to_cytoscape,
    parse_error_response,
    create_error_alert,
    create_table_display,
    create_graph_success_alert,
    create_performance_metrics,
    get_graph_api_base_url,
)

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


@callback(
    Output("query-validation-message", "children"),
    Input("graph-query-input", "value")
)
def validate_query(query_text):
    """Validate Cypher query and provide real-time feedback"""
    # Empty query - no message
    if not query_text or not query_text.strip():
        return None
    
    query_upper = query_text.strip().upper()
    
    # Check for write operations (not allowed)
    write_keywords = ['CREATE', 'MERGE', 'SET', 'DELETE', 'REMOVE', 'DROP']
    for keyword in write_keywords:
        if f' {keyword} ' in f' {query_upper} ' or query_upper.startswith(f'{keyword} '):
            return dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"Write operations ({keyword}) are not allowed for security reasons. Only read-only queries (MATCH, RETURN) are permitted."
            ], color="danger", className="mb-0", style=VALIDATION_ALERT_STYLE)
    
    # Check if query starts with valid read keywords
    valid_starts = ['MATCH', 'RETURN', 'WITH', 'UNWIND', 'CALL', 'OPTIONAL']
    starts_valid = any(query_upper.startswith(keyword) for keyword in valid_starts)
    
    if not starts_valid:
        return dbc.Alert([
            html.I(className="fas fa-info-circle me-2"),
            "Query should typically start with MATCH, RETURN, or other read-only keywords."
        ], color="warning", className="mb-0", style=VALIDATION_ALERT_STYLE)
    
    # Check for missing LIMIT (performance warning)
    if 'LIMIT' not in query_upper and 'MATCH' in query_upper:
        return dbc.Alert([
            html.I(className="fas fa-lightbulb me-2"),
            "Consider adding ",
            html.Code("LIMIT 100", style=VALIDATION_CODE_STYLE),
            " to improve query performance and avoid loading too many nodes."
        ], color="info", className="mb-0", style=VALIDATION_ALERT_STYLE)
    
    # Query looks good
    return None


@callback(
    [Output("graph-data-store", "data"),
     Output("graph-cytoscape", "elements"),
     Output("graph-cytoscape-container", "style"),
     Output("graph-table-container", "children"),
     Output("graph-table-container", "style"),
     Output("graph-results-container", "children"),
     Output("graph-results-container", "style"),
     Output("graph-details-panel", "style"),
     Output("graph-performance-metrics", "children"),
     Output("graph-performance-metrics", "style"),
     Output("loaded-node-ids", "data"),
     Output("expanded-nodes", "data"),
    Output("expansion-debounce-store", "data"),
    Output("unfiltered-elements-store", "data"),
    Output("node-type-filter", "value", allow_duplicate=True),
    Output("relationship-type-filter", "value", allow_duplicate=True),
    Output("weight-threshold-slider", "value", allow_duplicate=True),
    Output("top-n-toggle", "value", allow_duplicate=True)],
    [Input("graph-execute-btn", "n_clicks")],
    [State("graph-query-input", "value")],
    prevent_initial_call=True
)
def execute_query(_n_clicks, query_text):
    """Execute Cypher query and display results"""
    # Default empty states
    empty_elements = []
    hide_style = {"display": "none"}
    show_style = {"display": "block"}
    # Keep graph container style consistent - don't change size
    graph_container_style = {"display": "block"}
    default_container_style = {"minHeight": "400px", "padding": "20px"}
    panel_visible_style = GRAPH_DETAILS_PANEL_STYLE
    default_filters = ([], [], 0, "all")

    def build_response(
        graph_data,
        elements,
        table_children,
        table_style,
        results_children,
        results_style,
        details_style,
        metrics_children,
        metrics_style,
        unfiltered_elements,
    ):
        """Build execute-query callback response with a stable output contract."""
        return (
            graph_data,
            elements,
            graph_container_style,
            table_children,
            table_style,
            results_children,
            results_style,
            details_style,
            metrics_children,
            metrics_style,
            [],
            {},
            {},
            unfiltered_elements,
            *default_filters,
        )

    def error_response(error_display):
        return build_response(
            None,
            empty_elements,
            None,
            hide_style,
            error_display,
            default_container_style,
            hide_style,
            None,
            hide_style,
            [],
        )
    
    # Validate query not empty
    if not query_text or not query_text.strip():
        error_display = create_error_alert(
            "Please enter a Cypher query before executing.",
            alert_type='warning',
            heading=None
        )
        return error_response(error_display)
    
    # Get API base URL
    api_base = get_graph_api_base_url()
    
    # Track execution time
    start_time = time.time()
    query_preview = (query_text or "").strip().replace("\n", " ")[:120]
    logger.info(
        "[GRAPH-DEBUG][query.execute] start "
        f"query_len={len((query_text or '').strip())} api_base={api_base} "
        f"preview='{query_preview}'"
    )
    
    try:
        # Send query to API
        response = requests.post(
            f"{api_base}/api/v1/graph/query",
            json={"query": query_text},
            timeout=TIMEOUT_SECONDS
        )
        
        # Calculate execution time in milliseconds
        execution_time_ms = (time.time() - start_time) * 1000
        logger.info(
            "[GRAPH-DEBUG][query.execute] response "
            f"status={response.status_code} duration_ms={round(execution_time_ms, 2)}"
        )
        
        # Handle error responses
        if response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            error_preview = ""
            try:
                error_preview = (response.text or "")[:500]
            except Exception:
                error_preview = ""
            logger.warning(
                "[GRAPH-DEBUG][query.execute] error "
                f"status={response.status_code} error_preview='{error_preview}'"
            )
            
            # Parse error and get user-friendly message
            heading, hint, doc_link, alert_type = parse_error_response(error_data, response.status_code)
            
            error_display = create_error_alert(
                "",  # message is in heading for parsed errors
                alert_type=alert_type,
                hint=hint,
                heading=heading,
                doc_link=doc_link
            )
            return error_response(error_display)
        
        response.raise_for_status()
        data = response.json()
        
        # Check if result is a graph or tabular data
        is_graph = data.get("isGraph", False)
        node_count = len(data.get("nodes", []))
        rel_count = len(data.get("relationships", []))
        result_count = data.get("resultCount", 0)
        logger.info(
            "[GRAPH-DEBUG][query.execute] parsed "
            f"is_graph={is_graph} nodes={node_count} rels={rel_count} "
            f"result_count={result_count}"
        )
        
        if is_graph:
            # Transform data to Cytoscape format
            cyto_elements = neo4j_to_cytoscape(data)

            success_alert = create_graph_success_alert(node_count, rel_count)
            performance_metrics = create_performance_metrics(node_count, rel_count, execution_time_ms, is_graph=True)
            
            # Show graph, hide table and default, show details panel
            return build_response(
                data,
                cyto_elements,
                success_alert,
                show_style,
                None,
                hide_style,
                panel_visible_style,  # Show details panel for graph results
                performance_metrics,
                show_style,  # Show performance metrics
                cyto_elements,  # Reset unfiltered baseline to fresh execute result
            )
        else:
            # Tabular results - create table
            raw_results = data.get("rawResults", [])
            table_display = create_table_display(raw_results, result_count)
            performance_metrics = create_performance_metrics(result_count, 0, execution_time_ms, is_graph=False)
            
            # Show table, hide graph and default, hide details panel
            return build_response(
                data,
                empty_elements,
                table_display,
                show_style,
                None,
                hide_style,
                hide_style,  # Hide details panel for tabular results
                performance_metrics,
                show_style,  # Show performance metrics
                [],  # No unfiltered graph baseline for tabular query
            )
        
    except requests.exceptions.Timeout:
        logger.error(
            "[GRAPH-DEBUG][query.execute] timeout "
            f"timeout_seconds={TIMEOUT_SECONDS} api_base={api_base}"
        )
        error_display = create_error_alert(
            "",
            alert_type='warning',
            heading=f"⏱️ Request Timeout ({TIMEOUT_SECONDS}s)",
            hint=f"The request to the backend API took longer than {TIMEOUT_SECONDS} seconds. Your query might be too complex or the database is slow. Try adding LIMIT 100 to reduce the result set.",
            doc_link="https://neo4j.com/docs/cypher-manual/current/clauses/limit/"
        )
        return error_response(error_display)
    
    except requests.exceptions.ConnectionError:
        api_url = get_graph_api_base_url()
        logger.error(
            "[GRAPH-DEBUG][query.execute] connection_error "
            f"api_base={api_url}"
        )
        error_display = create_error_alert(
            "",
            alert_type='danger',
            heading="🔌 Backend API Connection Failed",
            hint=f"Unable to connect to the backend API at {api_url}. Please ensure the FastAPI server is running using 'uvicorn app.main:app --reload'.",
            doc_link=None
        )
        return error_response(error_display)
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"[GRAPH-DEBUG][query.execute] http_error {e}")
        error_display = create_error_alert(
            "",
            alert_type='danger',
            heading="⚠️ HTTP Error",
            hint=f"An HTTP error occurred: {str(e)}. This usually indicates a server-side issue. Check the backend logs for more details.",
            doc_link=None
        )
        return error_response(error_display)
    
    except Exception as e:
        logger.exception(f"[GRAPH-DEBUG][query.execute] unexpected_error {e}")
        error_display = create_error_alert(
            "",
            alert_type='danger',
            heading="💥 Unexpected Error",
            hint=f"An unexpected error occurred: {str(e)}. Please try again or contact support if the issue persists.",
            doc_link=None
        )
        return error_response(error_display)
