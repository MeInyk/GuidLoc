"""Function tools exposed to OpenAI Agents."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext
from guidloc.locations.models import LocationCategory
from guidloc.locations.service import list_locations

_MAX_RESULTS = 20
_DEFAULT_RESULTS = 5

logger = logging.getLogger("guidloc.agents.tools")


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
    """Search OUR Chernivtsi database for places.

    Filters:
        query    — free-text snippet matched against name and description.
        category — one of: cafe, restaurant, bar, park, museum, gallery,
                attraction, shop, hotel, entertainment, other.
        tag      — a single tag the place must have (e.g. "wifi", "walk",
                "date-night", "family-friendly", "quiet").
        limit    — 1..20.

    Returns a short bulleted list of matching places (name, address, tags).

    When to use:
    - ALWAYS first, before suggesting any venue.
    - If the first call is empty, broaden it (drop a tag, widen category,
    simplify query) before falling back to web_search.

    Examples:
    - "Quiet cafe with wifi" -> category="cafe", tag="wifi", query="quiet".
    - "Cheesecake nearby"    -> category="cafe", query="cheesecake"."""
    logger.info(
        "tool=search_locations user_id=%s query=%r category=%s tag=%s limit=%s",
        ctx.context.user_id,
        query,
        category,
        tag,
        limit,
    )
    async with ctx.context.db_lock:
        result = await search_locations_impl(
            ctx.context.session,
            query=query,
            category=category,
            tag=tag,
            limit=limit,
        )
    logger.info(
        "tool=search_locations result=ok lines=%d",
        result.count("\n") + 1 if result else 0,
    )
    return result
