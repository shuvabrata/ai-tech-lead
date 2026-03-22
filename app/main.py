import time
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.wsgi import WSGIMiddleware
from .api import endpoints
from .api.projects.v1.router import router as projects_v1_router
from .api.chats.v1.router import router as chats_v1_router
from .api.graph.v1.router import router as graph_v1_router
from .api.connectors.v1.router import router as connectors_v1_router
from .dash_app.layout import create_dash_app
from .common.logger import logger, LogContext


app = FastAPI()


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    start_time = time.time()
    with LogContext(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(
                "[HTTP] request_failed "
                f"method={request.method} path={request.url.path} "
                f"duration_ms={round(duration_ms, 2)}"
            )
            raise

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "[HTTP] request_complete "
            f"method={request.method} path={request.url.path} "
            f"status={response.status_code} duration_ms={round(duration_ms, 2)}"
        )
        response.headers["X-Request-ID"] = request_id
        return response

app.include_router(endpoints.router, prefix="/api")
app.include_router(projects_v1_router, prefix="/api/v1")
app.include_router(chats_v1_router, prefix="/api/v1")
app.include_router(graph_v1_router, prefix="/api/v1")
app.include_router(connectors_v1_router, prefix="/api/v1")

dash_app = create_dash_app()
app.mount("/app", WSGIMiddleware(dash_app.server))
