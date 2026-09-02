"""Cypher parameter substitution for catalog queries loaded into the console.

When a catalog query is loaded into the query console (via "Load into Console"
or a deep link), the raw Cypher text may contain ``$param`` placeholders such
as ``$person1_id``.  The console executes the text as-is, so these placeholders
must be replaced with concrete values (or an empty string) before the query is
pasted, otherwise the query fails with an undefined-parameter error.

This module provides a small, pure helper that performs that substitution for
the parameters declared in a catalog query's ``parameters`` list.
"""

from __future__ import annotations

from typing import Any


def cypher_literal(value: str) -> str:
    """Render a string as a single-quoted, escaped Cypher string literal.

    Args:
        value: The raw string value to render.

    Returns:
        A Cypher string literal, e.g. ``'github::Person::alice'``.  Single
        quotes and backslashes are escaped so the literal is safe to embed
        directly in a Cypher query.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _extract_param_value(value: Any) -> str | None:
    """Unwrap a catalog parameter value to its raw runtime form.

    Person pickers store ``{"wba": "...", "display": "..."}`` while scalar
    parameters remain plain strings.  This mirrors the unwrapping done by
    ``_extract_param_value`` in the catalog callbacks so the helper is robust
    regardless of how the value was stored.
    """
    if isinstance(value, dict):
        wba = value.get("wba")
        return wba if isinstance(wba, str) else None
    return value if isinstance(value, str) else None


def substitute_catalog_query_parameters(
    cypher: str,
    query: dict[str, Any],
    params: dict[str, Any] | None,
) -> str:
    """Replace each declared ``$param`` in ``cypher`` with its concrete value.

    Only parameters declared in ``query["parameters"]`` are substituted; any
    other ``$`` tokens in the query are left untouched.  A parameter with no
    value (or an empty/whitespace value) is rendered as an empty string literal
    ``''`` so the pasted query remains valid Cypher.

    Args:
        cypher: The raw catalog query text (a single view's Cypher).
        query: The catalog query dict, including its ``parameters`` list.
        params: The parameter values keyed by parameter name.  Person-picker
            values may be dicts ``{"wba": ..., "display": ...}``.

    Returns:
        The ``cypher`` text with declared parameters substituted.
    """
    params = params or {}
    result = cypher
    for parameter in query.get("parameters") or []:
        name = parameter.get("name")
        if not name:
            continue
        raw = params.get(name)
        value = _extract_param_value(raw)
        if value is None or not value.strip():
            value = ""
        result = result.replace(f"${name}", cypher_literal(value))
    return result
