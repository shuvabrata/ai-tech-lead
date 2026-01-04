from app.ai_agent.ai_agent import new_chat, do_chat, end_chat
from .model import ChatCreate, ChatSession, MessageCreate, MessageResponse, ChatDeleteResponse


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
