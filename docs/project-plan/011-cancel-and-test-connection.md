# Plan 011: Cancel Scan + Test Connection via RabbitMQ

> **Executor instructions**: This plan is structured in sequential phases. Each phase
> has its own implementation checklist, automated test requirements, and manual
> verification steps. Complete phases in order — later phases depend on earlier ones.
> Mark each task `[ ]` → `[x]` as you complete them. Update the status table at the
> top when wrapping up each phase.

> **Reference documents**: During implementation, always consult the following
> documents for project conventions, patterns, and design constraints:
> - [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) —
>   project-wide rules (imports, code style, testing, architecture patterns)
> - [`docs/design/`](../docs/design/) — all design documents in this folder,
>   including the high-level design, design system, frontend design spec,
>   activity signal spec, producer/consumer development guides, RabbitMQ
>   topology, graph DB schema, relationship design, index strategy, and
>   GitHub API optimization notes.
> - [`docs/project-plan/completed/command-and-control-scan-triggering.md`](completed/command-and-control-scan-triggering.md) —
>   the existing command-and-control implementation that this plan extends.

---

## Status

| Phase | Title | Effort | Status |
|-------|-------|--------|--------|
| 1 | Model updates — `"cancelled"` status + `_find_pid_by_command_id` | XS | ✅ DONE |
| 2 | Daemon — cancel scan implementation | S | ✅ DONE |
| 3 | Daemon — test connection infrastructure | M | ✅ DONE |
| 4 | Producer test functions (github, jira, confluence) | M | ✅ DONE |
| 5 | API layer — allow `test` and `cancel` command types | XS | ✅ DONE |
| 6 | UI — inline cancel button on scan rows | S | ✅ DONE |
| 7 | UI — per-item Test Connection via commands API | S | ✅ DONE |
| 8 | Full integration verification | M | ⬜ PENDING |

---

## TL;DR

Extend the existing command-and-control system (Plan 010) with two new workflows:

1. **Cancel Scan**: Add a `"cancelled"` terminal status. The daemon handles
   `command_type: "cancel"` by looking up the child PID via a reverse helper,
   sending SIGTERM, and PATCHing both the scan and cancel command statuses.
   The UI gets an inline "Cancel" button on each running/accepted scan row.

2. **Test Connection**: Add `command_type: "test"` handled by the daemon.
   Each producer gets a `test_connection()` async function that loads config
   (same as scan), makes a lightweight API call, and prints result to stdout.
   The daemon spawns test children with `stdout=PIPE`, polls them on each
   loop iteration, and PATCHes the result. The existing per-item "Test
   Connection" button is repurposed to POST to `/api/v1/commands/` with
   `parameters.item_id`. Test results appear in the same "Recent Scans"
   section alongside scan results.

---

## Decisions Log (from design interview)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Cancel — how to find child PID by command_id | Add `_find_pid_by_command_id()` helper (linear scan on `_children` dict) | Avoids maintaining two dicts; `_children` stays `pid→command_id` for optimal reaping; max 5 entries makes linear scan trivially cheap |
| 2 | Cancel — how does cancel command carry target scan ID | `parameters.cancel_command_id` in the `CommandEnvelope` | `parameters` is already `dict[str, Any]` for flexible payloads; avoids semantic pollution of the envelope schema |
| 3 | Cancel — new status value | Add `"cancelled"` to `CommandStatusValue` and `_VALID_TRANSITIONS` (terminal from `"running"` / `"accepted"`) | Clean terminal state; UI can render distinct icon |
| 4 | Cancel — who sets the "cancelled" status | Daemon, after sending SIGTERM to child | Child may die before it can PATCH; daemon already has `_update_status()` for the max-concurrency-rejection path |
| 5 | Cancel — does the cancel command itself reach terminal state | Yes — daemon PATCHes cancel command to `"completed"` after killing child | Keeps command list honest; no dangling `"accepted"` rows |
| 6 | Test — where does test logic live | `--mode test` on existing `main.py`; `producer_main()` gets a new `test_func` parameter | Consistent CLI; reuses existing config loading; no new entry points |
| 7 | Test — test function signature | `async def test_connection() -> tuple[bool, str]` — loads config same as scan, bails after connectivity check, prints result to stdout | Self-contained; follows same pattern as `main_async` |
| 8 | Test — how does daemon capture result | `subprocess.Popen(stdout=PIPE)`, store in `_test_children` dict, poll `.poll()` on each loop iteration | Non-blocking — daemon stays responsive during 30s HTTP timeouts; no threading complexity |
| 9 | Test — how to identify which config item to test | `parameters.item_id` in the command envelope; test function loads all configs via `load_config_from_server()`, filters to matching item | No secrets in RabbitMQ messages; reuses existing config loading |
| 10 | Test — where does the button live | Replace the existing per-item "Test Connection" button to POST to `/api/v1/commands/` with `command_type: "test"` | Old stub endpoint was never truly functional for producers; strict upgrade |
| 11 | Test — where do results appear | Same "Recent Scans" section as scan results | No new UI section needed; polling already works; `render_scan_item` shows command_type |
| 12 | Cancel — where does cancel button live | Inline cancel button on each running/accepted scan row in "Recent Scans" | Precise — user cancels a specific scan; natural placement |

