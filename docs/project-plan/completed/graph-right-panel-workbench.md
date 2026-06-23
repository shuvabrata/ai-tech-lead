# Graph Page — Right Panel Workbench Redesign

**Status**: Complete
**Created**: 2026-06-11
**Last Updated**: 2026-06-11

## Progress Summary
- [x] **Phase 1**: Layout Restructuring (`layout.py` + `styles.py`)
- [x] **Phase 2**: New Right Panel Tab Callbacks (`callbacks/right_panel.py`)
- [x] **Phase 3**: Modify Existing Callbacks (`catalog.py`, `query.py`, `filtering.py`, `analytics_mode.py`, `__init__.py`)
- [x] **Phase 4**: CSS Additions (`executive-dashboard.css`)

---

## TL;DR

Consolidate the Filters, Query Console, and Query Catalog tools into a unified right-panel workbench. The right panel (Bootstrap column width=4, right of the graph canvas) gains a sticky icon-only horizontal tab bar at the top. Clicking an icon opens that tool's content below it; clicking the same icon again closes it (accordion). The Properties/Legend panel remains below — it is always visible and gets pushed down when a tab is open. The two bottom collapsible sections (Query Console and Query Catalog) are removed from the page entirely, giving the graph canvas more vertical space. Performance metrics stay at the bottom of the left column, unchanged.

The design is inspired by Draw.io and Lightroom — the right side is the control workbench; the left side is the visualization canvas.

---

## All Design Decisions

| # | Decision | Chosen Option | Notes |
|---|----------|--------------|-------|
| 1 | Layout model | Priority Stack (Option C) | Tab bar at top of right panel; open tab pushes Properties down |
| 2 | Tab toggle interaction | Accordion (C1) | Same icon click closes the open tab; only one tab open at a time |
| 3 | Bottom sections fate | Remove both | `create_query_input_section()` and `create_catalog_section()` deleted from `get_layout()` |
| 4 | Performance metrics location | Keep at bottom of left column | `create_hidden_elements()` and `graph-performance-metrics` div unchanged |
| 5 | Tab bar visual | Icon-only horizontal strip | `fas fa-sliders fa-fw` (Filters), `fas fa-terminal fa-fw` (Console), `fas fa-book-open fa-fw` (Catalog) |
| 6 | Icon tooltips | Native `title` attribute | `title="Filters"` / `"Console"` / `"Catalog"` — same pattern as left nav bar |
| 7 | Active tab indicator | 2px navy accent underline | Active icon turns `var(--color-navy)` + `border-bottom: 2px solid var(--color-navy)` |
| 8 | "Full" button | No change | Collapses entire `graph-details-col`; canvas expands to width=12 |
| 9 | Node/edge selection | Push Properties down | No auto-collapse of active tab; panel scrollable |
| 10 | Catalog tab layout | Single-column stacked | List on top, detail below; no 2-column split |
| 11 | Catalog list-level view filter | Remove `catalog-view-filter` | "Graph / Tabular / All" dropdown removed from catalog tab |
| 12 | Catalog per-query view toggle | **Restored** in catalog tab | Radio items kept; API requires explicit `"graph"` or `"tabular"` (rejects `"auto"` for catalog source) |
| 13 | Catalog view selection | Pass resolved view to API | `execute_query` reads `catalog-query-view-toggle` state; falls back to `"graph"` if unset |
| 14 | Scroll model | Unified scroll, sticky tab bar | Right column container has `overflowY: auto`; icon bar is `position: sticky; top: 0` |
| 15 | "Load into Console" cross-tab | Auto-switch to Console tab | `load_catalog_query_into_console` outputs `right-panel-active-tab` → `"console"` on button click |
| 16 | Properties/Legend separator | Existing card styling only | `GRAPH_DETAILS_PANEL_STYLE` border/background is sufficient; no explicit divider needed |

---

## Component ID Reference

### New IDs (created in this implementation)

