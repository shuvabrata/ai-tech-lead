"""Tests for graph time filter helper utilities.

Covers ``_parse_days_since_epoch``, ``_format_day_label``, and
``compute_time_range`` from ``utils/time_helpers.py``.
"""

import pytest

from app.dash_app.pages.graph.utils.time_helpers import (
    _parse_days_since_epoch,
    _format_day_label,
    compute_time_range,
)


pytestmark = pytest.mark.unit


# ── _parse_days_since_epoch ──────────────────────────────────────────────


def test_parse_days_valid_iso():
    """A known ISO 8601 string should return the correct day count."""
    # 2025-12-01T14:30:00Z → 20423 days since epoch
    result = _parse_days_since_epoch("2025-12-01T14:30:00Z")
    assert result == 20423


def test_parse_days_empty():
    """Empty string should return None."""
    assert _parse_days_since_epoch("") is None


def test_parse_days_none():
    """None should return None."""
    assert _parse_days_since_epoch(None) is None  # type: ignore[arg-type]


def test_parse_days_invalid():
    """Unparseable string should return None."""
    assert _parse_days_since_epoch("not-a-date") is None


def test_parse_days_naive_datetime():
    """Naive datetime (no timezone) should be treated as UTC."""
    result = _parse_days_since_epoch("2025-12-01T00:00:00")
    assert result == 20423


def test_parse_days_with_timezone_offset():
    """ISO string with explicit offset should be handled correctly."""
    # 2025-12-01T00:00:00+05:00 → 20422 (5 hours before UTC midnight)
    result = _parse_days_since_epoch("2025-12-01T00:00:00+05:00")
    assert result == 20422


# ── _format_day_label ────────────────────────────────────────────────────


def test_format_day_label():
    """Known days-since-epoch should produce expected formatted date."""
    # 20423 days → Dec 01, 2025
    result = _format_day_label(20423)
    assert result == "Dec 01, 2025"


def test_format_day_label_epoch():
    """Day 0 should produce Jan 01, 1970."""
    result = _format_day_label(0)
    assert result == "Jan 01, 1970"


def test_format_day_label_future():
    """Future dates should format correctly."""
    result = _format_day_label(25000)
    assert result == "Jun 13, 2038"


# ── compute_time_range ───────────────────────────────────────────────────


def _make_node(node_id, **props):
    """Build a minimal Cytoscape node element dict."""
    data = {"id": node_id, "elementType": "node", **props}
    return {"data": data}


def test_compute_time_range_with_nodes():
    """Multiple nodes with distinct dates should return correct min/max."""
    nodes = [
        _make_node("n1", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", _created_at="2025-06-01T00:00:00Z"),
        _make_node("n3", _created_at="2025-12-01T00:00:00Z"),
    ]
    min_d, max_d = compute_time_range(nodes, "_created_at")
    assert min_d == 20103  # 2025-01-15
    assert max_d == 20423  # 2025-12-01


def test_compute_time_range_no_nodes():
    """Empty node list should return (0, 1)."""
    assert compute_time_range([], "_created_at") == (0, 1)


def test_compute_time_range_no_property():
    """Nodes without the property should return (0, 1)."""
    nodes = [
        _make_node("n1", _last_updated_at="2025-06-01T00:00:00Z"),
    ]
    assert compute_time_range(nodes, "_created_at") == (0, 1)


def test_compute_time_range_mixed():
    """Nodes with and without the property — min/max from those that have it."""
    nodes = [
        _make_node("n1", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2"),  # no _created_at
        _make_node("n3", _created_at="2025-12-01T00:00:00Z"),
    ]
    min_d, max_d = compute_time_range(nodes, "_created_at")
    assert min_d == 20103
    assert max_d == 20423


def test_compute_time_range_single_node():
    """Single node should return min == max."""
    nodes = [
        _make_node("n1", _created_at="2025-06-15T00:00:00Z"),
    ]
    min_d, max_d = compute_time_range(nodes, "_created_at")
    assert min_d == max_d
    assert min_d == 20254


def test_compute_time_range_all_missing():
    """All nodes missing the property should return (0, 1)."""
    nodes = [
        _make_node("n1", other_prop="value"),
        _make_node("n2", other_prop="value2"),
    ]
    assert compute_time_range(nodes, "_created_at") == (0, 1)


def test_compute_time_range_unparseable_skipped():
    """Nodes with unparseable date values should be skipped."""
    nodes = [
        _make_node("n1", _created_at="2025-06-01T00:00:00Z"),
        _make_node("n2", _created_at="not-a-date"),
    ]
    min_d, max_d = compute_time_range(nodes, "_created_at")
    assert min_d == 20240
    assert max_d == 20240
