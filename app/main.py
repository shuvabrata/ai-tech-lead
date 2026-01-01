from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware
from .api import endpoints
from .dash_app.layout import create_dash_app

app = FastAPI()
app.include_router(endpoints.router, prefix="/api")

dash_app = create_dash_app()
app.mount("/app", WSGIMiddleware(dash_app.server))