---

## Phase 1: Model Updates — `"cancelled"` Status + Reverse Lookup Helper

### What

Add the `"cancelled"` terminal status to the shared models and the daemon's
state transition validation. Add the `_find_pid_by_command_id()` helper to
the daemon for cancel lookup.

### Files to modify

#### `src/common/command_n_control/models.py`

- Add `"cancelled"` to `CommandStatusValue` literal type:

```python
CommandStatusValue = Literal[
    "accepted",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]
```

#### `src/app/api/commands/v1/service.py`

- Add `"cancelled"` to `_VALID_TRANSITIONS`:

```python
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "failed"},
    "accepted": {"running", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}
```

#### `src/connectors/producers/daemon_common.py`

- Add `_find_pid_by_command_id()` helper:

```python
def _find_pid_by_command_id(command_id: uuid.UUID) -> int | None:
    """Linear scan of ``_children`` — max 5 entries, trivially cheap."""
    for pid, cid in _children.items():
        if cid == command_id:
            return pid
    return None
```

### Tests to write (unit, `@pytest.mark.unit`)

| Test | What it verifies |
|---|---|
| `test_cancelled_status_in_literal` | `"cancelled"` is accepted by `CommandStatusValue` |
| `test_cancelled_status_update_model` | `CommandStatusUpdate(status="cancelled")` validates |
| `test_cancelled_transition_from_running` | `"running" → "cancelled"` is valid |
| `test_cancelled_transition_from_accepted` | `"accepted" → "cancelled"` is valid |
| `test_cancelled_transition_from_completed` | `"completed" → "cancelled"` raises ValueError |
| `test_find_pid_by_command_id_found` | Returns PID for known command_id |
| `test_find_pid_by_command_id_not_found` | Returns None for unknown command_id |
| `test_find_pid_by_command_id_empty` | Returns None when `_children` is empty |

### Manual verification

1. Run unit tests: `pytest -m unit tests/ -q -k "cancelled or find_pid"`
2. Verify `"cancelled"` appears in the literal type (IDE autocomplete)

### Phase 1 progress

- [x] `src/common/command_n_control/models.py` — `"cancelled"` added to `CommandStatusValue`
- [x] `src/app/api/commands/v1/service.py` — `"cancelled"` added to `_VALID_TRANSITIONS`
- [x] `src/connectors/producers/daemon_common.py` — `_find_pid_by_command_id()` added
- [x] Unit tests written and passing
- [x] `pylint` on modified files — no errors
- [x] `mypy` on modified files — no errors
- [x] Regression: existing unit tests still pass

---

## Phase 2: Daemon — Cancel Scan Implementation

### What

Implement the cancel command handler in the daemon. When a `command_type:
"cancel"` message arrives, the daemon looks up the child PID by
`parameters.cancel_command_id`, sends SIGTERM, reaps the child, and PATCHes
both the scan and cancel command statuses.

### Files to modify

#### `src/connectors/producers/daemon_common.py`

Replace the cancel stub in `run_daemon()`:

```python
elif envelope.command_type == "cancel":
    cancel_command_id = envelope.command_id
    target_command_id_str = (envelope.parameters or {}).get("cancel_command_id")
    if not target_command_id_str:
        logger.warning("Cancel command missing cancel_command_id parameter")
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message="Missing cancel_command_id parameter",
        ))
        channel.basic_ack(method_frame.delivery_tag)
        continue

    try:
        target_command_id = uuid.UUID(str(target_command_id_str))
    except ValueError:
        logger.warning("Invalid cancel_command_id: %s", target_command_id_str)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=f"Invalid cancel_command_id: {target_command_id_str}",
        ))
        channel.basic_ack(method_frame.delivery_tag)
        continue

    pid = _find_pid_by_command_id(target_command_id)
    if pid is None:
        logger.info("No running scan found for command_id=%s", target_command_id)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"message": f"No running scan found for {target_command_id}"},
        ))
        channel.basic_ack(method_frame.delivery_tag)
        continue

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to pid=%d for command_id=%s", pid, target_command_id)
        # Remove from _children so reaper doesn't double-log
        _children.pop(pid, None)
        # Mark the scan as cancelled
        _update_status(target_command_id, CommandStatusUpdate(
            status="cancelled", completed_at=datetime.now(timezone.utc),
        ))
        # Mark the cancel command as completed
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"cancelled_command_id": str(target_command_id)},
        ))
    except ProcessLookupError:
        logger.warning("Process pid=%d already exited for command_id=%s", pid, target_command_id)
        _children.pop(pid, None)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"message": f"Process already exited for {target_command_id}"},
        ))
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_cancel_with_valid_command_id` | SIGTERM sent to correct PID, status PATCHed to "cancelled" |
| Unit | `test_cancel_missing_parameter` | Status=failed, error message set |
| Unit | `test_cancel_invalid_uuid` | Status=failed, error message set |
| Unit | `test_cancel_no_running_scan` | Cancel command completed, scan not found message |
| Unit | `test_cancel_process_already_exited` | ProcessLookupError handled gracefully |
| Unit | `test_cancel_unknown_command_type` | Unknown type discarded, no spawn |
| Int | `test_cancel_end_to_end` | POST cancel → RabbitMQ → daemon kills child → scan status=cancelled |

