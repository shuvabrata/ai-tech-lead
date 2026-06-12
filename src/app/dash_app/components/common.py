"""
Common Reusable Components for Executive Dashboard

This module provides factory functions for creating consistent UI components
across all pages of the Work Behavior Analytics AI application.

Usage:
    from app.dash_app.components.common import create_page_header, create_feature_card
    
    layout = html.Div([
        create_page_header("My Page Title"),
        create_feature_card("Feature Title", "Feature description...")
    ])
"""

from typing import Any

from dash import html, dcc
import dash_bootstrap_components as dbc

from app.dash_app.styles import (
    # Style patterns
    PAGE_HEADER_STYLE,
    CARD_CONTAINER_STYLE,
    FEATURE_CARD_STYLE,
    FEATURE_CARD_TITLE_STYLE,
    FEATURE_CARD_DESCRIPTION_STYLE,
    PLACEHOLDER_ICON_STYLE,
    PLACEHOLDER_MESSAGE_STYLE,
    # Details panel
    DETAILS_PANEL_HEADER_STYLE,
    DETAILS_PANEL_SUBTYPE_STYLE,
    DETAILS_TABLE_STYLE,
    DETAILS_TABLE_KEY_STYLE,
    DETAILS_TABLE_VALUE_STYLE,
    DETAILS_TABLE_VALUE_MONO_STYLE,
    DETAILS_TABLE_LINK_STYLE,
    DETAILS_MUTED_TEXT_STYLE,
    # Colors
    COLOR_NAVY,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    COLOR_BORDER,
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHTER,
    # Typography
    FONT_SANS,
    FONT_SIZE_XSMALL,
    FONT_SIZE_XTINY,
    FONT_WEIGHT_SEMIBOLD,
    # Spacing
    SPACING_XSMALL,
    SPACING_SMALL,
    SPACING_MEDIUM,
    SPACING_XXSMALL
)


def create_page_header(text: str) -> html.Div:
    """
    Create a consistent page header with Executive Dashboard styling.
    
    Args:
        text: The header text to display
        
    Returns:
        html.Div: A styled page header component
        
    Example:
        create_page_header("Strategic Analysis & Advisory")
    """
    return html.Div(text, style=PAGE_HEADER_STYLE)


def create_alert(
    content: Any,
    color: str = "info",
    class_name: str = "mb-2",
    dismissable: bool = True,
    duration: int | None = None,
    style: dict | None = None,
) -> dbc.Alert:
    """Create a standardized alert with consistent typography and behavior."""
    merged_style = {
        "fontFamily": FONT_SANS,
        "fontSize": FONT_SIZE_XSMALL,
        **(style or {}),
    }
    kwargs = {
        "color": color,
        "className": class_name,
        "dismissable": dismissable,
        "style": merged_style,
    }
    if duration is not None:
        kwargs["duration"] = duration
    return dbc.Alert(content, **kwargs)


def create_feature_card(title: str, description: str) -> html.Div:
    """
    Create a feature card with title and description.
    
    Args:
        title: The feature title
        description: The feature description text
        
    Returns:
        html.Div: A styled feature card component
        
    Example:
        create_feature_card(
            "Personnel Profiles",
            "Detailed team member information, roles, and expertise areas"
        )
    """
    return html.Div([
        html.Div(title, style=FEATURE_CARD_TITLE_STYLE),
        html.Div(description, style=FEATURE_CARD_DESCRIPTION_STYLE)
    ], style=FEATURE_CARD_STYLE)


def create_placeholder_section(message: str, features: list, icon: str = "📋") -> html.Div:
    """
    Create a placeholder section with icon, message, and feature cards.
    
    Args:
        message: The placeholder message to display
        features: List of (title, description) tuples for feature cards
        icon: Optional icon to display (default: "📋")
        
    Returns:
        html.Div: A complete placeholder section
        
    Example:
        create_placeholder_section(
            message="Team directory integration pending",
            features=[
                ("Personnel Profiles", "Detailed team member information..."),
                ("Contact Directory", "Email addresses and communication...")
            ]
        )
    """
    # Create feature cards in a 2-column grid
    feature_cols = []
    for title, description in features:
        feature_cols.append(
            dbc.Col([
                create_feature_card(title, description)
            ], md=6)
        )
    
    return html.Div([
        # Icon
        html.Div(icon, style=PLACEHOLDER_ICON_STYLE),
        
        # Message
        html.Div(message, style=PLACEHOLDER_MESSAGE_STYLE),
        
        # Feature cards
        html.Div([
            dbc.Row(feature_cols)
        ], style=CARD_CONTAINER_STYLE)
    ])


