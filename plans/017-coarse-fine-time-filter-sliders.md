# Plan 017: Coarse + Fine Time Filter Sliders (Graph Page)

## Status

- **Priority**: P1 (UX — time-range filtering is imprecise on wide date ranges)
- **Effort**: M (spans 3 phases × ~6 files)
- **Risk**: LOW
- **Depends on**: None
- **Category**: UX / graph visualization
- **Planned at**: 2026-08-10
- **Status**: READY

## Why this matters

When a graph with a wide date range (e.g. 3–4 months) is loaded, the single
`dcc.RangeSlider` time filter makes it difficult to select a narrow window
because the slider track is small. This plan replaces each single slider with
a **coarse + fine pair** grouped in a muted background section. The coarse
slider picks the window, the fine slider refines within it. No new text labels
are introduced.

## Design decisions

All decisions reached via the grill-me process on 2026-08-10.

### Phase 1 — Section containers (pure layout)

- Each property (Created At / Last Updated / Last Seen) gets a muted background
  box: `--color-background-light` (#f7fafc), 2px border-radius, ~10px padding,
  no border.
- Contains: property label → coarse slider → fine slider → value label (bottom).
- The Time Filters collapse remains; the 3 sections sit inside it.

### Phase 2 — Fine slider mechanics

| Rule | Detail |
|---|---|
| **Coarse ID** | Existing `time-slider-{created,updated,seen}` (min/max = full graph range) |
| **Fine ID** | New `time-slider-{created,updated,seen}-fine` (min/max = coarse slider value) |
| **Coarse moves → fine resets** | Fine jumps to full coarse extent. Coarse drag alone = immediate coarse-level filter |
| **Effective range** | Fine slider value |
| **Inert-check** | Compare fine vs full graph range (unchanged from today) |
| **New baseline** | Query or expansion → both coarse and fine reset to full range |
| **Clear All** | Both coarse and fine reset to full range in one callback |

### Phase 3 — Visual differentiation

| Slider | Track | Color | Handle |
|---|---|---|---|
| Coarse | 4px (standard) | Navy (`--color-navy`) | 14px (standard) |
| Fine | **2px (thinner)** | **Slightly lighter navy** (~#5a7fa0) | 14px (standard) |

Label line stays at the bottom of each section, reflecting the fine slider's
value — no new text labels.

## Files to modify

| File | Change |
|---|---|
| `src/app/dash_app/pages/graph/components/sliders.py` | Rewrite `create_time_slider()` → `create_time_slider_pair()` returning a muted section div with both sliders and the label |
| `src/app/dash_app/pages/graph/layout.py` | Replace 3x `create_time_slider()` with `create_time_slider_pair()` in `_filter_card()` |
| `src/app/dash_app/pages/graph/callbacks/filtering.py` | Add fine slider outputs to `update_time_filter_ranges`; add new callback `update_fine_slider_bounds` (coarse→fine sync); update all consuming callbacks to read fine values; update `clear_all_filters` to reset fine sliders too |
| `src/app/dash_app/assets/executive-dashboard.css` | Add `.rc-slider-track.fine` (2px, lighter) and `.rc-slider-handle.fine` rules |
| `tests/test_graph_filtering_callbacks.py` | Update tests for new fine slider outputs |
| `tests/test_graph_time_filter_integration.py` | No change (tests `_compute_filtered_graph` which is unchanged) |

## Scope boundaries

- **Included**: 3 muted sections, 3 coarse + 3 fine sliders, fine-reset-on-coarse-move,
  label/chip reads fine, visual differentiation, Clear All
- **Excluded**: No new text labels, no changes to `_filter_nodes_by_time` /
  `_compute_filtered_graph` (they accept ranges generically), no tooltip changes,
  no collapse toggle changes

---

## Phase 1 — Section containers

**Goal**: Wrap each time filter property in a muted background box with the
existing single slider. Pure layout change — no behavioral changes yet.

### Tasks

- [x] **1.1** Rewrite `create_time_slider()` in `components/sliders.py` to
      `create_time_slider_pair()` that returns a `html.Div` with:
  - `style` using `--color-background-light`, `borderRadius: 2px`, `padding: 10px`
  - Property label (existing)
  - Coarse slider (existing `dcc.RangeSlider` — unchanged)
  - Fine slider (new `dcc.RangeSlider` — same min/max/value as coarse for now)
  - Value label (existing `html.Small` — unchanged)
- [x] **1.2** Update `_filter_card()` in `layout.py` to call
      `create_time_slider_pair()` instead of `create_time_slider()`.
- [x] **1.3** Update `components/__init__.py` exports.

### Automated tests

- [x] **T1.1** Verify `create_time_slider_pair` returns a `html.Div` with 4
      children (label, coarse slider, fine slider, value label).
- [x] **T1.2** Verify the fine slider's initial `min`/`max`/`value` match the
      coarse slider's `min`/`max`/`value`.
- [x] **T1.3** Verify the section div has `--color-background-light` style.

### Manual verification

- [x] **M1.1** Load a graph with a 3+ month range. Confirm 3 muted sections
      appear inside the Time Filters collapse, each with a label, one slider,
      and a date label below.
- [x] **M1.2** Confirm the existing single slider still works (drag handles,
      tooltip, label updates).

---

## Phase 2 — Fine slider mechanics

**Goal**: Wire the fine slider to track the coarse slider's bounds and become
the effective filter source. All consuming callbacks read fine values instead
of coarse values.

### Tasks

- [x] **2.1** In `filtering.py`, add new callback `update_fine_slider_bounds`:
  - **Inputs**: `time-slider-{created,updated,seen}` (coarse values)
  - **Outputs**: `time-slider-{created,updated,seen}-fine.min`,
    `time-slider-{created,updated,seen}-fine.max`,
    `time-slider-{created,updated,seen}-fine.value`
  - **Logic**: When coarse value changes, set fine min/max to coarse value,
    and reset fine value to coarse value (full coarse extent).
- [x] **2.2** Update `update_time_filter_ranges` to also output fine slider
      min/max/value/marks (same as coarse on initial load).
- [x] **2.3** Update `update_time_filter_labels` to read fine slider values
      instead of coarse slider values.
- [x] **2.4** Update `apply_relationship_filters` to read fine slider values
      instead of coarse slider values.
- [x] **2.5** Update `update_relationship_type_filter` and
      `update_node_type_filter` to read fine slider values instead of coarse.
- [x] **2.6** Update `update_filter_panel_feedback` to read fine slider values
      instead of coarse.
- [x] **2.7** Update `clear_all_filters` to output fine slider reset values
      (same as coarse reset values).
- [ ] **2.8** Update `_build_active_filter_chips` / `_summarize_time_filter`
      — no change needed (they receive range values generically).

### Automated tests

- [x] **T2.1** Test `update_fine_slider_bounds`: coarse [30, 75] → fine
      min=30, max=75, value=[30, 75].
- [x] **T2.2** Test `update_fine_slider_bounds`: coarse [61, 106] → fine
      min=61, max=106, value=[61, 106].
- [x] **T2.3** Test `update_time_filter_labels` reads fine values (not coarse)
      for label text.
- [x] **T2.4** Test `clear_all_filters` resets both coarse and fine to full
      range.
- [x] **T2.5** Test `apply_relationship_filters` uses fine values for
      `_filter_nodes_by_time` (integration test with known data).

### Manual verification

- [ ] **M2.1** Load a graph. Drag coarse slider to a narrow window. Confirm
      fine slider resets to match coarse extent. Confirm graph filters to
      coarse window.
- [ ] **M2.2** Drag fine slider within the coarse window. Confirm graph
      narrows further. Confirm label updates to fine range.
- [ ] **M2.3** Drag coarse slider again. Confirm fine resets to new coarse
      extent (previous fine selection discarded).
- [ ] **M2.4** Click "Clear All". Confirm both coarse and fine reset to full
      range. Confirm label shows "All dates".
- [ ] **M2.5** Expand a node (double-click). Confirm both sliders reset to
      new full range.

---

## Phase 3 — Visual differentiation

**Goal**: Make the coarse and fine sliders visually distinct without adding
text labels.

### Tasks

- [ ] **3.1** Add CSS rules in `executive-dashboard.css`:
  ```css
  .graph-filter-card .rc-slider-track.fine-track {
      background-color: #5a7fa0;
      height: 2px;
  }
  .graph-filter-card .rc-slider-handle.fine-handle {
      /* Inherits standard 14px size, but track is thinner */
  }
  ```
  (Fine slider uses the same handle size; only the track is thinner and
  lighter. The CSS class is applied via the fine slider's `className` prop.)
- [ ] **3.2** In `sliders.py`, add `className="fine-track"` to the fine
      slider's track and `className="fine-handle"` to its handle via
      `dcc.RangeSlider` props (Dash supports `trackStyle` and `handleStyle`
      for per-slider overrides, or use a wrapper div with a class that
      scopes the CSS).
- [ ] **3.3** Verify no regressions in dark theme — the lighter blue should
      still be visible against `--color-background-light` in both themes.

### Automated tests

- [ ] **T3.1** Verify fine slider has `className` containing `fine-track` /
      `fine-handle` (or equivalent style props).

### Manual verification

- [ ] **M3.1** Visually confirm coarse slider has standard navy track (4px)
      and fine slider has thinner (2px) lighter blue track.
- [ ] **M3.2** Toggle to dark theme. Confirm both sliders remain visible and
      distinguishable.
- [ ] **M3.3** Confirm no regressions in any existing slider behavior
      (tooltip, drag, label, Clear All, expansion).

---

## Rollback

If any phase introduces a regression, revert the changes for that phase only:

```bash
# Phase 1 revert
git checkout -- src/app/dash_app/pages/graph/components/sliders.py
git checkout -- src/app/dash_app/pages/graph/layout.py

# Phase 2 revert
git checkout -- src/app/dash_app/pages/graph/callbacks/filtering.py

# Phase 3 revert
git checkout -- src/app/dash_app/assets/executive-dashboard.css
```

Each phase is independently testable and revertable.
