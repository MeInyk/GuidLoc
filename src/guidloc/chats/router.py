"""HTTP routes for chats."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.agents.base import StreamEvent
from guidloc.agents.factory import get_llm_provider
from guidloc.agents.runner import (
    EmptyChatError,
    generate_assistant_reply,
    stream_user_message,
)
from guidloc.auth.dependencies import get_current_user
from guidloc.chats.models import Chat
from guidloc.chats.schemas import (
    ChatCreate,
    ChatRead,
    ChatUpdate,
    MessageCreate,
    MessageRead,
    SendMessageRequest,
)
from guidloc.chats.service import (
    create_chat,
    create_message,
    delete_chat,
    get_user_chat,
    list_chat_messages,
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


@router.post(
    "/{chat_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a chat",
)
async def post_message(
    chat_id: int,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await _get_owned_chat(chat_id, session, current_user)
    return await create_message(session, chat, payload)


@router.get(
    "/{chat_id}/messages",
    response_model=list[MessageRead],
    summary="List messages of a chat",
)
async def get_messages(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await _get_owned_chat(chat_id, session, current_user)
    return await list_chat_messages(session, chat)


@router.post(
    "/{chat_id}/generate",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an assistant reply for the current chat history",
)
async def generate_reply(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await _get_owned_chat(chat_id, session, current_user)
    try:
        return await generate_assistant_reply(session, chat, current_user.id, get_llm_provider())
    except EmptyChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat has no messages to reply to",
        ) from exc


async def _sse(events: AsyncIterator[StreamEvent]) -> AsyncIterator[bytes]:
    async for ev in events:
        payload = json.dumps(ev.data, ensure_ascii=False)
        yield f"event: {ev.type}\ndata: {payload}\n\n".encode()


@router.post(
    "/{chat_id}/send",
    summary="Send a user message and stream the assistant reply via SSE",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    chat_id: int,
    payload: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    chat = await _get_owned_chat(chat_id, session, current_user)
    events = stream_user_message(
        session,
        chat,
        current_user.id,
        payload.content,
        get_llm_provider(),
    )
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
