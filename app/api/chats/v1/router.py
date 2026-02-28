# FastAPI router for Chat endpoints (v1)
from fastapi import APIRouter, HTTPException

from .model import ChatCreate, ChatSession, MessageCreate, MessageResponse, ChatDeleteResponse, ChatSessionStatus
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


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def send_message(session_id: str, message: MessageCreate):
    """
    Send a message to an existing chat session.
    Returns the AI's response and token count.
    """
    try:
        return service.send_chat_message(session_id, message)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{session_id}", response_model=ChatDeleteResponse)
async def delete_chat(session_id: str):
    """
    End and delete a chat session.
    """
    return service.delete_chat_session(session_id)
