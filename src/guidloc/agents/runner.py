"""High-level entry point that ties chat history, LLM and persistence."""

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.agents.base import AgentContext, ChatTurn, LLMProvider, StreamEvent
from guidloc.chats.models import Chat, Message, MessageRole
from guidloc.chats.schemas import MessageCreate, MessageRead
from guidloc.chats.service import create_message, list_chat_messages

logger = logging.getLogger("guidloc.agents.runner")


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


async def stream_user_message(
    session: AsyncSession,
    chat: Chat,
    user_id: int,
    content: str,
    llm: LLMProvider,
) -> AsyncIterator[StreamEvent]:
    """Persist user message, stream assistant reply, persist final reply.

    Yields wire events for the SSE endpoint:
        user_message -> [agent|tool_call|tool_output|delta]* -> done | error

    On any error during streaming, no assistant message is persisted; an
    `error` event is emitted and the stream ends. The user message stays
    in the DB so the client can retry.
    """
    user_message = await create_message(
        session,
        chat,
        MessageCreate(role=MessageRole.USER, content=content),
    )
    user_payload = MessageRead.model_validate(user_message).model_dump(mode="json")
    yield StreamEvent(type="user_message", data={"message": user_payload})

    history = await list_chat_messages(session, chat)
    turns = [ChatTurn(role=m.role, content=m.content) for m in history]
    agent_context = AgentContext(session=session, user_id=user_id)

    parts: list[str] = []
    logger.info(
        "event=stream_start chat_id=%s user_id=%s history_len=%d",
        chat.id,
        user_id,
        len(turns),
    )
    try:
        async for ev in llm.stream(turns, agent_context):
            if ev.type == "delta":
                text = ev.data.get("text", "")
                if text:
                    parts.append(text)
            yield ev
    except Exception as exc:
        logger.exception(
            "event=stream_error chat_id=%s user_id=%s",
            chat.id,
            user_id,
        )
        yield StreamEvent(type="error", data={"message": str(exc)})
        return

    final_text = "".join(parts).strip()
    if not final_text:
        logger.warning(
            "event=stream_empty chat_id=%s user_id=%s",
            chat.id,
            user_id,
        )
        yield StreamEvent(
            type="error",
            data={"message": "Empty assistant reply"},
        )
        return

    assistant_message = await create_message(
        session,
        chat,
        MessageCreate(role=MessageRole.ASSISTANT, content=final_text),
    )
    assistant_payload = MessageRead.model_validate(assistant_message).model_dump(
        mode="json",
    )
    logger.info(
        "event=stream_done chat_id=%s user_id=%s bytes=%d",
        chat.id,
        user_id,
        len(final_text),
    )
    yield StreamEvent(
        type="done",
        data={"assistant_message": assistant_payload},
    )
