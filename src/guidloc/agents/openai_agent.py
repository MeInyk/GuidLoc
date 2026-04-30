"""OpenAI Agents SDK provider with one places specialist and one tool."""

from agents import Agent, Runner, set_default_openai_key
from guidloc.agents.base import AgentContext, ChatTurn, LLMProvider
from guidloc.agents.tools import search_locations
from guidloc.chats.models import MessageRole
from guidloc.common.config import get_settings

ORCHESTRATOR_INSTRUCTIONS = """\
You are GuidLoc, a friendly assistant who helps visitors and locals discover \
Chernivtsi, Ukraine. You can answer general questions about the city: history, \
neighborhoods, getting around, etiquette, weather context.

When the user asks for concrete recommendations — places to eat, drink, walk, \
visit, shop, or any specific venue — hand off to PlacesAgent. Do not invent \
venues yourself.

Always reply in the same language the user wrote in. Keep replies concise, \
warm and practical.
"""

PLACES_INSTRUCTIONS = """\
You are a Chernivtsi places expert.

Always call the search_locations tool before suggesting venues — never invent \
places that are not returned by the tool. Refine your tool call (category, tag, \
query) to match the user's intent. If the first call returns nothing, try a \
broader search.

When suggesting, mention each place's name, a short reason why it fits the \
request, and the address. Suggest 2-4 options unless the user asked for more. \
Reply in the same language the user wrote in.
"""


def _build_places_agent(model: str) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="PlacesAgent",
        instructions=PLACES_INSTRUCTIONS,
        tools=[search_locations],
        model=model,
    )


def _build_orchestrator_agent(
    model: str,
    places: Agent[AgentContext],
) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="Orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        handoffs=[places],
        model=model,
    )


class OpenAIAgentsProvider:
    """LLMProvider backed by the OpenAI Agents SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        set_default_openai_key(settings.openai_api_key)

        places = _build_places_agent(settings.openai_model)
        self._root = _build_orchestrator_agent(settings.openai_model, places)

    async def complete(
        self,
        messages: list[ChatTurn],
        context: AgentContext,
    ) -> str:
        # Pass full conversation as the input. Drop system messages (we don't
        # currently store them, and instructions live on the Agent).
        sdk_input = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]
        result = await Runner.run(self._root, input=sdk_input, context=context)
        return str(result.final_output)


# Type-check that the class satisfies the protocol.
_: LLMProvider = OpenAIAgentsProvider.__new__(OpenAIAgentsProvider)