| Component ID | Type | Purpose |
|---|---|---|
| `right-panel-active-tab` | `dcc.Store` (memory) | Active tab name: `"filters"`, `"console"`, `"catalog"`, or `None` |
| `graph-right-panel-tab-bar` | `html.Div` | Container for the 3 icon buttons |
| `right-tab-filters-btn` | `html.Button` | Filters tab toggle button |
| `right-tab-console-btn` | `html.Button` | Console tab toggle button |
| `right-tab-catalog-btn` | `html.Button` | Catalog tab toggle button |
| `right-tab-filters-collapse` | `dbc.Collapse` | Wraps filter content (replaces `filter-panel-collapse`) |
| `right-tab-console-collapse` | `dbc.Collapse` | Wraps console content (replaces `query-panel-collapse`) |
| `right-tab-catalog-collapse` | `dbc.Collapse` | Wraps catalog content (replaces `catalog-panel-collapse`) |

### Removed IDs (no longer in DOM after this implementation)

| Removed ID | Was In | Replaced By |
|---|---|---|
| `toggle-filter-collapse-btn` | `create_filter_panel()` | `right-tab-filters-btn` |
| `toggle-query-collapse-btn` | `create_query_input_section()` | `right-tab-console-btn` |
| `toggle-catalog-collapse-btn` | `create_catalog_section()` | `right-tab-catalog-btn` |
| `filter-panel-collapse` | `create_filter_panel()` | `right-tab-filters-collapse` |
| `query-panel-collapse` | `create_query_input_section()` | `right-tab-console-collapse` |
| `catalog-panel-collapse` | `create_catalog_section()` | `right-tab-catalog-collapse` |
| `filter-collapse-icon` | `create_filter_panel()` | Tab button `className` (active/inactive) |
| `query-collapse-icon` | `create_query_input_section()` | Tab button `className` (active/inactive) |
| `catalog-collapse-icon` | `create_catalog_section()` | Tab button `className` (active/inactive) |
| `graph-query-section` | `get_layout()` outer div | (section removed entirely) |
| `graph-catalog-section` | `get_layout()` outer div | (section removed entirely) |
| `catalog-view-filter` | `create_catalog_section()` | (removed; view auto-selected) |
| `catalog-query-view-toggle` | `create_catalog_section()` | (removed; view auto-selected) |

---

## Phase 1: Layout Restructuring

**Goal**: Restructure `layout.py` to render the new icon tab bar and three collapsible tab panels in the right column. Remove the two bottom sections from `get_layout()`. Update `styles.py` to remove the fixed height from the properties panel (the outer scroll container handles it instead).

**Files**:
- `src/app/dash_app/pages/graph/layout.py`
- `src/app/dash_app/styles.py`

### Tasks

- [x] **1.1** Add `right-panel-active-tab` store to `create_stores()`:
  - Add `dcc.Store(id="right-panel-active-tab", storage_type="memory", data=None)` to the stores list

- [x] **1.2** Create `create_right_panel_tab_bar()` function:
  - Returns `html.Div(id="graph-right-panel-tab-bar", className="graph-right-panel-tab-bar", children=[...])`
  - Contains 3 `html.Button` elements:
    - `id="right-tab-filters-btn"`, `children=html.I(className="fas fa-sliders fa-fw")`, `title="Filters"`, `className="graph-right-panel-tab-icon"`, `n_clicks=0`
    - `id="right-tab-console-btn"`, `children=html.I(className="fas fa-terminal fa-fw")`, `title="Console"`, `className="graph-right-panel-tab-icon"`, `n_clicks=0`
    - `id="right-tab-catalog-btn"`, `children=html.I(className="fas fa-book-open fa-fw")`, `title="Catalog"`, `className="graph-right-panel-tab-icon"`, `n_clicks=0`

- [x] **1.3** Create `create_right_panel_tabs()` function:
  - Returns `html.Div(children=[filters_collapse, console_collapse, catalog_collapse])`
  - `right-tab-filters-collapse`: `dbc.Collapse(id="right-tab-filters-collapse", is_open=False)` wrapping the `dbc.Card`/`dbc.CardBody` content that currently lives inside `dbc.Collapse(id="filter-panel-collapse", ...)` in `create_filter_panel()`
  - `right-tab-console-collapse`: `dbc.Collapse(id="right-tab-console-collapse", is_open=False)` wrapping the `dbc.Card`/`dbc.CardBody` content that currently lives inside `dbc.Collapse(id="query-panel-collapse", ...)` in `create_query_input_section()`
  - `right-tab-catalog-collapse`: `dbc.Collapse(id="right-tab-catalog-collapse", is_open=False, children=[create_catalog_tab_content()])`

