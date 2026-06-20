"""Unit tests for the person autocomplete combobox feature.

Tests cover:
- _build_person_picker returns a dbc.Input (not dcc.Dropdown)
- Chip area, search area, debounce store, value store all present
- render_catalog_query_detail routes person_id type to the picker
- render_catalog_query_detail still uses dbc.Input for other types
- sync_person_parameter_values merges/clears into parameters store
- sync_person_suggestions returns empty for query < 3 chars
- sync_person_suggestions calls /api/v1/search/persons and builds Button items
- handle_person_pick returns chip content, hides search area, stores wba_id
- handle_person_chip_clear resets chip, restores search area, clears value
- persons_router._extract_name fallback chain
- persons_router._build_suggestion field extraction

Run with:
    pytest -m unit tests/test_person_autocomplete.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from dash import dcc, html
import dash_bootstrap_components as dbc

from app.dash_app.pages.graph.callbacks import catalog as catalog_callbacks
from app.api.search.v1 import persons_router


pytestmark = pytest.mark.unit


# ===========================================================================
# Helpers
# ===========================================================================


def _find_component_by_type(children, component_type):
    """Recursively find the first component of the given type in children."""
    if isinstance(children, component_type):
        return children
    kids = getattr(children, "children", None)
    if kids is None:
        return None
    if isinstance(kids, list):
        for child in kids:
            found = _find_component_by_type(child, component_type)
            if found is not None:
                return found
    else:
        return _find_component_by_type(kids, component_type)
    return None


def _find_components_by_type(children, component_type, results=None):
    """Recursively collect ALL components of the given type."""
    if results is None:
        results = []
    if isinstance(children, component_type):
        results.append(children)
    kids = getattr(children, "children", None)
    if isinstance(kids, list):
        for child in kids:
            _find_components_by_type(child, component_type, results)
    elif kids is not None:
        _find_components_by_type(kids, component_type, results)
    return results


def _find_component_by_id_type(root, id_type: str):
    """Recursively find first component whose id dict has type == id_type."""
    comp_id = getattr(root, "id", None)
    if isinstance(comp_id, dict) and comp_id.get("type") == id_type:
        return root
    kids = getattr(root, "children", None)
    if isinstance(kids, list):
        for child in kids:
            found = _find_component_by_id_type(child, id_type)
            if found is not None:
                return found
    elif kids is not None:
        return _find_component_by_id_type(kids, id_type)
    return None


def _flatten_text(value):
    """Recursively extract all string leaves from a Dash component tree."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        texts = []
        for child in value:
            texts.extend(_flatten_text(child))
        return texts
    children = getattr(value, "children", None)
    if isinstance(children, (list, tuple)):
        texts = []
        for child in children:
            texts.extend(_flatten_text(child))
        return texts
    if children is not None:
        return _flatten_text(children)
    return []


# ===========================================================================
# _build_person_picker — structure tests
# ===========================================================================


