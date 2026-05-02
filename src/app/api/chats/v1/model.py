# Chat Pydantic models for v1
from typing import Optional
from pydantic import BaseModel


class ChatCreate(BaseModel):
    """Request model for creating a new chat session"""
    system_prompt: Optional[str] = "You are a helpful AI assistant."


class ChatSession(BaseModel):
    """Response model for chat session"""
    session_id: str



class ChatDeleteResponse(BaseModel):
    """Response model for chat deletion"""
    session_id: str
    deleted: bool


class ChatSessionStatus(BaseModel):
    """Response model for chat session status check"""
    session_id: str
    exists: bool
    message_count: Optional[int] = None  # Number of messages in session


class StreamMessageCreate(BaseModel):
    """Request model for streaming a chat message"""
    message: str
