"""Common types and the LLM provider protocol."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.chats.models import MessageRole


class ChatTurn(BaseModel):
    role: MessageRole
    content: str


# ...


@dataclass
class AgentContext:
    """Mutable context shared with Agents SDK tools and handoffs."""

    session: AsyncSession
    user_id: int
    # Serialises DB-touching tool calls so concurrent tools never share
    # the AsyncSession in the middle of a flush.
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class StreamEvent(BaseModel):
    """Wire contract for the SSE stream.

    type:
      - "agent"        data={"name": str}
      - "tool_call"    data={"name": str, "args": dict | None}
      - "tool_output"  data={"name": str, "ok": bool, "summary": str | None}
      - "delta"        data={"text": str}
      - "user_message" data={"message": <MessageRead dict>}   (runner only)
      - "done"         data={"assistant_message": <MessageRead dict>}  (runner)
      - "error"        data={"message": str}                  (runner only)
    """

    type: str
    data: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> str: ...

    def stream(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> AsyncIterator[StreamEvent]: ...
