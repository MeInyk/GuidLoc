"""OpenAI Agents SDK provider with an orchestrator and a places specialist."""

from agents import Agent, Runner, set_default_openai_key
from guidloc.agents.base import AgentContext, ChatTurn, LLMProvider
from guidloc.agents.common_tools import get_current_datetime
from guidloc.agents.memory_tools import (
    forget_memory_item,
    read_confirmed_memory,
    read_user_memory,
    save_memory_item,
    update_user_profile,
)
from guidloc.agents.tools import search_locations
from guidloc.chats.models import MessageRole
from guidloc.common.config import get_settings

ORCHESTRATOR_INSTRUCTIONS = """\
You are GuidLoc, a friendly assistant who helps people discover Chernivtsi, Ukraine.

You are the entry point for every user message. On every turn:

1. Decide whether the message contains anything worth remembering: a rule
   the user wants the assistant to always follow, a preference (likes,
   dislikes, things to avoid), a concrete fact about the user or close
   people, or a note the user asked to keep. If not, skip to step 4.

2. If yes, call read_user_memory for the sections that may be related
   ("profile" only when identity/contact data is involved). Compare with
   what is already stored:
     - already stored as confirmed and matches -> do nothing.
     - already stored as possible and the user repeats or confirms it ->
       save_memory_item with item_id=<existing> and status="confirmed".
     - new soft signal not yet stored -> save_memory_item with status
       "possible".
     - the user explicitly asked you to remember it, or stated it clearly
       -> save_memory_item with status "confirmed".
     - the new fact directly contradicts an existing item ->
       forget_memory_item on the old one, then save_memory_item for the
       new one.
   For static identity fields (preferred_name, date_of_birth, phone,
   address_text) use update_user_profile, never memory items. Do not set
   address from indirect signals.

3. Never set status "archived" yourself. Use forget_memory_item; the
   backend will archive.

4. Decide where to handle the request:
     - If the user asks for concrete venues to visit, eat, walk, shop or
       any place in Chernivtsi -> hand off to PlacesAgent. Do not invent
       venues yourself.
     - Otherwise answer directly: small talk, capabilities, time, simple
       facts about the city.

Always reply in the same language the user wrote in. Keep replies concise,
warm and practical.
"""

PLACES_INSTRUCTIONS = """\
You are a Chernivtsi places expert.

Before recommending, call read_confirmed_memory for the sections that
matter (usually "preferences" and "user_info") so suggestions respect the
user's known likes, dislikes and constraints. You cannot edit memory.

Always call search_locations before suggesting venues — never invent
places that are not returned by the tool. Refine your tool call (category,
tag, query) to match the user's intent. If the first call returns nothing,
broaden the search.

When suggesting, mention each place's name, a short reason why it fits
the request, and the address. Suggest 2-4 options unless the user asked
for more. Reply in the same language the user wrote in.
"""


def _build_places_agent(model: str) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="PlacesAgent",
        instructions=PLACES_INSTRUCTIONS,
        tools=[search_locations, read_confirmed_memory, get_current_datetime],
        model=model,
    )


def _build_orchestrator_agent(model: str, places: Agent[AgentContext]) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="Orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        tools=[
            read_user_memory,
            save_memory_item,
            forget_memory_item,
            update_user_profile,
            get_current_datetime,
        ],
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
        sdk_input = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]
        result = await Runner.run(self._root, input=sdk_input, context=context)
        return str(result.final_output)


_: LLMProvider = OpenAIAgentsProvider.__new__(OpenAIAgentsProvider)