def create_diamond_icon(color: str | None = None) -> html.Span:
    """
    Create a diamond icon (◆) for visual accents.
    
    Args:
        color: The color of the diamond (default: theme accent)
        
    Returns:
        html.Span: A styled diamond icon
        
    Example:
        create_diamond_icon()
        create_diamond_icon(COLOR_GRAY_MEDIUM)
    """
    resolved_color = color or COLOR_NAVY

    return html.Span(
        "◆",
        style={
            "color": resolved_color,
            "fontSize": FONT_SIZE_XSMALL,
            "marginRight": SPACING_XXSMALL
        }
    )


def create_empty_state(message: str, icon: str = "📭") -> html.Div:
    """
    Create an empty state display for when there's no data.
    
    Args:
        message: The message to display
        icon: Optional icon to display (default: "📭")
        
    Returns:
        html.Div: A styled empty state component
        
    Example:
        create_empty_state("No messages yet. Start a conversation!")
    """
    return html.Div([
        html.Div(icon, style=PLACEHOLDER_ICON_STYLE),
        html.Div(message, style=PLACEHOLDER_MESSAGE_STYLE)
    ], style={
        "padding": SPACING_MEDIUM,
        "textAlign": "center"
    })


# ---------------------------------------------------------------------------
# Shared graph visualization helpers
# ---------------------------------------------------------------------------

def toggle_details_panel(is_fullwidth: bool) -> tuple:
    """Return (canvas_col_width, right_panel_style) for fullwidth toggle.

    Used by both the graph page and future visualization pages.

    Args:
        is_fullwidth: True when the canvas should expand to full width.

    Returns:
        (int, dict) — Dash column width for the canvas col and a style dict
        for the right-hand details/filter column (empty dict = visible,
        ``{"display": "none"}`` = hidden).
    """
    if is_fullwidth:
        return 12, {"display": "none"}
    return 8, {}


def register_fullwidth_callback(id_prefix: str) -> None:
    """Register the full-width toggle callback for a visualization page.

    Eliminates boilerplate duplication across pages that share the standard
    controls-bar / viz-col / details-col layout pattern.  Any page whose
    component IDs follow the ``{id_prefix}-*`` naming convention can call
    this once during module import instead of writing its own callback.

    Component IDs expected:
        ``{id_prefix}-fullwidth-btn``   — the toggle button
        ``{id_prefix}-fullwidth-state`` — dcc.Store holding bool state
        ``{id_prefix}-viz-col``         — Bootstrap Col for the canvas
        ``{id_prefix}-details-col``     — Bootstrap Col for the right panel

    Args:
        id_prefix: Page-specific prefix, e.g. ``"graph"`` or ``"collab"``.
    """
    from dash import Input, Output, State, callback  # pylint: disable=import-outside-toplevel

    @callback(
        [
            Output(f"{id_prefix}-fullwidth-state", "data"),
            Output(f"{id_prefix}-viz-col", "width"),
            Output(f"{id_prefix}-details-col", "style"),
            Output(f"{id_prefix}-fullwidth-btn", "children"),
        ],
        Input(f"{id_prefix}-fullwidth-btn", "n_clicks"),
        State(f"{id_prefix}-fullwidth-state", "data"),
        prevent_initial_call=True,
    )
    def _toggle_fullwidth(_n_clicks: int, is_fullwidth: bool) -> tuple:
        new_state = not is_fullwidth
        viz_width, panel_style = toggle_details_panel(new_state)
        btn_label = "Exit" if new_state else "Full"
        return new_state, viz_width, panel_style, btn_label


def register_edge_hover_dimming_callback(cytoscape_id: str) -> None:
    """Register the edge-hover dimming clientside callback for a Cytoscape component.

    On edge mouseover, the hovered edge and its two endpoint nodes are highlighted
    and all other elements are dimmed.  On mouseout the classes are cleared.
    The listener is attached once (guarded by ``cy._edgeHoverListenerAttached``) so
    re-renders that re-invoke this callback do not stack duplicate listeners.

    Component IDs expected:
        ``{cytoscape_id}`` — the ``cyto.Cytoscape`` component

    Args:
        cytoscape_id: The Dash component ID of the Cytoscape element,
            e.g. ``"graph-cytoscape"`` or ``"collab-cytoscape"``.
    """
    from dash import Input, Output, clientside_callback  # pylint: disable=import-outside-toplevel

    clientside_callback(
        """
        function(elements) {
            const elem = document.getElementById('""" + cytoscape_id + """');
            if (!elem || !elem._cyreg || !elem._cyreg.cy) {
                return window.dash_clientside.no_update;
            }

            const cy = elem._cyreg.cy;

            if (!cy._edgeHoverListenerAttached) {
                let hoverTimeout = null;
                let isHovering = false;

                cy.on('mouseover', 'edge', function(evt) {
                    const edge = evt.target;

                    if (hoverTimeout) {
                        clearTimeout(hoverTimeout);
                    }

                    hoverTimeout = setTimeout(function() {
                        isHovering = true;

                        const sourceNode = edge.source();
                        const targetNode = edge.target();

                        edge.addClass('highlighted');
                        sourceNode.addClass('highlighted');
                        targetNode.addClass('highlighted');

                        cy.elements().not(edge).not(sourceNode).not(targetNode).addClass('dimmed');
                    }, 50);
                });

                cy.on('mouseout', 'edge', function(evt) {
                    if (hoverTimeout) {
                        clearTimeout(hoverTimeout);
                        hoverTimeout = null;
                    }

                    if (isHovering) {
                        cy.elements().removeClass('highlighted dimmed');
                        isHovering = false;
                    }
                });

                cy._edgeHoverListenerAttached = true;
            }

            return window.dash_clientside.no_update;
        }
        """,
        Output(cytoscape_id, "className"),
        Input(cytoscape_id, "elements"),
        prevent_initial_call=False,
    )


_CONTROLS_BUTTON_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": "11px",
    "padding": "4px 12px",
    "borderRadius": "2px",
    "borderColor": COLOR_GRAY_LIGHTER,
    "color": COLOR_GRAY_DARK,
}

_LAYOUT_OPTIONS = [
    {"label": "Manual Stable (preset)", "value": "preset"},
    {"label": "Force-Directed (cose)", "value": "cose"},
    {"label": "Circle", "value": "circle"},
    {"label": "Grid", "value": "grid"},
    {"label": "Hierarchical (breadthfirst)", "value": "breadthfirst"},
    {"label": "Concentric", "value": "concentric"},
]


def create_controls_bar(id_prefix: str, *, layout_enabled: bool = True) -> dbc.Row:
    """Create a graph controls bar (layout selector, spotlight, Fit/Reset/Full).

    Produces identical chrome for every graph visualization page. Non-applicable
    controls are rendered ``disabled=True`` (grayed out) rather than omitted, to
    keep a consistent look across pages.

    Args:
        id_prefix: Component ID prefix (e.g. ``"graph"`` or ``"collab"``).
            Produces IDs like ``{id_prefix}-layout-selector``,
            ``{id_prefix}-spotlight-input``, ``{id_prefix}-fit-btn``, etc.
        layout_enabled: When False the layout selector is rendered disabled.
            Use False for pages where the layout is fixed (e.g. collab preset).

    Returns:
        A ``dbc.Row`` containing the full controls bar.
    """
    return dbc.Row([
        dbc.Col([
            html.Label(
                "Layout:",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": "11px",
                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                    "color": COLOR_GRAY_DARK,
                    "marginRight": SPACING_XXSMALL,
                    "textTransform": "uppercase",
                    "letterSpacing": "0.3px",
                }
            ),
            dbc.Select(
                id=f"{id_prefix}-layout-selector",
                options=_LAYOUT_OPTIONS,
                value="cose",
                disabled=not layout_enabled,
                style={
                    "fontFamily": FONT_SANS,
                    "width": "200px",
                    "display": "inline-block",
                    "fontSize": "12px",
                    "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                    "borderRadius": "2px",
                    "opacity": "1" if layout_enabled else "0.45",
                    "cursor": "not-allowed" if not layout_enabled else "default",
                },
                size="sm",
            ),
        ], width="auto"),
        dbc.Col([
            html.Div([
                dbc.Input(
                    id=f"{id_prefix}-spotlight-input",
                    type="text",
                    placeholder="Search nodes\u2026",
                    size="sm",
                    debounce=False,
                    className="graph-spotlight-input",
                ),
                html.Small(
                    id=f"{id_prefix}-spotlight-count",
                    className="graph-spotlight-count-label",
                    children="",
                ),
            ], className="d-flex align-items-center gap-2 justify-content-center"),
        ], width=True),
        dbc.Col([
            dbc.ButtonGroup([
                dbc.Button(
                    "Fit",
                    id=f"{id_prefix}-fit-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style=_CONTROLS_BUTTON_STYLE,
                ),
                dbc.Button(
                    "Reset",
                    id=f"{id_prefix}-reset-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style=_CONTROLS_BUTTON_STYLE,
                ),
                dbc.Button(
                    "Full",
                    id=f"{id_prefix}-fullwidth-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style=_CONTROLS_BUTTON_STYLE,
                ),
            ], size="sm"),
        ], width="auto"),
    ], className="mb-2", align="center")


# ---------------------------------------------------------------------------
# Shared element properties panel builder
# ---------------------------------------------------------------------------

_PANEL_INTERNAL_KEYS = {"ID", "elementID", "elementId"}


def _panel_is_visible_key(key: str) -> bool:
    """Return True when a property key is safe to show in the properties panel."""
    if key in _PANEL_INTERNAL_KEYS:
        return False
    return not str(key).startswith("_")


def _panel_build_visible_properties(data: dict, exclude_keys: set) -> dict:
    """Return a filtered property dict for the properties panel."""
    return {
        k: v
        for k, v in data.items()
        if k not in exclude_keys and v is not None and _panel_is_visible_key(k)
    }


def _panel_resolve_endpoint(edge_data: dict, endpoint: str) -> str:
    """Resolve an edge source/target using explicit *_id fields before Cytoscape id."""
    for key in (f"{endpoint}_id", f"{endpoint}Id", endpoint):
        value = edge_data.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, dict):
            nested = value.get("id")
            if nested not in (None, ""):
                return nested
            continue
        return value
    return "N/A"


def _panel_properties_table(items: list) -> html.Table:
    """Render (key, value) pairs as an Executive Dashboard tabular layout."""
    rows = []
    for key, value in items:
        str_value = str(value)
        is_url = key == "url" or str_value.startswith(("http://", "https://"))
        is_mono = key in ("id",) or (len(str_value) > 16 and " " not in str_value)
        if is_url:
            value_cell = html.Span(
                [
                    html.A(
                        str_value,
                        href=str_value,
                        target="_blank",
                        rel="noopener noreferrer",
                        style=DETAILS_TABLE_LINK_STYLE,
                    ),
                    html.I(
                        className="fas fa-external-link-alt details-prop-icon details-prop-icon--link",
                    ),
                ],
                className="details-prop-value-wrap",
            )
        elif is_mono:
            value_cell = html.Span(
                [
                    html.Code(str_value, style=DETAILS_TABLE_VALUE_MONO_STYLE),
                    dcc.Clipboard(
                        content=str_value,
                        className="details-prop-icon details-prop-icon--copy",
                        title="Copy",
                    ),
                ],
                className="details-prop-value-wrap",
            )
        else:
            value_cell = html.Span(
                [
                    html.Span(str_value, style=DETAILS_TABLE_VALUE_STYLE),
                    dcc.Clipboard(
                        content=str_value,
                        className="details-prop-icon details-prop-icon--copy",
                        title="Copy",
                    ),
                ],
                className="details-prop-value-wrap",
            )
        rows.append(html.Tr(
            [
                html.Td(key, style=DETAILS_TABLE_KEY_STYLE),
                html.Td(
                    value_cell,
                    style={
                        "padding": "6px 0 6px 8px",
                        "borderBottom": "1px solid var(--color-border-light)",
                        "verticalAlign": "top",
                        "wordBreak": "break-word",
                    },
                ),
            ],
            className="details-prop-row",
        ))
    return html.Table(html.Tbody(rows), style=DETAILS_TABLE_STYLE)


