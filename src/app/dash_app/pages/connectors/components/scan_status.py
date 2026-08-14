"""Scan status component for connector detail pages.

Renders a single scan command row with status icon, timestamp, duration,
and result summary.
"""

import json
from datetime import datetime

from dash import html
import dash_bootstrap_components as dbc

from app.common.timezone import humanize_duration, to_app_timezone
from app.settings import settings
from app.dash_app.styles import (
    COLOR_BORDER,
    COLOR_ERROR,
    COLOR_GRAY_MEDIUM,
    COLOR_INFO,
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
    "cancelled": {
        "icon": "fa-regular fa-circle-stop",
        "color": COLOR_INFO,
        "label": "Cancelled",
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
    """Render a single scan command row with labeled timestamps and details.

    Args:
        command: A ``CommandResponse`` dict from the API.

    Returns:
        An ``html.Div`` with status icon, labeled timestamps, duration,
        error message, and result summary.
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
    result_summary = command.get("result_summary")

    # Duration calculation — only when the scan has finished
    start_dt = command.get("started_at")
    end_dt = command.get("completed_at")
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

    # Build labeled details rows
    detail_parts = []

    def _labeled_time(label: str, value: str | None) -> str | None:
        if value:
            return f"{label}: {value}"
        return None

    detail_parts.append(_labeled_time("Created", created_str))
    detail_parts.append(_labeled_time("Started", started_str))
    detail_parts.append(_labeled_time("Completed", completed_str))
    detail_parts.append(f"Duration: {duration_text}" if duration_text else None)

    # Build detail line from text parts, then append the error segment
    # separately so it can be styled in red when there's a real error.
    detail_prefix = " | ".join(p for p in detail_parts if p is not None)

    has_error = bool(error_message)
    error_part = html.Span(
        f"Error: {error_message}" if has_error else "Error: None",
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_XSMALL,
            "color": COLOR_ERROR if has_error else COLOR_GRAY_MEDIUM,
        },
    )

    command_id = str(command.get("command_id", ""))

    # Raw result_summary hover — expose the full JSON for any scan result
    # that carries one (completed, failed, cancelled, test, etc.).
    raw_summary_part: list = []
    if result_summary is not None:
        tooltip_id = f"scan-summary-json-{command_id}"
        try:
            raw_json = json.dumps(result_summary, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            raw_json = str(result_summary)
        raw_summary_part = [
            html.I(
                className="fas fa-code",
                id=tooltip_id,
                style={
                    "cursor": "help",
                    "marginLeft": SPACING_XSMALL,
                    "color": COLOR_INFO,
                    "fontSize": FONT_SIZE_XSMALL,
                },
            ),
            dbc.Popover(
                dbc.PopoverBody(
                    html.Pre(
                        raw_json,
                        style={
                            "fontFamily": "monospace",
                            "fontSize": "11px",
                            "margin": "0",
                            "whiteSpace": "pre-wrap",
                            "wordBreak": "break-word",
                        },
                    )
                ),
                target=tooltip_id,
                trigger="hover focus",
                placement="auto",
                style={"maxWidth": "560px"},
            ),
        ]

    # Combine prefix and error into a single line
    detail_line = html.Span(
        [detail_prefix + " | ", error_part] + raw_summary_part
        if detail_prefix
        else [error_part] + raw_summary_part,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_XSMALL,
            "color": COLOR_GRAY_MEDIUM,
        },
    )

    # Command type badge — distinguish scan, cancel, test actions
    command_type = command.get("command_type", "scan")
    type_badge = html.Span()
    if command_type == "test":
        type_badge = html.Span(
            "[TEST]",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_INFO,
                "fontWeight": "600",
                "marginRight": SPACING_XSMALL,
            },
        )
    elif command_type == "cancel":
        type_badge = html.Span(
            "[CANCEL]",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_WARNING,
                "fontWeight": "600",
                "marginRight": SPACING_XSMALL,
            },
        )
    else:
        type_badge = html.Span(
            "[SCAN]",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "fontWeight": "600",
                "marginRight": SPACING_XSMALL,
            },
        )

    cancel_button = html.Div()
    if status in ("running", "accepted"):
        cancel_button = dbc.Button(
            "Cancel",
            id={"type": "connector-cancel-scan", "command_id": command_id},
            color="warning",
            size="sm",
            className="ms-2",
            style={"fontSize": "11px", "padding": "1px 6px"},
        )

    return html.Div(
        [
            html.Div(
                [
                    html.I(
                        className=cfg["icon"],
                        style={
                            "color": cfg["color"],
                            "marginRight": SPACING_XSMALL,
                            "width": "16px",
                            "textAlign": "center",
                            "flexShrink": 0,
                        },
                    ),
                    html.Span(
                        cfg["label"],
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": cfg["color"],
                            "fontWeight": "500",
                            "marginRight": SPACING_XSMALL,
                            "flexShrink": 0,
                        },
                    ),
                    type_badge,
                    detail_line,
                ],
                style={"display": "flex", "alignItems": "center", "flex": "1"},
            ),
            cancel_button,
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "flexWrap": "wrap",
            "gap": SPACING_XXXSMALL,
            "padding": f"{SPACING_XSMALL} {SPACING_SMALL}",
            "borderBottom": f"1px solid {COLOR_BORDER}",
        },
    )