- [x] **1.4** Create `create_catalog_tab_content()` function (single-column, narrow panel):
  - Namespace filter label + `dbc.Select(id="catalog-namespace-filter", ...)` — full width, stacked vertically
  - Search label + `dbc.Input(id="catalog-search-input", ...)` — full width, stacked vertically
  - **Do NOT include** `catalog-view-filter` select or its label
  - `html.Div(id="query-catalog-load-status", className="mb-2")`
  - `html.Div(id="catalog-query-list", style={"maxHeight": "240px", "overflowY": "auto", ...})`
  - `html.Div(id="catalog-query-detail", ...)` — full width below list
  - **Do NOT include** `catalog-query-view-toggle` radio items or its enclosing label div
  - `html.Div(id="catalog-parameter-inputs", className="mt-3")`
  - Buttons: `dbc.Button("Run", id="catalog-run-btn", ...)` + `dbc.Button("Load into Console", id="catalog-load-console-btn", ...)` side by side, `className="mt-3"`

- [x] **1.5** Restructure right column in `create_results_section()`:
  - The right `dbc.Col(id="graph-details-col", width=4)` children become an inner wrapper `html.Div` with `style={"overflowY": "auto", "maxHeight": "calc(75vh + 40px)", "position": "relative"}` containing:
    1. `create_right_panel_tab_bar()`
    2. `create_right_panel_tabs()`
    3. The existing `html.Div(id="graph-details-panel", ...)` (Properties/Legend panel — keep unchanged)
  - Remove the old `create_filter_panel()` call from the right column

- [x] **1.6** Update `get_layout()`:
  - Remove the `create_catalog_section()` call
  - Remove the `create_query_input_section()` call
  - Keep all other calls unchanged (`create_results_section()`, `create_hidden_elements()`, `create_stores()`, `create_context_menu()`, `create_expansion_modal()`)

- [x] **1.7** Retire old section builder functions (do not delete yet):
  - Add comment `# Retired in right-panel-workbench redesign — no longer called from get_layout()` to the top of:
    - `create_filter_panel()`
    - `create_query_input_section()`
    - `create_catalog_section()`

- [x] **1.8** Update `GRAPH_DETAILS_PANEL_STYLE` in `src/app/dash_app/styles.py`:
  - Remove the `"height": "calc(75vh + 40px)"` entry from the dict
  - Remove the `"overflowY": "auto"` entry from the dict
  - Keep: `"backgroundColor"`, `"borderRadius"`, `"border"`, `"padding"`
  - Scroll and height are now owned by the outer wrapper added in task 1.5

### Phase 1 Manual Test Checkpoint

Start the application:
```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn app.main:app --reload
```

Open http://localhost:8000/app/graph and verify:

- [ ] Page loads without Python or Dash errors in the server console
- [ ] The right panel shows three icon buttons in a horizontal row at the very top
- [ ] Hovering each icon shows a native browser tooltip: "Filters", "Console", "Catalog"
- [ ] The Properties/Legend placeholder ("Execute a query to see the graph") is visible below the icon strip
- [ ] There are **no** "Query Catalog" or "Query Console" collapsible sections at the bottom of the page
- [ ] Clicking the "Full" button hides the entire right panel and the graph canvas expands; clicking "Exit" restores it
- [ ] Running a Cypher query renders results in the graph canvas
- [ ] Clicking a node after running a query shows the Properties panel in the right column
- [ ] The three icon buttons do not respond to clicks yet (callbacks not wired until Phase 2) — this is expected

---

## Phase 2: New Right Panel Tab Callbacks

**Goal**: Create `callbacks/right_panel.py` with three callbacks to drive tab toggling, visual sync, and URL deep-link handling.

**Files**:
- `src/app/dash_app/pages/graph/callbacks/right_panel.py` **(NEW)**
- `src/app/dash_app/pages/graph/callbacks/__init__.py`

### Tasks

- [x] **2.1** Create `src/app/dash_app/pages/graph/callbacks/right_panel.py`:

  Module docstring: `"""Right panel workbench tab callbacks."""`

  Required imports:
  ```python
  from urllib.parse import parse_qs, unquote
  from dash import Input, Output, State, callback, ctx, no_update
  from dash.exceptions import MissingCallbackContextException, PreventUpdate
  ```

