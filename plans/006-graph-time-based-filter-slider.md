# Plan 006: Time-Based RangeSlider Filters for Graph Page

> **Executor instructions**: Follow this plan step by step. Each phase has test steps — run them before moving to the next phase.
>
> **Drift check (run first)**: `git diff --stat HEAD -- src/app/dash_app/pages/graph/`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: feature
- **Planned at**: 2026-07-06

## Why this matters

When lots of nodes are loaded in the graph visualization, users need to filter
nodes by time ranges (created, updated, last seen) to focus on relevant
activity windows. A RangeSlider provides a more intuitive experience than
date-picker start/end fields. The min/max range is auto-computed from the
loaded graph and refreshes on expansion.

## Design decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Which time properties to support? | All 3: `_created_at`, `_last_updated_at`, `_last_seen_at` |
| 2 | How to handle nodes missing a property? | Include them — the filter only excludes nodes that HAVE the property but fall outside the range |
| 3 | Slider value unit? | Days-since-epoch (integer), step=1 |
| 4 | Slider layout? | Single collapsible parent "Time Filters" section (collapsed by default) — no sub-collapses per slider |
| 5 | Collapsible order? | Created At → Last Updated → Last Seen |
| 6 | Slider marks? | Min and max only, formatted as human-readable dates (e.g. `"Jan 15, 2026"`) |
| 7 | Range source? | Always `unfiltered-elements-store` (full graph baseline) — stable across other filter changes |
| 8 | Filter chips? | Only shown when slider is narrowed from full range — chip shows `"Created: Jan 15 – Mar 20, 2026"` |
| 9 | Clear All behavior? | Resets all 3 sliders to full range |
| 10 | Initial collapsible state? | Collapsed by default |
| 11 | Where to add in filter card? | After the Weight/Top-N section, before `weight-filter-unavailable-note` |
| 12 | Edge filtering scope? | Deferred — edges get hidden automatically when their endpoint nodes are hidden |

## Scope

**In scope** (all files in `src/app/dash_app/pages/graph/`):
- `callbacks/filtering.py` — all filter functions extended
- `layout.py` — `_filter_card()` and `create_stores()`
- `utils/time_helpers.py` — new date conversion helpers

**Out of scope**:
- Edge-level time filtering
- Server-side or database-level date filtering
- Neo4j schema changes
- Tests in `tests/` (add new ones)
- CSS changes (existing classes suffice)

## Phase 1 — Utility helpers

### Step 1.1: Create `utils/time_helpers.py`

Create new file with:

**`_parse_days_since_epoch(iso_string: str) -> int | None`**
- Parse ISO 8601 string → `datetime` → days since epoch (UTC)
- Return `None` if string is empty or unparseable

**`_format_day_label(days: int) -> str`**
- Convert days-since-epoch → human-readable date
- Format: `"%b %d, %Y"` (e.g. `"Jan 15, 2026"`)

**`compute_time_range(nodes: list, property_name: str) -> tuple[int, int]`**
- Scan unfiltered nodes (list of Cytoscape element dicts)
- For each node, read `data[property_name]`, parse to days
- Return `(min_days, max_days)` over all nodes that have the property
- If no nodes have the property, return `(0, 1)` — slider exists but is inert

### Step 1.2: Add helper to `filtering.py`

Add **`_summarize_time_filter(range_value, full_range, label_prefix) -> str | None`**:
- If `range_value` equals `full_range` → return `None` (no chip)
- Else return `"Created: Jan 15 – Mar 20, 2026"` (using `_format_day_label`)

### Step 1.3: Automated tests

**Add** `tests/test_graph_time_filter_helpers.py`:

```python
"""Test time helper utilities for graph time-based filters."""
import pytest
from app.dash_app.pages.graph.utils.time_helpers import (
    _parse_days_since_epoch,
    _format_day_label,
    compute_time_range,
)
```

Tests:
- `test_parse_days_valid_iso` — `"2025-12-01T14:30:00Z"` → known day count
- `test_parse_days_empty` — `""` → `None`
- `test_parse_days_invalid` — `"not-a-date"` → `None`
- `test_format_day_label` — known days → `"Dec 01, 2025"`
- `test_compute_time_range` — list of mock node dicts with three distinct dates → correct min/max
- `test_compute_time_range_no_property` — nodes without the property → `(0, 1)`
- `test_compute_time_range_mixed` — some nodes have property, some don't → min/max from only those that do