### Manual verification

1. Start a producer daemon: `python src/connectors/producers/github/main.py`
2. Send a scan command: `curl -X POST http://localhost:8000/api/v1/commands/ -H "Content-Type: application/json" -d '{"command_type":"scan","target":"github-producer"}'`
3. Immediately send a cancel: `curl -X POST http://localhost:8000/api/v1/commands/ \
  -H "Content-Type: application/json" \
  -d '{"command_type":"cancel","target":"github-producer","parameters":{"cancel_command_id":"<scan_command_id>"}}' \
  | jq`
4. Verify scan status = "cancelled" via GET
5. Verify cancel command status = "completed" via GET
6. Test cancel on non-existent command_id → cancel shows "completed" with "no running scan" message

### Phase 2 progress

- [x] `src/connectors/producers/daemon_common.py` — cancel handler implemented (`_cancel_scan()` function)
- [x] Unit tests written and passing
- [x] Manual verification: cancel flow works end-to-end
- [x] `pylint` — no errors (score 9.86/10)
- [x] `mypy` on modified files — no errors (pre-existing stubs only)
- [x] Regression: existing unit tests still pass

---

## Phase 3: Daemon — Test Connection Infrastructure

### What

Add `--mode test` CLI dispatch, `test_func` parameter to `producer_main()`,
and the `_test_children` polling infrastructure to the daemon.

### Files to modify

#### `src/connectors/producers/daemon_common.py`

1. Add `_test_children` dict alongside `_children`:

```python
_test_children: Dict[int, tuple[uuid.UUID, subprocess.Popen]] = {}  # pid → (command_id, Popen)
```

2. Add `_poll_test_children()` function called on each daemon loop iteration:

```python
def _poll_test_children() -> None:
    """Poll all test child processes and PATCH status when they finish."""
    for pid in list(_test_children.keys()):
        command_id, popen_obj = _test_children[pid]
        if popen_obj.poll() is not None:
            stdout, stderr = popen_obj.communicate()
            message = (stdout or stderr or "").strip()
            success = popen_obj.returncode == 0
            _update_status(command_id, CommandStatusUpdate(
                status="completed" if success else "failed",
                completed_at=datetime.now(timezone.utc),
                result_summary={"message": message},
            ))
            del _test_children[pid]
```

3. Add `_spawn_test()` function:

```python
def _spawn_test(
    envelope: CommandEnvelope,
    producer_main_path: str,
) -> Optional[subprocess.Popen]:
    """Spawn a child process to run the test (or reject if at capacity)."""
    if len(_test_children) >= _max_scans:
        logger.warning(
            "Max concurrent tests reached (%d) — rejecting command_id=%s",
            _max_scans, envelope.command_id,
        )
        _update_status(envelope.command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=f"Max concurrent tests reached ({_max_scans})",
        ))
        return None

    cmd = [
        sys.executable, producer_main_path,
        "--mode", "test",
        "--command-id", str(envelope.command_id),
        "--target", envelope.target,
    ]
    if envelope.parameters:
        cmd += ["--parameters", json.dumps(envelope.parameters)]

    logger.info("Spawning test child command_id=%s", envelope.command_id)
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _test_children[child.pid] = (envelope.command_id, child)
    return child
```

4. In `run_daemon()` main loop, add `_poll_test_children()` call after the
   `inactivity_timeout` check:

```python
for method_frame, properties, body in channel.consume(
    queue_name, inactivity_timeout=1
):
    if method_frame is None:
        _poll_test_children()  # ← NEW: poll test children on idle ticks
        continue
    # ... rest of message handling
```

5. Add `command_type == "test"` handler in the message dispatch:

```python
if envelope.command_type == "scan":
    _spawn_scan(envelope, producer_main_path)
elif envelope.command_type == "test":
    _spawn_test(envelope, producer_main_path)
elif envelope.command_type == "cancel":
    # ... cancel handler from Phase 2
```