- [x] **2.2** Implement `toggle_right_panel_tab` callback:
  - **Inputs**: `right-tab-filters-btn.n_clicks`, `right-tab-console-btn.n_clicks`, `right-tab-catalog-btn.n_clicks`
  - **State**: `right-panel-active-tab.data`
  - **Output**: `right-panel-active-tab.data`
  - `prevent_initial_call=True`
  - Logic: use `ctx.triggered_id` to determine which button was clicked; map button ID to tab name (`"filters"`, `"console"`, `"catalog"`); if `active_tab == clicked_tab`, return `None` (accordion close); otherwise return `clicked_tab`

- [x] **2.3** Implement `sync_right_panel_ui` callback:
  - **Input**: `right-panel-active-tab.data`
  - **Outputs** (6 total, in order):
    1. `right-tab-filters-collapse.is_open`
    2. `right-tab-console-collapse.is_open`
    3. `right-tab-catalog-collapse.is_open`
    4. `right-tab-filters-btn.className`
    5. `right-tab-console-btn.className`
    6. `right-tab-catalog-btn.className`
  - `prevent_initial_call=False` (must fire on initial load to set all tabs to closed/inactive state)
  - Logic: for each tab, `is_open = (active_tab == tab_name)`; `className = "graph-right-panel-tab-icon active"` if active else `"graph-right-panel-tab-icon"`

- [x] **2.4** Implement `handle_url_deep_link_tab` callback:
  - **Input**: `url.search`
  - **Outputs** (3 total):
    1. `right-panel-active-tab.data` (`allow_duplicate=True`)
    2. `graph-query-input.value` (`allow_duplicate=True`)
    3. `cypher-autoexec-store.data` (`allow_duplicate=True`)
  - `prevent_initial_call=False`
  - Logic:
    - Parse `search` with `parse_qs`
    - If `?cypher=` param present: `decoded = unquote(raw_cypher)`; return `("console", decoded, decoded)` — opens Console tab, fills textarea, sets autoexec store to trigger execution
    - If `?catalog=` param present: return `("catalog", no_update, no_update)` — opens Catalog tab; existing `sync_selected_catalog_query` handles pre-selection
    - Otherwise: `raise PreventUpdate`

- [x] **2.5** Update `callbacks/__init__.py`:
  - Add import line: `from .right_panel import toggle_right_panel_tab, sync_right_panel_ui, handle_url_deep_link_tab`
  - Add all three names to the `__all__` list under a `# Right panel tab callbacks` comment

### Phase 2 Manual Test Checkpoint

- [ ] Page loads without Dash duplicate output errors or missing component errors in server console
- [ ] Clicking the Filters icon opens the filter controls below the tab bar
- [ ] Clicking the Filters icon again collapses it (accordion close)
- [ ] Clicking Console while Filters is open: Console opens, Filters closes
- [ ] Clicking Catalog opens the catalog panel (list + detail)
- [ ] Scrolling the right panel when a long filter list is open: icon tab bar stays fixed at the top
- [ ] No tab open: Properties/Legend uses the full remaining right column height
- [ ] Navigate to `http://localhost:8000/app/graph?cypher=MATCH+%28n%29+RETURN+n+LIMIT+5` — Console tab auto-opens with query pre-filled and auto-executes
- [ ] Navigate to `http://localhost:8000/app/graph?catalog=<valid_catalog_id>` (use a real ID from the catalog) — Catalog tab opens and that query is pre-selected

---

## Phase 3: Modify Existing Callbacks

**Goal**: Remove the three old toggle callbacks (their target component IDs no longer exist), update `execute_query` to drop the view toggle dependency, simplify `render_catalog_query_detail` and `render_catalog_query_list`, update `load_catalog_query_into_console` to auto-switch tabs, and update `analytics_mode` to target the new button IDs.

### 3.1 `src/app/dash_app/pages/graph/callbacks/filtering.py`

- [x] **3.1.1** Delete the `toggle_filter_panel` callback function entirely.
  - This callback had `Output("filter-panel-collapse", "is_open")` and `Output("filter-collapse-icon", "className")` — both component IDs are gone after Phase 1.
  - Delete from `@callback(Output("filter-panel-collapse", "is_open"), ...)` through the closing line of `def toggle_filter_panel(...)`.

### 3.2 `src/app/dash_app/pages/graph/callbacks/query.py`

- [x] **3.2.1** Delete the `toggle_query_collapse` callback function entirely.
  - Component IDs `query-panel-collapse` and `query-collapse-icon` no longer exist.
  - The `?cypher=` URL deep-link logic is now handled by `handle_url_deep_link_tab` in `right_panel.py`.
  - Delete from `@callback(Output("query-panel-collapse", "is_open"), ...)` through the closing line of `def toggle_query_collapse(...)`.

- [x] **3.2.2** Update `execute_query` callback:
  - In the `State` list, remove `State("catalog-query-view-toggle", "value")` (currently the 4th State).
  - Remove `catalog_view` from the function parameter list.
  - In the catalog branch (`triggered_id == "catalog-run-btn"`), change:
    `"view": catalog_view or "auto"` → `"view": "auto"`
  - The `"auto"` value tells the API to resolve view using `default_view` from the query YAML.

### 3.3 `src/app/dash_app/pages/graph/callbacks/catalog.py`

- [x] **3.3.1** Delete the `toggle_catalog_collapse` callback function entirely.
  - Component IDs `catalog-panel-collapse` and `catalog-collapse-icon` no longer exist.
  - Note: this function is registered via `@callback` decorator directly (not listed in `__init__.py` imports), so deleting it is sufficient.
  - Delete from `@callback(Output("catalog-panel-collapse", "is_open"), ...)` through the closing line of `def toggle_catalog_collapse(...)`.

- [x] **3.3.2** Update `render_catalog_query_list` callback:
  - Remove `Input("catalog-view-filter", "value")` from the Input list.
  - Remove `view_filter: str | None` from the function signature.
  - Update the `filter_catalog_queries(...)` call to: `filter_catalog_queries(catalog_queries, namespace_filter, search_text, None)`.

- [x] **3.3.3** Update `render_catalog_query_detail` callback:
  - Remove `Output("catalog-query-view-toggle", "options")` from outputs.
  - Remove `Output("catalog-query-view-toggle", "value")` from outputs.
  - Remove `State("catalog-query-view-toggle", "value")` from states.
  - Remove `current_view: str | None` from the function signature.
  - Update `determine_catalog_view(...)` call: change `determine_catalog_view(query, preferred_view, current_view)` → `determine_catalog_view(query, (selected_query or {}).get("preferred_view"), None)`.
  - Reduce the return tuple from 6 values to 4 values — remove `view_options` (2nd) and `selected_view` (3rd): `return (detail_children, parameter_children, disabled_run, disabled_load)`.
  - Update the early-return when no query found from 6-tuple to 4-tuple accordingly.

- [x] **3.3.4** Update `load_catalog_query_into_console` callback:
  - Add `Output("right-panel-active-tab", "data", allow_duplicate=True)` to the outputs list.
  - Remove `State("catalog-query-view-toggle", "value")` from states.
  - Remove `selected_view: str | None` from the function signature.
  - At the top of the function body, add: `resolved_view = determine_catalog_view(query, None, None) if query else None`.
  - Replace all uses of `selected_view` with `resolved_view`.
  - Update guard: `if not query or not resolved_view: return no_update, no_update`.
  - Button-triggered branch: return `((query.get("queries") or {}).get(resolved_view, no_update), "console")`.
  - Deep-link branch: return `((query.get("queries") or {}).get(resolved_view, no_update), no_update)`.
  - Fallback: `return no_update, no_update`.

### 3.4 `src/app/dash_app/pages/graph/callbacks/analytics_mode.py`

- [x] **3.4.1** Update `toggle_query_panel_for_analytics_mode` callback:
  - Replace `Output("graph-query-section", "style")` with `Output("right-tab-console-btn", "style")`.
  - Replace `Output("graph-catalog-section", "style")` with `Output("right-tab-catalog-btn", "style")`.
  - Logic unchanged: analytics mode → `{"display": "none"}, {"display": "none"}`; normal mode → `{}, {}`.

### 3.5 `src/app/dash_app/pages/graph/callbacks/__init__.py`

- [x] **3.5.1** Update query import line:
  - Change `from .query import validate_query, execute_query, toggle_query_collapse` → `from .query import validate_query, execute_query`.

