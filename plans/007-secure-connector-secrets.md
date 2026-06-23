# Plan 007: Remove Secret Exposure from Connectors API
  
> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat c832d0c..HEAD -- src/app/api/connectors/v1/router.py src/app/api/connectors/v1/service.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `c832d0c`, 2026-06-23
- **Issue**: https://github.com/shuvabrata/work-behavior-analytics-ai/issues/169

## Why this matters

The Connectors API endpoints currently allow any user (by default unauthenticated) to retrieve plaintext API tokens (like GitHub and Jira tokens) by appending `?include_secrets=true` to GET requests. Exposing secrets to the frontend is fundamentally insecure and unnecessary. We must remove the ability to fetch plaintext secrets. Instead, the frontend should only receive a masked value (`********`), and when the user submits updates, the backend must ignore `"********"` so that the existing secret is preserved.

## Current state

- `src/app/api/connectors/v1/router.py` — Exposes `include_secrets` via GET endpoints.
  ```python
  # file:src/app/api/connectors/v1/router.py:60
  @router.get("/{connector_type}", response_model=ConnectorStatus)
  async def get_connector(
      connector_type: str,
      include_secrets: bool = False,
      db: AsyncSession = Depends(get_async_db),
  ):
  ```
- `src/app/api/connectors/v1/service.py` — In `save_config_item`, it checks if the value is `None` or `""` to preserve it, but we need it to also preserve it if the value is `"********"`.
  ```python
  # file:src/app/api/connectors/v1/service.py:402
          if encrypted_field:
              if value in (None, ""):
                  payload[encrypted_field] = None
              else:
                  payload[encrypted_field] = encrypt(value)
  ```

## Scope

**In scope**:
- `src/app/api/connectors/v1/router.py`
- `src/app/api/connectors/v1/service.py`

**Out of scope**:
- Frontend UI components. (The frontend already correctly treats `"********"` as an opaque string, we just need the backend to ignore it).

## Git workflow

- Branch: `advisor/007-secure-connector-secrets`
- Commit message style: `fix: remove include_secrets from API and prevent secret exposure`

## Steps

### Step 1: Ignore masked secrets in save_config_item and prepare_connector_config

In `src/app/api/connectors/v1/service.py`, update the logic so that if an incoming secret field is `"********"`, it is treated as "do not change" (same as `None` or `""`).

In `_prepare_connector_config_for_storage`:
```python
        encrypted_field = encrypted_map.get(key)
        if encrypted_field:
            if value in (None, "", "********"):
                if existing_dict.get(encrypted_field):
                    payload[encrypted_field] = existing_dict.get(encrypted_field)
            else:
                payload[encrypted_field] = encrypt(value)
```

In `save_config_item`:
```python
        encrypted_field = encrypted_map.get(key)
        if encrypted_field:
            if value in (None, "", "********"):
                payload[encrypted_field] = None
            else:
                payload[encrypted_field] = encrypt(value)
```

### Step 2: Remove include_secrets from router and service signatures

In `src/app/api/connectors/v1/router.py`:
- Remove `include_secrets: bool = False` from `get_connector` and `list_config_items` function signatures.
- Change the calls to `service.get_connector` and `service.list_config_items` to remove `include_secrets=include_secrets`.

In `src/app/api/connectors/v1/service.py`:
- Remove `include_secrets: bool = False` from `get_connector` and `list_config_items` function signatures.
- Update `_normalize_connector_config` calls to omit `include_secrets` or pass `False`.
- Update `_normalize_connector_config` definition to remove the `include_secrets` parameter entirely, so it always masks secrets.
- In `_test_atlassian_mcp_connection`, `get_connector(db, "atlassian_mcp", include_secrets=True)` will fail. We need to query the DB directly, or we can use `query.get_connector` directly.
Update `_test_atlassian_mcp_connection`:
```python
    connector_record = await query.get_connector(db, "atlassian_mcp")
    config = connector_record.config if connector_record else {}
    
    db_server_url = config.get("server_url")
    db_token = decrypt(config.get("encrypted_token")) if config.get("encrypted_token") else None
```

## Done criteria

- [ ] `include_secrets` is entirely removed from the router endpoints.
- [ ] Incoming `"********"` values for secrets do not overwrite the real secrets with the encrypted string `"********"`.
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated
