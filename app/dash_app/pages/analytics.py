"""Analytics gallery page for pre-built graph visualizations."""

from urllib.parse import urlencode

from dash import Input, Output, State, callback, html
import dash_bootstrap_components as dbc

from app.analytics.collaboration.config import (
    CollaborationNetworkConfig,
    DEFAULT_EXCLUDE_BOTS,
    DEFAULT_ENSURE_MIN_CONNECTION,
    DEFAULT_COMMUNITY_GAP_X,
    DEFAULT_COMMUNITY_GAP_Y,
    DEFAULT_LAYER_WEIGHTS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_PAIR_SCORE,
    DEFAULT_TOP_N_EDGES_PER_NODE,
    LAYER_LABELS,
    LAYER_ORDER,
)
from app.analytics.registry import GRAPH_ANALYTICS
from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_DARK,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_MEDIUM,
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_XSMALL,
)


def get_layout():
    """Return the analytics gallery page."""
    return html.Div(
        [
            create_page_header("Analytics"),
            html.Div(
                [
                    html.Div(
                        "Launch pre-built graph visualizations for common leadership and delivery questions.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginBottom": SPACING_MEDIUM,
                        },
                    ),
                    dbc.Row(
                        [
                            dbc.Col(_create_analytic_card(analytic), md=6, className="mb-3")
                            for analytic in GRAPH_ANALYTICS
                        ],
                        className="g-3",
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )


def _create_analytic_card(analytic) -> dbc.Card:
    is_collaboration = analytic.key == "collaboration_network"

    footer = (
        _create_collaboration_controls()
        if is_collaboration
        else dbc.Button("Open Visualization", href=analytic.href, color="primary", size="sm")
    )

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className=analytic.icon, style={"fontSize": "20px", "color": COLOR_CHARCOAL_MEDIUM}),
                        html.Span(
                            analytic.title,
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_LARGE,
                                "fontWeight": FONT_WEIGHT_MEDIUM,
                                "color": COLOR_GRAY_DARK,
                                "marginLeft": SPACING_XSMALL,
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": SPACING_SMALL},
                ),
                html.Div(
                    analytic.description,
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_MEDIUM,
                        "color": COLOR_GRAY_MEDIUM,
                        "lineHeight": "1.6",
                        "marginBottom": SPACING_MEDIUM,
                    },
                ),
                footer,
            ]
        ),
        style={
            "backgroundColor": COLOR_BACKGROUND_WHITE,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "padding": SPACING_SMALL,
            "minHeight": "220px",
            "boxShadow": "none",
        },
    )


def _create_collaboration_controls() -> html.Div:
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Button(
                            "Open Visualization",
                            id="collab-open-btn",
                            href="/app/graph?mode=collaboration_network",
                            color="primary",
                            size="sm",
                        ),
                        width="auto",
                    ),
                    dbc.Col(
                        dbc.Button(
                            "Show Options",
                            id="collab-controls-toggle-btn",
                            color="secondary",
                            outline=True,
                            size="sm",
                        ),
                        width="auto",
                    ),
                ],
                className="g-2 align-items-center",
            ),
            dbc.Collapse(
                [
                    html.Div(
                        "Adjust layers and weights before opening the graph.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginBottom": SPACING_XSMALL,
                            "marginTop": SPACING_SMALL,
                        },
                    ),
                    html.Label("Layers", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                    dbc.Checklist(
                        id="collab-layers",
                        options=[{"label": LAYER_LABELS[layer], "value": layer} for layer in LAYER_ORDER],
                        value=list(LAYER_ORDER),
                        inline=False,
                        style={"fontSize": FONT_SIZE_SMALL, "marginBottom": SPACING_SMALL},
                    ),
                    dbc.Row(
                        [
                            dbc.Col(_weight_input(layer), md=6)
                            for layer in LAYER_ORDER
                        ],
                        className="g-2 mb-2",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Community Gap X", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                                    dbc.Input(
                                        id="collab-community-gap-x",
                                        type="number",
                                        min=200,
                                        max=10000,
                                        step=10,
                                        value=DEFAULT_COMMUNITY_GAP_X,
                                        size="sm",
                                    ),
                                ],
                                md=6,
                            ),
                            dbc.Col(
                                [
                                    html.Label("Community Gap Y", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                                    dbc.Input(
                                        id="collab-community-gap-y",
                                        type="number",
                                        min=200,
                                        max=10000,
                                        step=10,
                                        value=DEFAULT_COMMUNITY_GAP_Y,
                                        size="sm",
                                    ),
                                ],
                                md=6,
                            ),
                        ],
                        className="g-2 mb-2",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Lookback Days", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                                    dbc.Input(id="collab-lookback-days", type="number", min=1, max=365, step=1, value=DEFAULT_LOOKBACK_DAYS, size="sm"),
                                ],
                                md=4,
                            ),
                            dbc.Col(
                                [
                                    html.Label("Min Pair Score", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                                    dbc.Input(id="collab-min-pair-score", type="number", min=0, step=0.1, value=DEFAULT_MIN_PAIR_SCORE, size="sm"),
                                ],
                                md=4,
                            ),
                            dbc.Col(
                                [
                                    html.Label("Top-N Edges / Node", style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS}),
                                    dbc.Input(id="collab-top-n-edges", type="number", min=0, max=200, step=1, value=DEFAULT_TOP_N_EDGES_PER_NODE, size="sm"),
                                ],
                                md=4,
                            ),
                        ],
                        className="g-2 mb-2",
                    ),
                    html.Div(
                        "Tip: For dense networks, start with X=1400-2400 and Y=1000-1800. Higher values increase spacing between communities.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": "11px",
                            "color": COLOR_GRAY_MEDIUM,
                            "marginTop": "-4px",
                            "marginBottom": SPACING_XSMALL,
                        },
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Switch(
                                    id="collab-exclude-bots",
                                    label="Exclude bots",
                                    value=DEFAULT_EXCLUDE_BOTS,
                                ),
                                md=6,
                            ),
                            dbc.Col(
                                dbc.Switch(
                                    id="collab-ensure-min-connection",
                                    label="Ensure min connection",
                                    value=DEFAULT_ENSURE_MIN_CONNECTION,
                                ),
                                md=6,
                            ),
                        ],
                        className="g-2 mb-2",
                    ),
                ],
                id="collab-controls-collapse",
                is_open=False,
            ),
            html.Div(
                id="collab-url-preview",
                style={
                    "fontSize": "11px",
                    "color": COLOR_GRAY_MEDIUM,
                    "marginTop": SPACING_XSMALL,
                    "wordBreak": "break-all",
                },
            ),
        ]
    )


