from dash import html


def get_layout():
    """Return the settings page layout"""
    return html.Div([
        html.H2("Settings", className="mb-4"),
        html.P("Settings page (placeholder)."),
        html.Hr(),
        html.Div([
            html.P("This page will display:"),
            html.Ul([
                html.Li("Application preferences"),
                html.Li("User profile settings"),
                html.Li("Notification preferences"),
                html.Li("API configuration")
            ])
        ])
    ], className="mt-4")
