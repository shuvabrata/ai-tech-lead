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
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
            "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600;700&family=Inter:wght@300;400;500;600&display=swap"
        ],
        suppress_callback_exceptions=True  # Required for multi-page apps
    )
    app.title = "AI Tech Lead"

    # Sidebar using Bootstrap Nav - Executive Dashboard style
    sidebar = dbc.Nav(
        [
            dbc.NavLink("Chat", href="/app/chat", active="exact", id="nav-genai", className="executive-nav-link"),
            dbc.NavLink("People", href="/app/people", active="exact", id="nav-people", className="executive-nav-link"),
            dbc.NavLink("Progress", href="/app/progress", active="exact", id="nav-progress", className="executive-nav-link"),
            dbc.NavLink("Graph", href="/app/graph", active="exact", id="nav-graph", className="executive-nav-link"),
            dbc.NavLink("Settings", href="/app/settings", active="exact", id="nav-settings", className="executive-nav-link"),
        ],
        vertical=True,
        pills=False,
        className="vh-100 sidebar executive-sidebar",
        style={
            "backgroundColor": "#ffffff",
            "borderRight": "1px solid #e2e8f0",
            "padding": "24px 0"
        }
    )

    # Top menu using Bootstrap Navbar - Executive Dashboard style
    top_menu = dbc.Navbar(
        dbc.Container(
            dbc.Row([
                dbc.Col([
                    dbc.Button(
                        "☰",
                        id="sidebar-toggle",
                        color="light",
                        outline=True,
                        className="me-2 sidebar-toggle-btn",
                        size="sm",
                        style={
                            "fontSize": "16px",
                            "fontWeight": "normal",
                            "padding": "4px 10px",
                            "lineHeight": "1",
                            "borderColor": "#cbd5e0",
                            "color": "#4a5568",
                            "backgroundColor": "transparent"
                        }
                    ),
                    dbc.NavbarBrand(
                        app.title,
                        style={
                            "fontFamily": "'Inter', sans-serif",
                            "fontSize": "14px", 
                            "marginBottom": "0",
                            "fontWeight": "600",
                            "padding": "0",
                            "color": "#2d3748",
                            "letterSpacing": "0.5px",
                            "textTransform": "uppercase"
                        }
                    )
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
                                style={
                                    "fontFamily": "'Inter', sans-serif",
                                    "fontSize": "12px"
                                }
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
            style={"padding": "8px 16px"}
        ),
        color="white",
        dark=False,
        className="mb-0 executive-topbar",
        style={
            "minHeight": "auto",
            "height": "44px",
            "padding": "0",
            "borderBottom": "1px solid #e2e8f0",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)"
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
                width="auto",
                className="sidebar-col",
                style={"minWidth": "180px", "maxWidth": "180px"}  # Fixed narrow width
            ),
            dbc.Col(content, id="content-col", width=True)
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
            Output("sidebar-col", "style")
        ],
        Input("sidebar-toggle", "n_clicks"),
        State("sidebar-collapsed", "data"),
        prevent_initial_call=True
    )
    def toggle_sidebar(_n_clicks, is_collapsed):
        # Toggle the state
        new_state = not is_collapsed
        
        # Adjust visibility based on sidebar state
        if new_state:  # Sidebar collapsed
            sidebar_style = {"display": "none"}
        else:  # Sidebar open
            sidebar_style = {"minWidth": "180px", "maxWidth": "180px"}
        
        return new_state, sidebar_style

    # Initialize sidebar state from localStorage
    @app.callback(
        Output("sidebar-col", "style", allow_duplicate=True),
        Input("sidebar-collapsed", "data"),
        prevent_initial_call='initial_duplicate'
    )
    def init_sidebar_state(is_collapsed):
        # Apply stored state on page load
        if is_collapsed:  # Sidebar collapsed
            sidebar_style = {"display": "none"}
        else:  # Sidebar open
            sidebar_style = {"minWidth": "180px", "maxWidth": "180px"}
        
        return sidebar_style

    # No custom CSS or sidebar collapse for now; Bootstrap handles layout and theme

    return app
