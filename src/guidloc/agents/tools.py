"""Function tools exposed to OpenAI Agents."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext
from guidloc.locations.models import LocationCategory
from guidloc.locations.service import list_locations

_MAX_RESULTS = 20
_DEFAULT_RESULTS = 5


async def search_locations_impl(
    session: AsyncSession,
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = _DEFAULT_RESULTS,
) -> str:
    """Plain async implementation, callable directly in tests."""
    categories = None
    if category:
        try:
            categories = [LocationCategory(category.lower())]
        except ValueError:
            return f"Unknown category: {category}."

    tags = [tag] if tag else None
    bounded_limit = max(1, min(limit, _MAX_RESULTS))

    results = await list_locations(
        session,
        categories=categories,
        tags=tags,
        query=query,
        limit=bounded_limit,
    )

    if not results:
        return "No matching locations found."

    lines = []
    for loc in results:
        snippet = (loc.description or "").strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        tag_str = ", ".join(loc.tags) if loc.tags else "none"
        address = loc.address or "no address"
        lines.append(f"- {loc.name} [{loc.category.value}] — {address}. Tags: {tag_str}. {snippet}")
    return "\n".join(lines)


@function_tool
async def search_locations(
    ctx: RunContextWrapper[AgentContext],
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = _DEFAULT_RESULTS,
) -> str:
    """Search the GuidLoc location database for places in Chernivtsi.

    Args:
        query: Free-text substring to match in the place name or description.
        category: One of: cafe, restaurant, bar, park, museum, gallery,
            attraction, shop, hotel, entertainment, other.
        tag: A single tag the place must have (e.g. 'wifi', 'walk',
            'date-night', 'family-friendly', 'quiet').
        limit: Maximum number of places to return (1..20).
    """
    return await search_locations_impl(
        ctx.context.session,
        query=query,
        category=category,
        tag=tag,
        limit=limit,
    )
