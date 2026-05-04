"""Tools shared by every agent in the system."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext

_LOCAL_TZ = ZoneInfo("Europe/Kyiv")

logger = logging.getLogger("guidloc.agents.tools")


@function_tool
async def get_current_datetime(
    ctx: RunContextWrapper[AgentContext],
) -> str:
    """Return the current date, weekday and time in Chernivtsi.

    When to use:
    - The user uses a time-relative phrase ("сьогодні", "ввечері",
    "цими вихідними", "за дві години").
    - You need to check opening hours, plan a "tonight" outing, or compute
    whether a saved note is still relevant."""
    logger.info("tool=get_current_datetime user_id=%s", ctx.context.user_id)
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    now_local = now_utc.astimezone(_LOCAL_TZ)
    result = (
        f"utc={now_utc.isoformat(timespec='seconds')} "
        f"local={now_local.isoformat(timespec='seconds')} "
        f"weekday_local={now_local.strftime('%A')}"
    )
    logger.info("tool=get_current_datetime result=ok %s", result)
    return result


_CHERNIVTSI_LAT = 48.2917
_CHERNIVTSI_LON = 25.9354
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather interpretation codes -> short human label
_WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "light rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


@function_tool
async def get_weather(
    ctx: RunContextWrapper[AgentContext],
) -> str:
    """Return the current weather in Chernivtsi.

    Returns a short string with temperature, "feels like", humidity,
    precipitation, wind speed and a human-readable condition.

    When to use:
    - The user is choosing an outdoor activity (walk, park, terrace,
      picnic, BBQ).
    - The user asks what to wear or whether to take an umbrella.
    - The recommendation might be much better indoors today
      (rain, cold, heat).

    Examples:
    - "Що мені сьогодні вдягти?"   -> call get_weather, then advise.
    - "Куди піти прогулятись?"      -> check weather before suggesting
                                       indoor vs outdoor."""
    logger.info("tool=get_weather user_id=%s", ctx.context.user_id)
    params = {
        "latitude": _CHERNIVTSI_LAT,
        "longitude": _CHERNIVTSI_LON,
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "precipitation,weather_code,wind_speed_10m"
        ),
        "timezone": "Europe/Kyiv",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(_OPEN_METEO_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        msg = f"Weather service unavailable: {exc.__class__.__name__}."
        logger.warning("tool=get_weather result=error %s", msg)
        return msg

    current = payload.get("current") or {}
    code = int(current.get("weather_code", -1))
    condition = _WMO_CODES.get(code, f"code {code}")

    result = (
        f"Chernivtsi now: {condition}, "
        f"temp={current.get('temperature_2m')}°C "
        f"(feels {current.get('apparent_temperature')}°C), "
        f"humidity={current.get('relative_humidity_2m')}%, "
        f"precipitation={current.get('precipitation')}mm, "
        f"wind={current.get('wind_speed_10m')} km/h"
    )
    logger.info("tool=get_weather result=ok %s", result)
    return result
