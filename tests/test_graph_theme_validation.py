"""Unit tests for override-document validation.

Covers rejection of invalid hex colours, unknown shapes, and non-positive
dimensions when parsing raw override documents.
"""

import pytest

from app.common.graph_theme import parse_overrides

pytestmark = pytest.mark.unit

RAW_MINIMAL = {"nodes": {}, "edges": {}, "global": {}}


def test_parse_empty_doc_ok():
    """An empty override doc parses cleanly into empty defaults."""
    parsed = parse_overrides({})
    assert parsed.nodes == {}
    assert parsed.edges.line_color is None
    assert parsed.global_.selection_color is None


def test_parse_none_ok():
    """None parses to empty defaults."""
    parsed = parse_overrides(None)
    assert parsed.nodes == {}


def test_reject_invalid_hex_color():
    """A non-hex colour string is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"color": "red"}}})


def test_reject_malformed_hex():
    """A structurally invalid hex (non-hex digits) is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"color": "#GGG"}}})


def test_reject_short_color():
    """Too-short hex codes are rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"color": "#FF"}}})


def test_reject_unknown_shape():
    """An unsupported shape is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"shape": "blob"}}})


def test_reject_negative_width():
    """Negative width is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"width": -5}}})


def test_reject_zero_height():
    """Zero height is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"height": 0}}})


def test_reject_non_int_width():
    """Non-integer dimensions are rejected.

    Pydantic raises ``ValidationError`` (a ``ValueError`` subclass) for a
    non-integer width.
    """
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Person": {"width": "big"}}})


def test_reject_unknown_node_type():
    """An unknown node type key is rejected."""
    with pytest.raises(ValueError):
        parse_overrides({"nodes": {"Unicorn": {"color": "#00FF00"}}})


def test_accept_valid_full_doc():
    """A well-formed override document parses without error."""
    parsed = parse_overrides(
        {
            "nodes": {
                "Person": {
                    "color": "#00FF00",
                    "border": "#008800",
                    "border_width": 2,
                    "shape": "diamond",
                    "width": 80,
                    "height": 60,
                },
                "default": {"color": "#CCCCCC"},
            },
            "edges": {"line_color": "#999999", "width": 3,
                      "arrow_shape": "triangle", "label_color": "#666666"},
            "global": {"node_label_color": "#FFFFFF",
                       "selection_color": "#FFAA00",
                       "edge_label_background": "#222222"},
        }
    )
    person = parsed.nodes["Person"]
    assert person.color == "#00FF00"
    assert person.shape == "diamond"
    assert person.width == 80
    assert person.border_width == 2
    assert parsed.nodes["default"].color == "#CCCCCC"
    assert parsed.edges.line_color == "#999999"
    assert parsed.edges.arrow_shape == "triangle"


def test_accept_in_use_snake_global_none():
    """Valid edge/global present; unset remain None."""
    parsed = parse_overrides(
        {"edges": {"line_color": "#888888"}, "global": {"selection_color": "#111111"}}
    )
    assert parsed.edges.width is None
    assert parsed.global_.node_label_color is None
    assert parsed.global_.selection_color == "#111111"