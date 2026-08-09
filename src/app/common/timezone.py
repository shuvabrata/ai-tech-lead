"""Helpers for working with the app-configured timezone."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.runtime_settings import runtime_settings


def get_app_timezone() -> ZoneInfo:
    """Return the configured app timezone."""
    return ZoneInfo(runtime_settings.get("TIMEZONE"))


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


def humanize_duration(dt: datetime, tz: ZoneInfo | None = None) -> str:
    """Return a human readable duration from the current time.
    e.g. 1 min ago, 1 hr ago, 1 day ago, etc.
    """
    if tz is None:
        tz = get_app_timezone()
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = datetime.now(tz)
    dt_tz = dt.astimezone(tz)
    
    diff = now - dt_tz
    
    if diff.total_seconds() < 60:
        return "just now"
    
    mins = int(diff.total_seconds() / 60)
    if mins < 60:
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    
    hours = int(mins / 60)
    if hours < 24:
        return f"{hours} hr{'s' if hours != 1 else ''} ago"
    
    days = diff.days
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    
    weeks = int(days / 7)
    if days < 30:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    
    months = int(days / 30)
    if days < 365:
        return f"{months} month{'s' if months != 1 else ''} ago"
    
    years = int(days / 365)
    return f"{years} year{'s' if years != 1 else ''} ago"
