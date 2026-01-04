from dash import html


def get_layout():
    """Return the people page layout"""
    return html.Div([
        html.H2("People", className="mb-4"),
        html.P("List of people involved in the project (placeholder)."),
        html.Hr(),
        html.Div([
            html.P("This page will display:"),
            html.Ul([
                html.Li("Team members"),
                html.Li("Their roles and responsibilities"),
                html.Li("Contact information"),
                html.Li("Availability status")
            ])
        ])
    ], className="mt-4")
