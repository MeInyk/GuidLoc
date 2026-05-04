"""Memory tools available to agents.

Two read tools and three write tools live here. Read tools come in two
flavours so we can give different agents different views of memory:

- `read_user_memory`  -> orchestrator only; sees `possible` and `confirmed`.
- `read_confirmed_memory` -> recommendation agents; only `confirmed` items,
  statuses are stripped from the response.

Write tools are orchestrator-only.
"""

import logging

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

logger = logging.getLogger("guidloc.agents.tools")

logger = logging.getLogger("guidloc.agents.tools")

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
    """Read what we know about the current user.

    Returns memory items grouped by section, including their statuses
    (possible / confirmed) and ids — so you can decide whether new info is
    worth saving, or which existing item to update or forget.

    Sections you can request:
    - "rule"        — hard rules the user wants always followed.
    - "preference"  — likes and dislikes.
    - "user_info"   — facts about the user or people in their life.
    - "note"        — plans, ideas, reminders.
    - "profile"     — static profile fields (name, date of birth, phone,
                    address).
    Pass None or [] to get everything except profile.

    When to use:
    - Before saving a new fact, to check whether something similar already
    exists.
    - Before recommending or answering, to personalise the reply.

    Examples:
    - User says "Я люблю чізкейк" -> read with sections=["preference"]
    to see if "loves cheesecake" is already there.
    - Planning a date suggestion -> read sections=["rule","preference",
    "user_info"]."""
    logger.info(
        "tool=read_user_memory user_id=%s sections=%s",
        ctx.context.user_id,
        sections,
    )
    parsed = _parse_sections(sections)
    # include_profile = parsed is not None and any(s.value == "profile" for s in [])  # placeholder
    # Profile is requested via the literal string "profile" outside enum.
    requested_profile = bool(sections) and any(s.lower() == "profile" for s in sections)
    async with ctx.context.db_lock:
        result = await _load_memory(
            ctx.context.session,
            ctx.context.user_id,
            parsed,
            [MemoryItemStatus.POSSIBLE, MemoryItemStatus.CONFIRMED],
            include_profile=requested_profile,
            include_status=True,
        )
    logger.info(
        "tool=read_user_memory result=ok bytes=%d",
        len(result),
    )
    return result


@function_tool
async def read_confirmed_memory(
    ctx: RunContextWrapper[AgentContext],
    sections: list[str] | None = None,
) -> str:
    """Read confirmed facts about the current user.

    Returns only items with status "confirmed" (statuses are stripped from
    the output). Use this when you want personalisation without the noise
    of unverified guesses.

    Sections work the same way as in read_user_memory; pass "profile" to
    include static profile fields.

    When to use:
    - Specialist agents that personalise recommendations but cannot edit
    memory.
    - Always read sections "rule" and "preference" before recommending."""
    logger.info(
        "tool=read_confirmed_memory user_id=%s sections=%s",
        ctx.context.user_id,
        sections,
    )
    parsed = _parse_sections(sections)
    requested_profile = bool(sections) and any(s.lower() == "profile" for s in sections)
    async with ctx.context.db_lock:
        result = await _load_memory(
            ctx.context.session,
            ctx.context.user_id,
            parsed,
            [MemoryItemStatus.CONFIRMED],
            include_profile=requested_profile,
            include_status=False,
        )
    logger.info(
        "tool=read_confirmed_memory result=ok bytes=%d",
        len(result),
    )
    return result


# --- WRITE TOOLS (orchestrator only) -------------------------------------


