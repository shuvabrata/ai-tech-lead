import dash
from dash import html

def create_dash_app():
    app = dash.Dash(__name__, requests_pathname_prefix="/app/")
    app.layout = html.Div([
        html.H1("Hello from Dash!"),
        html.P("This is a minimal Dash app.")
    ])
    return app
