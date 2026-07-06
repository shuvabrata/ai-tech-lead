"""Common base for all Neo4j node dataclasses in models.py.

Provides the three always-present, computed display/time properties:
_display_name, _on_hover_name, _last_updated_at. These are
never stored as redundant dataclass fields — they are derived from each
subclass's own existing fields and materialize only as dict keys inside
to_neo4j_properties(), where they become real, queryable Neo4j properties.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any, Dict, Optional


def _get_field(obj: object, name: str) -> Optional[str]:
    """Return the string value of a dataclass field, or None.

    Uses getattr but only returns the value if it is a non-callable string
    (i.e. an actual data field, not a method/property override).  This
    prevents a subclass method from being picked up as a field value.
    """
    value = getattr(obj, name, None)
    if value is None:
        return None
    if callable(value):
        return None
    if isinstance(value, str) and value:
        return value
    return None


class GraphNode(ABC):
    """Mixin enforcing common identity/display/time metadata on node dataclasses."""

    id: str
    url: str

    def display_name(self) -> str:
        """Default: first non-empty of name/title/summary/key, else id.

        Override for node types needing custom composition (e.g. PullRequest).
        """
        for attr in ("name", "title", "summary", "key"):
            value = _get_field(self, attr)
            if value:
                return str(value)
        return self.id

    def on_hover_name(self) -> str:
        """Default: same as display_name(). Override for a richer tooltip."""
        return self.display_name()

    def last_seen_at(self) -> Optional[str]:
        """The timestamp of when this node was last synced.

        Returns _last_synced_at if the subclass defines it, else None.
        This value is NOT stored as a separate Neo4j property — it is
        written directly as _last_synced_at (which will be renamed to
        _last_seen_at in a future pass).
        """
        return _get_field(self, "_last_synced_at")

    def _calc_last_updated_at(self) -> Optional[str]:
        """Default: first non-empty of updated_at/last_updated_at, else None.

        Override for immutable entities (e.g. Commit -> created_at).

        NOTE: This is intentionally prefixed with ``_calc_`` to avoid name
        collision with dataclass fields like ``last_updated_at`` that several
        subclasses declare.
        """
        for attr in ("updated_at", "last_updated_at"):
            value = _get_field(self, attr)
            if value:
                return str(value)
        return None

    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Default to_neo4j_properties(): asdict() + the 3 computed keys.

        Subclasses with custom filtering (e.g. dropping empty lists) should
        call this via super() and layer their own filtering on top, or
        replicate the same 4-key injection if they can't call super() cleanly.
        """
        props = {k: v for k, v in asdict(self).items() if v is not None}
        self._inject_computed_properties(props)
        return props

    def _inject_computed_properties(self, props: Dict[str, Any]) -> None:
        """Inject _display_name, _on_hover_name, _last_updated_at in-place.

        Uses type(self) to resolve methods at class-level, avoiding name collision
        between dataclass fields and methods that share the same name (e.g. a
        ``last_updated_at`` field and the ``last_updated_at()`` method).
        """
        cls = type(self)
        props["_display_name"] = cls.display_name(self)
        props["_on_hover_name"] = cls.on_hover_name(self)
        last_updated = cls._calc_last_updated_at(self)  # pylint: disable=protected-access
        if last_updated is not None:
            props["_last_updated_at"] = last_updated

    @abstractmethod
    def print_cli(self) -> None:
        """Every node type must implement its own CLI pretty-printer (existing convention)."""