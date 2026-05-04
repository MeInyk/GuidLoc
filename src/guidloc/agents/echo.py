"""Deterministic LLM provider used for tests and local development."""

from collections.abc import AsyncIterator

from guidloc.agents.base import AgentContext, ChatTurn, StreamEvent
from guidloc.chats.models import MessageRole


class EchoLLMProvider:
    async def complete(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> str:
        last_user = next(
            (m for m in reversed(messages) if m.role == MessageRole.USER),
            None,
        )
        if last_user is None:
            return "I have nothing to reply to yet."
        return f"Echo: {last_user.content}"

    async def stream(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> AsyncIterator[StreamEvent]:
        text = await self.complete(messages, context)
        yield StreamEvent(type="agent", data={"name": "Echo"})
        yield StreamEvent(type="delta", data={"text": text})
