# Plan 002: Fix swallowed exceptions in critical paths

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 5b3a7f7..HEAD -- src/app/ai_agent/mcp_integration/client_manager.py src/app/dash_app/pages/search.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `5b3a7f7`, 2026-06-23

## Why this matters

The application contains several places where `Exception` is caught and implicitly swallowed by returning defaults or doing nothing. In AI agent workflows and UI layers, silent failures obscure the root cause of issues, making debugging in production extremely difficult. We need to add proper logging and context propagation so that errors are observable without breaking the fallback behaviors.

## Current state

- `src/app/ai_agent/mcp_integration/client_manager.py` (lines 148-150): The `list_tools` method swallows exceptions entirely and returns an empty list `[]`.
- `src/app/dash_app/pages/search.py` (lines 170-173): The `_format_event_time` helper catches `Exception` and returns the unformatted string without logging the parsing failure.

Conventions to follow:
Use the existing logger imported at the top of the files. For example, `logger.exception("Failed to do X")` or `logger.warning("Failed to do X: %s", exc)`.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `pytest -m unit tests/`  | all pass            |
| Lint      | `pylint src/app/ai_agent/mcp_integration/client_manager.py src/app/dash_app/pages/search.py` | exit 0 |

## Scope

**In scope**:
- `src/app/ai_agent/mcp_integration/client_manager.py`
- `src/app/dash_app/pages/search.py`

**Out of scope**:
- Exceptions swallowed with explicit `# noqa` comments that indicate intentional ignoring (e.g., `tool_executor.py`).
- Changing the return types or signatures of the affected functions.

## Git workflow

- Branch: `advisor/002-fix-swallowed-exceptions`
- Commit message: `fix: add logging to swallowed exceptions in client manager and search`

## Steps

### Step 1: Add logging to `client_manager.py`

Locate `except Exception:` in `list_tools` for `GithubMCPClientManager` (around line 149). Change it to log the exception before returning the empty list:
```python
        except Exception as exc:
            logger.exception("Failed to list tools from GitHub MCP server: %s", exc)
            return []
```
Locate `except Exception:` in `list_tools` for `AtlassianMCPClientManager` (around line 275). Change it similarly:
```python
        except Exception as exc:
            logger.exception("Failed to list tools from Atlassian MCP server: %s", exc)
            return []
```

**Verify**: `pytest -m unit tests/` → tests pass

### Step 2: Add logging to `search.py`

Locate `_format_event_time` in `src/app/dash_app/pages/search.py` (around line 171). Change the `except Exception:` block to log a warning:
```python
    except Exception as exc:
        logger.warning("Failed to parse event time '%s': %s", event_time_str, exc)
        return event_time_str
```

**Verify**: `pytest -m unit tests/` → tests pass

## Test plan

- No new tests are strictly required since this only adds logging to existing error paths.
- Existing unit tests must continue to pass.
- Verification: `pytest -m unit tests/` → all pass.

## Done criteria

- [ ] `pylint` reports no new errors in the modified files.
- [ ] `pytest -m unit tests/` exits 0.
- [ ] Swallowed exceptions in the target functions now include `logger` calls.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- The structure of `list_tools` or `_format_event_time` has changed such that the except blocks no longer exist.
- The logger is not available in the module and cannot be imported without creating circular dependencies.

## Maintenance notes

- Reviewers should ensure that the added logging does not expose PII or sensitive secrets. `exc` should be safe to log.