@function_tool
async def save_memory_item(
    ctx: RunContextWrapper[AgentContext],
    section: str,
    value: str,
    status: str = "possible",
    item_id: int | None = None,
) -> str:
    """Create or update a dynamic memory item for the current user.

    Args:
        section: One of: "rule", "preference", "user_info", "note".
            - "rule"        — only when the user uses absolute language
                            ("завжди", "ніколи", "тільки") or explicitly
                            asks to make it a rule.
            - "preference"  — likes / dislikes.
            - "user_info"   — facts about the user or people in their life.
            - "note"        — plans, ideas, reminders.
            Identity / contact fields go to update_user_profile, not here.
        value: Short factual sentence in English or the user's language.
        status: One of: "possible", "confirmed".
            - "confirmed"   — clear statement, explicit ask to remember,
                            or a previously "possible" fact the user
                            repeated.
            - "possible"    — soft signal worth verifying later.
            NEVER pass "archived" — use forget_memory_item to remove.
        item_id: Pass an existing id to update that item; omit to create.

    Returns a short status string with the resulting item id.

    Examples:
    - "Я люблю чізкейк."   -> section="preference",
                            value="loves cheesecake", status="confirmed".
    - "Здається, мені там сподобалось." -> section="preference",
                            value="possibly likes <place>",
                            status="possible".
    - Repeated later       -> save_memory_item(item_id=<existing>,
                            status="confirmed")."""
    logger.info(
        "tool=save_memory_item user_id=%s section=%s status=%s item_id=%s value=%r",
        ctx.context.user_id,
        section,
        status,
        item_id,
        value,
    )
    try:
        section_enum = MemorySection(section.lower())
    except ValueError:
        allowed = ", ".join(s.value for s in MemorySection)
        msg = f"Unknown section '{section}'. Allowed: {allowed}."
        logger.warning("tool=save_memory_item result=error %s", msg)
        return msg
    try:
        status_enum = MemoryItemStatus(status.lower())
    except ValueError:
        allowed = ", ".join(s.value for s in MemoryItemStatus if s.value != "archived")
        msg = f"Unknown status '{status}'. Allowed: {allowed}."
        logger.warning("tool=save_memory_item result=error %s", msg)
        return msg
    if status_enum is MemoryItemStatus.ARCHIVED:
        msg = "Cannot set status to archived. Use the forget tool instead."
        logger.warning("tool=save_memory_item result=error %s", msg)
        return msg

    session = ctx.context.session
    user_id = ctx.context.user_id

    async with ctx.context.db_lock:
        if item_id is not None:
            item = await service.get_item(session, user_id, item_id)
            if item is None:
                msg = f"Item {item_id} not found."
                logger.warning("tool=save_memory_item result=error %s", msg)
                return msg
            item = await service.update_item(
                session,
                item,
                MemoryItemUpdate(value=value, status=status_enum),
            )
            result = (
                f"Updated item id={item.id} "
                f"section={item.section.value} "
                f"status={item.status.value}."
            )
            logger.info("tool=save_memory_item result=ok %s", result)
            return result

        item = await service.create_item(
            session,
            user_id,
            MemoryItemCreate(section=section_enum, value=value, status=status_enum),
        )
    result = f"Created item id={item.id} section={item.section.value} status={item.status.value}."
    logger.info("tool=save_memory_item result=ok %s", result)
    return result


@function_tool
async def forget_memory_item(
    ctx: RunContextWrapper[AgentContext],
    item_id: int,
) -> str:
    """Archive a memory item that is no longer true.

    The item is moved to status "archived" and stops appearing in reads.
    Nothing is hard-deleted.

    When to use:
    - The user said something is no longer true ("я більше не люблю рибу",
    "забудь про прийом у лікаря").
    - You are about to save a new fact that directly contradicts an
    existing one — archive the old, save the new."""
    logger.info(
        "tool=forget_memory_item user_id=%s item_id=%s",
        ctx.context.user_id,
        item_id,
    )
    async with ctx.context.db_lock:
        item = await service.get_item(ctx.context.session, ctx.context.user_id, item_id)
        if item is None:
            msg = f"Item {item_id} not found."
            logger.warning("tool=forget_memory_item result=error %s", msg)
            return msg
        await service.archive_item(ctx.context.session, item)
    result = f"Archived item id={item.id}."
    logger.info("tool=forget_memory_item result=ok %s", result)
    return result


@function_tool
async def update_user_profile(
    ctx: RunContextWrapper[AgentContext],
    preferred_name: str | None = None,
    date_of_birth: str | None = None,
    phone: str | None = None,
    address_text: str | None = None,
) -> str:
    """Update static profile fields of the current user.

    Only the fields you pass are changed. Profile fields have no statuses —
    set them only when the user states them clearly or asks you to remember
    them.

    Fields:
    - preferred_name — how to address the user.
    - date_of_birth  — ISO YYYY-MM-DD.
    - phone          — string as the user provided.
    - address_text   — only if the user explicitly authorised storing it.

    Examples:
    - "Звати мене Олег."             -> preferred_name="Олег".
    - "Мій телефон +380 …"           -> phone="+380 …".
    - "Народився 12.07.1990."        -> date_of_birth="1990-07-12"."""
    from datetime import date as _date

    logger.info(
        "tool=update_user_profile user_id=%s preferred_name=%r date_of_birth=%r "
        "phone=%r address_text=%r",
        ctx.context.user_id,
        preferred_name,
        date_of_birth,
        phone,
        address_text,
    )

    payload_kwargs: dict = {}
    if preferred_name is not None:
        payload_kwargs["preferred_name"] = preferred_name
    if date_of_birth is not None:
        try:
            payload_kwargs["date_of_birth"] = _date.fromisoformat(date_of_birth)
        except ValueError:
            msg = "date_of_birth must be in YYYY-MM-DD format."
            logger.warning("tool=update_user_profile result=error %s", msg)
            return msg
    if phone is not None:
        payload_kwargs["phone"] = phone
    if address_text is not None:
        payload_kwargs["address_text"] = address_text

    if not payload_kwargs:
        msg = "No profile fields provided."
        logger.warning("tool=update_user_profile result=error %s", msg)
        return msg

    async with ctx.context.db_lock:
        profile = await service.update_profile(
            ctx.context.session,
            ctx.context.user_id,
            UserProfileUpdate(**payload_kwargs),
        )
    result = f"Profile updated for user_id={profile.user_id}."
    logger.info("tool=update_user_profile result=ok %s", result)
    return result
