# Connector Detail Page — UI Improvement Plan

## Overview

Refactor the GitHub connector detail page layout and card rendering for better UX. Changes are organized into small, independently verifiable phases.

---

## Phase 1 — Reorder Sections in `get_detail_layout()`

**Files:** `src/app/dash_app/pages/connectors/layout.py`

**Changes:**
1. Move the **action buttons** (`Test Connection`, `Delete Configuration`) to the top of the page, grouped in a horizontal bar.
2. Move **Run Scan** button into the same top action bar (since it's the most-used button).
3. Move **Recent Scans** section to position #2 (right below the action bar).
4. Move **Add New Repository** section to position #3.
5. Keep **Repository Cards** (items list) at position #4.
6. Keep **Global Configuration** (Connector Settings + Save button) at position #5.

**Resulting section order:**
```
Feedback (sticky)
────────────────────
[ Run Scan ] [ Delete Configuration ]     ← Top Action Bar
────────────────────
Recent Scans                              ← Always visible
────────────────────
+ Add New Repository                      ← Collapsible, collapsed by default
────────────────────
Repository Cards                          ← List of configured repos
────────────────────
Connector Settings                        ← Global config + Save button
────────────────────
```

**Validation:** Navigate to `/app/connectors/github` — sections should appear in the order above. No visual polish yet, just structural reordering.

---

## Phase 2 — Collapsible "Add New Repository" Section

**Files:** `src/app/dash_app/pages/connectors/layout.py`

**Changes:**
1. Wrap the "Add New Repository" form in a `dbc.Collapse(is_open=False)`.
2. Replace the static section title with a clickable `collapse-toggle-subtle` header.
3. Use a `+` icon (not chevron) to signal "add new" intent.
4. Add a callback to toggle the collapse on header click.

**Validation:** Page loads with the form hidden. Clicking `+ Add New Repository` expands the form. Clicking again collapses it.

---

## Phase 3 — Repository Cards: Two-Column Field Layout

**Files:** `src/app/dash_app/pages/connectors/callbacks.py` (the `render_items_list` function)

**Changes:**
1. Replace the single-column vertical field list with a `dbc.Row` 2-column grid.
2. Field order per row (matching the form):
   ```
   Row 1: [ url                      | (empty — access_token hidden) ]
   Row 2: [ branch_name_patterns     | extraction_sources            ]
   Row 3: [ (empty)                  | search_filters                ]
   ```
3. Each cell shows `Label: Value` with the same typography as before.
4. `search_filters` renders as compact key:value tags.

**Validation:** Each repository card shows fields in a 2-column grid matching the form layout. Empty cells are truly empty (no placeholder text).

---

## Phase 4 — Add "Test Connection" to Each Repository Card

**Files:** `src/app/dash_app/pages/connectors/callbacks.py` (the `render_items_list` function)

**Changes:**
1. Add a `Test Connection` button to each card's action footer.
2. Placement: `[ Test Connection | Edit | Delete ]` left-aligned, `Active toggle` right-aligned.
3. Add a callback to handle per-card test connection (POST to `/api/v1/connectors/{type}/configs/{id}/test` or similar endpoint — verify endpoint exists).

**Validation:** Each card has a `Test Connection` button. Clicking it shows a success/failure alert in the feedback area.

---

## Phase 5 — Visual Polish: Section Containers & Feedback Area

**Files:** `src/app/dash_app/pages/connectors/layout.py`

**Changes:**
1. Wrap each major section in a subtle container with a left navy accent border (matching `FEATURE_CARD_STYLE` pattern from `styles.py`):
   - Top Action Bar
   - Recent Scans
   - Add New Repository
   - Repository Cards list
   - Global Configuration
2. Style the sticky feedback area with a subtle background and shadow so it doesn't blend into the page.
3. Ensure consistent spacing between sections.

**Validation:** Each section is visually distinct with a left navy border. The feedback area is elevated and noticeable.

---

## Phase 6 — Search Filters: Right Column in Form & Card

**Files:** `src/app/dash_app/pages/connectors/layout.py` + `callbacks.py`

**Changes:**
1. In `_render_item_form()`: move the search filters editor to the right column of the form grid (alongside an empty left column).
2. In `render_items_list()`: render `search_filters` in the right column of row 3 in the card grid.
3. Search filters display as compact tags/badges in the card (e.g., `props.division: platform`).

**Validation:** In both the add form and the card display, search filters appear in the right column on row 3.

---

## Phase 7 — Cleanup & Edge Cases

**Files:** Various

**Changes:**
1. Verify the `connector-action-feedback` key uses a stable ID (remove `uuid.uuid4()` from the key to prevent unnecessary remounting).
2. Ensure the "Clear Form" button resets the collapse state.
3. Verify scan polling interval re-enables when scans are visible.
4. Test with 0, 1, and many repositories.
5. Test with non-GitHub connectors (Jira, Confluence) to ensure no regression.

**Validation:** All edge cases pass. Non-GitHub connectors remain unaffected.