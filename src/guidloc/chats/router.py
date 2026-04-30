"""HTTP routes for chats."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.chats.models import Chat
from guidloc.chats.schemas import ChatCreate, ChatRead, ChatUpdate
from guidloc.chats.service import (
    create_chat,
    delete_chat,
    get_user_chat,
    list_user_chats,
    update_chat,
)
from guidloc.common.database import get_session
from guidloc.users.models import User

router = APIRouter(prefix="/chats", tags=["chats"])


async def _get_owned_chat(
    chat_id: int,
    session: AsyncSession,
    user: User,
) -> Chat:
    """Fetch a chat belonging to the user, or raise 404.

    We deliberately return 404 (not 403) for chats the user does not own,
    so we never leak that a given chat id exists.
    """
    chat = await get_user_chat(session, user.id, chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.post(
    "",
    response_model=ChatRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat",
)
async def create(
    payload: ChatCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Chat:
    return await create_chat(session, current_user.id, payload)


@router.get(
    "",
    response_model=list[ChatRead],
    summary="List the current user's chats",
)
async def list_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Chat]:
    return await list_user_chats(session, current_user.id)


@router.get(
    "/{chat_id}",
    response_model=ChatRead,
    summary="Get a chat by id",
)
async def read_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Chat:
    return await _get_owned_chat(chat_id, session, current_user)


@router.patch(
    "/{chat_id}",
    response_model=ChatRead,
    summary="Update a chat (rename, pin/unpin)",
)
async def patch_chat(
    chat_id: int,
    payload: ChatUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Chat:
    chat = await _get_owned_chat(chat_id, session, current_user)
    return await update_chat(session, chat, payload)


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat",
)
async def remove_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    chat = await _get_owned_chat(chat_id, session, current_user)
    await delete_chat(session, chat)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