- [x] **3.5.2** Update filtering import block:
  - Remove `toggle_filter_panel` from the `from .filtering import (...)` block.

- [x] **3.5.3** Update `__all__` list:
  - Remove `'toggle_query_collapse'`.
  - Remove `'toggle_filter_panel'`.
  - Add (under right panel section): `'toggle_right_panel_tab'`, `'sync_right_panel_ui'`, `'handle_url_deep_link_tab'`.

### Phase 3 Manual Test Checkpoint

- [ ] App starts with **no** Dash duplicate output errors or "component not found" warnings in the server console
- [ ] Run a raw Cypher query via the Console tab — results render in the graph canvas; status strip shows success message; performance metrics appear at bottom of left column
- [ ] Run a catalog query that has `default_view: tabular` in its YAML — it executes as tabular without prompting for view selection
- [ ] Run a catalog query that has `default_view: graph` — it executes as graph
- [ ] Select a catalog query and click "Load into Console" — Console tab auto-opens; query text appears in the textarea; query is editable
- [ ] After "Load into Console", press Ctrl+Enter — query executes
- [ ] Click a node in the graph — Properties panel appears below any currently open tab in the right panel; both tab content and Properties are visible simultaneously
- [ ] Click on empty canvas area — Node Legend appears in the Properties panel area
- [ ] Open Filters tab, set a node type filter, run a query — filter checkboxes populate; toggling a checkbox updates the graph correctly

---

## Phase 4: CSS Additions

**Goal**: Add the `.graph-right-panel-tab-bar` and `.graph-right-panel-tab-icon` CSS rule blocks to `executive-dashboard.css`. These are the only new styles needed for the tab bar.

**File**: `src/app/dash_app/assets/executive-dashboard.css`

### Tasks

- [x] **4.1** Add the following CSS block to `executive-dashboard.css`, after the existing `collapse-toggle-subtle` block (approximately line 430). Add a section comment header:

```css
/* ============================================================
   Right Panel Workbench Tab Bar
   ============================================================ */

.graph-right-panel-tab-bar {
    display: flex;
    gap: 4px;
    padding: 4px 0 0 0;
    border-bottom: 1px solid var(--color-border);
    position: sticky;
    top: 0;
    background-color: var(--color-background-white);
    z-index: 10;
    margin-bottom: 8px;
}

.graph-right-panel-tab-icon {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--color-gray-medium);
    padding: 6px 12px;
    font-size: 14px;
    cursor: pointer;
    transition: color 0.15s ease, border-color 0.15s ease;
    margin-bottom: -1px; /* overlap parent border-bottom so active underline is flush */
    outline: none;
}

.graph-right-panel-tab-icon:hover {
    color: var(--color-charcoal-medium);
}

.graph-right-panel-tab-icon.active {
    color: var(--color-navy);
    border-bottom: 2px solid var(--color-navy);
}

.graph-right-panel-tab-icon:focus-visible {
    outline: 2px solid var(--color-navy);
    outline-offset: 2px;
    border-radius: 2px;
}
```

### Phase 4 Manual Test Checkpoint

- [ ] Inactive icons render in the correct gray color (`var(--color-gray-medium)`)
- [ ] Hovering an icon changes it to charcoal (`var(--color-charcoal-medium)`)
- [ ] The active tab icon is navy with a 2px navy underline flush with the bar's bottom border (no visible gap)
- [ ] Clicking Filters → Console → Catalog: each active icon highlights correctly; previously active icon returns to gray
- [ ] All three icons are unlit when no tab is open; Properties/Legend fills the remaining right column height
- [ ] The icon tab bar does not scroll with the panel content when a long filter list is open (position: sticky holds)
- [ ] Keyboard navigation: tab to an icon button and press Enter — same toggle behavior as click; focus ring visible (`focus-visible` outline)

---

## Final Integration Verification

### Automated Tests
```bash
source .venv/bin/activate
pytest -m unit tests -q
```

### Manual Full-Flow Checklist

