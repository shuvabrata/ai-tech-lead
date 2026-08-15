import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from typing import AsyncGenerator, Callable, Awaitable
import aio_pika
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
from app.db.session import ASYNC_SESSION_LOCAL
from app.runtime_settings import load_db_overrides_from_session
from app.api.connectors.v1.service import sync_github_mcp_env_status
from common.logger import logger, LogContext
from common.runtime_settings.events import listen_for_settings_changed
from app.settings import settings


# Module-level RabbitMQ connection reference — opened in lifespan startup,
# closed in lifespan shutdown.  Used by the settings API to publish events.
_rabbitmq_connection: aio_pika.RobustConnection | None = None


def get_rabbitmq_connection() -> aio_pika.RobustConnection | None:
    """Return the current RabbitMQ connection (may be ``None``)."""
    return _rabbitmq_connection


async def _on_settings_changed(changed_keys: list[str]) -> None:
    """Callback invoked when a ``settings.changed`` event is received.

    Refreshes the local runtime settings cache from the DB.
    """
    try:
        async with ASYNC_SESSION_LOCAL() as db:
            await load_db_overrides_from_session(db)
        logger.info(
            "Runtime settings cache refreshed after settings.changed event: "
            "keys=%s",
            changed_keys,
        )
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "Failed to refresh runtime settings cache after event: "
            "keeping last known good snapshot",
            exc_info=True,
        )


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup initialisation and shutdown cleanup."""
    # ── Startup ──────────────────────────────────────────────────────────
    global _rabbitmq_connection  # noqa: PLW0603

    logger.info(
        "[Startup] feature_flags "
        f"github_mcp_enabled={settings.GITHUB_MCP_ENABLED} "
        f"github_mcp_server_url={settings.GITHUB_MCP_SERVER_URL}"
    )

    # 1. Load DB overrides into the runtime settings cache.
    try:
        async with ASYNC_SESSION_LOCAL() as db:
            await load_db_overrides_from_session(db)
        logger.info("[Startup] Runtime settings loaded from DB")
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "[Startup] Failed to load runtime settings from DB — "
            "using env/default values",
            exc_info=True,
        )

    # 1.1 Sync the env-configured GitHub MCP Server connector status.
    try:
        async with ASYNC_SESSION_LOCAL() as db:
            await sync_github_mcp_env_status(db)
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "[Startup] Failed to sync github_mcp connector status from env",
            exc_info=True,
        )

    # 2. Connect to RabbitMQ and start the runtime config listener.
    try:
        _rabbitmq_connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL
        )
        # Start the listener as a background task.
        listener_task = asyncio.ensure_future(
            listen_for_settings_changed(
                connection=_rabbitmq_connection,
                on_event=_on_settings_changed,
                instance_id="app",
            )
        )
        logger.info("[Startup] RabbitMQ runtime config listener started")
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "[Startup] Failed to start RabbitMQ runtime config listener — "
            "settings changes will apply on next container restart",
            exc_info=True,
        )
        _rabbitmq_connection = None
        listener_task = None

    yield  # ── Application runs here ────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────
    if listener_task is not None:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] RabbitMQ runtime config listener stopped")

    if _rabbitmq_connection is not None and not _rabbitmq_connection.is_closed:
        await _rabbitmq_connection.close()
        logger.info("[Shutdown] RabbitMQ connection closed")


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
