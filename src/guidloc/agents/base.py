"""Common types and the LLM provider protocol."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.chats.models import MessageRole


class ChatTurn(BaseModel):
    """A single message in the conversation passed to the LLM."""

    role: MessageRole
    content: str


@dataclass
class AgentContext:
    """Mutable context shared with Agents SDK tools and handoffs.

    Carries the per-request DB session and the authenticated user id so
    tools can query data on behalf of the right user.
    """

    session: AsyncSession
    user_id: int


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for any LLM backend the application can call."""

    async def complete(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> str:
        """Produce an assistant reply for the given conversation."""
        ...
