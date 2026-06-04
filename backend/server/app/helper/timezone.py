from __future__ import annotations

import os
from datetime import datetime, timezone, tzinfo
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_APP_TIMEZONE = "America/Toronto"


def _load_timezone() -> tzinfo:
    configured = (os.getenv("APP_TIMEZONE") or DEFAULT_APP_TIMEZONE).strip() or DEFAULT_APP_TIMEZONE
    try:
        return ZoneInfo(configured)
    except ZoneInfoNotFoundError:
        try:
            return ZoneInfo(DEFAULT_APP_TIMEZONE)
        except ZoneInfoNotFoundError:
            return timezone.utc


APP_TIMEZONE = _load_timezone()


def now_in_app_timezone() -> datetime:
    return datetime.now(APP_TIMEZONE)


def ensure_app_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Mongo stores datetimes as naive UTC by default. Treat naive as UTC.
            return value.replace(tzinfo=timezone.utc).astimezone(APP_TIMEZONE)
        return value.astimezone(APP_TIMEZONE)
    return None