**Verify**: `pytest -m unit tests/test_graph_time_filter_helpers.py -v` → all pass.

### Phase 1 Done Criteria

- [ ] `utils/time_helpers.py` exists with all 3 functions
- [ ] `_summarize_time_filter` exists in `filtering.py`
- [ ] All 7 automated tests pass

---

## Phase 2 — Layout additions

### Step 2.1: Add Store to `create_stores()`

In `layout.py`, add to `create_stores()`:

```python
# --- Phase 1.2.5: Time-Based Filters ---
# Store for full time-range metadata per property: {property_name: [min_days, max_days]}
# Used by the range-computation callback to remember the full range for chip
# display and by clear-all to reset sliders.
dcc.Store(id="time-filter-full-ranges", data={}),
```

### Step 2.2: Add Time Filters section to `_filter_card()`

In `_filter_card()`, after the `weight-based-filter-group` div and **before** the `weight-filter-unavailable-note` div, add:

```python
# Time Filters (collapsible section)
html.Div([
    html.Div(
        [html.I(className="fas fa-chevron-down collapse-toggle-chevron me-1"),
         "Time Filters"],
        id="time-filters-collapse-toggle",
        className="collapse-toggle-subtle",
        style={
            "fontSize": "11px",
            "fontWeight": FONT_WEIGHT_SEMIBOLD,
            "color": COLOR_GRAY_DARK,
            "marginBottom": "8px",
            "cursor": "pointer",
            "userSelect": "none",
        }
    ),
    dbc.Collapse(
        id="time-filters-collapse",
        is_open=False,
        children=[
            # Created At
            html.Div([
                html.Label("Created At", style={
                    "fontSize": "11px",
                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                    "color": COLOR_GRAY_DARK,
                    "marginBottom": "4px",
                    "display": "block"
                }),
                dcc.RangeSlider(
                    id="time-slider-created",
                    min=0, max=1, step=1,
                    value=[0, 1],
                    marks={},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                html.Small(
                    id="time-slider-created-label",
                    className="d-block mt-1",
                    style={"fontSize": "10px", "color": "var(--color-text-secondary)"}
                ),
            ], className="mb-2"),

            # Last Updated
            html.Div([
                html.Label("Last Updated", style={
                    "fontSize": "11px",
                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                    "color": COLOR_GRAY_DARK,
                    "marginBottom": "4px",
                    "display": "block"
                }),
                dcc.RangeSlider(
                    id="time-slider-updated",
                    min=0, max=1, step=1,
                    value=[0, 1],
                    marks={},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                html.Small(
                    id="time-slider-updated-label",
                    className="d-block mt-1",
                    style={"fontSize": "10px", "color": "var(--color-text-secondary)"}
                ),
            ], className="mb-2"),

            # Last Seen
            html.Div([
                html.Label("Last Seen", style={
                    "fontSize": "11px",
                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                    "color": COLOR_GRAY_DARK,
                    "marginBottom": "4px",
                    "display": "block"
                }),
                dcc.RangeSlider(
                    id="time-slider-seen",
                    min=0, max=1, step=1,
                    value=[0, 1],
                    marks={},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                html.Small(
                    id="time-slider-seen-label",
                    className="d-block mt-1",
                    style={"fontSize": "10px", "color": "var(--color-text-secondary)"}
                ),
            ], className="mb-2"),
        ]
    )
], className="mb-3"),
```

### Step 2.3: Add collapse-toggle callback

In `callbacks/__init__.py` or a new callbacks file, add:

```python
@callback(
    [Output("time-filters-collapse", "is_open"),
     Output("time-filters-collapse-toggle", "children")],
    Input("time-filters-collapse-toggle", "n_clicks"),
    State("time-filters-collapse", "is_open"),
    prevent_initial_call=True
)
def toggle_time_filters_collapse(n_clicks, is_open):
    """Toggle the Time Filters collapsible section."""
    if not n_clicks:
        raise PreventUpdate
    new_state = not is_open
    chevron = "chevron-down" if new_state else "chevron-right"
    children = [
        html.I(className=f"fas fa-{chevron} collapse-toggle-chevron me-1"),
        "Time Filters",
    ]
    return new_state, children
```

### Step 2.4: Manual verification

