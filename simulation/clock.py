from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")


def singapore_now() -> datetime:
    """Return the current wall-clock time in Singapore for live 24/7 simulation."""
    return datetime.now(SGT)


def day_phase(moment: datetime | None = None) -> str:
    moment = moment or singapore_now()
    local = moment.astimezone(SGT)
    hour = local.hour + local.minute / 60
    if 5.0 <= hour < 7.0:
        return "early_morning"
    if 7.0 <= hour < 10.0:
        return "morning_peak"
    if 10.0 <= hour < 14.0:
        return "midday"
    if 14.0 <= hour < 17.0:
        return "afternoon"
    if 17.0 <= hour < 20.0:
        return "evening_peak"
    if 20.0 <= hour < 22.5:
        return "evening"
    return "night"
