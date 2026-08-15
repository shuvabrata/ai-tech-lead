"""Settings pages."""

from .layout import get_layout
from .runtime import get_runtime_layout

# Import callbacks to register them with Dash
# pylint: disable=unused-import
from . import callbacks  # noqa: F401
from . import runtime  # noqa: F401

__all__ = ["get_layout", "get_runtime_layout"]