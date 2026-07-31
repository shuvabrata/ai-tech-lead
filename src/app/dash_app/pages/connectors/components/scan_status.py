"""Scan status component for connector detail pages.

Renders a single scan command row with status icon, timestamp, duration,
and result summary.
"""

from datetime import datetime

from dash import html

from app.common.timezone import humanize_duration, to_app_timezone
from app.settings import settings
from app.dash_app.styles import (
    COLOR_BORDER,
    COLOR_ERROR,
    COLOR_GRAY_MEDIUM,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FONT_SANS,
    FONT_SIZE_SMALL,
    FONT_SIZE_XSMALL,
    SPACING_XXXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
)

STATUS_CONFIG = {
    "pending": {
        "icon": "fa-regular fa-clock",
        "color": COLOR_GRAY_MEDIUM,
        "label": "Pending",
    },
    "accepted": {
        "icon": "fa-regular fa-circle-check",
        "color": COLOR_WARNING,
        "label": "Accepted",
    },
    "queued": {
        "icon": "fa-regular fa-hourglass-half",
        "color": COLOR_WARNING,
        "label": "Queued",
    },
    "running": {
        "icon": "fa-solid fa-spinner fa-spin",
        "color": COLOR_WARNING,
        "label": "Running",
    },
    "completed": {
        "icon": "fa-regular fa-circle-check",
        "color": COLOR_SUCCESS,
        "label": "Completed",
    },
    "failed": {
        "icon": "fa-regular fa-circle-xmark",
        "color": COLOR_ERROR,
        "label": "Failed",
    },
}


def _format_timestamp(ts: str | None) -> str | None:
    """Parse an ISO timestamp and return a human-readable relative time."""
    if not ts:
        return None
    try:
        dt_str = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        local_dt = to_app_timezone(dt)
        fmt = getattr(settings, "UI_DATETIME_FORMAT", "%b %d, %Y %I:%M %p")
        title = local_dt.strftime(fmt)
        return humanize_duration(local_dt)
    except (ValueError, TypeError, AttributeError):
        return ts


def render_scan_item(command: dict) -> html.Div:  # type: ignore[type-arg]
    """Render a single scan command row.

    Args:
        command: A ``CommandResponse`` dict from the API.

    Returns:
        An ``html.Div`` with status icon, timing, and summary.
    """
    status = command.get("status", "unknown")
    cfg = STATUS_CONFIG.get(status, {
        "icon": "fa-regular fa-circle-question",
        "color": COLOR_GRAY_MEDIUM,
        "label": status.title(),
    })

    created_str = _format_timestamp(command.get("created_at"))
    started_str = _format_timestamp(command.get("started_at"))
    completed_str = _format_timestamp(command.get("completed_at"))
    error_message: str | None = command.get("error_message")  # type: ignore[type-arg]
    result_summary: dict | None = command.get("result_summary")  # type: ignore[type-arg]

    # Duration calculation
    start_dt = command.get("started_at")
    end_dt = command.get("completed_at") or command.get("created_at")
    duration_text = None
    if start_dt and end_dt:
        try:
            s = datetime.fromisoformat(str(start_dt).replace("Z", "+00:00"))
            e = datetime.fromisoformat(str(end_dt).replace("Z", "+00:00"))
            delta = e - s
            total_seconds = int(delta.total_seconds())
            if total_seconds < 60:
                duration_text = f"{total_seconds}s"
            elif total_seconds < 3600:
                duration_text = f"{total_seconds // 60}m {total_seconds % 60}s"
            else:
                duration_text = f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
        except (ValueError, TypeError):
            pass

    # Summary text
    summary_parts = []
    if result_summary:
        for key, value in result_summary.items():
            label = key.replace("_", " ").title()
            summary_parts.append(f"{label}: {value}")
    if error_message:
        summary_parts.append(f"Error: {error_message}")

    summary_text = " | ".join(summary_parts) if summary_parts else None

    return html.Div(
        [
            html.Div(
                [
                    # Status icon
                    html.I(
                        className=cfg["icon"],
                        style={
                            "color": cfg["color"],
                            "marginRight": SPACING_XSMALL,
                            "width": "16px",
                            "textAlign": "center",
                        },
                    ),
                    # Status label
                    html.Span(
                        cfg["label"],
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": cfg["color"],
                            "fontWeight": "500",
                            "marginRight": SPACING_SMALL,
                        },
                    ),
                    # Created time
                    html.Span(
                        created_str or "",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginRight": SPACING_SMALL,
                        },
                    ),
                    # Duration
                    html.Span(
                        duration_text or "",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_XSMALL,
                            "color": COLOR_GRAY_MEDIUM,
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": SPACING_XXXSMALL,
                },
            ),
            # Summary / error line
            html.Div(
                summary_text or "",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_XSMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "marginLeft": "22px",  # indent to align with status text
                },
            ),
        ],
        style={
            "padding": f"{SPACING_XSMALL} {SPACING_SMALL}",
            "borderBottom": f"1px solid {COLOR_BORDER}",
        },
    )