"""Search Page — C1a: Static layout.

Provides the full-text entity search interface backed by Elasticsearch.
Callbacks (search execution, pagination) are wired in C1b and C1c.
"""

from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.dash_app.components.common import create_alert
from app.dash_app.styles import (
    COLOR_BORDER,
    COLOR_GRAY_MEDIUM,
    COLOR_NAVY,
    COLOR_BACKGROUND_LIGHT,
    FONT_SANS,
    FONT_SIZE_XSMALL,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
    FONT_WEIGHT_MEDIUM,
    INPUT_STYLE,
    SPACING_XXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
    SPACING_MEDIUM,
    SPACING_LARGE,
    PLACEHOLDER_ICON_STYLE,
    PLACEHOLDER_MESSAGE_STYLE,
    CARD_CONTAINER_STYLE,
)
from app.settings import settings
from app.scripts.create_es_indexes import MANAGED_INDEXES


# ---------------------------------------------------------------------------
# Dropdown options derived from MANAGED_INDEXES — stays in sync automatically
# as new (source, entity_type) pairs are registered in create_es_indexes.py.
# ---------------------------------------------------------------------------
_SOURCES = sorted({source for source, _ in MANAGED_INDEXES})
_ENTITY_TYPES = sorted({entity_type for _, entity_type in MANAGED_INDEXES})

_SOURCE_OPTIONS = [{"label": "All sources", "value": ""}] + [
    {"label": s.capitalize(), "value": s} for s in _SOURCES
]
_ENTITY_TYPE_OPTIONS = [{"label": "All types", "value": ""}] + [
    {"label": et, "value": et} for et in _ENTITY_TYPES
]

# ---------------------------------------------------------------------------
# Layout helper styles (page-scoped, not worth adding to styles.py)
# ---------------------------------------------------------------------------
_LABEL_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "fontWeight": FONT_WEIGHT_MEDIUM,
    "color": COLOR_GRAY_MEDIUM,
    "textTransform": "uppercase",
    "letterSpacing": "0.8px",
    "marginBottom": SPACING_XXSMALL,
}

_RESULTS_HEADER_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "borderBottom": f"1px solid {COLOR_BORDER}",
    "paddingBottom": SPACING_XSMALL,
    "marginBottom": SPACING_SMALL,
}

_COUNT_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "color": COLOR_GRAY_MEDIUM,
    "letterSpacing": "0.5px",
}

_PAGINATION_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "gap": SPACING_SMALL,
    "marginTop": SPACING_MEDIUM,
    "paddingTop": SPACING_SMALL,
    "borderTop": f"1px solid {COLOR_BORDER}",
}

_PAGE_INDICATOR_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "color": COLOR_GRAY_MEDIUM,
    "minWidth": "80px",
    "textAlign": "center",
}


def _build_filters_panel() -> dbc.Collapse:
    """Return the collapsible advanced filters panel."""
    return dbc.Collapse(
        html.Div(
            dbc.Row(
                [
                    # Entity type
                    dbc.Col(
                        [
                            html.Label("Entity Type", style=_LABEL_STYLE),
                            dbc.Select(
                                id="search-entity-type",
                                options=_ENTITY_TYPE_OPTIONS,
                                value="",
                                style={**INPUT_STYLE, "height": "36px"},
                            ),
                        ],
                        md=3,
                        className="mb-2",
                    ),
                    # Source
                    dbc.Col(
                        [
                            html.Label("Source", style=_LABEL_STYLE),
                            dbc.Select(
                                id="search-source",
                                options=_SOURCE_OPTIONS,
                                value="",
                                style={**INPUT_STYLE, "height": "36px"},
                            ),
                        ],
                        md=2,
                        className="mb-2",
                    ),
                    # Status — free-text; could be upgraded to a context-aware
                    # dropdown in a future pass when source filter is also set.
                    dbc.Col(
                        [
                            html.Label("Status", style=_LABEL_STYLE),
                            dbc.Input(
                                id="search-status",
                                type="text",
                                placeholder="e.g. open, done…",
                                style=INPUT_STYLE,
                            ),
                        ],
                        md=2,
                        className="mb-2",
                    ),
                    # Priority — same rationale as Status above.
                    dbc.Col(
                        [
                            html.Label("Priority", style=_LABEL_STYLE),
                            dbc.Input(
                                id="search-priority",
                                type="text",
                                placeholder="e.g. high, medium…",
                                style=INPUT_STYLE,
                            ),
                        ],
                        md=2,
                        className="mb-2",
                    ),
                    # Date from
                    dbc.Col(
                        [
                            html.Label("From", style=_LABEL_STYLE),
                            dbc.Input(
                                id="search-date-from",
                                type="date",
                                style=INPUT_STYLE,
                            ),
                        ],
                        md=2,
                        className="mb-2",
                    ),
                    # Date to
                    dbc.Col(
                        [
                            html.Label("To", style=_LABEL_STYLE),
                            dbc.Input(
                                id="search-date-to",
                                type="date",
                                style=INPUT_STYLE,
                            ),
                        ],
                        md=2,
                        className="mb-2",
                    ),
                ],
                className="g-2",
            ),
            style={
                "backgroundColor": COLOR_BACKGROUND_LIGHT,
                "border": f"1px solid {COLOR_BORDER}",
                "borderTop": "none",
                "borderRadius": "0 0 2px 2px",
                "padding": f"{SPACING_SMALL} {SPACING_SMALL} {SPACING_XXSMALL}",
            },
        ),
        id="search-filters-collapse",
        is_open=False,
    )