- [ ] **Cold load**: Navigate to `/app/graph` — page loads; icon bar visible at top of right panel; Properties placeholder below it; no bottom Query Console or Query Catalog sections; no console errors
- [ ] **Console flow**: Click Console icon → textarea expands below tab bar → type `MATCH (n) RETURN n LIMIT 5` → press Ctrl+Enter → graph renders in canvas → status strip shows node/edge count → performance metrics (Time / Nodes / Edges / Status) appear at bottom of left column
- [ ] **Catalog flow**: Click Catalog icon → list loads (query count shown) → search to filter list → select a query → Run button enabled → click Run → results render correctly
- [ ] **Load into Console**: In Catalog, click "Load into Console" → Console tab auto-opens → query text appears in the textarea ready to edit
- [ ] **Filter flow**: Run a query first → click Filters icon → Node Type and Relationship Type checkboxes populate → uncheck a node type → matching nodes hide/dim in graph
- [ ] **Accordion behavior**: With Filters open, click the Filters icon again → Filters closes; click Console → Console opens; click Console again → Console closes; all icons return to gray when no tab open
- [ ] **Properties push**: Open Filters tab → click a node in the graph → Properties panel appears below the open Filters content; both sections visible simultaneously; scroll to reach Properties if needed
- [ ] **Legend**: Run a query → click on empty canvas area → Node Legend appears in the right panel below any open tab
- [ ] **Full/Exit**: Click "Full" button → entire right panel disappears; graph canvas expands to full 12-column width; click "Exit" → right panel restores
- [ ] **URL deep-link (Console)**: Navigate to `/app/graph?cypher=MATCH+%28n%29+RETURN+n+LIMIT+5` → Console tab opens automatically; query is pre-filled; graph executes without clicking anything
- [ ] **URL deep-link (Catalog)**: Navigate to `/app/graph?catalog=<valid_catalog_id>` → Catalog tab opens; the specified query is pre-selected in the list
- [ ] **Analytics mode**: Navigate to `/app/graph?mode=analytics` → Console and Catalog icon buttons are hidden from the tab bar; Filters icon remains visible

---

## Relevant Files Reference

| File | Role in This Change |
|---|---|
| `src/app/dash_app/pages/graph/layout.py` | Major restructuring — new tab bar + tab collapse functions; retire old section builders |
| `src/app/dash_app/styles.py` | Update `GRAPH_DETAILS_PANEL_STYLE` (remove `height` and `overflowY`) |
| `src/app/dash_app/pages/graph/callbacks/right_panel.py` | **NEW** — 3 callbacks: tab toggle, UI sync, URL deep-link |
| `src/app/dash_app/pages/graph/callbacks/__init__.py` | Add right_panel imports; remove `toggle_query_collapse`, `toggle_filter_panel` |
| `src/app/dash_app/pages/graph/callbacks/query.py` | Delete `toggle_query_collapse`; update `execute_query` (drop view toggle State) |
| `src/app/dash_app/pages/graph/callbacks/filtering.py` | Delete `toggle_filter_panel` callback |
| `src/app/dash_app/pages/graph/callbacks/catalog.py` | Delete `toggle_catalog_collapse`; update 3 callbacks |
| `src/app/dash_app/pages/graph/callbacks/analytics_mode.py` | Update outputs from removed section IDs to new button IDs |
| `src/app/dash_app/assets/executive-dashboard.css` | Add tab bar CSS block |

---

## Notes for Resuming

1. Check task checkboxes above — `[ ]` = not done, `[x]` = done, update as you complete tasks.

2. Phases are designed to be sequential. Each phase has a manual test checkpoint that gates proceeding to the next phase.

3. **If pausing after Phase 1 only**: Phase 3 hasn't run yet, so the old toggle callbacks (`toggle_filter_panel`, `toggle_query_collapse`, `toggle_catalog_collapse`) will reference component IDs that no longer exist in the DOM. Dash will log warnings on startup. The app will still load and the graph canvas will work. To suppress warnings while paused, temporarily add the old bottom sections back to `get_layout()` (comment them back in), then remove them again when resuming Phase 3.

4. **Most critical callback**: `sync_right_panel_ui` in Phase 2 — it drives the visual state of 6 components (3 collapse panels + 3 button classes) from a single store value. If something looks wrong visually, check this callback first.

5. **Catalog view logic**: The `determine_catalog_view(query, None, None)` call used in `load_catalog_query_into_console` after Phase 3 uses the existing priority order from `catalog.py`: prefers `"graph"` if available, then `default_view` from YAML, then first available view. This is intentional and preserves the existing product preference for graph views.

---

*Created by design interview session on 2026-06-11.*