6. In the `finally` block, also kill test children:

```python
finally:
    for pid in list(_children.keys()):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for pid in list(_test_children.keys()):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    connection.close()
```

7. Add `run_test()` function (scan-mode equivalent for tests):

```python
def run_test(
    *,
    command_id: uuid.UUID,
    parameters: dict[str, Any],
    test_func: Callable[[], Coroutine[Any, Any, tuple[bool, str]]],
) -> None:
    """Test mode entry point — run test and print result to stdout."""
    logger.info("Test started command_id=%s", command_id)

    try:
        success, message = asyncio.run(test_func())
        if success:
            print(f"SUCCESS: {message}")
        else:
            print(f"FAILED: {message}")
            sys.exit(1)
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
```

8. Update `producer_main()` to accept `test_func` and handle `--mode test`:

```python
def producer_main(
    *,
    description: str,
    default_container: str,
    producer_main_path: str,
    scan_func: Callable[[], Coroutine[Any, Any, None]],
    test_func: Callable[[], Coroutine[Any, Any, tuple[bool, str]]] | None = None,
) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--mode", choices=["daemon", "scan", "test"], default="daemon")
    parser.add_argument("--command-id")
    parser.add_argument("--target")
    parser.add_argument("--parameters")

    args = parser.parse_args()

    if args.mode == "daemon":
        run_daemon(...)
    elif args.mode == "test":
        if test_func is None:
            print("ERROR: No test function provided for this producer.")
            sys.exit(1)
        command_id = uuid.UUID(args.command_id) if args.command_id else uuid.uuid4()
        parameters = json.loads(args.parameters) if args.parameters else {}
        run_test(
            command_id=command_id,
            parameters=parameters,
            test_func=test_func,
        )
    else:
        # scan mode (existing)
        ...
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_cli_test_mode` | `--mode test` invokes `run_test()` |
| Unit | `test_cli_test_mode_no_func` | No `test_func` → prints error, exits 1 |
| Unit | `test_spawn_test_creates_child` | Valid test envelope → `subprocess.Popen` called with `stdout=PIPE` |
| Unit | `test_spawn_test_rejects_when_max_concurrent` | At capacity → status=failed, no spawn |
| Unit | `test_poll_test_children_completed` | Child exits 0 → status=completed, message from stdout |
| Unit | `test_poll_test_children_failed` | Child exits 1 → status=failed, message from stderr |
| Unit | `test_poll_test_children_not_finished` | Child still running → no status update |
| Unit | `test_daemon_kills_test_children_on_shutdown` | Daemon exit → SIGTERM sent to test children |
| Unit | `test_run_test_success` | `test_func` returns `(True, "ok")` → prints "SUCCESS: ok", exits 0 |
| Unit | `test_run_test_failure` | `test_func` returns `(False, "bad")` → prints "FAILED: bad", exits 1 |
| Unit | `test_run_test_exception` | `test_func` raises → prints "FAILED: ...", exits 1 |
| Int | `test_daemon_receives_test_via_rabbitmq` | Publish test command → daemon spawns test child |

### Manual verification

1. Start daemon: `python src/connectors/producers/github/main.py`
2. Send test command: `curl -X POST http://localhost:8000/api/v1/commands/   -H "Content-Type: application/json" -d '{"command_type":"test","target":"github-producer","parameters":{"item_id":1}}'`
3. Verify test result appears in command list: `curl http://localhost:8000/api/v1/commands/?target=github-producer`
4. Test with unreachable endpoint → verify status=failed after timeout
5. Test max concurrency: send 6 test commands → 5th+ shows "max concurrent tests reached"

### Phase 3 progress

- [x] `src/connectors/producers/daemon_common.py` — `_test_children` dict added
- [x] `src/connectors/producers/daemon_common.py` — `_poll_test_children()` added
- [x] `src/connectors/producers/daemon_common.py` — `_spawn_test()` added
- [x] `src/connectors/producers/daemon_common.py` — `run_test()` added
- [x] `src/connectors/producers/daemon_common.py` — `producer_main()` updated with `test_func` + `--mode test`
- [x] `src/connectors/producers/daemon_common.py` — main loop polls test children on idle ticks
- [x] `src/connectors/producers/daemon_common.py` — finally block kills test children
- [x] Unit tests written and passing
- [x] Manual verification: test flow works end-to-end
- [x] `pylint` — no errors
- [x] `mypy` on modified files — no errors (pre-existing stubs only)
- [x] Regression: existing unit tests still pass

---

## Phase 4: Producer Test Functions

### What

Create `test_connection()` async function for each of the three producers.
Each function loads config (same as scan), filters to the specific item if
`item_id` is provided, makes a lightweight API call, and returns
`(success, message)`.

### Files to create / modify

