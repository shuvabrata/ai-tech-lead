"""Setup banner — nudges users to configure recommended settings.

A subtle, dismissable banner that appears on every page when recommended
settings (e.g. OpenAI API key, GitHub MCP token) are not yet configured.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from dash import Input, Output, State, callback, dcc, html

from app.dash_app.styles import (
    COLOR_NAVY,
    FONT_WEIGHT_MEDIUM,
)

SETTINGS_API = os.getenv("API_BASE_URL", "http://localhost:8000") + "/api/v1/settings/"


def get_banner_layout() -> html.Div:
    """Return the banner container and its supporting stores."""
    return html.Div([
        dcc.Store(id="banner-dismissed", data=False, storage_type="session"),
        html.Div(id="setup-banner"),
    ])


@callback(
    Output("setup-banner", "children"),
    Input("url", "pathname"),
    Input("banner-dismissed", "data"),
)
def render_setup_banner(pathname: str, dismissed: bool) -> Any:
    """Fetch settings and render a banner for unconfigured recommended settings."""
    _ = pathname  # triggers on navigation; content depends only on settings
    if dismissed:
        return None

    try:
        resp = requests.get(SETTINGS_API, timeout=10)
        resp.raise_for_status()
        settings_list: list[dict[str, Any]] = resp.json()
    except requests.exceptions.RequestException:
        # If the settings API is unreachable, silently skip the banner.
        return None

    # Find recommended settings that are not configured.
    unconfigured: list[str] = []
    for s in settings_list:
        if s.get("importance") == "recommended" and not s.get("is_configured", True):
            unconfigured.append(s["key"])

    if not unconfigured:
        return None

    # Build human-readable labels for the unconfigured keys.
    labels: dict[str, str] = {
        "OPENAI_API_KEY": "OpenAI API key",
        "GITHUB_MCP_TOKEN": "GitHub MCP token",
    }
    names = [labels.get(k, k) for k in unconfigured]

    count = len(unconfigured)
    if count == 1:
        text = f"{names[0]} is not configured."
    else:
        text = f"{', '.join(names[:-1])} and {names[-1]} are not configured."

    return html.Div(
        [
            html.Span(
                f"⚠️  {text}  ",
                style={"flex": 1},
            ),
            html.A(
                "Configure now →",
                href="/app/settings/runtime",
                style={
                    "color": COLOR_NAVY,
                    "textDecoration": "underline",
                    "fontWeight": FONT_WEIGHT_MEDIUM,
                    "whiteSpace": "nowrap",
                    "marginRight": "16px",
                },
            ),
            html.Span(
                "×",
                id="banner-dismiss-btn",
                n_clicks=0,
                className="setup-banner-dismiss",
            ),
        ],
        className="setup-banner",
    )


@callback(
    Output("banner-dismissed", "data"),
    Input("banner-dismiss-btn", "n_clicks"),
    prevent_initial_call=True,
)
def dismiss_banner(n_clicks: int) -> bool:
    """Persist banner dismissal for the session."""
    if n_clicks:
        return True
    return False