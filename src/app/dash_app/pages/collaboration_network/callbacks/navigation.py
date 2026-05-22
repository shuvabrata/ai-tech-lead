"""Collaboration Network navigation callbacks — fit, fullwidth toggle, layout reset."""

from dash import Input, Output, callback, clientside_callback

from app.dash_app.components.common import register_fullwidth_callback
from ..layout import _COLLABORATION_LAYOUT

register_fullwidth_callback("collab")


# Clientside callback — fit graph to viewport when Fit button is clicked
clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks) {
            const elem = document.getElementById('collab-cytoscape');
            if (elem && elem._cyreg && elem._cyreg.cy) {
                elem._cyreg.cy.fit(null, 30);
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("collab-fit-btn", "className"),
    Input("collab-fit-btn", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("collab-cytoscape", "layout", allow_duplicate=True),
    Input("collab-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_collab_layout(n_clicks):
    """Re-apply the preset layout to restore default zoom and pan."""
    stop_value = 1000 if (n_clicks or 0) % 2 == 0 else 1001
    return {**_COLLABORATION_LAYOUT, "stop": stop_value}