#### `src/connectors/producers/github/main.py`

Add `test_connection()` function:

```python
async def test_connection() -> tuple[bool, str]:
    """Test GitHub connectivity. Loads config, authenticates, returns result."""
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()
    config = load_config_from_server() if config_source == "SERVER" else load_config_from_file()
    repos_cfg = config.get("repos", [])

    # If item_id is provided, filter to that specific item
    item_id = _get_test_item_id()
    if item_id is not None:
        repos_cfg = [r for r in repos_cfg if r.get("id") == item_id]
        if not repos_cfg:
            return (False, f"No repository config found with id={item_id}")

    for repo_cfg in repos_cfg:
        url = repo_cfg.get("url", "")
        access_token = repo_cfg.get("access_token", "")
        if not url or not access_token:
            continue
        try:
            auth = Auth.Token(access_token)
            g = Github(auth=auth)
            user = g.get_user()
            _ = user.login  # lightweight call to verify credentials
            return (True, f"Authenticated as {user.login}")
        except Exception as exc:
            return (False, f"GitHub auth failed for {url}: {exc}")

    return (False, "No enabled repository configurations to test")
```

Where `_get_test_item_id()` reads from a temp file or env var set by the
daemon. **Design decision**: Since the test function is called via
`asyncio.run(test_func())` in `run_test()`, and `run_test()` receives
`parameters`, we need a way to pass `item_id` into the test function without
changing its signature. Options:

| Option | How it works |
|--------|-------------|
| **A — Environment variable** | `run_test()` sets `os.environ["TEST_ITEM_ID"]` before calling `test_func()` |
| **B — Module-level global** | `run_test()` sets a global `_test_params` dict in `daemon_common.py` |

**Recommendation: Option A — environment variable.** Simple, thread-safe
(since daemon is single-threaded), and doesn't require module-level state
changes.

```python
# In run_test():
if "item_id" in parameters:
    os.environ["TEST_ITEM_ID"] = str(parameters["item_id"])

# In test_connection():
def _get_test_item_id() -> int | None:
    raw = os.environ.get("TEST_ITEM_ID")
    return int(raw) if raw else None
```

Update `producer_main()` call in each producer:

```python
def main() -> None:
    producer_main(
        description="GitHub Producer",
        default_container="github-producer",
        producer_main_path=__file__,
        scan_func=main_async,
        test_func=test_connection,  # NEW
    )
```

#### `src/connectors/producers/jira/main.py`

Add `test_connection()`:

```python
async def test_connection() -> tuple[bool, str]:
    """Test Jira connectivity. Loads config, authenticates, returns result."""
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()
    config = load_config_from_server() if config_source == "SERVER" else load_config_from_file()
    accounts = config.get("account", [])

    item_id = _get_test_item_id()
    if item_id is not None:
        accounts = [a for a in accounts if a.get("id") == item_id]
        if not accounts:
            return (False, f"No Jira account config found with id={item_id}")

    for account in accounts:
        try:
            jira = create_jira_connection({"account": [account]})
            user = jira.myself()
            name = user.get("displayName", user.get("emailAddress", "Unknown"))
            return (True, f"Authenticated as {name}")
        except Exception as exc:
            url = account.get("url", "unknown")
            return (False, f"Jira auth failed for {url}: {exc}")

    return (False, "No enabled Jira account configurations to test")
```

#### `src/connectors/producers/confluence/main.py`

Add `test_connection()`:

```python
async def test_connection() -> tuple[bool, str]:
    """Test Confluence connectivity. Loads config, authenticates, returns result."""
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()
    config = load_config_from_server() if config_source == "SERVER" else load_config_from_file()
    accounts = config.get("account", [])

    item_id = _get_test_item_id()
    if item_id is not None:
        accounts = [a for a in accounts if a.get("id") == item_id]
        if not accounts:
            return (False, f"No Confluence account config found with id={item_id}")

    for account in accounts:
        try:
            confluence = create_confluence_connection({"account": [account]})
            user = confluence.myself()
            name = user.get("displayName", user.get("email", "Unknown"))
            return (True, f"Authenticated as {name}")
        except Exception as exc:
            url = account.get("url", "unknown")
            return (False, f"Confluence auth failed for {url}: {exc}")

    return (False, "No enabled Confluence account configurations to test")
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_github_test_connection_success` | Valid token → returns `(True, "Authenticated as ...")` |
| Unit | `test_github_test_connection_failure` | Invalid token → returns `(False, "GitHub auth failed ...")` |
| Unit | `test_github_test_connection_with_item_id` | Filters to specific item, tests only that one |
| Unit | `test_github_test_connection_item_id_not_found` | Unknown item_id → returns `(False, "No repository config found ...")` |
| Unit | `test_jira_test_connection_success` | Valid credentials → returns `(True, "Authenticated as ...")` |
| Unit | `test_jira_test_connection_failure` | Invalid credentials → returns `(False, "Jira auth failed ...")` |
| Unit | `test_confluence_test_connection_success` | Valid credentials → returns `(True, "Authenticated as ...")` |
| Unit | `test_confluence_test_connection_failure` | Invalid credentials → returns `(False, "Confluence auth failed ...")` |
| Unit | `test_test_item_id_env_var` | `TEST_ITEM_ID` env var parsed correctly |
| Unit | `test_test_item_id_env_var_missing` | No env var → returns None |