1. Open the app, navigate to Graph page
2. Open the Filters tab in the right panel
3. Verify "Time Filters" collapsed header appears after the Weight controls
4. Click "Time Filters" → collapses expand, chevron rotates down
5. Click again → collapses, chevron rotates right
6. Verify "Clear All" button still works on existing filters
7. Verify no console errors

### Phase 2 Done Criteria

- [ ] `time-filter-full-ranges` Store added to `create_stores()`
- [ ] Time Filters section added to `_filter_card()` with 3 RangeSliders
- [ ] Collapse toggle callback registered
- [ ] Manual verification passes

---

## Phase 3 — Dynamic range computation

### Step 3.1: Add range computation callback to `filtering.py`

Add **`update_time_filter_ranges`** callback:

```python
@callback(
    [Output("time-filter-full-ranges", "data"),
     Output("time-slider-created", "min"),
     Output("time-slider-created", "max"),
     Output("time-slider-created", "value"),
     Output("time-slider-created", "marks"),
     Output("time-slider-updated", "min"),
     Output("time-slider-updated", "max"),
     Output("time-slider-updated", "value"),
     Output("time-slider-updated", "marks"),
     Output("time-slider-seen", "min"),
     Output("time-slider-seen", "max"),
     Output("time-slider-seen", "value"),
     Output("time-slider-seen", "marks")],
    Input("unfiltered-elements-store", "data"),
    [State("time-filter-full-ranges", "data")],
    prevent_initial_call=True,
)
def update_time_filter_ranges(unfiltered_elements, previous_ranges):
    """Compute slider ranges from all unfiltered nodes.

    Called whenever the unfiltered baseline changes (new query or expansion).
    Uses Interpretation A: range is always the full min/max from
    unfiltered-elements-store regardless of other active filters.

    When a property is absent from ALL nodes, slider is set to [0, 1]
    which is effectively inert (no nodes excluded).
    """
    if not unfiltered_elements:
        raise PreventUpdate

    nodes = [e for e in unfiltered_elements if is_node_data(e.get("data", {}))]

    # Compute ranges for each time property
    ranges = {}
    for prop in ("_created_at", "_last_updated_at", "_last_seen_at"):
        min_days, max_days = compute_time_range(nodes, prop)
        ranges[prop] = [min_days, max_days]

    full_ranges_data = previous_ranges or {}

    def _slider_outputs(prop):
        r = ranges[prop]
        lbl_min = _format_day_label(r[0])
        lbl_max = _format_day_label(r[1])
        marks = {r[0]: lbl_min, r[1]: lbl_max}
        # Preserve previous value if available, else full range
        prev = full_ranges_data.get(prop)
        value = prev if prev and prev == r else r
        return r[0], r[1], value, marks

    outputs = []
    for prop in ("_created_at", "_last_updated_at", "_last_seen_at"):
        outputs.extend(_slider_outputs(prop))

    return ranges, *outputs
```

### Step 3.2: Add label update callbacks (multi-output)

```python
@callback(
    [Output("time-slider-created-label", "children"),
     Output("time-slider-updated-label", "children"),
     Output("time-slider-seen-label", "children")],
    [Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value"),
     Input("time-filter-full-ranges", "data")],
)
def update_time_filter_labels(created_val, updated_val, seen_val, full_ranges):
    """Format the selected range as human-readable labels below each slider."""
    if not full_ranges:
        return "", "", ""

    def _label(prop, val):
        full = full_ranges.get(prop, [0, 1])
        lo = _format_day_label(val[0])
        hi = _format_day_label(val[1])
        if val == full:
            return f"All dates ({lo} – {hi})"
        return f"{lo} – {hi}"

    return (
        _label("_created_at", created_val),
        _label("_last_updated_at", updated_val),
        _label("_last_seen_at", seen_val),
    )
```

### Step 3.3: Automated tests

**Add to** `tests/test_graph_time_filter_helpers.py`:

- `test_compute_time_range_with_nodes` — mock 5 nodes with known dates, verify correct min/max
- `test_compute_time_range_no_nodes` — empty list → `(0, 1)`
- `test_compute_time_range_all_missing` — nodes without the property → `(0, 1)`
- `test_compute_time_range_single_node` — one node → min == max

**Verify**: `pytest -m unit tests/test_graph_time_filter_helpers.py -v` → all pass.

### Step 3.4: Manual verification

