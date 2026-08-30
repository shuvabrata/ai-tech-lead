"""Search Page — C1b: Search execution callback + result cards.

Provides the full-text entity search interface backed by Elasticsearch.
Pagination (Prev/Next) is wired in C1c.
"""

from __future__ import annotations

import math
import os
import re
import requests
from datetime import datetime
from urllib.parse import quote

from dash import callback, ctx, dcc, html, no_update, Input, Output, State
from dash.exceptions import PreventUpdate
from urllib.parse import parse_qs, unquote
import dash_bootstrap_components as dbc

from app.common.timezone import humanize_duration, to_app_timezone
from app.dash_app.components.common import create_alert
from app.dash_app.pages.graph.utils import fetch_effective_theme
from app.dash_app.styles import (
    COLOR_BORDER,
    COLOR_BORDER_LIGHT,
    COLOR_GRAY_MEDIUM,
    COLOR_NAVY,
    COLOR_BACKGROUND_LIGHT,
    COLOR_TEXT_SECONDARY,
    TOKENS,
    DETAILS_TABLE_STYLE,
    DETAILS_TABLE_KEY_STYLE,
    DETAILS_TABLE_VALUE_STYLE,
    DETAILS_TABLE_VALUE_MONO_STYLE,
    FONT_SANS,
    FONT_SIZE_TINY,
    FONT_SIZE_XSMALL,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
    FONT_WEIGHT_MEDIUM,
    FONT_WEIGHT_SEMIBOLD,
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
from app.runtime_settings import runtime_settings
from app.settings import settings
from app.scripts.create_es_indexes import MANAGED_INDEXES
from common.logger import logger


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


# ---------------------------------------------------------------------------
# API base URL — same pattern as graph page utils
# ---------------------------------------------------------------------------
def _get_api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Entity type → badge background colour (aligned with graph node palette)
# ---------------------------------------------------------------------------
# Base palette comes from the same TOKENS dict as the graph page so badge
# colours always match the Cytoscape node colours exactly. These values are
# the *fallback*: at render time the effective graph theme (base ⊕ user
# overrides, fetched from /api/v1/graph-themes/effective) may override them via
# :func:`_badge_colors_from_effective`. The unit test
# tests/test_search_node_color_consistency.py enforces the invariant.
_ENTITY_TYPE_BADGE_COLORS: dict[str, str] = {
    "Person": TOKENS["graph.node.person"],
    "Issue": TOKENS["graph.node.issue"],
    "Epic": TOKENS["graph.node.epic"],
    "Repository": TOKENS["graph.node.repository"],
    "Branch": TOKENS["graph.node.branch"],
    "Project": TOKENS["graph.node.project"],
    "Team": TOKENS["graph.node.team"],
    "IdentityMapping": TOKENS["graph.node.identity_mapping"],
    "Initiative": TOKENS["graph.node.initiative"],
    "Sprint": TOKENS["graph.node.sprint"],
    "Commit": TOKENS["graph.node.commit"],
    "File": TOKENS["graph.node.file"],
    "PullRequest": TOKENS["graph.node.pull_request"],
    "Space": TOKENS["graph.node.space"],
    "Page": TOKENS["graph.node.page"],
    "Blogpost": TOKENS["graph.node.blogpost"],
}

_DEFAULT_BADGE_COLOR = TOKENS["graph.node.default"]


def _badge_colors_from_effective(effective: dict | None) -> dict[str, str]:
    """Resolve nodeType → badge colour from an effective theme document.

    ``effective`` is the merged tokens returned by ``/api/v1/graph-themes/effective``
    (shape: ``{"nodes": {<Type>: {"background-color": ...}, "default": {...}}, ...}``).
    Base colours are the fallback; any node type present in the effective theme
    overrides its base colour. Returns a copy, never mutates the base map.
    """
    colors = dict(_ENTITY_TYPE_BADGE_COLORS)
    if not effective:
        return colors
    nodes = effective.get("nodes", {})
    for node_type, base_color in _ENTITY_TYPE_BADGE_COLORS.items():
        props = nodes.get(node_type, {})
        if props and props.get("background-color"):
            colors[node_type] = props["background-color"]
    return colors


def _badge_color(
    entity_type: str, badge_colors: dict[str, str] | None = None
) -> str:
    """Return the badge background hex colour for a given entity type.

    ``badge_colors`` is the resolved effective nodeType → colour map (from the
    graph-theme store). When omitted, the base ``TOKENS`` snapshot is used.
    """
    colors = badge_colors or _ENTITY_TYPE_BADGE_COLORS
    return colors.get(entity_type, _DEFAULT_BADGE_COLOR)


# ---------------------------------------------------------------------------
# Result card helpers
# ---------------------------------------------------------------------------

def _format_event_time(event_time_str: str | None) -> html.Span | str:
    """Format an ISO 8601 event_time string using app timezone and humanized duration."""
    if not event_time_str:
        return ""
    try:
        dt = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
        local_dt = to_app_timezone(dt)
        actual_time = local_dt.strftime(runtime_settings.get("UI_DATETIME_FORMAT"))
        duration_str = humanize_duration(local_dt)
        return html.Span(duration_str, title=actual_time)
    except Exception as exc:
        logger.warning("Failed to parse event time '%s': %s", event_time_str, exc)
        return event_time_str


def _extract_display_name(wba_id: str, attributes: dict | None) -> str:
    """Return a human-readable display name for a search result.

    When full=True, prefer rich attribute fields in order of specificity.
    Falls back to the last segment of wba_id for full=False results.
    """
    if attributes:
        for field in ("full_name", "title", "summary", "name", "key"):
            value = attributes.get(field)
            if value and isinstance(value, str) and value.strip():
                return value.strip()
    # Fallback: last segment of wba_id (e.g. "alice_dev" or "PROJ-123")
    parts = wba_id.split("::")
    return parts[-1] if parts else wba_id


def _build_attributes_table(attributes: dict) -> html.Table:
    """Render the attributes dict as a two-column table — matches graph Details Panel."""
    rows = []
    for key, value in sorted(attributes.items()):
        if value is None or str(key).startswith("_"):
            continue
        str_value = str(value)
        # Monospace for IDs and long technical tokens (no spaces, >16 chars)
        is_mono = key in ("id", "wba_id") or (
            len(str_value) > 16 and " " not in str_value
        )
        
        formatted_date = None
        if isinstance(str_value, str) and ("T" in str_value or "Z" in str_value) and len(str_value) >= 19:
            try:
                dt = datetime.fromisoformat(str_value.replace("Z", "+00:00"))
                local_dt = to_app_timezone(dt)
                actual_time = local_dt.strftime(runtime_settings.get("UI_DATETIME_FORMAT"))
                duration_str = humanize_duration(local_dt)
                formatted_date = html.Span(duration_str, title=actual_time, style=DETAILS_TABLE_VALUE_STYLE)
            except Exception:
                pass
                
        if formatted_date:
            value_cell = formatted_date
        elif is_mono:
            value_cell = html.Code(str_value, style=DETAILS_TABLE_VALUE_MONO_STYLE)
        else:
            value_cell = html.Span(str_value, style=DETAILS_TABLE_VALUE_STYLE)
            
        rows.append(
            html.Tr([
                html.Td(key, style=DETAILS_TABLE_KEY_STYLE),
                html.Td(
                    value_cell,
                    style={
                        "padding": "6px 0 6px 8px",
                        "borderBottom": f"1px solid {COLOR_BORDER_LIGHT}",
                        "verticalAlign": "top",
                        "wordBreak": "break-word",
                    },
                ),
            ])
        )
    return html.Table(html.Tbody(rows), style=DETAILS_TABLE_STYLE)


def _build_node_cypher(wba_id: str) -> str:
    """Build a Cypher query that loads a node and its immediate neighbours."""
    return (
        f"MATCH (n {{id: '{wba_id}'}}) "
        f"OPTIONAL MATCH (n)-[r]-(m) "
        f"RETURN n, r, m LIMIT 50"
    )


# ---------------------------------------------------------------------------
# Person "activity" time-window deep-links
#
# Each Person result exposes three extra actions (24 hrs / 7 days / 30 days)
# that deep-link into the Graph page with a time-windowed Cypher query. The
# window is a rolling duration applied to the neighbour node's
# ``_last_updated_at`` / ``_created_at`` and, for interaction edges
# (COMMENTED_ON / REACTED_TO), to ``r.last_interaction_at``. This surfaces the
# Person's "hot neighbourhood" — the things they're connected to that changed
# recently — without manually working the graph page's Time Filters.
# ---------------------------------------------------------------------------

#: Ordered (label, duration) pairs rendered as buttons under "View in Graph".
_PERSON_ACTIVITY_WINDOWS: tuple[tuple[str, str], ...] = (
    ("24 hrs", "PT24H"),
    ("7 days", "P7D"),
    ("30 days", "P30D"),
)


def _build_person_activity_cypher(wba_id: str, duration: str) -> str:
    """Build a time-windowed Cypher query for a Person's recent neighbourhood.

    Parameters
    ----------
    wba_id : str
        Canonical WBA identifier (e.g. ``github::Person::shuvabrata``).
    duration : str
        ISO 8601 duration literal (e.g. ``"P7D"``, ``"PT24H"``).

    Returns
    -------
    str
        Cypher query keeping the Person anchor even when no neighbour falls
        within the window (``OPTIONAL MATCH`` emits the ``(n, null, null)``
        row, so the anchor node is always returned).
    """
    return (
        f"MATCH (n {{id: '{wba_id}'}}) "
        f"OPTIONAL MATCH (n)-[r]-(m) "
        f"WHERE m._last_updated_at >= datetime() - duration('{duration}') "
        f"OR m._created_at >= datetime() - duration('{duration}') "
        f"OR r.last_interaction_at >= datetime() - duration('{duration}') "
        f"RETURN n, r, m LIMIT 50"
    )


def _build_person_activity_buttons(wba_id: str) -> list:
    """Build the three time-window deep-link buttons for a Person result.

    Parameters
    ----------
    wba_id : str
        Canonical WBA identifier for the Person.

    Returns
    -------
    list
        A list of ``dbc.Button`` ("24 hrs", "7 days", "30 days") linking to the
        Graph page with a time-windowed Cypher query. Inline buttons — the
        caller places them alongside the primary "View in Graph" action.
    """
    buttons = []
    for label, duration in _PERSON_ACTIVITY_WINDOWS:
        buttons.append(
            dbc.Button(
                [label, html.I(className="fas fa-project-diagram ms-1")],
                href=f"/app/graph?cypher={quote(_build_person_activity_cypher(wba_id, duration))}",
                color="primary",
                outline=True,
                size="sm",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_TINY,
                    "borderRadius": "2px",
                    "padding": "2px 8px",
                    "letterSpacing": "0.3px",
                    "marginRight": SPACING_XXSMALL,
                },
            )
        )
    return buttons