def _build_placeholder() -> html.Div:
    """Return the empty-state placeholder shown before any search is run."""
    return html.Div(
        [
            html.Div(
                html.I(className="fas fa-search"),
                style=PLACEHOLDER_ICON_STYLE,
            ),
            html.Div(
                "Enter a search term to find people, issues, pull requests, and more",
                style=PLACEHOLDER_MESSAGE_STYLE,
            ),
        ],
        id="search-empty-state",
        style={"paddingTop": SPACING_LARGE, "paddingBottom": SPACING_LARGE},
    )


def _build_pagination_row() -> html.Div:
    """Return the Prev / page-indicator / Next pagination row."""
    return html.Div(
        [
            dbc.Button(
                [html.I(className="fas fa-chevron-left me-1"), "Prev"],
                id="search-prev-btn",
                color="secondary",
                outline=True,
                size="sm",
                disabled=True,
                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_XSMALL},
            ),
            html.Div(
                "Page 1",
                id="search-page-indicator",
                style=_PAGE_INDICATOR_STYLE,
            ),
            dbc.Button(
                ["Next", html.I(className="fas fa-chevron-right ms-1")],
                id="search-next-btn",
                color="secondary",
                outline=True,
                size="sm",
                disabled=True,
                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_XSMALL},
            ),
        ],
        id="search-pagination-row",
        style={**_PAGINATION_STYLE, "display": "none"},  # hidden until results arrive
    )


def get_layout() -> html.Div:
    """Return the Search page layout (static — callbacks wired in C1b / C1c)."""

    # Non-blocking warning banner when Elasticsearch is disabled
    es_disabled_banner = None
    if not settings.ELASTICSEARCH_ENABLED:
        es_disabled_banner = create_alert(
            [
                html.I(className="fas fa-exclamation-triangle me-2"),
                "Elasticsearch is disabled. Set ",
                html.Code("ELASTICSEARCH_ENABLED=true"),
                " in your environment to activate search.",
            ],
            color="warning",
            dismissable=True,
            class_name="mb-3",
        )

    return html.Div(
        [
            # Hidden state stores
            dcc.Store(id="search-current-page", storage_type="session", data=1),
            dcc.Store(id="search-last-query-params", storage_type="session", data={}),

            html.Div(
                [
                    # Optional ES-disabled banner
                    es_disabled_banner,

                    # ── Search bar ──────────────────────────────────────────
                    dbc.InputGroup(
                        [
                            dbc.Input(
                                id="search-q-input",
                                type="text",
                                placeholder="Search entities — people, issues, pull requests, commits…",
                                debounce=False,
                                n_submit=0,
                                style={
                                    **INPUT_STYLE,
                                    "borderRadius": "2px 0 0 2px",
                                    "height": "40px",
                                    "fontSize": FONT_SIZE_MEDIUM,
                                },
                            ),
                            dbc.Button(
                                html.I(className="fas fa-search"),
                                id="search-submit-btn",
                                color="primary",
                                n_clicks=0,
                                style={
                                    "backgroundColor": COLOR_NAVY,
                                    "border": f"1px solid {COLOR_NAVY}",
                                    "borderRadius": "0 2px 2px 0",
                                    "padding": f"0 {SPACING_SMALL}",
                                    "fontSize": FONT_SIZE_SMALL,
                                },
                            ),
                        ],
                        style={"marginBottom": "0"},
                    ),

                    # ── Filters toggle + collapse ───────────────────────────
                    html.Div(
                        dbc.Button(
                            [
                                html.I(
                                    className="fas fa-sliders-h me-1",
                                    style={"fontSize": FONT_SIZE_XSMALL},
                                ),
                                html.Span(
                                    "Filters",
                                    id="search-filters-toggle-label",
                                ),
                                html.I(
                                    className="fas fa-chevron-down ms-1",
                                    id="search-filters-chevron",
                                    style={"fontSize": FONT_SIZE_XSMALL},
                                ),
                            ],
                            id="search-filters-toggle-btn",
                            color="link",
                            size="sm",
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_XSMALL,
                                "color": COLOR_GRAY_MEDIUM,
                                "textDecoration": "none",
                                "padding": f"{SPACING_XXSMALL} 0",
                                "letterSpacing": "0.3px",
                            },
                        ),
                        style={"marginTop": SPACING_XXSMALL},
                    ),
                    _build_filters_panel(),

                    # ── Results header (count + full-attributes toggle) ─────
                    html.Div(
                        [
                            html.Div(
                                "",
                                id="search-results-count",
                                style=_COUNT_STYLE,
                            ),
                            dbc.Switch(
                                id="search-full-toggle",
                                label="Show all attributes",
                                value=False,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_XSMALL,
                                    "color": COLOR_GRAY_MEDIUM,
                                },
                            ),
                        ],
                        id="search-results-header",
                        style={**_RESULTS_HEADER_STYLE, "display": "none"},
                    ),

                    # ── Results container ──────────────────────────────────
                    html.Div(
                        _build_placeholder(),
                        id="search-results-container",
                    ),

                    # ── Pagination ─────────────────────────────────────────
                    _build_pagination_row(),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )
