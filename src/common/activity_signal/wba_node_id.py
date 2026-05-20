"""WBA canonical node ID helpers.

Shared by both producers (when constructing ``ActivitySignal.id`` /
``external_id`` values) and consumers (when resolving Neo4j node IDs from
incoming signals).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.activity_signal.models import ActivitySignal


def wba_format(source: str, entity_type: str, id: str) -> str:
    """Return the WBA canonical node ID string: ``{source}::{entity_type}::{id}``."""
    return f"{source}::{entity_type}::{id}"


def wba_node_id(signal: "ActivitySignal") -> str:
    """Return the WBA canonical node ID for a signal.

    Returns ``{source}::{entity_type}::{id}`` when ``signal.id`` is set.
    Falls back to ``signal.external_id`` for backward compatibility during
    the migration period (Phases 1–12).  The fallback is removed in Phase 13.
    """
    if signal.id:
        return wba_format(signal.source, signal.entity_type, signal.id)
    return signal.external_id