def _weight_input(layer: str) -> html.Div:
    return html.Div(
        [
            html.Label(
                f"Weight: {LAYER_LABELS[layer]}",
                style={"fontSize": FONT_SIZE_SMALL, "fontFamily": FONT_SANS},
            ),
            dbc.Input(
                id=f"collab-weight-{layer}",
                type="number",
                min=0,
                step=0.1,
                value=DEFAULT_LAYER_WEIGHTS[layer],
                size="sm",
            ),
        ]
    )


@callback(
    [Output("collab-open-btn", "href"), Output("collab-url-preview", "children")],
    [
        Input("collab-layers", "value"),
        Input("collab-lookback-days", "value"),
        Input("collab-min-pair-score", "value"),
        Input("collab-top-n-edges", "value"),
        Input("collab-community-gap-x", "value"),
        Input("collab-community-gap-y", "value"),
        Input("collab-exclude-bots", "value"),
        Input("collab-ensure-min-connection", "value"),
        Input("collab-weight-reporter_assignee", "value"),
        Input("collab-weight-pr_reviews", "value"),
        Input("collab-weight-shared_file_commits", "value"),
        Input("collab-weight-sprint_coworkers", "value"),
        Input("collab-weight-explicit_review_requests", "value"),
        Input("collab-weight-epic_overlap", "value"),
    ],
)
def build_collaboration_href(
    layers,
    lookback_days,
    min_pair_score,
    top_n_edges_per_node,
    community_gap_x,
    community_gap_y,
    exclude_bots,
    ensure_min_connection,
    w_reporter_assignee,
    w_pr_reviews,
    w_shared_file_commits,
    w_sprint_coworkers,
    w_explicit_review_requests,
    w_epic_overlap,
):
    """Build a graph-mode URL that carries collaboration query overrides."""
    query_values = {
        "layers": layers or list(LAYER_ORDER),
        "lookback_days": lookback_days,
        "min_pair_score": min_pair_score,
        "top_n_edges_per_node": top_n_edges_per_node,
        "community_gap_x": community_gap_x,
        "community_gap_y": community_gap_y,
        "exclude_bots": exclude_bots,
        "ensure_min_connection": ensure_min_connection,
        "w_reporter_assignee": w_reporter_assignee,
        "w_pr_reviews": w_pr_reviews,
        "w_shared_file_commits": w_shared_file_commits,
        "w_sprint_coworkers": w_sprint_coworkers,
        "w_explicit_review_requests": w_explicit_review_requests,
        "w_epic_overlap": w_epic_overlap,
    }

    try:
        config = CollaborationNetworkConfig.from_query_values(query_values)
    except Exception:
        config = CollaborationNetworkConfig()

    params = {
        "mode": "collaboration_network",
        "layers": ",".join(config.enabled_layers),
        "lookback_days": config.lookback_days,
        "min_pair_score": config.min_pair_score,
        "top_n_edges_per_node": config.top_n_edges_per_node,
        "community_gap_x": config.community_gap_x,
        "community_gap_y": config.community_gap_y,
        "exclude_bots": str(config.exclude_bots).lower(),
        "ensure_min_connection": str(config.ensure_min_connection).lower(),
        "w_reporter_assignee": config.weights["reporter_assignee"],
        "w_pr_reviews": config.weights["pr_reviews"],
        "w_shared_file_commits": config.weights["shared_file_commits"],
        "w_sprint_coworkers": config.weights["sprint_coworkers"],
        "w_explicit_review_requests": config.weights["explicit_review_requests"],
        "w_epic_overlap": config.weights["epic_overlap"],
    }

    href = f"/app/graph?{urlencode(params)}"
    return href, f"URL: {href}"


@callback(
    [Output("collab-controls-collapse", "is_open"), Output("collab-controls-toggle-btn", "children")],
    Input("collab-controls-toggle-btn", "n_clicks"),
    State("collab-controls-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_collaboration_controls(_n_clicks, is_open):
    """Toggle collaboration controls visibility in the analytics card."""
    next_state = not is_open
    label = "Hide Options" if next_state else "Show Options"
    return next_state, label
