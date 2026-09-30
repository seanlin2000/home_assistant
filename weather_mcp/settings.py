"""Where home is and how its weather is spoken, from WEATHER_* environment variables.

scripts/ha_setup.py copies the home coordinates, time zone, and unit system from Home Assistant into .env, and scripts/services.sh passes them to
the tool server. Without coordinates the server does not offer the weather tool at all.
"""

import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

# Met.no's terms require a User-Agent that names the application and a way to reach its owner; the repository serves as the contact, so no
# personal address ever leaves the network.
USER_AGENT = "studio-assistant-weather/1.0 github.com/seanlin2000/home_assistant"
LOCALTIME_LINK = Path("/etc/localtime")
ZONEINFO_MARKER = "zoneinfo/"
FALLBACK_TIMEZONE = "UTC"


class WeatherSettings(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None  # an IANA name such as America/New_York; unset means the Mac's own zone
    units: Literal["metric", "imperial"] = "metric"
    timeout_seconds: float = 8.0
    user_agent: str = USER_AGENT

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone or local_timezone_name())


def weather_settings_from_environment() -> WeatherSettings:
    """WEATHER_LATITUDE, WEATHER_LONGITUDE, WEATHER_TIMEZONE, and WEATHER_UNITS override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("WEATHER_").lower(): value for key, value in os.environ.items() if key.startswith("WEATHER_") and value.strip()}
    return WeatherSettings(**overrides)


def local_timezone_name() -> str:
    """The zone the Mac runs in. datetime's own local zone is a fixed offset that would be an hour wrong across a daylight-saving change inside the
    week being forecast, so the IANA name is read from TZ or from the /etc/localtime link instead."""
    if os.environ.get("TZ"):
        return os.environ["TZ"]
    target = str(LOCALTIME_LINK.resolve())
    return target.split(ZONEINFO_MARKER, 1)[1] if ZONEINFO_MARKER in target else FALLBACK_TIMEZONE