def build_element_properties_content(
    data: dict,
    *,
    expand_node_enabled: bool = True,
) -> html.Div:
    """Build the properties panel content for a selected node or edge.

    Detects element type from the data dict (edges have a ``source`` key).
    Used by both the graph page and future visualization pages.  Pages that
    do not support node expansion should pass ``expand_node_enabled=False``
    — the button is rendered disabled (grayed out) rather than omitted.

    Args:
        data: Cytoscape element ``data`` dict (from ``selectedNodeData[0]``
            or ``tapEdgeData``).
        expand_node_enabled: Whether the Expand Node button should be active.

    Returns:
        An ``html.Div`` containing the formatted properties panel content.
    """
    is_edge = "source" in data

    if not is_edge:
        # --- Node ---
        exclude_keys = {"displayLabel", "id", "wba_id", "label", "nodeType", "elementType"}
        properties = _panel_build_visible_properties(data, exclude_keys)
        wba_id = data.get("wba_id") or data.get("id")
        sorted_items = sorted(properties.items())
        if wba_id is not None:
            sorted_items = [("id", wba_id)] + sorted_items

        header = html.Div([
            html.Div(data.get("label", "N/A"), style=DETAILS_PANEL_HEADER_STYLE),
            html.Div(data.get("nodeType", "Unknown"), style=DETAILS_PANEL_SUBTYPE_STYLE),
        ], className="mb-3")

        if sorted_items:
            properties_section: list = [_panel_properties_table(sorted_items)]
        else:
            properties_section = [
                html.P("No properties", className="text-muted", style=DETAILS_MUTED_TEXT_STYLE)
            ]

        btn_kwargs: dict = {
            "color": "primary",
            "size": "sm",
            "outline": True,
            "disabled": not expand_node_enabled,
            "className": "w-100",
            "style": {"fontSize": FONT_SIZE_XSMALL},
        }
        if expand_node_enabled:
            btn_kwargs["id"] = "expand-node-btn"

        expand_button = html.Div([
            html.Hr(style={"margin": "16px 0"}),
            dbc.Button(
                [html.I(className="fas fa-project-diagram me-2"), "Expand Node"],
                **btn_kwargs,
            ),
            html.Small(
                "Load connected neighbors" if expand_node_enabled
                else "Not available for this graph",
                className="text-muted d-block text-center mt-1",
                style={"fontSize": FONT_SIZE_XTINY},
            ),
        ], className="mt-3")

        return html.Div([header] + properties_section + [expand_button])

    # --- Edge ---
    exclude_keys = {"id", "source", "target", "label", "relType", "elementType"}
    properties = _panel_build_visible_properties(data, exclude_keys)
    source_id = _panel_resolve_endpoint(data, "source")
    target_id = _panel_resolve_endpoint(data, "target")

    header = html.Div([
        html.Div(
            data.get("relType", data.get("label", "Unknown")),
            style=DETAILS_PANEL_HEADER_STYLE,
        ),
        html.Div("Relationship", style=DETAILS_PANEL_SUBTYPE_STYLE),
    ], className="mb-3")

    meta_items = [("from", source_id), ("to", target_id)]
    if properties:
        meta_items += sorted(properties.items())

    return html.Div([header, _panel_properties_table(meta_items)])


def create_info_card(title: str, content: str, accent_color: str | None = None) -> html.Div:
    """
    Create an informational card with custom accent color.
    
    Args:
        title: The card title
        content: The card content text
        accent_color: Border accent color (default: theme accent)
        
    Returns:
        html.Div: A styled info card component
        
    Example:
        create_info_card(
            "Project Status",
            "All systems operational",
            COLOR_SUCCESS
        )
    """
    resolved_accent_color = accent_color or COLOR_NAVY

    card_style = {
        **FEATURE_CARD_STYLE,
        "borderLeft": f"3px solid {resolved_accent_color}"
    }
    
    return html.Div([
        html.Div(title, style=FEATURE_CARD_TITLE_STYLE),
        html.Div(content, style=FEATURE_CARD_DESCRIPTION_STYLE)
    ], style=card_style)


def create_section_divider(text: str = None) -> html.Div:
    """
    Create a section divider with optional text.
    
    Args:
        text: Optional text to display in the divider
        
    Returns:
        html.Div: A styled section divider
        
    Example:
        create_section_divider()
        create_section_divider("Analysis Results")
    """
    if text:
        return html.Div(
            text,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "textTransform": "uppercase",
                "letterSpacing": "1px",
                "borderTop": f"1px solid {COLOR_BORDER}",
                "paddingTop": SPACING_XSMALL,
                "marginTop": SPACING_MEDIUM,
                "marginBottom": SPACING_SMALL
            }
        )
    else:
        return html.Hr(style={
            "borderTop": f"1px solid {COLOR_BORDER}",
            "marginTop": SPACING_MEDIUM,
            "marginBottom": SPACING_MEDIUM
        })


def create_stat_card(label: str, value: str, subtitle: str = None) -> html.Div:
    """
    Create a statistics card with label, value, and optional subtitle.
    
    Args:
        label: The stat label
        value: The stat value to display prominently
        subtitle: Optional subtitle text
        
    Returns:
        html.Div: A styled stat card component
        
    Example:
        create_stat_card("Active Tasks", "24", "↑ 12% from last week")
    """
    components = [
        html.Div(
            label,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "textTransform": "uppercase",
                "letterSpacing": "1px",
                "marginBottom": SPACING_XXSMALL
            }
        ),
        html.Div(
            value,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": "32px",
                "fontWeight": "700",
                "color": COLOR_CHARCOAL_MEDIUM,
                "marginBottom": SPACING_XXSMALL
            }
        )
    ]
    
    if subtitle:
        components.append(
            html.Div(
                subtitle,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_XSMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "fontStyle": "italic"
                }
            )
        )
    
    return html.Div(
        components,
        style={
            **FEATURE_CARD_STYLE,
            "textAlign": "center"
        }
    )
