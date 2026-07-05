# Plan 001: Remove `include_secrets` from public API routes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat ec14dc5..HEAD -- src/app/api/connectors/v1/router.py src/app/api/connectors/v1/service.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P0
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `ec14dc5`, 2026-06-26

## Why this matters

The `include_secrets=true` query parameter on `GET /connectors/{type}` and
`GET /connectors/{type}/configs` returns decrypted plaintext credentials
(GitHub tokens, Jira API tokens, email passwords) in the HTTP response body.
There is **no authentication** on these endpoints. Anyone with network access
to the API can steal all stored credentials.

Removing this parameter from the public-facing router eliminates the exposure
while preserving internal server-side access for connection testing.

## Current state

The relevant files and their roles:

- `src/app/api/connectors/v1/router.py` — FastAPI route definitions for connector CRUD
- `src/app/api/connectors/v1/service.py` — Business logic layer for connector operations

**Router — public routes that accept `include_secrets`** (lines 59–68):
```python
@router.get("/{connector_type}", response_model=ConnectorStatus)
async def get_connector(
    connector_type: str,
    include_secrets: bool = False,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.get_connector(db, connector_type, include_secrets=include_secrets)
```

And (lines 94–104):
```python
@router.get("/{connector_type}/configs", response_model=List[Dict[str, Any]])
async def list_config_items(
    connector_type: str,
    # TODO: This should be based on user permissions, not an explicit query parameter.
    include_secrets: bool = False,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.list_config_items(db, connector_type, include_secrets=include_secrets)
```

**Service — internal caller that needs secrets** (`service.py:485`):
```python
async def _test_atlassian_mcp_connection(db: AsyncSession, now: datetime) -> Dict[str, Any]:
    connector = await get_connector(db, "atlassian_mcp", include_secrets=True)
```

This internal call must continue to work. The fix is to keep `include_secrets` on the
service function but remove it from the router (public API surface).

## Commands you will need

| Purpose   | Command                                     | Expected on success |
|-----------|---------------------------------------------|---------------------|
| Tests     | `python -m pytest tests/test_connectors_service.py -v` | all pass |
| Typecheck | `python -m mypy src/app/api/connectors/v1/router.py --ignore-missing-imports` | exit 0 or pre-existing errors only |
| Grep      | `grep -n "include_secrets" src/app/api/connectors/v1/router.py` | no matches |

## Scope

**In scope** (the only files you should modify):
- `src/app/api/connectors/v1/router.py`
- `tests/test_connectors_service.py` (if it tests `include_secrets` via the router)

**Out of scope** (do NOT touch):
- `src/app/api/connectors/v1/service.py` — the service layer's `include_secrets` parameter stays, because internal callers (e.g., `_test_atlassian_mcp_connection`) use it.
- Any other router or service file.

## Steps

### Step 1: Remove `include_secrets` from `get_connector` route

In `src/app/api/connectors/v1/router.py`, change the `get_connector` function
(around line 59) to remove the `include_secrets` parameter and always pass
`include_secrets=False` to the service:

```python
@router.get("/{connector_type}", response_model=ConnectorStatus)
async def get_connector(
    connector_type: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.get_connector(db, connector_type)
```

**Verify**: `grep -n "include_secrets" src/app/api/connectors/v1/router.py` — should return only the `list_config_items` match (step 2 will fix that).

### Step 2: Remove `include_secrets` from `list_config_items` route

In the same file, change the `list_config_items` function (around line 94):

```python
@router.get("/{connector_type}/configs", response_model=List[Dict[str, Any]])
async def list_config_items(
    connector_type: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.list_config_items(db, connector_type)
```

Remove the TODO comment as well — it's resolved by this change.

**Verify**: `grep -n "include_secrets" src/app/api/connectors/v1/router.py` → no matches.

### Step 3: Update tests if needed

Check `tests/test_connectors_service.py` for any test that passes `include_secrets` via the router (e.g., via `TestClient`). If found, update to not pass the parameter.

**Verify**: `python -m pytest tests/test_connectors_service.py -v` → all pass.

## Test plan

- Existing tests in `test_connectors_service.py` should continue to pass (they test the service layer, not the router).
- If router-level tests exist, they should no longer pass `include_secrets=true`.
- **Verification**: `python -m pytest tests/test_connectors_service.py -v` → all pass.

## Done criteria

- [ ] `grep -rn "include_secrets" src/app/api/connectors/v1/router.py` returns no matches
- [ ] `python -m pytest tests/test_connectors_service.py -v` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations in "Current state" doesn't match the excerpts.
- The service's `_test_atlassian_mcp_connection` or any other internal caller breaks because it routes through the public endpoint instead of calling the service function directly.
- Any test that directly tests the router's `include_secrets` behavior cannot be trivially updated.

## Maintenance notes

- When auth is eventually added (Plan 004), the `include_secrets` parameter could be re-introduced gated behind an admin role. Until then, secrets must only be read server-side.
- The service layer's `include_secrets` parameter remains for internal use — do not remove it.
