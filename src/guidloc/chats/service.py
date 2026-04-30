"""Database operations for chats."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.chats.models import Chat
from guidloc.chats.schemas import ChatCreate, ChatUpdate


async def create_chat(session: AsyncSession, user_id: int, payload: ChatCreate) -> Chat:
    """Create a new chat owned by the given user."""
    chat = Chat(user_id=user_id, title=payload.title)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return chat


async def list_user_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """List all chats owned by the user. Pinned first, then most recent."""
    result = await session.execute(
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(Chat.is_pinned.desc(), Chat.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_user_chat(session: AsyncSession, user_id: int, chat_id: int) -> Chat | None:
    """Return a chat only if it exists and belongs to the user, otherwise None."""
    result = await session.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    return result.scalar_one_or_none()


async def update_chat(session: AsyncSession, chat: Chat, payload: ChatUpdate) -> Chat:
    """Apply a partial update to the given chat."""
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(chat, field, value)

    await session.commit()
    await session.refresh(chat)
    return chat


async def delete_chat(session: AsyncSession, chat: Chat) -> None:
    """Delete the given chat."""
    await session.delete(chat)
    await session.commit()
