"""Tests for the EchoLLMProvider."""

from unittest.mock import MagicMock

from guidloc.agents.base import AgentContext, ChatTurn
from guidloc.agents.echo import EchoLLMProvider
from guidloc.chats.models import MessageRole


def _ctx() -> AgentContext:
    return AgentContext(session=MagicMock(), user_id=1)


async def test_echo_returns_last_user_message() -> None:
    provider = EchoLLMProvider()

    reply = await provider.complete(
        [
            ChatTurn(role=MessageRole.USER, content="first"),
            ChatTurn(role=MessageRole.ASSISTANT, content="ignored"),
            ChatTurn(role=MessageRole.USER, content="latest"),
        ],
        _ctx(),
    )

    assert reply == "Echo: latest"


async def test_echo_handles_empty_history() -> None:
    provider = EchoLLMProvider()

    reply = await provider.complete([], _ctx())

    assert "nothing to reply" in reply.lower()


async def test_echo_when_only_non_user_messages() -> None:
    provider = EchoLLMProvider()

    reply = await provider.complete(
        [ChatTurn(role=MessageRole.ASSISTANT, content="prior")],
        _ctx(),
    )

    assert "nothing to reply" in reply.lower()
