

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output

def create_dash_app():

    app = dash.Dash(
        __name__,
        requests_pathname_prefix="/app/",
        external_stylesheets=[dbc.themes.MATERIA]
    )
    app.title = "AI Tech Lead"

    # Sidebar using Bootstrap Nav
    sidebar = dbc.Nav(
        [
            dbc.NavLink("💬 GenAI Search", href="/app/", active="exact", id="nav-genai"),
            dbc.NavLink("👥 People", href="/app/people", active="exact", id="nav-people"),
            dbc.NavLink("📈 Progress", href="/app/progress", active="exact", id="nav-progress"),
            dbc.NavLink("⚙️ Settings", href="/app/settings", active="exact", id="nav-settings"),
        ],
        vertical=True,
        pills=True,
        className="bg-dark vh-100 sidebar p-2"
    )

    # Top menu using Bootstrap Navbar with left/right alignment (flex row)
    top_menu = dbc.Navbar(
        dbc.Container(
            dbc.Row([
                dbc.Col(dbc.NavbarBrand(app.title), width="auto"),
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
                            ),
                        ],
                        className="justify-content-end flex-nowrap"
                    ),
                    width=True,
                    className="d-flex justify-content-end align-items-center"
                ),
            ], className="w-100 flex-nowrap g-0 align-items-center justify-content-between"),
            fluid=True
        ),
        color="primary",
        dark=True,
        className="mb-4"
    )

    # Main content area with page routing
    content = html.Div(id="page-content", className="p-4")

    app.layout = dbc.Container([
        dcc.Location(id="url", refresh=False),
        top_menu,
        dbc.Row([
            dbc.Col(sidebar, width=2, className="sidebar-col"),
            dbc.Col(content, width=10)
        ], className="g-0"),
    ], fluid=True)

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
            ], className="mt-4")
        elif pathname == "/app/progress":
            return html.Div([
                html.H2("Progress"),
                html.P("Project progress dashboard (placeholder).")
            ], className="mt-4")
        elif pathname == "/app/settings":
            return html.Div([
                html.H2("Settings"),
                html.P("Settings page (placeholder).")
            ], className="mt-4")
        else:
            return html.Div([
                html.H2("GenAI Search"),
                html.P("Conversational AI assistant (placeholder).")
            ], className="mt-4")


    # No custom CSS or sidebar collapse for now; Bootstrap handles layout and theme

    return app

    return app
