from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware
from .api import endpoints
from .api.projects.v1.router import router as projects_v1_router
from .dash_app.layout import create_dash_app


app = FastAPI()
app.include_router(endpoints.router, prefix="/api")
app.include_router(projects_v1_router, prefix="/api/v1")

dash_app = create_dash_app()
app.mount("/app", WSGIMiddleware(dash_app.server))
