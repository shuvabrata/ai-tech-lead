import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output, State

from .pages import chat, people, progress, settings, graph


def create_dash_app():

    app = dash.Dash(
        __name__,
        requests_pathname_prefix="/app/",
        external_stylesheets=[
            dbc.themes.MATERIA,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
        ]
    )
    app.title = "AI Tech Lead"

    # Sidebar using Bootstrap Nav
    sidebar = dbc.Nav(
        [
            dbc.NavLink("💬 Chat", href="/app/chat", active="exact", id="nav-genai"),
            dbc.NavLink("👥 People", href="/app/people", active="exact", id="nav-people"),
            dbc.NavLink("📈 Progress", href="/app/progress", active="exact", id="nav-progress"),
            dbc.NavLink("📊 Graph", href="/app/graph", active="exact", id="nav-graph"),
            dbc.NavLink("⚙️ Settings", href="/app/settings", active="exact", id="nav-settings"),
        ],
        vertical=True,
        pills=True,
        className="bg-dark vh-100 sidebar p-1",
        style={"fontSize": "14px"}  # Slightly smaller nav links
    )

    # Top menu using Bootstrap Navbar with toggle button and project switcher
    top_menu = dbc.Navbar(
        dbc.Container(
            dbc.Row([
                dbc.Col([
                    dbc.Button(
                        "☰",
                        id="sidebar-toggle",
                        color="light",
                        outline=True,
                        className="me-1",
                        size="sm",
                        style={
                            "fontSize": "14px",
                            "fontWeight": "bold",
                            "padding": "1px 6px",
                            "lineHeight": "1"
                        }
                    ),
                    dbc.NavbarBrand(app.title, style={
                        "fontSize": "15px", 
                        "marginBottom": "0",
                        "fontWeight": "500",
                        "padding": "0"
                    })
                ], width="auto", className="d-flex align-items-center"),
                dbc.Col(
                    dbc.Nav(
                        [
                            dbc.DropdownMenu(
                                label="Switch Project",
                                children=[
                                    dbc.DropdownMenuItem("Project Alpha", id="proj-alpha"),
                                    dbc.DropdownMenuItem("Project Beta", id="proj-beta"),
                                ],
                                nav=True,
                                in_navbar=True,
                                size="sm",
                                style={"fontSize": "13px"}
                            ),
                        ],
                        className="justify-content-end flex-nowrap",
                        style={"padding": "0"}
                    ),
                    width=True,
                    className="d-flex justify-content-end align-items-center"
                ),
            ], className="w-100 flex-nowrap g-0 align-items-center justify-content-between", style={"margin": "0"}),
            fluid=True,
            style={"padding": "4px 12px"}  # Very minimal padding
        ),
        color="primary",
        dark=True,
        className="mb-1",
        style={
            "minHeight": "auto",
            "height": "36px",
            "padding": "0"
        }
    )

    # Main content area with page routing
    content = html.Div(id="page-content", className="p-2")

    app.layout = dbc.Container([
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="sidebar-collapsed", storage_type="local", data=False),
        top_menu,
        dbc.Row([
            dbc.Col(
                sidebar,
                id="sidebar-col",
                width=2,
                className="sidebar-col",
                style={}  # Will be updated by callback
            ),
            dbc.Col(content, id="content-col", width=10)
        ], className="g-0"),
    ], fluid=True)

    # Callbacks for page routing
    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname")
    )
    def display_page(pathname):
        if pathname == "/app/people":
            return people.get_layout()
        if pathname == "/app/progress":
            return progress.get_layout()
        if pathname == "/app/graph":
            return graph.get_layout()
        if pathname == "/app/settings":
            return settings.get_layout()
        if pathname == "/app/chat":
            return chat.get_layout()
        # Default to chat page
        return chat.get_layout()

    # Callback for sidebar toggle
    @app.callback(
        [
            Output("sidebar-collapsed", "data"),
            Output("sidebar-col", "style"),
            Output("sidebar-col", "width"),
            Output("content-col", "width")
        ],
        Input("sidebar-toggle", "n_clicks"),
        State("sidebar-collapsed", "data"),
        prevent_initial_call=True
    )
    def toggle_sidebar(n_clicks, is_collapsed):
        # Toggle the state
        new_state = not is_collapsed
        
        # Adjust column widths and visibility based on sidebar state
        if new_state:  # Sidebar collapsed
            sidebar_style = {"display": "none"}
            sidebar_width = 0
            content_width = 12
        else:  # Sidebar open
            sidebar_style = {}
            sidebar_width = 2
            content_width = 10
        
        return new_state, sidebar_style, sidebar_width, content_width

    # Initialize sidebar state from localStorage
    @app.callback(
        [
            Output("sidebar-col", "style", allow_duplicate=True),
            Output("sidebar-col", "width", allow_duplicate=True),
            Output("content-col", "width", allow_duplicate=True)
        ],
        Input("sidebar-collapsed", "data"),
        prevent_initial_call='initial_duplicate'
    )
    def init_sidebar_state(is_collapsed):
        # Apply stored state on page load
        if is_collapsed:  # Sidebar collapsed
            sidebar_style = {"display": "none"}
            sidebar_width = 0
            content_width = 12
        else:  # Sidebar open
            sidebar_style = {}
            sidebar_width = 2
            content_width = 10
        
        return sidebar_style, sidebar_width, content_width

    # No custom CSS or sidebar collapse for now; Bootstrap handles layout and theme

    return app
