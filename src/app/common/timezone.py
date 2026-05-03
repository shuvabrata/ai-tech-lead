"""Helpers for working with the app-configured timezone."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.settings import settings


def get_app_timezone() -> ZoneInfo:
    """Return the configured app timezone."""
    return ZoneInfo(settings.TIMEZONE)


def to_app_timezone(dt: datetime) -> datetime:
    """Convert a datetime to the configured app timezone.

    Naive datetimes are treated as UTC so existing persisted timestamps remain stable.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_app_timezone())


def now_in_app_timezone() -> datetime:
    """Return the current time in the configured app timezone."""
    return datetime.now(get_app_timezone())
