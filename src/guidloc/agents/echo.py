"""Deterministic LLM provider used for tests and local development."""

from guidloc.agents.base import AgentContext, ChatTurn
from guidloc.chats.models import MessageRole


class EchoLLMProvider:
    """Echoes the last user message. No network calls."""

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
