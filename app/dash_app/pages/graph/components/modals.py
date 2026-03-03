"""Modal dialog components

Modal dialogs for graph interactions:
- Expansion modal (configure node expansion)
- Future: Filter modal, search modal, etc.
"""

import dash_bootstrap_components as dbc
from dash import html

from app.settings import settings


def create_expansion_modal():
    """Create the node expansion configuration modal
    
    Returns:
        dbc.Modal component for node expansion
    """
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Expand Node")),
        dbc.ModalBody([
            html.Div([
                html.Label("Direction:", style={"fontWeight": "500", "fontSize": "13px", "marginBottom": "6px"}),
                dbc.RadioItems(
                    id="expansion-direction-selector",
                    options=[
                        {"label": "Both (Incoming + Outgoing)", "value": "both"},
                        {"label": "Incoming Only", "value": "incoming"},
                        {"label": "Outgoing Only", "value": "outgoing"}
                    ],
                    value="both",
                    inline=False,
                    className="mb-3"
                ),
            ]),
            html.Div([
                html.Label("Limit:", style={"fontWeight": "500", "fontSize": "13px", "marginBottom": "6px"}),
                dbc.Input(
                    id="expansion-limit-input",
                    type="number",
                    value=settings.GRAPH_UI_MAX_NODES_TO_EXPAND,
                    min=1,
                    max=500,
                    step=1,
                    size="sm",
                    className="mb-2"
                ),
                html.Small("Will load up to this many neighbors (1-500)", className="text-muted", style={"fontSize": "11px"})
            ]),
            html.Div([
                dbc.Checkbox(
                    id="expansion-auto-fit-checkbox",
                    label="Auto-fit graph after expansion",
                    value=True,
                    className="mt-3"
                ),
                html.Small("Automatically zoom to show all nodes", className="text-muted d-block", style={"fontSize": "11px", "marginLeft": "24px"})
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="expansion-modal-cancel", color="secondary", size="sm", className="me-2"),
            dbc.Button("Expand", id="expansion-modal-expand", color="primary", size="sm")
        ])
    ], id="expansion-modal", is_open=False, size="md")
