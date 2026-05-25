"""Connectors pages."""

from .layout import get_detail_layout, get_layout

# Import callbacks to register them with Dash
# pylint: disable=unused-import
from . import callbacks  # noqa: F401
