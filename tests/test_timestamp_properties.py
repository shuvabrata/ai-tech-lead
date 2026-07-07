"""Integration tests for timestamp property validity in Neo4j.

Verifies that all ``_created_at``, ``_last_updated_at``, and ``_last_seen_at``
property values stored on Neo4j nodes can be parsed as Python ``datetime``
objects.  The values may be stored as native Neo4j types (``Date``,
``DateTime``) or as ISO-8601 strings — the test accepts any representation
as long as Python can convert it.

Run with::

    pytest tests/test_timestamp_properties.py -m neo4j -v
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from neo4j import GraphDatabase

from app.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.neo4j]


TIMESTAMP_PROPS = ("_created_at", "_last_updated_at", "_last_seen_at")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def neo4j_driver() -> GraphDatabase.driver:
    """Create a Neo4j driver using application settings."""
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    try:
        driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Cannot connect to Neo4j: {exc}")
    yield driver
    driver.close()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_datetime(val: object) -> datetime:
    """Convert a Neo4j property value to a Python ``datetime``.

    Accepts:
    - Native ``neo4j.time.DateTime`` (a ``datetime`` subclass)
    - Native ``neo4j.time.Date``
    - Plain ISO-8601 ``str``
    - Anything else with a ``to_native()`` method

    Raises ``ValueError`` (or ``TypeError``) when conversion fails.
    """
    if val is None:
        raise ValueError("value is None")

    # neo4j.time.DateTime is a subclass of datetime.datetime
    if isinstance(val, datetime):
        return val

    # neo4j.time.Date → combine with midnight
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())

    # Plain ISO string
    if isinstance(val, str):
        return datetime.fromisoformat(val)

    # Fallback: try to_native() then recurse
    native = val.to_native() if hasattr(val, "to_native") else val
    if native is not val:
        return _to_datetime(native)

    raise TypeError(f"Cannot convert {type(val).__name__} to datetime")


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)",
)
class TestTimestampValidity:
    """Validate that all timestamp properties are convertible to Python datetime."""

    @pytest.mark.parametrize("prop", TIMESTAMP_PROPS)
    def test_all_timestamps_convertible(self, neo4j_driver, prop: str) -> None:
        """Every non-null ``{prop}`` value must be convertible to ``datetime``."""
        query = (
            f"MATCH (n) WHERE n.{prop} IS NOT NULL "
            f"RETURN labels(n)[0] AS label, n.id AS id, n.{prop} AS value"
        )

        failures: list[str] = []

        with neo4j_driver.session() as session:
            result = session.run(query)
            for record in result:
                val = record["value"]
                node_id = record.get("id", "?")
                label = record.get("label", "?")
                try:
                    _to_datetime(val)
                except (ValueError, TypeError, OverflowError) as exc:
                    failures.append(
                        f"  {label} id={node_id}: {val!r} "
                        f"(type={type(val).__name__}) → {exc}"
                    )

        total = len(failures)
        if total:
            sample = "\n".join(failures[:10])
            pytest.fail(
                f"{total} timestamp(s) in '{prop}' are not valid "
                f"Python datetime(s):\n{sample}"
            )

    def test_count_timestamps_by_type(self, neo4j_driver) -> None:
        """Report the type distribution of timestamp properties (informational)."""
        lines: list[str] = []
        with neo4j_driver.session() as session:
            for prop in TIMESTAMP_PROPS:
                result = session.run(
                    f"MATCH (n) WHERE n.{prop} IS NOT NULL "
                    f"RETURN n.{prop} AS val"
                )
                counts: dict[str, int] = {}
                for record in result:
                    t = type(record["val"]).__name__
                    counts[t] = counts.get(t, 0) + 1
                total = sum(counts.values())
                parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                lines.append(f"  {prop}: {total} total [{parts}]")
        print("\n" + "\n".join(lines))