def _parse_highlight(highlight: str) -> list:
    """Split a highlight string with <em> tags into a list of Dash components.

    Matched terms are wrapped in html.Mark with a subtle yellow background;
    surrounding text is rendered as plain strings.
    """
    parts: list = []
    segments = re.split(r"(<em>|</em>)", highlight)
    in_em = False
    for segment in segments:
        if segment == "<em>":
            in_em = True
        elif segment == "</em>":
            in_em = False
        elif segment:
            if in_em:
                parts.append(
                    html.Mark(
                        segment,
                        style={
                            "backgroundColor": "#fff3cd",
                            "fontStyle": "normal",
                            "padding": "0 1px",
                        },
                    )
                )
            else:
                parts.append(segment)
    return parts


def _build_result_card(result: dict, full: bool, badge_colors: dict[str, str] | None = None) -> html.Div:
    """Build a single search result card."""
    wba_id: str = result.get("wba_id", "")
    url: str | None = result.get("url")
    event_time: str | None = result.get("event_time")
    highlight: str | None = result.get("highlight")
    attributes: dict | None = result.get("attributes")

    # Parse entity type and source from wba_id: "{source}::{entity_type}::{id...}"
    parts = wba_id.split("::", 2)
    source_label = parts[0].capitalize() if len(parts) > 0 else ""
    entity_type = parts[1] if len(parts) > 1 else ""
    badge_bg = _badge_color(entity_type, badge_colors)

    display_name = _extract_display_name(wba_id, attributes)
    formatted_time = _format_event_time(event_time)

    # ── Badges + View in Graph ─────────────────────────────────────────────
    header_row = html.Div(
        [
            html.Div(
                [
                    html.Span(
                        entity_type or "Entity",
                        style={
                            "backgroundColor": badge_bg,
                            "color": "#f4f7fb",
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_TINY,
                            "fontWeight": FONT_WEIGHT_SEMIBOLD,
                            "letterSpacing": "0.6px",
                            "textTransform": "uppercase",
                            "padding": "2px 8px",
                            "borderRadius": "2px",
                            "marginRight": SPACING_XXSMALL,
                        },
                    ),
                    html.Span(
                        source_label,
                        style={
                            "backgroundColor": "transparent",
                            "color": COLOR_GRAY_MEDIUM,
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_TINY,
                            "fontWeight": FONT_WEIGHT_MEDIUM,
                            "letterSpacing": "0.5px",
                            "textTransform": "uppercase",
                            "padding": "2px 7px",
                            "borderRadius": "2px",
                            "border": f"1px solid {COLOR_BORDER}",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
            html.Div(
                [
                    # Person-only: time-window "activity" shortcuts preceding
                    # the primary "View in Graph" action, in the same row.
                    *(_build_person_activity_buttons(wba_id) if entity_type == "Person" else []),
                    dbc.Button(
                        ["View in Graph ", html.I(className="fas fa-project-diagram ms-1")],
                        href=f"/app/graph?cypher={quote(_build_node_cypher(wba_id))}",
                        color="primary",
                        outline=True,
                        size="sm",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_TINY,
                            "padding": "2px 10px",
                            "borderRadius": "2px",
                            "letterSpacing": "0.3px",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": SPACING_XXSMALL,
        },
    )

    # ── Display name (+ optional URL link) ────────────────────────────────
    name_children: list = [
        html.Span(
            display_name,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "fontWeight": FONT_WEIGHT_SEMIBOLD,
                "color": COLOR_TEXT_SECONDARY,
            },
        )
    ]
    if url:
        name_children.append(
            html.A(
                [html.I(className="fas fa-external-link-alt ms-1"), " link"],
                href=url,
                target="_blank",
                rel="noopener noreferrer",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_TINY,
                    "color": COLOR_NAVY,
                    "textDecoration": "none",
                    "marginLeft": SPACING_XXSMALL,
                },
            )
        )
    name_row = html.Div(
        name_children,
        style={"display": "flex", "alignItems": "center", "marginBottom": SPACING_XXSMALL},
    )

    # ── Highlight snippet ──────────────────────────────────────────────────
    highlight_row = (
        html.Div(
            _parse_highlight(highlight),
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
                "lineHeight": "1.6",
                "marginBottom": SPACING_XXSMALL,
            },
        )
        if highlight
        else None
    )

    # ── Timestamp ─────────────────────────────────────────────────────────
    time_row = (
        html.Div(
            [html.I(className="far fa-clock me-1"), formatted_time],
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "marginBottom": SPACING_XXSMALL,
            },
        )
        if formatted_time
        else None
    )

    # ── wba_id (technical footnote at bottom) ─────────────────────────────
    wba_id_row = html.Div(
        html.Code(
            wba_id,
            style={
                "fontFamily": "'SFMono-Regular', 'Consolas', 'Menlo', monospace",
                "fontSize": FONT_SIZE_TINY,
                "color": COLOR_GRAY_MEDIUM,
                "backgroundColor": "transparent",
                "padding": "0",
                "border": "none",
            },
        ),
        style={"marginTop": SPACING_XXSMALL},
    )

    # ── Attributes table (only when full=True and attributes are returned) ─
    attrs_section = None
    if full and attributes:
        attrs_section = html.Div(
            [
                html.Hr(
                    style={
                        "margin": f"{SPACING_XSMALL} 0",
                        "borderColor": COLOR_BORDER,
                    }
                ),
                _build_attributes_table(attributes),
            ]
        )

    card_children: list = [header_row, name_row]
    if highlight_row:
        card_children.append(highlight_row)
    if time_row:
        card_children.append(time_row)
    card_children.append(wba_id_row)
    if attrs_section:
        card_children.append(attrs_section)

    return html.Div(
        card_children,
        style={
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "border": f"1px solid {COLOR_BORDER}",
            "borderLeft": f"3px solid {badge_bg}",
            "borderRadius": "2px",
            "padding": SPACING_SMALL,
            "marginBottom": SPACING_XSMALL,
        },
    )


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
                                style={
                                    **INPUT_STYLE,
                                    "height": "36px",
                                    "lineHeight": "18px",
                                    "padding": "4px 8px",
                                },
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
                                style={
                                    **INPUT_STYLE,
                                    "height": "36px",
                                    "lineHeight": "18px",
                                    "padding": "4px 8px",
                                },
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
            dcc.Store(id="search-url-q-store", storage_type="memory", data=None),

            html.Div(
                [
                    # Optional ES-disabled banner
                    es_disabled_banner,

                    # ── Search bar — centered, constrained (Option A) ──────
                    html.Div(
                        [
                            dbc.Input(
                                id="search-q-input",
                                type="text",
                                placeholder="Search entities — people, issues, pull requests, commits…",
                                debounce=False,
                                n_submit=0,
                                style={
                                    **INPUT_STYLE,
                                    "borderRadius": "24px",
                                    "height": "44px",
                                    "fontSize": FONT_SIZE_MEDIUM,
                                    "paddingLeft": "20px",
                                    "paddingRight": "20px",
                                    "boxShadow": "0 2px 8px rgba(0,0,0,0.08)",
                                    "border": f"1px solid {COLOR_BORDER}",
                                },
                            ),

                            # ── Filters toggle + Person only ───────────────
                            html.Div(
                                [
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
                                        className="collapse-toggle-subtle",
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_XSMALL,
                                            "color": COLOR_GRAY_MEDIUM,
                                            "textDecoration": "none",
                                            "padding": f"{SPACING_XXSMALL} 0",
                                            "letterSpacing": "0.3px",
                                        },
                                    ),
                                    dbc.Checklist(
                                        options=[
                                            {
                                                "label": html.Span([
                                                    "Person only",
                                                    html.Span(html.I(className="fas fa-info-circle"), id="search-person-only-help", style={"marginLeft": 0, "color": COLOR_GRAY_MEDIUM, "fontSize": "12px", "cursor": "default", "display": "inline-flex", "alignItems": "center"})
                                                ]),
                                                "value": "person_only",
                                            }
                                        ],
                                        value=[],
                                        id="search-person-only",
                                        inline=True,
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_XSMALL,
                                            "color": COLOR_GRAY_MEDIUM,
                                        },
                                    ),
                                ],
                                style={
                                    "marginTop": SPACING_XXSMALL,
                                    "display": "flex",
                                    "alignItems": "center",
                                    "gap": SPACING_MEDIUM,
                                },
                            ),
                        ],
                        style={
                            "maxWidth": "650px",
                            "margin": "0 auto",
                            "marginBottom": SPACING_SMALL,
                        },
                    ),
                    _build_filters_panel(),

                    dbc.Tooltip(
                        "Finds people by name, username, or email when you type 3 or more starting characters.",
                        target="search-person-only-help",
                        placement="right",
                    ),

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

                    # ── Results container + pagination (wrapped in Loading) ─
                    dcc.Loading(
                        id="search-loading",
                        type="circle",
                        color=COLOR_NAVY,
                        overlay_style={
                            "visibility": "visible",
                            "filter": "blur(1px)",
                            "opacity": "0.4",
                        },
                        delay_show=100,
                        children=[
                            html.Div(
                                _build_placeholder(),
                                id="search-results-container",
                            ),
                            _build_pagination_row(),
                        ],
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )


# ===========================================================================
# C1b — Callbacks: filters toggle + search execution
# ===========================================================================


@callback(
    Output("search-url-q-store", "data"),
    Input("url", "search"),
    prevent_initial_call=False,
)
def _populate_url_q_store(search: str | None) -> str | None:
    """Write the ?q= value from the URL into the memory store.

    Fires on every url.search change and on page mount (prevent_initial_call=False).
    The store fires AFTER the page layout is mounted, so execute_search can
    safely read from search page components when triggered by this store.
    """
    if not search:
        raise PreventUpdate
    qs = parse_qs(search.lstrip("?"))
    terms = qs.get("q", [])
    q = unquote(terms[0]).strip() if terms else None
    if not q:
        raise PreventUpdate
    return q

@callback(
    Output("search-theme-store", "data"),
    Input("theme-store", "data"),
)
def _populate_search_theme_store(theme_name: str | None) -> dict | None:
    """Fetch the effective graph theme into the search theme store.

    Fires when the app theme changes (light/dark) and on page mount. Returns
    the merged tokens or ``None`` on error so badge colours fall back to base.
    """
    active_theme = theme_name or "executive-light"
    return fetch_effective_theme(active_theme)


# Shared output spec — used by execute_search, paginate_search, and
# restore_search_on_navigate so allow_duplicate is needed on the latter two.
_SEARCH_OUTPUTS = [
    Output("search-results-container", "children"),
    Output("search-results-count", "children"),
    Output("search-results-header", "style"),
    Output("search-pagination-row", "style"),
    Output("search-page-indicator", "children"),
    Output("search-next-btn", "disabled"),
    Output("search-prev-btn", "disabled"),
    Output("search-current-page", "data"),
    Output("search-last-query-params", "data"),
]


@callback(
    Output("search-results-container", "children", allow_duplicate=True),
    Output("search-results-count", "children", allow_duplicate=True),
    Output("search-results-header", "style", allow_duplicate=True),
    Output("search-pagination-row", "style", allow_duplicate=True),
    Output("search-page-indicator", "children", allow_duplicate=True),
    Output("search-next-btn", "disabled", allow_duplicate=True),
    Output("search-prev-btn", "disabled", allow_duplicate=True),
    Output("search-q-input", "value"),
    Input("search-last-query-params", "data"),
    State("search-current-page", "data"),
    State("search-full-toggle", "value"),
    State("search-theme-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def restore_search_on_navigate(
    last_query_params: dict | None,
    current_page: int | None,
    full: bool,
    effective_theme: dict | None,
) -> tuple:
    """Re-execute the last search when the session store is restored on page load.

    Triggered by the session store restoring its value from sessionStorage when
    the search page mounts. Does not update the stores (no circular feedback).
    """
    _empty_header = {**_RESULTS_HEADER_STYLE, "display": "none"}
    _empty_pagination = {**_PAGINATION_STYLE, "display": "none"}
    _no_restore = (
        no_update, no_update, no_update, no_update,
        no_update, no_update, no_update, no_update,
    )

    if not last_query_params:
        return _no_restore

    badge_colors = _badge_colors_from_effective(effective_theme)

    page = int(current_page or 1)
    params = dict(last_query_params)
    params["page"] = page
    params["full"] = "true" if full else "false"
    params.setdefault("page_size", 10)

    try:
        response = requests.get(
            f"{_get_api_base_url()}/api/v1/search",
            params=params,
            timeout=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(f"Search restore failed: {exc}")
        return _no_restore

    total: int = data.get("total", 0)
    results: list = data.get("results", [])
    page = data.get("page", page)
    page_size: int = data.get("page_size", 20)
    total_pages = max(1, math.ceil(total / page_size))

    if results:
        content = html.Div([_build_result_card(r, bool(full), badge_colors) for r in results])
    else:
        content = html.Div(
            [
                html.Div(html.I(className="fas fa-search-minus"), style=PLACEHOLDER_ICON_STYLE),
                html.Div("No results found.", style=PLACEHOLDER_MESSAGE_STYLE),
            ],
            style={"paddingTop": SPACING_LARGE, "paddingBottom": SPACING_LARGE},
        )

    count_text = f"{total:,} result{'s' if total != 1 else ''}"
    has_prev = page > 1
    has_next = page < total_pages
    show_pagination = total > page_size
    restored_q = last_query_params.get("q", "")

    return (
        content,
        count_text,
        _RESULTS_HEADER_STYLE,
        _PAGINATION_STYLE if show_pagination else _empty_pagination,
        f"Page {page} of {total_pages}",
        not has_next,
        not has_prev,
        restored_q,
    )


@callback(
    Output("search-filters-collapse", "is_open"),
    Output("search-filters-chevron", "className"),
    Input("search-filters-toggle-btn", "n_clicks"),
    State("search-filters-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_filters_panel(_n_clicks: int | None, is_open: bool) -> tuple:
    """Open or close the advanced filters collapse panel."""
    new_open = not is_open
    chevron_class = (
        "fas fa-chevron-up ms-1" if new_open else "fas fa-chevron-down ms-1"
    )
    return new_open, chevron_class


@callback(
    Output("search-entity-type", "disabled"),
    Input("search-person-only", "value"),
    prevent_initial_call=False,
)
def _toggle_entity_type_disabled(person_only_values: list | None) -> bool:
    """Disable the Entity Type dropdown while Person only is checked."""
    return bool(person_only_values)


@callback(
    Output("search-results-container", "children"),
    Output("search-results-count", "children"),
    Output("search-results-header", "style"),
    Output("search-pagination-row", "style"),
    Output("search-page-indicator", "children"),
    Output("search-next-btn", "disabled"),
    Output("search-prev-btn", "disabled"),
    Output("search-current-page", "data"),
    Output("search-last-query-params", "data"),
    Input("search-q-input", "n_submit"),
    Input("search-full-toggle", "value"),
    Input("search-url-q-store", "data"),
    State("search-q-input", "value"),
    State("search-entity-type", "value"),
    State("search-source", "value"),
    State("search-status", "value"),
    State("search-priority", "value"),
    State("search-date-from", "value"),
    State("search-date-to", "value"),
    State("search-last-query-params", "data"),
    State("search-person-only", "value"),
    State("search-theme-store", "data"),
    prevent_initial_call=True,
)
def execute_search(
    _n_submit: int | None,
    full: bool,
    url_q: str | None,
    q: str | None,
    entity_type: str | None,
    source: str | None,
    status: str | None,
    priority: str | None,
    date_from: str | None,
    date_to: str | None,
    last_query_params: dict | None,
    person_only: list | None,
    effective_theme: dict | None,
) -> tuple:
    """Fire a search request and render result cards."""
    triggered_id = ctx.triggered_id

    # When arriving via the global navbar search bar (?q=), use the URL term.
    if triggered_id == "search-url-q-store":
        if not url_q:
            raise PreventUpdate
        q = url_q

    # When the full-attributes toggle fires before any search has been run,
    # there are no prior results to re-fetch — do nothing.
    if triggered_id == "search-full-toggle" and not last_query_params:
        return (
            no_update, no_update, no_update, no_update,
            no_update, no_update, no_update, no_update, no_update,
        )

    _empty_header = {**_RESULTS_HEADER_STYLE, "display": "none"}
    _empty_pagination = {**_PAGINATION_STYLE, "display": "none"}

    badge_colors = _badge_colors_from_effective(effective_theme)

    # ── Build query params ─────────────────────────────────────────────────
    params: dict = {
        "page": 1,
        "page_size": 10,
        "full": "true" if full else "false",
    }
    if q and q.strip():
        params["q"] = q.strip()
    # Person only checkbox overrides the Entity Type dropdown.
    if person_only:
        entity_type = "Person"
    if entity_type:
        params["entity_type"] = entity_type
    if source:
        params["source"] = source
    if status and status.strip():
        params["status"] = status.strip()
    if priority and priority.strip():
        params["priority"] = priority.strip()
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    # ── Call search API ────────────────────────────────────────────────────
    try:
        response = requests.get(
            f"{_get_api_base_url()}/api/v1/search",
            params=params,
            timeout=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(f"Search API call failed: {exc}")
        error_content = create_alert(
            [
                html.I(className="fas fa-exclamation-circle me-2"),
                "Search failed. Check that the application server is running.",
            ],
            color="danger",
        )
        return (
            error_content, "", _empty_header, _empty_pagination,
            "Page 1", True, True, 1, last_query_params or {},
        )

    total: int = data.get("total", 0)
    results: list = data.get("results", [])
    page: int = data.get("page", 1)
    page_size: int = data.get("page_size", 20)
    total_pages = max(1, math.ceil(total / page_size))

    # ── Render results or empty state ──────────────────────────────────────
    if results:
        content = html.Div([_build_result_card(r, bool(full), badge_colors) for r in results])
    else:
        content = html.Div(
            [
                html.Div(
                    html.I(className="fas fa-search-minus"),
                    style=PLACEHOLDER_ICON_STYLE,
                ),
                html.Div(
                    "No results found. Try different search terms or filters.",
                    style=PLACEHOLDER_MESSAGE_STYLE,
                ),
            ],
            style={"paddingTop": SPACING_LARGE, "paddingBottom": SPACING_LARGE},
        )

    count_text = f"{total:,} result{'s' if total != 1 else ''}"
    has_prev = page > 1
    has_next = page < total_pages
    page_indicator = f"Page {page} of {total_pages}"
    show_pagination = total > page_size

    # Save query params for pagination (C1c) — exclude page number
    saved_params = {k: v for k, v in params.items() if k != "page"}

    return (
        content,
        count_text,
        _RESULTS_HEADER_STYLE,
        _PAGINATION_STYLE if show_pagination else _empty_pagination,
        page_indicator,
        not has_next,
        not has_prev,
        1,
        saved_params,
    )


@callback(
    Output("search-results-container", "children", allow_duplicate=True),
    Output("search-results-count", "children", allow_duplicate=True),
    Output("search-results-header", "style", allow_duplicate=True),
    Output("search-pagination-row", "style", allow_duplicate=True),
    Output("search-page-indicator", "children", allow_duplicate=True),
    Output("search-next-btn", "disabled", allow_duplicate=True),
    Output("search-prev-btn", "disabled", allow_duplicate=True),
    Output("search-current-page", "data", allow_duplicate=True),
    Output("search-last-query-params", "data", allow_duplicate=True),
    Input("search-prev-btn", "n_clicks"),
    Input("search-next-btn", "n_clicks"),
    State("search-current-page", "data"),
    State("search-last-query-params", "data"),
    State("search-full-toggle", "value"),
    State("search-theme-store", "data"),
    prevent_initial_call=True,
)
def paginate_search(
    _prev_clicks: int | None,
    _next_clicks: int | None,
    current_page: int | None,
    last_query_params: dict | None,
    full: bool,
    effective_theme: dict | None,
) -> tuple:
    """Navigate to the previous or next page of search results."""
    _empty_header = {**_RESULTS_HEADER_STYLE, "display": "none"}
    _empty_pagination = {**_PAGINATION_STYLE, "display": "none"}

    if not last_query_params:
        return (
            no_update, no_update, no_update, no_update,
            no_update, no_update, no_update, no_update, no_update,
        )

    badge_colors = _badge_colors_from_effective(effective_theme)

    page = int(current_page or 1)
    triggered_id = ctx.triggered_id

    if triggered_id == "search-prev-btn":
        page = max(1, page - 1)
    elif triggered_id == "search-next-btn":
        page += 1

    params = dict(last_query_params)
    params["page"] = page
    params["full"] = "true" if full else "false"
    if "full" not in last_query_params:
        # page_size may have been stored; keep it
        params.setdefault("page_size", 10)

    try:
        response = requests.get(
            f"{_get_api_base_url()}/api/v1/search",
            params=params,
            timeout=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(f"Pagination API call failed: {exc}")
        error_content = create_alert(
            [
                html.I(className="fas fa-exclamation-circle me-2"),
                "Search failed. Check that the application server is running.",
            ],
            color="danger",
        )
        return (
            error_content, "", _empty_header, _empty_pagination,
            f"Page {page}", True, True, page, last_query_params,
        )

    total: int = data.get("total", 0)
    results: list = data.get("results", [])
    page = data.get("page", page)
    page_size: int = data.get("page_size", 20)
    total_pages = max(1, math.ceil(total / page_size))

    if results:
        content = html.Div([_build_result_card(r, bool(full), badge_colors) for r in results])
    else:
        content = html.Div(
            [
                html.Div(
                    html.I(className="fas fa-search-minus"),
                    style=PLACEHOLDER_ICON_STYLE,
                ),
                html.Div(
                    "No results found.",
                    style=PLACEHOLDER_MESSAGE_STYLE,
                ),
            ],
            style={"paddingTop": SPACING_LARGE, "paddingBottom": SPACING_LARGE},
        )

    count_text = f"{total:,} result{'s' if total != 1 else ''}"
    has_prev = page > 1
    has_next = page < total_pages
    page_indicator = f"Page {page} of {total_pages}"
    show_pagination = total > page_size

    # Persist query params unchanged (page number is tracked separately)
    saved_params = {k: v for k, v in params.items() if k != "page"}

    return (
        content,
        count_text,
        _RESULTS_HEADER_STYLE,
        _PAGINATION_STYLE if show_pagination else _empty_pagination,
        page_indicator,
        not has_next,
        not has_prev,
        page,
        saved_params,
    )
