"""Tools shared by every agent in the system."""

from datetime import datetime
from zoneinfo import ZoneInfo

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext

_LOCAL_TZ = ZoneInfo("Europe/Kyiv")


@function_tool
async def get_current_datetime(
    ctx: RunContextWrapper[AgentContext],
) -> str:
    """Return the current date and time.

    How it works: returns the current moment as ISO 8601 strings, both in
    UTC and in Europe/Kyiv local time, plus the local weekday name.

    When to use:
        - The user asks something time-relative ("today", "tonight",
          "this weekend", "in two hours").
        - You need to compute opening hours, expirations or scheduled
          notes against the current moment.
    """
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    now_local = now_utc.astimezone(_LOCAL_TZ)
    return (
        f"utc={now_utc.isoformat(timespec='seconds')} "
        f"local={now_local.isoformat(timespec='seconds')} "
        f"weekday_local={now_local.strftime('%A')}"
    )
