"""Smoke tests for Dash layout callback registration.

Guards against accidental drops of Output declarations — a class of silent bug
where a callback is registered with Inputs but no Output, leaving the feature
broken with no runtime error and no exception raised at startup.

Pattern: Dash stores all registered callback outputs in ``app.callback_map``.
For single-output callbacks the key is ``"component_id.prop"``.  For
multi-output callbacks Dash serialises all outputs into one composite key
(format is internal and can change between Dash versions).  To stay resilient
across Dash upgrades every assertion uses ``_has_output`` which searches for
``"component_id.prop"`` as a *substring* of any registered key — meaning it
works regardless of how Dash formats multi-output keys.

How to use when a test fails
-----------------------------
1. The test docstring names the callback function and the feature it guards.
2. Find that function in ``src/app/dash_app/layout.py``.
3. Verify its ``@app.callback(...)`` decorator still contains the expected
   ``Output(...)`` argument — it was likely dropped during an edit or a
   string-replacement refactor.
4. Restore the missing ``Output`` line.

Each assertion in this file corresponds to a specific user-visible feature
that broke silently in production when its Output was accidentally removed.
"""

import pytest

pytestmark = pytest.mark.unit


def _has_output(registered_outputs: set, component_id: str, prop: str) -> bool:
    """Return True if any registered callback outputs to ``component_id.prop``.

    Uses substring matching so the check is resilient to Dash's internal
    key-format changes between major versions (single-output keys look like
    ``"comp.prop"``; multi-output keys embed the same token in a longer
    composite string).
    """
    token = f"{component_id}.{prop}"
    return any(token in key for key in registered_outputs)


@pytest.fixture(scope="module")
def registered_outputs():
    """Return the set of all registered callback output keys for the Dash app.

    ``scope="module"`` means the app is created once for the entire test
    module — Dash callback registration is global and idempotent, so this is
    both safe and fast.
    """
    from app.dash_app.layout import create_dash_app  # noqa: PLC0415
    app = create_dash_app()
    return set(app.callback_map.keys())


# ---------------------------------------------------------------------------
# Theme switching
# ---------------------------------------------------------------------------

def test_persist_theme_output_registered(registered_outputs):
    """persist_theme must output to theme-store.data.

    ``persist_theme`` in layout.py listens to the theme-selector dropdown and
    writes the chosen value to the ``theme-store`` localStorage store.  If its
    ``Output('theme-store', 'data')`` is dropped, the selector appears to work
    but the chosen theme is never persisted — the UI silently stays in the
    default light theme and reverts on every page load.

    This exact regression occurred when a string-replacement edit consumed the
    Output line while inserting the ``navigate_global_search`` callback above it.
    """
    assert _has_output(registered_outputs, "theme-store", "data"), (
        "persist_theme is missing Output('theme-store', 'data'). "
        "Theme switching will appear to work but the value is never saved — "
        "check the @app.callback decorator of persist_theme in layout.py."
    )


def test_apply_theme_output_registered(registered_outputs):
    """apply_theme must output to app-shell.className.

    ``apply_theme`` reads the ``theme-store`` value and applies the matching
    CSS class (``theme-executive-light`` / ``theme-executive-dark``) to the
    top-level ``app-shell`` container.  Without this Output the theme CSS
    variables are never activated regardless of the toggle button state.
    It also outputs to ``theme-icon.className`` to swap the sun/moon icon.
    """
    assert _has_output(registered_outputs, "app-shell", "className"), (
        "apply_theme is missing Output('app-shell', 'className'). "
        "The theme CSS class will never be applied — "
        "check the @app.callback decorator of apply_theme in layout.py."
    )
    assert _has_output(registered_outputs, "theme-icon", "className"), (
        "apply_theme is missing Output('theme-icon', 'className'). "
        "The sun/moon icon will never update when the theme changes — "
        "check the @app.callback decorator of apply_theme in layout.py."
    )


# ---------------------------------------------------------------------------
# Global search bar navigation
# ---------------------------------------------------------------------------

def test_navigate_global_search_pathname_registered(registered_outputs):
    """navigate_global_search must output to url.pathname.

    ``navigate_global_search`` is the callback behind the navbar search bar.
    It sets ``url.pathname`` to ``/app/search`` to trigger page routing.
    Without this Output the navbar search bar submits but nothing navigates.
    """
    assert _has_output(registered_outputs, "url", "pathname"), (
        "navigate_global_search is missing Output('url', 'pathname'). "
        "The navbar search bar will not navigate to the search page — "
        "check the @app.callback decorator of navigate_global_search in layout.py."
    )


def test_navigate_global_search_search_param_registered(registered_outputs):
    """navigate_global_search must output to url.search.

    ``navigate_global_search`` sets ``url.search`` to ``?q=<term>`` so the
    search page can read the query and auto-execute.  Without this Output the
    page navigates to /app/search but arrives with no query term and shows a
    blank search page instead of results.
    """
    assert _has_output(registered_outputs, "url", "search"), (
        "navigate_global_search is missing Output('url', 'search'). "
        "The navbar search will navigate to /app/search but the query term "
        "will not be passed — check the @app.callback decorator in layout.py."
    )


def test_navigate_global_search_clears_input_registered(registered_outputs):
    """navigate_global_search must output to global-search-input.value.

    After navigating to the search page, the navbar input must be cleared so
    the query does not persist across subsequent page navigations.  Without
    this Output the search term stays visible in the navbar indefinitely.
    """
    assert _has_output(registered_outputs, "global-search-input", "value"), (
        "navigate_global_search is missing Output('global-search-input', 'value'). "
        "The navbar search input will not clear after submission — "
        "check the @app.callback decorator of navigate_global_search in layout.py."
    )


# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

def test_display_page_output_registered(registered_outputs):
    """display_page must output to page-content.children.

    ``display_page`` is the central routing callback — it reads ``url.pathname``
    and renders the matching page layout into the ``page-content`` div.
    Without this Output all navigation renders a blank content area with no
    error shown to the user.
    """
    assert _has_output(registered_outputs, "page-content", "children"), (
        "display_page is missing Output('page-content', 'children'). "
        "Page navigation will render a blank content area — "
        "check the @app.callback decorator of display_page in layout.py."
    )