1. Load a graph with nodes spanning multiple months
2. Open Filters tab → expand Time Filters
3. Verify each slider shows correct min/max marks as formatted dates
4. Verify label below each slider says "All dates (Jan 15, 2026 – Mar 20, 2026)"
5. Expand a node → verify slider ranges update to new min/max
6. Start a fresh query → verify slider ranges reset to new data

### Phase 3 Done Criteria

- [ ] `update_time_filter_ranges` callback registered
- [ ] `update_time_filter_labels` callback registered
- [ ] Slider ranges dynamically update on graph load/expansion
- [ ] Formatted date labels visible
- [ ] Unit tests pass

---

## Phase 4 — Filter logic integration

### Step 4.1: Extend `_compute_filtered_graph()`

Update signature to accept 3 additional optional params:

```python
def _compute_filtered_graph(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    unfiltered_elements,
    created_range=None,    # [min, max] or None
    updated_range=None,    # [min, max] or None
    seen_range=None,       # [min, max] or None
    full_ranges=None,      # {"_created_at": [min, max], ...}
):
```

Add after node-type filtering (after `visible_nodes` is computed):

```python
    # Apply time-based filters
    time_configs = [
        ("_created_at", created_range, full_ranges),
        ("_last_updated_at", updated_range, full_ranges),
        ("_last_seen_at", seen_range, full_ranges),
    ]

    for prop, current_range, ranges in time_configs:
        if current_range is None or ranges is None:
            continue
        full = ranges.get(prop)
        if full is None or current_range == full:
            continue  # Slider at full range = no filter active

        filtered = []
        for node in visible_nodes:
            raw = node.get("data", {}).get(prop, "")
            if not raw:
                filtered.append(node)  # Missing property = include
                continue
            days = _parse_days_since_epoch(raw)
            if days is None:
                filtered.append(node)  # Unparseable = include
                continue
            if current_range[0] <= days <= current_range[1]:
                filtered.append(node)
        visible_nodes = filtered
```

Then re-check edge visibility against the new `visible_node_ids`.

### Step 4.2: Update `apply_relationship_filters()`

Add 3 new Inputs and pass through to `_compute_filtered_graph()`:

```python
@callback(
    Output("graph-cytoscape", "elements", allow_duplicate=True),
    [Input("node-type-filter", "value"),
     Input("relationship-type-filter", "value"),
     Input("weight-threshold-slider", "value"),
     Input("top-n-toggle", "value"),
     Input("unfiltered-elements-store", "data"),
     # Time filter inputs
     Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value")],
    State("time-filter-full-ranges", "data"),
    prevent_initial_call=True,
)
def apply_relationship_filters(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    unfiltered_elements,
    created_range,
    updated_range,
    seen_range,
    full_ranges,
):
    ...
    filtered_graph = _compute_filtered_graph(
        selected_node_types, selected_rel_types,
        weight_threshold, top_n_mode, unfiltered_elements,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )
```

### Step 4.3: Update `update_filter_panel_feedback()`

Add 3 new Inputs and `full_ranges` Input, pass time ranges to `_compute_filtered_graph()`:

```python
[Input("time-slider-created", "value"),
 Input("time-slider-updated", "value"),
 Input("time-slider-seen", "value"),
 Input("time-filter-full-ranges", "data")],
```

### Step 4.4: Update `_build_active_filter_chips()`

Add parameters for time ranges + full ranges. Append chips like:

```python
chip_created = _summarize_time_filter(created_range, full_ranges.get("_created_at"), "Created")
chip_updated = _summarize_time_filter(updated_range, full_ranges.get("_last_updated_at"), "Updated")
chip_seen = _summarize_time_filter(seen_range, full_ranges.get("_last_seen_at"), "Seen")
```

### Step 4.5: Update `clear_all_filters()`

Add 3 new Outputs:

```python
Output("time-slider-created", "value", allow_duplicate=True),
Output("time-slider-updated", "value", allow_duplicate=True),
Output("time-slider-seen", "value", allow_duplicate=True),
```

Add State for full ranges and reset:

```python
State("time-filter-full-ranges", "data"),
...
created_reset = full_ranges.get("_created_at", [0, 1])
updated_reset = full_ranges.get("_last_updated_at", [0, 1])
seen_reset = full_ranges.get("_last_seen_at", [0, 1])
return all_node_types, all_rel_types, 0, "all", created_reset, updated_reset, seen_reset
```

### Step 4.6: Automated tests

**Add** `tests/test_graph_time_filter_integration.py`:

- `test_compute_filtered_graph_no_time_filters` — existing filters only, verify unchanged behavior
- `test_compute_filtered_graph_created_filter` — nodes with known dates, slider narrowed → only matching nodes visible
- `test_compute_filtered_graph_missing_property_included` — nodes missing `_created_at` remain visible when slider narrowed
- `test_compute_filtered_graph_combined` — node-type filter + created filter → both applied
- `test_compute_filtered_graph_edge_visibility` — edges to hidden nodes are removed

**Verify**: `pytest -m unit tests/test_graph_time_filter_integration.py -v` → all pass.

### Step 4.7: Full integration test

```bash
pytest tests/ -m "not neo4j and not server" -v --timeout=30
```

### Phase 4 Done Criteria

- [ ] `_compute_filtered_graph()` accepts and applies time filters
- [ ] `apply_relationship_filters()` integrates time slider inputs
- [ ] `update_filter_panel_feedback()` shows correct counts with time filters active
- [ ] Filter chips display time filter state when narrowed
- [ ] "Clear All" resets all 3 time sliders
- [ ] Nodes missing a property remain visible under time filter
- [ ] Edge visibility respected after time filtering
- [ ] Unit tests pass

---

## Phase 5 — Manual end-to-end verification

### Step 5.1: Sanity checks

1. Load a graph with 50+ nodes spanning multiple months
2. Open Filters tab → expand Time Filters
3. Verify all 3 sliders show correct date ranges as marks

### Step 5.2: Filter by Created At

1. Narrow the Created At slider to a 1-month window
2. Verify only nodes created in that window are visible
3. Verify nodes without `_created_at` are still visible
4. Verify edges to hidden nodes are hidden
5. Verify filter summary shows correct count
6. Verify chip shows "Created: Jan 15 – Feb 15, 2026"

### Step 5.3: Filter by Last Updated

1. Reset all filters
2. Narrow the Last Updated slider
3. Verify behavior mirrors Created At

### Step 5.4: Filter by Last Seen

1. Reset all filters
2. Narrow the Last Seen slider
3. Verify behavior mirrors Created At

### Step 5.5: Combined filters

1. Set node-type filter to show only specific types
2. Narrow Created At slider
3. Verify both filters apply simultaneously
4. Verify chips show both active filters

### Step 5.6: Expansion behavior

1. Start with a small graph, narrow Created At
2. Double-click a visible node to expand
3. Verify slider ranges update to include new nodes from expansion
4. Verify newly loaded nodes outside the selected range are hidden
5. Verify nodes without the property from expansion are visible

### Step 5.7: Clear All

1. Apply multiple filters (node type + time)
2. Click "Clear All"
3. Verify all sliders back to full range
4. Verify all nodes visible
5. Verify chips show "No active filters"

### Phase 5 Done Criteria

- [ ] All manual test cases pass
- [ ] No console errors

---

## Files modified

| File | Change |
|------|--------|
| `src/app/dash_app/pages/graph/utils/time_helpers.py` | **NEW** — 3 date conversion helpers |
| `src/app/dash_app/pages/graph/layout.py` | Add `time-filter-full-ranges` Store + Time Filters section in `_filter_card()` |
| `src/app/dash_app/pages/graph/callbacks/filtering.py` | Extend `_compute_filtered_graph`, `apply_relationship_filters`, `update_filter_panel_feedback`, `_build_active_filter_chips`, `clear_all_filters` + 2 new callbacks (`update_time_filter_ranges`, `update_time_filter_labels`) |
| `src/app/dash_app/pages/graph/callbacks/__init__.py` | Register `toggle_time_filters_collapse` callback |
| `tests/test_graph_time_filter_helpers.py` | **NEW** — 7+ unit tests for helpers |
| `tests/test_graph_time_filter_integration.py` | **NEW** — 5 integration tests for filter logic |

## Done criteria (overall)

- [ ] All 4 phases complete with passing tests
- [ ] Manual verification covers all scenarios
- [ ] Time filter chips display correctly
- [ ] "Clear All" button resets time filters
- [ ] Nodes missing time properties remain visible
- [ ] Slider ranges refresh on expansion