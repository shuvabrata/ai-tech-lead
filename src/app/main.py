import time
from contextlib import asynccontextmanager
from uuid import uuid4

from typing import AsyncGenerator, Callable, Awaitable
from fastapi import FastAPI, Request, Response
from a2wsgi import WSGIMiddleware
from app.api import endpoints
from app.api.projects.v1.router import router as projects_v1_router
from app.api.chats.v1.router import router as chats_v1_router
from app.api.graph.v1.router import router as graph_v1_router
from app.api.connectors.v1.router import router as connectors_v1_router
from app.api.queries.v1.router import router as queries_v1_router
from app.api.search.v1.router import router as search_v1_router
from app.api.search.v1.persons_router import router as persons_v1_router
from app.api.commands.v1.router import router as commands_v1_router
from app.api.settings.v1.router import router as settings_v1_router
from app.dash_app.layout import create_dash_app
from common.logger import logger, LogContext
from app.settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "[Startup] feature_flags "
        f"github_mcp_enabled={settings.GITHUB_MCP_ENABLED} "
        f"github_mcp_server_url={settings.GITHUB_MCP_SERVER_URL}"
    )
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def add_request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
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
app.include_router(queries_v1_router, prefix="/api/v1")
app.include_router(search_v1_router, prefix="/api/v1")
app.include_router(persons_v1_router, prefix="/api/v1")
app.include_router(commands_v1_router, prefix="/api/v1")
app.include_router(settings_v1_router, prefix="/api/v1")

dash_app = create_dash_app()  # type: ignore[no-untyped-call]
app.mount("/app", WSGIMiddleware(dash_app.server))  # type: ignore[arg-type]