### Manual verification

1. Run test directly (debug mode):
   ```bash
   TEST_ITEM_ID=1 python src/connectors/producers/github/main.py --mode test
   ```
   → Expect "SUCCESS: Authenticated as ..." or "FAILED: ..."

2. Run test with invalid token:
   ```bash
   # Temporarily set a bad token in config, then:
   python src/connectors/producers/github/main.py --mode test
   ```
   → Expect "FAILED: GitHub auth failed ..."

3. Repeat for jira and confluence producers

### Phase 4 progress

- [x] `src/connectors/producers/github/main.py` — `test_connection()` added
- [x] `src/connectors/producers/github/main.py` — `producer_main()` call updated with `test_func`
- [x] `src/connectors/producers/jira/main.py` — `test_connection()` added
- [x] `src/connectors/producers/jira/main.py` — `producer_main()` call updated with `test_func`
- [x] `src/connectors/producers/confluence/main.py` — `test_connection()` added
- [x] `src/connectors/producers/confluence/main.py` — `producer_main()` call updated with `test_func`
- [x] `src/connectors/producers/daemon_common.py` — `run_test()` sets `TEST_ITEM_ID` env var
- [x] Unit tests written and passing
- [x] Manual verification: each producer's test works standalone
- [x] `pylint` — no errors
- [x] `mypy` — no errors (pre-existing stubs only)
- [x] Regression: existing unit tests still pass

---

## Phase 5: API Layer — Allow `test` and `cancel` Command Types

### What

The existing `create_and_publish_command()` service validates the target
against `CONNECTOR_REGISTRY` but doesn't restrict `command_type`. Since
`command_type` is a free string, `"test"` and `"cancel"` already work.
However, we should ensure the API surface is clean and the `CreateCommandRequest`
model doesn't need changes.

### Files to check / modify

#### `src/app/api/commands/v1/models.py`

No changes needed — `command_type: str` already accepts any string.

#### `src/app/api/commands/v1/service.py`

No changes needed — `_is_producer_target()` already validates the target,
and `command_type` is passed through as-is.

#### `src/app/api/commands/v1/router.py`

No changes needed — the existing POST handler already works for any
`command_type`.

### Verification

- [x] POST `/api/v1/commands/` with `command_type: "test"` returns 201
- [x] POST `/api/v1/commands/` with `command_type: "cancel"` returns 201
- [x] GET `/api/v1/commands/` with `command_type=test` filters correctly
- [x] GET `/api/v1/commands/` with `command_type=cancel` filters correctly

### Phase 5 progress

- [x] Verified: `command_type: "test"` accepted by API
- [x] Verified: `command_type: "cancel"` accepted by API
- [x] Verified: filtering by `command_type` works in list endpoint
- [x] Regression: existing API tests still pass (66 tests)

---

## Phase 6: UI — Inline Cancel Button on Scan Rows

### What

Add a "Cancel" button to each scan row in the "Recent Scans" section when
the scan status is `"running"` or `"accepted"`. The button POSTs to
`/api/v1/commands/` with `command_type: "cancel"`.

### Files to modify

#### `src/app/dash_app/pages/connectors/components/scan_status.py`

Update `render_scan_item()` to accept a callback-friendly ID and optionally
render a cancel button:

```python
def render_scan_item(command: dict) -> html.Div:
    """Render a single scan command row with status, timestamps, and cancel button."""
    status = command.get("status", "unknown")
    command_id = command.get("command_id", "")
    cfg = STATUS_CONFIG.get(status, {...})

    # ... existing timestamp/duration rendering ...

    # Cancel button — only for active scans
    cancel_button = html.Div()
    if status in ("running", "accepted"):
        cancel_button = dbc.Button(
            "Cancel",
            id={"type": "connector-cancel-scan", "command_id": command_id},
            color="warning",
            size="sm",
            className="ms-2",
            style={"fontSize": "11px", "padding": "1px 6px"},
        )

    return html.Div(
        [
            html.Div(
                [
                    html.I(className=cfg["icon"], style={...}),
                    html.Span(cfg["label"], style={...}),
                    html.Span(detail_line, style={...}),
                ],
                style={"display": "flex", "alignItems": "center", "flex": "1"},
            ),
            cancel_button,
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            # ... existing style ...
        },
    )
```

