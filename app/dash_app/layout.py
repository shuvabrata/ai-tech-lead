import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output, State

from .pages import analytics, chat, people, progress, settings, graph, connectors
from .styles import (
    SIDEBAR_STYLE,
    NAVBAR_BRAND_STYLE,
    TOPBAR_STYLE,
    TOPBAR_CONTAINER_STYLE,
    TOGGLE_BUTTON_STYLE,
    DROPDOWN_MENU_STYLE,
    SIDEBAR_COL_STYLE
)


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
    app.title = "Work Behavior Analytics AI"

    # Sidebar using Bootstrap Nav - Executive Dashboard style
    sidebar = dbc.Nav(
        [
            dbc.NavLink("Chat", href="/app/chat", active="exact", id="nav-genai", className="executive-nav-link"),
            dbc.NavLink("People", href="/app/people", active="exact", id="nav-people", className="executive-nav-link"),
            dbc.NavLink("Progress", href="/app/progress", active="exact", id="nav-progress", className="executive-nav-link"),
            dbc.NavLink("Graph", href="/app/graph", active="exact", id="nav-graph", className="executive-nav-link"),
            dbc.NavLink("Analytics", href="/app/analytics", active="exact", id="nav-analytics", className="executive-nav-link"),
            dbc.NavLink("Connectors", href="/app/connectors", active="exact", id="nav-connectors", className="executive-nav-link"),
            dbc.NavLink("Settings", href="/app/settings", active="exact", id="nav-settings", className="executive-nav-link"),
        ],
        vertical=True,
        pills=False,
        className="vh-100 sidebar executive-sidebar",
        style=SIDEBAR_STYLE
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
                        style=TOGGLE_BUTTON_STYLE
                    ),
                    dbc.NavbarBrand(
                        app.title,
                        style=NAVBAR_BRAND_STYLE
                    )
                ], width="auto", className="d-flex align-items-center"),
                dbc.Col(
                    dbc.Nav(
                        [
                            dbc.Select(
                                id="theme-selector",
                                options=[
                                    {"label": "Executive Light", "value": "executive-light"},
                                    {"label": "Executive Dark", "value": "executive-dark"},
                                ],
                                value="executive-light",
                                size="sm",
                                className="theme-selector me-2",
                                style={"minWidth": "180px", "fontSize": "12px"}
                            ),
                            dbc.DropdownMenu(
                                label="Switch Project",
                                children=[
                                    dbc.DropdownMenuItem("Project Alpha", id="proj-alpha"),
                                    dbc.DropdownMenuItem("Project Beta", id="proj-beta"),
                                ],
                                nav=True,
                                in_navbar=True,
                                size="sm",
                                style=DROPDOWN_MENU_STYLE
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
            style=TOPBAR_CONTAINER_STYLE
        ),
        className="mb-0 executive-topbar",
        style=TOPBAR_STYLE
    )

    # Main content area with page routing
    content = html.Div(id="page-content", className="p-2")

    app.layout = dbc.Container([
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="sidebar-collapsed", storage_type="local", data=False),
        dcc.Store(id="theme-store", storage_type="local", data="executive-light"),
        top_menu,
        dbc.Row([
            dbc.Col(
                sidebar,
                id="sidebar-col",
                width="auto",
                className="sidebar-col",
                style=SIDEBAR_COL_STYLE
            ),
            dbc.Col(content, id="content-col", width=True)
        ], className="g-0"),
    ], fluid=True, id="app-shell", className="app-shell theme-executive-light")

    # Callbacks for page routing
    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname")
    )
    def display_page(pathname):
        if pathname in ("/app/analytics", "/app/analytics/"):
            return analytics.get_layout()
        if pathname == "/app/people":
            return people.get_layout()
        if pathname == "/app/progress":
            return progress.get_layout()
        if pathname == "/app/graph":
            return graph.get_layout()
        if pathname and pathname.startswith("/app/connectors/"):
            connector_type = pathname.split("/app/connectors/")[-1]
            return connectors.get_detail_layout(connector_type)
        if pathname in ("/app/connectors", "/app/connectors/"):
            return connectors.get_layout()
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
            sidebar_style = SIDEBAR_COL_STYLE
        
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
            sidebar_style = SIDEBAR_COL_STYLE
        
        return sidebar_style

    @app.callback(
        Output("theme-store", "data"),
        Input("theme-selector", "value"),
        prevent_initial_call=True
    )
    def persist_theme(theme_name):
        return theme_name or "executive-light"

    @app.callback(
        Output("app-shell", "className"),
        Input("theme-store", "data")
    )
    def apply_theme_class(theme_name):
        active_theme = theme_name or "executive-light"
        return f"app-shell theme-{active_theme}"

    # No custom CSS or sidebar collapse for now; Bootstrap handles layout and theme

    return app
