"""Memory tools available to agents.

Two read tools and three write tools live here. Read tools come in two
flavours so we can give different agents different views of memory:

- `read_user_memory`  -> orchestrator only; sees `possible` and `confirmed`.
- `read_confirmed_memory` -> recommendation agents; only `confirmed` items,
  statuses are stripped from the response.

Write tools are orchestrator-only.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext
from guidloc.memory import service
from guidloc.memory.models import (
    MemoryItemStatus,
    MemorySection,
    UserMemoryItem,
    UserProfile,
)
from guidloc.memory.schemas import (
    MemoryItemCreate,
    MemoryItemUpdate,
    UserProfileUpdate,
)

_SECTION_LABEL = {
    MemorySection.RULE: "RULES",
    MemorySection.PREFERENCE: "PREFERENCES",
    MemorySection.USER_INFO: "USER INFO",
    MemorySection.NOTE: "NOTES",
}


def _format_profile(profile: UserProfile) -> str:
    fields = {
        "preferred_name": profile.preferred_name,
        "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        "phone": profile.phone,
        "address_text": profile.address_text,
    }
    filled = [f"{k}={v}" for k, v in fields.items() if v]
    return "PROFILE: " + (", ".join(filled) if filled else "(empty)")


def _format_items(
    items: list[UserMemoryItem],
    *,
    include_status: bool,
) -> list[str]:
    by_section: dict[MemorySection, list[UserMemoryItem]] = {s: [] for s in MemorySection}
    for it in items:
        by_section[it.section].append(it)
    lines: list[str] = []
    for section, bucket in by_section.items():
        if not bucket:
            continue
        lines.append(f"{_SECTION_LABEL[section]}:")
        for it in bucket:
            if include_status:
                lines.append(f"  - id={it.id} [{it.status.value}] {it.value}")
            else:
                lines.append(f"  - {it.value}")
    return lines


def _parse_sections(values: list[str] | None) -> list[MemorySection] | None:
    if not values:
        return None
    out: list[MemorySection] = []
    for v in values:
        try:
            out.append(MemorySection(v.lower()))
        except ValueError:
            continue
    return out or None


async def _load_memory(
    session: AsyncSession,
    user_id: int,
    sections: list[MemorySection] | None,
    statuses: list[MemoryItemStatus],
    *,
    include_profile: bool,
    include_status: bool,
) -> str:
    items = await service.list_items(session, user_id, sections=sections, statuses=statuses)
    parts: list[str] = []
    if include_profile:
        profile = await service.get_or_create_profile(session, user_id)
        parts.append(_format_profile(profile))
    parts.extend(_format_items(items, include_status=include_status))
    if not parts:
        return "No memory stored for this user."
    return "\n".join(parts)


# --- READ TOOLS ----------------------------------------------------------


@function_tool
async def read_user_memory(
    ctx: RunContextWrapper[AgentContext],
    sections: list[str] | None = None,
) -> str:
    """Read the user's memory. Orchestrator-only view that includes both
    confirmed facts and unconfirmed assumptions.

    How it works: returns the requested sections as plain text. Each item
    is shown with its id and status so the orchestrator can decide whether
    to confirm, supersede or archive it.

    When to use: before deciding whether to add, update or remove a memory
    item that the current user message could affect.

    When NOT to use: do not call before every reply. Only call when the
    message looks like it carries a fact, preference, rule or note.

    Sections:
        - profile: static personal data (preferred_name, date_of_birth,
          phone, address_text). Returned only if explicitly requested.
        - rules: things the user said to ALWAYS do.
        - preferences: likes, dislikes, things to avoid.
        - user_info: concrete facts (family, allergies, friends' names...).
        - notes: short, often temporary reminders.

    If `sections` is empty, all dynamic sections are returned (no profile).
    """
    parsed = _parse_sections(sections)
    # include_profile = parsed is not None and any(s.value == "profile" for s in [])  # placeholder
    # Profile is requested via the literal string "profile" outside enum.
    requested_profile = bool(sections) and any(s.lower() == "profile" for s in sections)
    return await _load_memory(
        ctx.context.session,
        ctx.context.user_id,
        parsed,
        [MemoryItemStatus.POSSIBLE, MemoryItemStatus.CONFIRMED],
        include_profile=requested_profile,
        include_status=True,
    )


@function_tool
async def read_confirmed_memory(
    ctx: RunContextWrapper[AgentContext],
    sections: list[str] | None = None,
) -> str:
    """Read the confirmed parts of the user's memory for personalization.

    How it works: returns only memory the user explicitly confirmed or
    stated. Statuses and ids are not exposed because this view is read-only
    for the calling agent.

    When to use: before recommending venues or building a plan, to honour
    the user's known preferences, rules and relevant facts.

    When NOT to use: do not call to look up identity-only data unless you
    actually need it. Do not attempt to modify memory from this tool — it
    is read-only.

    Sections: same as `read_user_memory`. Pass "profile" explicitly to
    receive static personal data.
    """
    parsed = _parse_sections(sections)
    requested_profile = bool(sections) and any(s.lower() == "profile" for s in sections)
    return await _load_memory(
        ctx.context.session,
        ctx.context.user_id,
        parsed,
        [MemoryItemStatus.CONFIRMED],
        include_profile=requested_profile,
        include_status=False,
    )


# --- WRITE TOOLS (orchestrator only) -------------------------------------


@function_tool
async def save_memory_item(
    ctx: RunContextWrapper[AgentContext],
    section: str,
    value: str,
    status: str = "possible",
    item_id: int | None = None,
) -> str:
    """Create or update a dynamic memory item.

    How it works: when `item_id` is omitted, a new item is created in the
    given section. When `item_id` is provided, that item's value and/or
    status are updated. The item must belong to the current user.

    When to use:
        - The user said something worth remembering that is NOT already
          stored. Save with status "possible" if it is a soft signal
          ("I'd love some cake right now"), or "confirmed" if the user
          stated it explicitly or asked you to remember it.
        - You found an existing "possible" item and the user has now
          repeated or confirmed it: update with status "confirmed".

    When NOT to use:
        - Do not duplicate an item that already says the same thing.
        - Do not pass status "archived"; use the dedicated forget tool
          when something is no longer true.

    Allowed values:
        section: rule | preference | user_info | note
        status: possible | confirmed

    Examples:
        - "Я люблю чізкейки" -> section=preference, value="loves cheesecakes",
          status=possible.
        - User repeats it later -> save_memory_item(item_id=<existing>,
          status="confirmed").
        - "Запам'ятай, що в мене прийом до лікаря в п'ятницю" ->
          section=note, value="doctor appointment Friday", status=confirmed.
    """
    try:
        section_enum = MemorySection(section.lower())
    except ValueError:
        return f"Unknown section: {section}."
    try:
        status_enum = MemoryItemStatus(status.lower())
    except ValueError:
        return f"Unknown status: {status}."
    if status_enum is MemoryItemStatus.ARCHIVED:
        return "Cannot set status to archived. Use the forget tool instead."

    session = ctx.context.session
    user_id = ctx.context.user_id

    if item_id is not None:
        item = await service.get_item(session, user_id, item_id)
        if item is None:
            return f"Item {item_id} not found."
        item = await service.update_item(
            session,
            item,
            MemoryItemUpdate(value=value, status=status_enum),
        )
        return f"Updated item id={item.id} section={item.section.value} status={item.status.value}."

    item = await service.create_item(
        session,
        user_id,
        MemoryItemCreate(section=section_enum, value=value, status=status_enum),
    )
    return f"Created item id={item.id} section={item.section.value} status={item.status.value}."


@function_tool
async def forget_memory_item(
    ctx: RunContextWrapper[AgentContext],
    item_id: int,
) -> str:
    """Mark a memory item as no longer valid.

    How it works: the item is moved to the archived status. It will not be
    returned by either read tool again, but it is kept in the database for
    later analysis. There is no real delete from agents.

    When to use:
        - The user explicitly said something is no longer true
          ("я більше не люблю рибу", "забудь про прийом у лікаря").
        - A new fact directly contradicts an existing one and you have
          just saved the new one.

    When NOT to use: do not archive items just because they are old.
    Notes and rules expire only when the user implies they should.
    """
    item = await service.get_item(ctx.context.session, ctx.context.user_id, item_id)
    if item is None:
        return f"Item {item_id} not found."
    await service.archive_item(ctx.context.session, item)
    return f"Archived item id={item.id}."


@function_tool
async def update_user_profile(
    ctx: RunContextWrapper[AgentContext],
    preferred_name: str | None = None,
    date_of_birth: str | None = None,
    phone: str | None = None,
    address_text: str | None = None,
) -> str:
    """Update one or more static profile fields.

    How it works: only fields you pass are updated; the rest are kept.
    Profile fields have no statuses — set them only when the user states
    them clearly or asks you to remember them.

    When to use:
        - "Звати мене Олег" -> preferred_name="Олег".
        - "Мій телефон ..." -> phone="...".
        - "Я живу на ..." (only if the user explicitly asked to remember).

    When NOT to use:
        - Do not guess profile fields from indirect signals; use the
          memory items with status "possible" instead.
        - Do not store address unless the user clearly authorised it.

    Format:
        date_of_birth: ISO date string YYYY-MM-DD.
    """
    from datetime import date as _date

    payload_kwargs: dict = {}
    if preferred_name is not None:
        payload_kwargs["preferred_name"] = preferred_name
    if date_of_birth is not None:
        try:
            payload_kwargs["date_of_birth"] = _date.fromisoformat(date_of_birth)
        except ValueError:
            return "date_of_birth must be in YYYY-MM-DD format."
    if phone is not None:
        payload_kwargs["phone"] = phone
    if address_text is not None:
        payload_kwargs["address_text"] = address_text

    if not payload_kwargs:
        return "No profile fields provided."

    profile = await service.update_profile(
        ctx.context.session,
        ctx.context.user_id,
        UserProfileUpdate(**payload_kwargs),
    )
    return f"Profile updated for user_id={profile.user_id}."
