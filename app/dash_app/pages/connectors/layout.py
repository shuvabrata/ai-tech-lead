"""Dash layouts for the Connectors pages."""

from dash import html


def get_layout():
    return html.Div(
        [
            html.H2("Connectors"),
            html.P("Connectors page scaffold - coming soon."),
        ]
    )


def get_detail_layout(connector_type: str):
    return html.Div(
        [
            html.H2(f"Connector: {connector_type}"),
            html.P("Connector detail scaffold - coming soon."),
        ]
    )