#### `src/app/dash_app/pages/connectors/callbacks.py`

Add a new callback for the cancel button:

```python
@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Output("connector-scans-poll", "disabled", allow_duplicate=True),
    Input({"type": "connector-cancel-scan", "command_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_cancel_scan(n_clicks: List[int | None]):
    """Cancel a running scan by sending a cancel command via the API."""
    if not callback_context.triggered:
        return no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    scan_command_id = triggered.get("command_id")
    if not scan_command_id:
        return no_update, no_update

    # Determine the target container from the current connector page
    # (stored in a dcc.Store or derived from URL)
    # For simplicity, we derive from the URL pathname
    from dash import ctx
    pathname = ...  # get from a State or callback_context

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/commands/",
            json={
                "command_type": "cancel",
                "target": container_name,  # need to resolve this
                "parameters": {"cancel_command_id": scan_command_id},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return (
            create_alert(f"Cancel sent for scan {scan_command_id[:8]}...", color="warning", class_name="mb-0"),
            False,  # enable polling
        )
    except requests.exceptions.RequestException as exc:
        return (
            create_alert(f"Failed to cancel scan: {exc}", color="danger", class_name="mb-0"),
            no_update,
        )
```

**Design note**: The cancel callback needs to know the `container_name`
(target) to send the cancel command to. This can be derived from the current
URL pathname (same pattern as `load_recent_scans`). Add a `State("url",
"pathname")` to the callback.

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_cancel_button_visible_for_running` | Running scan row has Cancel button |
| Unit | `test_cancel_button_visible_for_accepted` | Accepted scan row has Cancel button |
| Unit | `test_cancel_button_hidden_for_completed` | Completed scan row has no Cancel button |
| Unit | `test_cancel_button_hidden_for_failed` | Failed scan row has no Cancel button |
| Unit | `test_cancel_button_hidden_for_cancelled` | Cancelled scan row has no Cancel button |
| Unit | `test_cancel_click_sends_api_request` | Button click triggers POST to `/api/v1/commands/` |
| Int | `test_cancel_button_end_to_end` | Click → API → RabbitMQ → daemon → status=cancelled |

### Manual verification

1. Open connector detail page → "Recent Scans" section
2. Trigger a scan → watch it appear with status "accepted" → "running"
3. Verify Cancel button appears while status is "running"
4. Click Cancel → verify success alert appears
5. Watch status transition to "cancelled" → Cancel button disappears
6. Verify completed/failed scans have no Cancel button

### Phase 6 progress

- [x] `src/app/dash_app/pages/connectors/components/scan_status.py` — cancel button added
- [x] `src/app/dash_app/pages/connectors/callbacks.py` — `handle_cancel_scan` callback added
- [x] Unit tests written and passing
- [x] Manual verification: cancel flow works in browser
- [x] `pylint` — no errors
- [x] Regression: existing UI tests still pass

---

## Phase 7: UI — Per-Item Test Connection via Commands API

### What

Replace the existing per-item "Test Connection" button behavior to POST to
`/api/v1/commands/` with `command_type: "test"` instead of calling the old
stub endpoint. Test results appear in the "Recent Scans" section.

### Files to modify

#### `src/app/dash_app/pages/connectors/callbacks.py`

Update `handle_item_test_connection()` callback:

```python
@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Output("connector-scans-poll", "disabled", allow_duplicate=True),
    Input({"type": "connector-item-test", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_item_test_connection(n_clicks: List[int | None]):
    """Test connection for a specific config item via the commands API.

    Sends a ``command_type: "test"`` command to the producer daemon, which
    runs the actual connectivity check and reports the result.
    """
    if not callback_context.triggered:
        return no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    connector_type = triggered.get("connector_type")
    item_id = triggered.get("item_id")
    if not connector_type or item_id is None:
        return no_update, no_update

    container_name = CONNECTOR_REGISTRY.get(connector_type, {}).get("producer_container")
    if not container_name:
        return (
            create_alert(f"No producer container for {connector_type}.", color="warning", class_name="mb-0"),
            no_update,
        )

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/commands/",
            json={
                "command_type": "test",
                "target": container_name,
                "parameters": {"item_id": item_id},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        command_id = data.get("command_id", "unknown")

        return (
            create_alert(
                f"Test triggered! Command ID: {command_id}",
                color="info",
                class_name="mb-0",
            ),
            False,  # enable polling so result appears
        )
    except requests.exceptions.RequestException as exc:
        return (
            create_alert(f"Test failed: {exc}", color="danger", class_name="mb-0"),
            no_update,
        )
```

#### `src/app/dash_app/pages/connectors/components/scan_status.py`

Update `render_scan_item()` to show a `[TEST]` prefix or distinct styling
for test commands so users can visually distinguish them from scans:

```python
command_type = command.get("command_type", "scan")
type_badge = ""
if command_type == "test":
    type_badge = html.Span(
        " [TEST]",
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_XSMALL,
            "color": COLOR_INFO,
            "fontWeight": "600",
            "marginRight": SPACING_XSMALL,
        },
    )
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_test_connection_button_sends_command` | Button click POSTs to `/api/v1/commands/` with `command_type: "test"` |
| Unit | `test_test_connection_no_producer_container` | Non-producer connector shows warning, no API call |
| Unit | `test_test_result_shows_in_recent_scans` | Test command appears in scan list with `[TEST]` badge |
| Unit | `test_test_badge_visible` | `render_scan_item` shows `[TEST]` for `command_type="test"` |
| Unit | `test_scan_no_badge` | `render_scan_item` does not show `[TEST]` for `command_type="scan"` |
| Int | `test_test_connection_end_to_end` | Click → API → RabbitMQ → daemon → result in UI |

### Manual verification

1. Open connector detail page (e.g., GitHub)
2. Find a config item card → click "Test Connection"
3. Verify info alert appears: "Test triggered! Command ID: ..."
4. Scroll to "Recent Scans" → verify test appears with `[TEST]` badge
5. Watch status transition: accepted → running → completed/failed
6. Verify test result message appears in the scan row detail
7. Repeat for Jira and Confluence connectors
8. Verify non-producer connectors (Slack, Teams) still show the old stub behavior

### Phase 7 progress

- [x] `src/app/dash_app/pages/connectors/callbacks.py` — `handle_item_test_connection` updated
- [x] `src/app/dash_app/pages/connectors/components/scan_status.py` — `[TEST]` badge added
- [x] Unit tests written and passing
- [x] Manual verification: test connection works end-to-end in browser
- [x] `pylint` — no errors
- [x] Regression: existing UI tests still pass

---

## Phase 8: Full Integration Verification

### What

Run the complete regression suite and manual end-to-end scenarios.

### Automated regression suite

```bash
# Unit tests
pytest -m unit tests/ -q

# Integration tests requiring running services
pytest -m "integration and server" tests/ -q

# RabbitMQ integration tests
pytest -m rabbitmq tests/ -q

# All tests
pytest tests/ -q

# Type checking
mypy src/

# Linting
pylint src/
```

### Manual end-to-end scenarios

**Scenario 1: Cancel a running scan**
1. Open browser → `http://localhost:8000/app/connectors/github`
2. Click "Run Scan"
3. While scan is running, click "Cancel" on the scan row
4. Verify status transitions to "cancelled" with appropriate icon
5. Verify Cancel button disappears after status changes

**Scenario 2: Cancel an accepted (queued) scan**
1. Send multiple scans rapidly (more than `MAX_CONCURRENT_SCANS`)
2. Find a scan stuck at "accepted" (queued)
3. Click "Cancel" → verify it transitions to "cancelled"

**Scenario 3: Test connection — success**
1. Open connector detail page → find a config item card
2. Click "Test Connection"
3. Verify `[TEST]` badge appears in Recent Scans
4. Wait for status → "completed" with green checkmark
5. Verify detail line shows "Authenticated as ..."

**Scenario 4: Test connection — failure**
1. Configure a connector with an invalid token
2. Click "Test Connection"
3. Verify status → "failed" with red X icon
4. Verify detail line shows error message

**Scenario 5: Test connection — timeout**
1. Configure a connector with an unreachable URL
2. Click "Test Connection"
3. Verify status stays "running" for up to 30s
4. Verify it eventually transitions to "failed"
5. Verify other scans can be triggered and cancelled during the timeout

**Scenario 6: Mixed scan and test results**
1. Trigger 2 scans and 2 tests in any order
2. Verify all 4 appear in "Recent Scans" sorted by time
3. Verify scans show no badge, tests show `[TEST]` badge

**Scenario 7: Non-producer connectors unaffected**
1. Open Slack connector detail page
2. Verify "Test Connection" button still works (old stub behavior)
3. Verify no "Run Scan" button (unchanged)
4. Verify no "Recent Scans" section (unchanged)

### Regression checks

- [ ] Existing connector API endpoints work (CRUD configs, test connection for MCP)
- [ ] Existing Dash pages work (Chat, People, Progress, Graph, Analytics, Settings)
- [ ] Signal consumer still processes signals correctly (unaffected)
- [ ] Existing tests pass: `pytest -m unit tests/ -q`
- [ ] Type checking: `mypy src/`
- [ ] Linting: `pylint src/`

### Phase 8 progress

- [ ] Full unit test suite passes
- [ ] Full integration test suite passes
- [ ] All 7 manual scenarios verified
- [ ] Regression checks pass
- [ ] `mypy src/` — no errors
- [ ] `pylint src/` — no errors