def test_build_person_picker_contains_text_input():
    """`_build_person_picker` must use a dbc.Input (not dcc.Dropdown)."""
    parameter = {"name": "person1_id", "required": True, "label": "First person", "type": "person_id"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    assert isinstance(result, html.Div)
    # Must NOT contain a dcc.Dropdown
    dropdown = _find_component_by_type(result, dcc.Dropdown)
    assert dropdown is None, "dcc.Dropdown must NOT be used in the new combobox"
    # Must contain a dbc.Input
    text_input = _find_component_by_type(result, dbc.Input)
    assert text_input is not None, "Expected a dbc.Input in the combobox"


def test_build_person_picker_input_id_uses_parameter_name():
    """The dbc.Input id must be the pattern-matching dict {type: catalog-person-input, name}."""
    parameter = {"name": "person2_id", "required": False, "label": "Second person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    text_input = _find_component_by_id_type(result, "catalog-person-input")
    assert text_input is not None
    assert text_input.id == {"type": "catalog-person-input", "name": "person2_id"}


def test_build_person_picker_has_suggestions_panel():
    """The picker must include a suggestions panel div."""
    parameter = {"name": "person1_id", "required": True, "label": "First person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    suggestions = _find_component_by_id_type(result, "catalog-person-suggestions")
    assert suggestions is not None
    assert suggestions.id == {"type": "catalog-person-suggestions", "name": "person1_id"}


def test_build_person_picker_has_chip_area():
    """The picker must include a chip area div (initially hidden)."""
    parameter = {"name": "person1_id", "required": True, "label": "First person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    chip = _find_component_by_id_type(result, "catalog-person-chip")
    assert chip is not None
    assert chip.style.get("display") == "none"


def test_build_person_picker_has_value_store():
    """The picker must embed a catalog-person-value dcc.Store."""
    parameter = {"name": "person1_id", "required": True, "label": "First person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    value_store = _find_component_by_id_type(result, "catalog-person-value")
    assert value_store is not None
    assert isinstance(value_store, dcc.Store)
    assert value_store.data is None


def test_build_person_picker_has_debounce_store():
    """The picker must embed a catalog-person-debounce dcc.Store."""
    parameter = {"name": "person1_id", "required": True, "label": "First person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    debounce_store = _find_component_by_id_type(result, "catalog-person-debounce")
    assert debounce_store is not None
    assert isinstance(debounce_store, dcc.Store)


def test_build_person_picker_label_shows_asterisk_for_required():
    """Required pickers must show an asterisk in the label."""
    parameter = {"name": "person1_id", "required": True, "label": "First person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    texts = _flatten_text(result)
    assert any("*" in t for t in texts), "Required picker label must contain '*'"


def test_build_person_picker_no_asterisk_for_optional():
    """Optional pickers must NOT show an asterisk."""
    parameter = {"name": "person1_id", "required": False, "label": "Some person"}
    result = catalog_callbacks._build_person_picker(parameter, current_value=None)

    label = result.children[0]  # First child is the Label
    assert "*" not in label.children


# ===========================================================================
# render_catalog_query_detail — person_id type routing
# ===========================================================================


def _make_p2p_query(parameter_type: str = "person_id") -> dict:
    return {
        "id": "person_to_person/direct_code_reviews",
        "name": "Direct Code Reviews",
        "description": "Review collaboration.",
        "summary": "Compare two people by code review.",
        "namespace": {"name": "Person-to-Person", "directory": "person_to_person"},
        "available_views": ["tabular", "graph"],
        "default_view": "tabular",
        "parameters": [
            {
                "name": "person1_id",
                "required": True,
                "label": "First person",
                "type": parameter_type,
                "placeholder": "e.g. github::Person::alice",
                "description": "WBA canonical Person ID.",
                "env_var": "PERSON1_ID",
            }
        ],
        "tags": ["people"],
        "owner": "graph-team",
        "status": "active",
    }


def test_render_catalog_query_detail_uses_input_for_person_id_type():
    """Parameters with type='person_id' must render a dbc.Input combobox, not dcc.Dropdown."""
    catalog_query = _make_p2p_query(parameter_type="person_id")

    _, _, _, parameter_children = catalog_callbacks.render_catalog_query_detail(
        selected_query={"id": "person_to_person/direct_code_reviews"},
        catalog_queries=[catalog_query],
        theme_name=None,
        parameter_values={},
        current_view=None,
    )

    assert len(parameter_children) >= 1
    first_param_block = parameter_children[0]

    text_input = _find_component_by_id_type(first_param_block, "catalog-person-input")
    dropdown = _find_component_by_type(first_param_block, dcc.Dropdown)

    assert text_input is not None, "Expected catalog-person-input for person_id parameter"
    assert dropdown is None, "Must NOT render dcc.Dropdown for person_id parameter"


def test_render_catalog_query_detail_uses_input_for_non_person_id_type():
    """Parameters without type='person_id' must still render as a plain dbc.Input (not combobox)."""
    catalog_query = _make_p2p_query(parameter_type="node_id")

    _, _, _, parameter_children = catalog_callbacks.render_catalog_query_detail(
        selected_query={"id": "person_to_person/direct_code_reviews"},
        catalog_queries=[catalog_query],
        theme_name=None,
        parameter_values={},
        current_view=None,
    )

    assert len(parameter_children) >= 1
    first_param_block = parameter_children[0]

    # Should have a plain dbc.Input (the catalog-parameter-input, NOT catalog-person-input)
    inputs = _find_components_by_type(first_param_block, dbc.Input)
    assert len(inputs) > 0

    # Should NOT have a catalog-person-input (the combobox variant)
    person_input = _find_component_by_id_type(first_param_block, "catalog-person-input")
    assert person_input is None, "Must NOT render person combobox for non-person_id parameter"


def test_render_catalog_query_detail_run_disabled_when_no_person_selected():
    """Run button must be disabled when a required person_id has no value."""
    catalog_query = _make_p2p_query(parameter_type="person_id")

    # update_run_button_state is the dedicated callback for button disabled state
    run_disabled, _ = catalog_callbacks.update_run_button_state(
        parameter_values={},
        selected_query={"id": "person_to_person/direct_code_reviews"},
        catalog_queries=[catalog_query],
        current_view="graph",
    )

    assert run_disabled is True


def test_render_catalog_query_detail_run_enabled_when_person_value_present():
    """Run button must be enabled when the required person_id field has a wba_id value."""
    catalog_query = _make_p2p_query(parameter_type="person_id")

    run_disabled, _ = catalog_callbacks.update_run_button_state(
        parameter_values={"person1_id": "github::Person::alice"},
        selected_query={"id": "person_to_person/direct_code_reviews"},
        catalog_queries=[catalog_query],
        current_view="graph",
    )

    assert run_disabled is False


# ===========================================================================
# sync_person_parameter_values
# ===========================================================================


def test_sync_person_parameter_values_merges_selection_into_store():
    """A selected wba_id must be written into catalog-parameters-store."""
    result = catalog_callbacks.sync_person_parameter_values(
        values=["github::Person::alice", None],
        ids=[
            {"type": "catalog-person-value", "name": "person1_id"},
            {"type": "catalog-person-value", "name": "person2_id"},
        ],
        current_params={"other_param": "existing_value"},
    )

    assert result["person1_id"] == "github::Person::alice"
    assert result["other_param"] == "existing_value"
    assert "person2_id" not in result


def test_sync_person_parameter_values_clears_on_deselect():
    """Clearing the value (None) removes the key from the store."""
    result = catalog_callbacks.sync_person_parameter_values(
        values=[None],
        ids=[{"type": "catalog-person-value", "name": "person1_id"}],
        current_params={"person1_id": "github::Person::alice"},
    )

    assert "person1_id" not in result


def test_sync_person_parameter_values_handles_empty_ids():
    """Empty input lists must return the current params unchanged."""
    current = {"person1_id": "github::Person::alice"}
    result = catalog_callbacks.sync_person_parameter_values(
        values=[], ids=[], current_params=current,
    )
    assert result == current


def test_sync_person_parameter_values_initialises_empty_store():
    """When current_params is None, result must be a fresh dict."""
    result = catalog_callbacks.sync_person_parameter_values(
        values=["github::Person::bob"],
        ids=[{"type": "catalog-person-value", "name": "person1_id"}],
        current_params=None,
    )
    assert result == {"person1_id": "github::Person::bob"}


# ===========================================================================
# sync_person_suggestions (replaces sync_person_search_options)
# ===========================================================================


def test_sync_person_suggestions_returns_empty_for_short_query():
    """Queries shorter than 3 chars must return empty children and hidden style."""
    children, styles = catalog_callbacks.sync_person_suggestions(
        debounced_queries=["ab", None],
        debounce_ids=[
            {"type": "catalog-person-debounce", "name": "person1_id"},
            {"type": "catalog-person-debounce", "name": "person2_id"},
        ],
    )
    assert children == [[], []]
    assert all(s.get("display") == "none" for s in styles)


def test_sync_person_suggestions_returns_empty_for_none_query():
    """None query values must return empty children and hidden style."""
    children, styles = catalog_callbacks.sync_person_suggestions(
        debounced_queries=[None],
        debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
    )
    assert children == [[]]
    assert styles[0].get("display") == "none"


def test_sync_person_suggestions_calls_persons_api_for_valid_query():
    """A query >= 3 chars must trigger a GET /api/v1/search/persons call."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "wba_id": "github::Person::alice",
                "name": "Alice Smith",
                "email": "alice@example.com",
                "source": "github",
                "login": "alice",
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.dash_app.pages.graph.callbacks.catalog.requests.get") as mock_get:
        mock_get.return_value = mock_response
        children, styles = catalog_callbacks.sync_person_suggestions(
            debounced_queries=["alice"],
            debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
        )

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    assert "persons" in call_kwargs[0][0]
    assert call_kwargs[1]["params"]["q"] == "alice"

    assert len(children[0]) == 1
    suggestion_button = children[0][0]
    assert suggestion_button.id.get("wba") == "github::Person::alice"


def test_sync_person_suggestions_renders_buttons_with_correct_id():
    """Suggestion items must be html.Button components with the correct ID structure."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "wba_id": "github::Person::alice",
                "name": "Alice Smith",
                "email": "alice@example.com",
                "source": "github",
                "login": "alice",
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.dash_app.pages.graph.callbacks.catalog.requests.get") as mock_get:
        mock_get.return_value = mock_response
        children, _ = catalog_callbacks.sync_person_suggestions(
            debounced_queries=["alice"],
            debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
        )

    button = children[0][0]
    assert isinstance(button, html.Button)
    assert button.id["type"] == "catalog-person-pick"
    assert button.id["name"] == "person1_id"
    assert button.id["wba"] == "github::Person::alice"
    assert button.id["display"] == "Alice Smith"


def test_sync_person_suggestions_shows_no_results_message():
    """When API returns 0 results, show a 'no results' message in the panel."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    with patch("app.dash_app.pages.graph.callbacks.catalog.requests.get") as mock_get:
        mock_get.return_value = mock_response
        children, styles = catalog_callbacks.sync_person_suggestions(
            debounced_queries=["xyznotfound"],
            debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
        )

    # Panel is visible but shows a "no results" message
    assert styles[0].get("display") != "none" or styles[0].get("display") == "block"
    # The children should contain a message element (not buttons)
    assert len(children[0]) > 0
    msg_texts = _flatten_text(children[0])
    assert any("No people found" in t or "try" in t.lower() for t in msg_texts)


def test_sync_person_suggestions_falls_back_gracefully_on_api_error():
    """API errors must not raise — they must return an error message in the panel."""
    import requests as req_lib

    with patch("app.dash_app.pages.graph.callbacks.catalog.requests.get") as mock_get:
        mock_get.side_effect = req_lib.exceptions.RequestException("connection refused")
        children, styles = catalog_callbacks.sync_person_suggestions(
            debounced_queries=["alice"],
            debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
        )

    assert len(children) == 1
    assert len(styles) == 1
    # Should show an error message, not raise
    msg_texts = _flatten_text(children[0])
    assert any("fail" in t.lower() or "connection" in t.lower() for t in msg_texts)


def test_sync_person_suggestions_handles_person_without_email():
    """A person with no email must still produce a valid suggestion button."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "wba_id": "github::Person::bob",
                "name": "Bob Smith",
                "email": None,
                "source": "github",
                "login": "bob",
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.dash_app.pages.graph.callbacks.catalog.requests.get") as mock_get:
        mock_get.return_value = mock_response
        children, _ = catalog_callbacks.sync_person_suggestions(
            debounced_queries=["bob"],
            debounce_ids=[{"type": "catalog-person-debounce", "name": "person1_id"}],
        )

    assert len(children[0]) == 1
    button = children[0][0]
    assert button.id["wba"] == "github::Person::bob"
    # Falls back to @login in the detail text
    detail_texts = _flatten_text(button)
    assert any("bob" in t.lower() for t in detail_texts)


# ===========================================================================
# persons_router unit tests
# ===========================================================================


def test_extract_name_prefers_full_name():
    assert persons_router._extract_name({"full_name": "Alice Smith", "login": "alice"}) == "Alice Smith"


def test_extract_name_falls_back_to_name():
    assert persons_router._extract_name({"name": "Alice Smith", "login": "alice"}) == "Alice Smith"


def test_extract_name_falls_back_to_login():
    assert persons_router._extract_name({"login": "alice"}) == "alice"


def test_extract_name_falls_back_to_wba_id():
    assert persons_router._extract_name({"wba_id": "github::Person::alice"}) == "github::Person::alice"


def test_extract_name_returns_unknown_when_all_missing():
    assert persons_router._extract_name({}) == "Unknown"


def test_build_suggestion_returns_correct_person_suggestion():
    """_build_suggestion maps SearchResult attributes to PersonSuggestion correctly."""
    from app.api.search.v1.model import SearchResult

    result = SearchResult(
        wba_id="github::Person::alice",
        score=10.0,
        url=None,
        event_time=None,
        highlight=None,
        attributes={
            "full_name": "Alice Smith",
            "login": "alice",
            "email": "alice@example.com",
            "source": "github",
        },
    )
    suggestion = persons_router._build_suggestion(result)

    assert suggestion is not None
    assert suggestion.wba_id == "github::Person::alice"
    assert suggestion.name == "Alice Smith"
    assert suggestion.email == "alice@example.com"
    assert suggestion.source == "github"
    assert suggestion.login == "alice"


def test_build_suggestion_derives_source_from_wba_id_when_missing():
    """When 'source' is absent from attributes, derive it from the wba_id prefix."""
    from app.api.search.v1.model import SearchResult

    result = SearchResult(
        wba_id="jira::Person::abc123",
        score=5.0,
        attributes={
            "full_name": "Jira User",
            "login": "jira_user",
        },
    )
    suggestion = persons_router._build_suggestion(result)

    assert suggestion is not None
    assert suggestion.source == "jira"


def test_build_suggestion_handles_null_email():
    """Email can be None — suggestion must still be returned."""
    from app.api.search.v1.model import SearchResult

    result = SearchResult(
        wba_id="github::Person::bob",
        score=3.0,
        attributes={
            "full_name": "Bob Jones",
            "login": "bob",
            "email": None,
            "source": "github",
        },
    )
    suggestion = persons_router._build_suggestion(result)

    assert suggestion is not None
    assert suggestion.email is None
