# Plan 005: Add timeout to MCP client thread join

> **Executor instructions**: Follow this plan step by step.
>
> **Drift check (run first)**: `git diff --stat ec14dc5..HEAD -- src/app/ai_agent/mcp_integration/client_manager.py`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `ec14dc5`, 2026-06-26

## Why this matters

`_MCPClientBase._run_sync` spawns a daemon thread to bridge async MCP SDK
calls into synchronous code. The thread is joined with no timeout
(`worker.join()` at line 54). If the MCP server hangs, the calling thread
blocks indefinitely — no timeout propagates from the HTTP client to the
thread join.

## Current state

- `src/app/ai_agent/mcp_integration/client_manager.py` — lines 35–57.

```python
    def _run_sync(self, async_fn, *args):
        ...
        worker = Thread(target=_runner, daemon=True)
        worker.start()
        ok, value = result_queue.get()
        worker.join()          # <-- no timeout
        if ok:
            return value
        raise value
```

## Scope

**In scope**: `src/app/ai_agent/mcp_integration/client_manager.py`

## Steps

### Step 1: Add timeout to `worker.join()` and `result_queue.get()`

Replace (around lines 52-57):
```python
        worker = Thread(target=_runner, daemon=True)
        worker.start()
        ok, value = result_queue.get()
        worker.join()
        if ok:
            return value
        raise value
```

with:
```python
        join_timeout = self.request_timeout_seconds + 10
        worker = Thread(target=_runner, daemon=True)
        worker.start()
        try:
            ok, value = result_queue.get(timeout=join_timeout)
        except Exception:
            raise TimeoutError(
                f"MCP operation timed out after {join_timeout}s"
            )
        worker.join(timeout=5)
        if ok:
            return value
        raise value
```

**Verify**: `grep -n "join_timeout" src/app/ai_agent/mcp_integration/client_manager.py` → visible.

### Step 2: Run tests

**Verify**: `python -m pytest tests/test_chains_mcp_composition.py tests/test_provider_tool_contract.py -v` → all pass.

## Done criteria

- [ ] `grep -n "timeout" src/app/ai_agent/mcp_integration/client_manager.py` shows timeout on both `get()` and `join()`
- [ ] Tests pass

## STOP conditions

- The `_run_sync` method has been significantly restructured.
