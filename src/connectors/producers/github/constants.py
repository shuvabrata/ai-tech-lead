import os
from typing import Any

_SOURCE = "github"
_VERSION = "1.0"
_TEXT_MAX = 2000


def _connector_url() -> str:
    api_server = os.environ.get("API_SERVER", "http://localhost:8000")
    return f"{api_server.rstrip('/')}/connectors/github"

def _truncate(value: Any) -> str:
    """Return *value* as a string truncated to ``_TEXT_MAX`` characters."""
    return str(value)[:_TEXT_MAX]

