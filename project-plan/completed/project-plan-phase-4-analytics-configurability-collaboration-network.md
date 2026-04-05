# Project Plan: Make Analytics Configurable

**Status**: Completed (ready for single PR)
**Created**: April 5, 2026
**Scope**: Collaboration Network configurability from Analytics UI to Cypher execution

## Overview

This work makes the Collaboration Network analytics flow configurable end-to-end.

Users can now:
1. Choose which collaboration layers are included.
2. Adjust weight per layer.
3. Configure additional controls (time window, score floor, bot filtering, top-N edge density).
4. Launch the visualization with those options from the Analytics page.

The implementation preserves the original defaults while enabling runtime overrides through query-string parameters.

## Goals Completed

1. Add runtime configuration model for Collaboration Network.
2. Parameterize the main collaboration Cypher query.
3. Wire configurable options through backend endpoint and service.
4. Add Analytics UI controls for configuration before launch.
5. Add graph rendering support for URL-driven configuration.
6. Add tests for config parsing, graph filtering, and layer-by-layer DB validation.
7. Keep a default static query snapshot for manual testing.

## Design Summary

### 1. Shared configuration model

Added [app/analytics/collaboration/config.py](app/analytics/collaboration/config.py) as the single source of truth for:
1. Layer keys and labels.
2. Default weights.
3. Default values for lookback days, min pair score, bot filtering, file suffix exclusions, and top-N behavior.
4. Query-string style parsing via `from_query_values`.
5. Neo4j parameter mapping via `to_cypher_parameters`.
6. Config echo payload for UI/debug via `to_summary`.

### 2. Cypher query parameterization

Updated [app/analytics/collaboration/queries/collaboration_score.cypher](app/analytics/collaboration/queries/collaboration_score.cypher):
1. Added per-layer toggles (`include_*`).
2. Added per-layer weights (`weight_*`).
3. Replaced fixed `P90D` with configurable lookback days.
4. Replaced hardcoded score floor with `min_pair_score`.
5. Added `exclude_bots` switch.
6. Replaced hardcoded file suffix filters with configurable list.

Kept a static default snapshot in [app/analytics/collaboration/queries/collaboration_score,cypher.default](app/analytics/collaboration/queries/collaboration_score,cypher.default) for manual execution and baseline comparisons.

### 3. Backend wiring

Updated [app/api/graph/v1/query.py](app/api/graph/v1/query.py):
1. `execute_cypher_query` now accepts optional query parameters.

Updated [app/api/graph/v1/service.py](app/api/graph/v1/service.py):
1. `get_collaboration_network` now accepts config input.
2. Passes config-derived parameters into Cypher execution.
3. Applies optional top-N edge filtering before Louvain detection.
4. Returns applied config in API response.

Updated [app/api/graph/v1/router.py](app/api/graph/v1/router.py):
1. `GET /api/v1/graph/collaboration-network` now accepts query params for layers, weights, and advanced options.
2. Builds config from request params.
3. Adds validation error handling for malformed config input.

Updated [app/api/graph/v1/model.py](app/api/graph/v1/model.py):
1. `CollaborationNetworkResponse` now includes `config` payload.

### 4. Graph analytics behavior

Updated [app/analytics/collaboration/algorithm.py](app/analytics/collaboration/algorithm.py):
1. Added `filter_top_edges_per_node` to reduce graph density.
2. Supports optional `ensure_min_connection` behavior.

Updated [app/dash_app/pages/graph/callbacks/collaboration.py](app/dash_app/pages/graph/callbacks/collaboration.py):
1. Parses URL parameters into config.
2. Calls collaboration service with parsed config.
3. Updates banner to display applied lookback, layer count, and top-N status.

Updated [app/analytics/collaboration/tune.py](app/analytics/collaboration/tune.py):
1. Runs parameterized query with default config parameters so tuner stays compatible.

### 5. Analytics page UX

Updated [app/dash_app/pages/analytics.py](app/dash_app/pages/analytics.py):
1. Added Collaboration-specific controls on the card:
- Layer selection
- Per-layer weights
- Lookback days
- Min pair score
- Top-N edges per node
- Exclude bots toggle
- Ensure min connection toggle
2. Open button now builds a query-string URL from current settings.
3. Added URL preview for transparency/debugging.
4. Added collapsible controls (hidden by default) to keep card compact:
- `Open Visualization` always visible
- `Show Options` / `Hide Options` toggle

## Test Coverage Added

### Unit tests

Updated [tests/test_collaboration_algorithm.py](tests/test_collaboration_algorithm.py):
1. Added tests for top-N edge filtering behavior.

Added [tests/test_collaboration_config.py](tests/test_collaboration_config.py):
1. Defaults and parsing validation.
2. Per-layer weight override validation.
3. Cypher parameter mapping validation.
4. Invalid layer rejection.

### Integration tests

Updated [tests/test_collaboration_query_integration.py](tests/test_collaboration_query_integration.py):
1. Runs single-layer query validation per layer (parameterized over all layers).
2. Prints fully rendered Cypher text for each layer run.
3. Uses explicit opt-in guard for live DB validation:
- Requires `NEO4J_ENABLED=true`
- Requires `RUN_COLLAB_DB_VALIDATION=1`

## Validation Commands

### Run standard test suite

```bash
pytest tests/
```

### Run layer-by-layer DB validation (with printed rendered query)

```bash
source .venv/bin/activate
RUN_COLLAB_DB_VALIDATION=1 pytest tests/test_collaboration_query_integration.py -q -s
```

## Key Finding During Validation

The Reporter-Assignee layer can return zero rows in current data snapshots when run in isolation. This behavior was reproduced through integration testing and explains the observed UI error for that specific single-layer selection.

This indicates a data availability/shape issue for that layer and time window, not necessarily a UI parsing bug.

## Backward Compatibility

1. Default behavior remains equivalent to original query when using all defaults.
2. Legacy graph mode compatibility remains intact.
3. Static query snapshot preserved for manual runs.

## Potential Follow-ups

1. Add per-layer row-count diagnostics endpoint (or banner details) to improve user feedback when a selected layer has no data.
2. Add UI warning when only one layer is selected and returns zero rows.
3. Add optional fallback behavior to auto-broaden lookback window for empty single-layer results.

## PR Packaging Note

This document is intended as the implementation record for the single PR that introduces Collaboration Network configurability and associated tests/UI improvements.
