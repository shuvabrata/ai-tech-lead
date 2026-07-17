"""Time conversion helpers for graph time-based filter sliders.

Provides functions to parse ISO 8601 timestamps to days-since-epoch,
format days back to human-readable labels, and compute slider ranges
from a collection of Cytoscape node elements.
"""

from datetime import datetime, timedelta, timezone

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_EMPTY_RANGE = (0, 1)


def _parse_days_since_epoch(iso_string: str) -> int | None:
    """Parse an ISO 8601 string to days since Unix epoch (UTC).

    Returns ``None`` when the string is empty, ``None``, or cannot be
    parsed as a valid ISO datetime.
    """
    if not iso_string:
        return None
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - EPOCH
        return delta.days
    except (ValueError, TypeError):
        return None


def _format_day_label(days: int) -> str:
    """Convert days-since-epoch to a human-readable date label.

    Format: ``"%b %d, %Y"`` (e.g. ``"Jan 15, 2026"``).
    """
    dt = EPOCH + timedelta(days=days)
    return dt.strftime("%b %d, %Y")


def compute_time_range(nodes: list, property_name: str) -> tuple[int, int]:
    """Scan a list of Cytoscape node element dicts for a time property.

    Returns ``(min_days, max_days)`` over all nodes that **have** the
    given property.  Nodes without the property, or with an unparseable
    value, are silently skipped.

    If *no* nodes have the property, returns ``(0, 1)`` — a safe range
    that makes the slider effectively inert (no nodes excluded).
    """
    days_list: list[int] = []
    for node in nodes:
        data = node.get("data", {}) if isinstance(node, dict) else {}
        raw = data.get(property_name, "")
        days = _parse_days_since_epoch(raw)
        if days is not None:
            days_list.append(days)

    if not days_list:
        return _EMPTY_RANGE

    return (min(days_list), max(days_list))