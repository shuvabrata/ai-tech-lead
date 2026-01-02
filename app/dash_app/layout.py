
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State

def create_dash_app():
    app = dash.Dash(__name__, requests_pathname_prefix="/app/")
    app.title = "AI Tech Lead"

    # Define the sidebar (collapsible)
    sidebar = html.Div(
        [
            html.Div(
                [
                    html.Button(
                        "☰", id="sidebar-toggle", n_clicks=0, className="sidebar-toggle-btn"
                    ),
                    html.H2("Menu", className="sidebar-title"),
                ],
                className="sidebar-header"
            ),
            html.Div(
                [
                    dcc.Link([
                        html.Span("💬", className="sidebar-icon"),
                        html.Span("GenAI Search", className="sidebar-text")
                    ], href="/app/", className="sidebar-link"),
                    dcc.Link([
                        html.Span("👥", className="sidebar-icon"),
                        html.Span("People", className="sidebar-text")
                    ], href="/app/people", className="sidebar-link"),
                    dcc.Link([
                        html.Span("📈", className="sidebar-icon"),
                        html.Span("Progress", className="sidebar-text")
                    ], href="/app/progress", className="sidebar-link"),
                    dcc.Link([
                        html.Span("⚙️", className="sidebar-icon"),
                        html.Span("Settings", className="sidebar-text")
                    ], href="/app/settings", className="sidebar-link"),
                ],
                className="sidebar-links"
            ),
        ],
        id="sidebar",
        className="sidebar open"
    )

    # Top menu for project switching
    top_menu = html.Div(
        [
            html.H1("AI Tech Lead", className="top-title"),
            dcc.Dropdown(
                id="project-switcher",
                options=[
                    {"label": "Project Alpha", "value": "alpha"},
                    {"label": "Project Beta", "value": "beta"},
                ],
                value="alpha",
                clearable=False,
                className="project-dropdown"
            ),
        ],
        className="top-menu"
    )

    # Main content area with page routing
    content = html.Div(id="page-content", className="content")

    app.layout = html.Div([
        dcc.Location(id="url", refresh=False),
        top_menu,
        html.Div([
            sidebar,
            content
        ], className="main-layout")
    ])

    # Callbacks for page routing
    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname")
    )
    def display_page(pathname):
        if pathname == "/app/people":
            return html.Div([
                html.H2("People"),
                html.P("List of people involved in the project (placeholder).")
            ])
        elif pathname == "/app/progress":
            return html.Div([
                html.H2("Progress"),
                html.P("Project progress dashboard (placeholder).")
            ])
        elif pathname == "/app/settings":
            return html.Div([
                html.H2("Settings"),
                html.P("Settings page (placeholder).")
            ])
        else:
            return html.Div([
                html.H2("GenAI Search"),
                html.P("Conversational AI assistant (placeholder).")
            ])

    # Collapsible sidebar callback (simple CSS toggle)
    @app.callback(
        Output("sidebar", "className"),
        Input("sidebar-toggle", "n_clicks"),
        State("sidebar", "className")
    )
    def toggle_sidebar(n, class_name):
        if n and n % 2 == 1:
            return "sidebar closed"
        return "sidebar open"

    # Add some simple CSS for layout
    app.clientside_callback(
        """
        function(className) {
            if (className === 'sidebar closed') {
                document.body.classList.add('sidebar-collapsed');
            } else {
                document.body.classList.remove('sidebar-collapsed');
            }
            return null;
        }
        """,
        Output("sidebar", "data-dummy"),
        Input("sidebar", "className")
    )

    app.index_string = """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; background: #f7f7f7; }
                .top-menu { display: flex; align-items: center; background: #222; color: #fff; padding: 0.5rem 1rem; }
                .top-title { flex: 1; font-size: 1.5rem; margin: 0; }
                .project-dropdown { width: 200px; }
                .main-layout { display: flex; height: calc(100vh - 56px); }
                .sidebar { width: 220px; background: #333; color: #fff; transition: width 0.2s; overflow: hidden; display: flex; flex-direction: column; }
                .sidebar.closed { width: 60px; }
                .sidebar-header { display: flex; align-items: center; padding: 1rem; }
                .sidebar.closed .sidebar-title { display: none; }
                .sidebar-toggle-btn { background: none; border: none; color: #fff; font-size: 1.5rem; cursor: pointer; margin-right: 0.5rem; }
                .sidebar-links { display: flex; flex-direction: column; }
                .sidebar-link { color: #fff; text-decoration: none; padding: 0.75rem 1rem; transition: background 0.1s; display: flex; align-items: center; white-space: nowrap; overflow: hidden; }
                .sidebar-link:hover { background: #444; }
                .sidebar-icon { font-size: 1.3rem; margin-right: 1rem; min-width: 1.5rem; text-align: center; }
                .sidebar.closed .sidebar-text { display: none; }
                .sidebar.closed .sidebar-link { justify-content: center; padding: 0.75rem 0.5rem; }
                .content { flex: 1; padding: 2rem; background: #f7f7f7; }
                body.sidebar-collapsed .sidebar { width: 60px !important; }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    """

    return app
