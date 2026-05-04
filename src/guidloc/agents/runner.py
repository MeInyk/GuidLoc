"""High-level entry point that ties chat history, LLM and persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.agents.base import AgentContext, ChatTurn, LLMProvider
from guidloc.chats.models import Chat, Message, MessageRole
from guidloc.chats.schemas import MessageCreate
from guidloc.chats.service import create_message, list_chat_messages


class EmptyChatError(Exception):
    """Raised when an assistant reply is requested but the chat has no messages."""


async def send_user_message(
    session: AsyncSession,
    chat: Chat,
    user_id: int,
    content: str,
    llm: LLMProvider,
) -> tuple[Message, Message]:
    """Persist a user message, generate and persist the assistant reply.

    Returns a tuple of (user_message, assistant_message).
    """
    user_message = await create_message(
        session,
        chat,
        MessageCreate(role=MessageRole.USER, content=content),
    )
    assistant_message = await generate_assistant_reply(session, chat, user_id, llm)
    return user_message, assistant_message


async def generate_assistant_reply(
    session: AsyncSession,
    chat: Chat,
    user_id: int,
    llm: LLMProvider,
) -> Message:
    """Build the conversation, call the LLM and persist the assistant reply."""
    history = await list_chat_messages(session, chat)
    if not history:
        raise EmptyChatError("Cannot generate a reply for an empty chat")

    turns = [ChatTurn(role=m.role, content=m.content) for m in history]
    context = AgentContext(session=session, user_id=user_id)
    reply_text = await llm.complete(turns, context)

    return await create_message(
        session,
        chat,
        MessageCreate(role=MessageRole.ASSISTANT, content=reply_text),
    )
