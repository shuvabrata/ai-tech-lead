# FastAPI router for Chat endpoints (v1)
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.common.logger import logger
from .model import  (
    ChatCreate,
    ChatSession,
    ChatDeleteResponse,
    ChatSessionStatus,
    StreamMessageCreate
)
from . import service

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/", response_model=ChatSession, status_code=201)
async def create_chat(chat: ChatCreate):
    """
    Create a new chat session with an optional system prompt.
    Returns a unique session_id to be used for subsequent messages.
    """
    return service.create_chat_session(chat)


@router.get("/{session_id}", response_model=ChatSessionStatus)
async def get_chat_session(session_id: str):
    """
    Check if a chat session exists.
    Returns session status without processing any messages.
    """
    return service.get_chat_session_status(session_id)



@router.post("/{session_id}/stream")
async def stream_message(session_id: str, message: StreamMessageCreate):
    """
    Stream a chat response as Server-Sent Events (SSE).

    Yields SSE events in order: thinking_start, thinking_chunk(s), thinking_end,
    message_start, message_chunk(s), message_end.  On error yields an error event.
    """
    try:
        # Validate session exists before returning a StreamingResponse.
        # Raising here produces a normal JSON 404 rather than a broken SSE stream.
        session_status = service.get_chat_session_status(session_id)
        if not session_status.exists:
            raise HTTPException(status_code=404, detail="Session not found.")

        logger.info(
            "[stream_message] Starting stream: session_id=%s message=%.80s",
            session_id,
            message.message,
        )

        async def event_generator():
            try:
                async for chunk in service.stream_chat_response(session_id, message.message):
                    yield chunk
            except asyncio.CancelledError:
                logger.warning("[stream_message] Client disconnected: session_id=%s", session_id)
                raise
            except Exception as exc:
                logger.error("[stream_message] Stream error: session_id=%s error=%s", session_id, exc)
                raise

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics/stream", tags=["metrics"])
async def stream_metrics():
    """
    Return current streaming metrics (starts, completions, errors, disconnects,
    total_duration_seconds).
    """
    return service.get_stream_metrics()


@router.delete("/{session_id}", response_model=ChatDeleteResponse)
async def delete_chat(session_id: str):
    """
    End and delete a chat session.
    """
    return service.delete_chat_session(session_id)
