"""Graph Visualization Page

This page allows users to:
- Enter and execute Cypher queries
- View graph results (nodes and relationships)
- Display tabular results for non-graph queries
"""

# Import layout
from .layout import get_layout

# Import all callbacks to register them with Dash
# pylint: disable=unused-import
from . import callbacks  # noqa: F401
