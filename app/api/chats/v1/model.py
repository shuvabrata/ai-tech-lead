# Chat Pydantic models for v1
from typing import Optional
from pydantic import BaseModel


class ChatCreate(BaseModel):
    """Request model for creating a new chat session"""
    system_prompt: Optional[str] = "You are a helpful AI assistant."


class ChatSession(BaseModel):
    """Response model for chat session"""
    session_id: str


class MessageCreate(BaseModel):
    """Request model for sending a message"""
    message: str


class MessageResponse(BaseModel):
    """Response model for chat message"""
    session_id: str
    ai_message: str


class ChatDeleteResponse(BaseModel):
    """Response model for chat deletion"""
    session_id: str
    deleted: bool
