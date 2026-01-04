from dash import html


def get_layout():
    """Return the progress page layout"""
    return html.Div([
        html.H2("Progress", className="mb-4"),
        html.P("Project progress dashboard (placeholder)."),
        html.Hr(),
        html.Div([
            html.P("This page will display:"),
            html.Ul([
                html.Li("Project timeline and milestones"),
                html.Li("Task completion status"),
                html.Li("Burndown charts"),
                html.Li("Key performance indicators")
            ])
        ])
    ], className="mt-4")
