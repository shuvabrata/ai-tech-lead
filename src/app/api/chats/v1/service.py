from app.ai_agent.ai_agent import new_chat, do_chat, end_chat, _chat_sessions
from .model import ChatCreate, ChatSession, MessageCreate, MessageResponse, ChatDeleteResponse, ChatSessionStatus


def create_chat_session(chat: ChatCreate) -> ChatSession:
    """Create a new chat session"""
    session_id = new_chat(system_prompt=chat.system_prompt)
    return ChatSession(session_id=session_id)


def send_chat_message(session_id: str, message: MessageCreate) -> MessageResponse:
    """Send a message to an existing chat session"""
    ai_message, _ = do_chat(
        session_id=session_id,
        user_message=message.message
    )
    return MessageResponse(
        session_id=session_id,
        ai_message=ai_message
    )


def delete_chat_session(session_id: str) -> ChatDeleteResponse:
    """End and delete a chat session"""
    end_chat(session_id)
    return ChatDeleteResponse(session_id=session_id, deleted=True)


def get_chat_session_status(session_id: str) -> ChatSessionStatus:
    """Check if a chat session exists and return its status"""
    exists = session_id in _chat_sessions
    message_count = len(_chat_sessions.get(session_id, [])) if exists else None
    
    return ChatSessionStatus(
        session_id=session_id,
        exists=exists,
        message_count=message_count
    )
