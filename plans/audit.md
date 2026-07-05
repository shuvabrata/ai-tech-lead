# Deep Audit Report — work-behavior-analytics-ai

> **Date**: 2026-06-26 · **Commit**: `ec14dc5` · **Source files**: 234 Python · **Test files**: 83
>
> **Methodology**: Full-depth static read of all core modules — `app/` (FastAPI + Dash), `connectors/` (producers, consumers, sinks), `common/` (shared libs), infra configs. No source code was modified.

---

## 1. Correctness / Bugs

### [BUG-01] Neo4j driver created and destroyed per request in Graph API

- **Evidence**: [`src/app/api/graph/v1/query.py:117`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L117), [`query.py:200`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L200), [`query.py:392`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L392) — `GraphDatabase.driver()` is called inside every `execute_cypher_query`, `fetch_relationships_between_nodes`, and `expand_node_query` function, followed by `driver.close()` in `finally`. The Neo4j driver is designed to be a long-lived singleton that manages its own connection pool. Re-creating it per request bypasses pooling, causing TCP connection overhead, TLS re-negotiation, and `verify_connectivity()` latency on every call.
- **Impact**: Every graph API request pays ~100–300ms of connection setup overhead. Under concurrent load, connection churn can exhaust server-side limits. The collaboration network page can trigger 3+ Cypher queries per render, multiplying the waste.
- **Effort**: S — Extract a module-level driver singleton (gated by `NEO4J_ENABLED`), reuse sessions from it. ~1 file change + test update.
- **Risk**: LOW — Driver singletons are the documented pattern; pool health is managed by `pool_pre_ping` equivalent in Neo4j.
- **Confidence**: HIGH — Code clearly shows `driver = GraphDatabase.driver(...)` + `driver.close()` inside every function body.
- **Fix sketch**: Create `_get_driver()` at module level that lazily initializes and caches a driver singleton. Replace the three `driver = GraphDatabase.driver(...)` blocks with `driver = _get_driver()` and remove `driver.close()` from `finally`.

### [BUG-02] Cypher query read-only validation bypassable via comment injection

- **Evidence**: [`src/app/api/graph/v1/query.py:27-79`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L27-L79) — `validate_read_only_query` normalizes the query by uppercasing and splitting whitespace, then checks if the query "starts with a read operation" after stripping leading `/` and `*` characters. A query like `/* comment */ CREATE (n) RETURN n` would have `MATCH` checked against `COMMENT */ CREATE ...` after the strip, failing the start check — but a query crafted as `MATCH (n) WITH n AS x CREATE (m) RETURN m` uses `MATCH` to pass the start-check, and `CREATE` should be caught by the write-keyword scan. However, the comment-stripping logic at line 67 (`query_start = normalized.lstrip('/').lstrip('*').lstrip()`) is fragile — it doesn't properly parse multi-line comments or nested comments, and a Cypher `// comment\nCREATE` could confuse the start-check.
- **Impact**: The write-keyword scan (`WRITE_KEYWORDS`) is the main defense and is robust for simple cases. The start-check is a secondary belt-and-suspenders layer. Real risk is LOW because Neo4j driver's own read-only session mode (`session.run` vs `session.read_transaction`) isn't used — the validation is purely string-based.
- **Effort**: S — Use Neo4j's native read-only session mode (`AccessMode.READ`) as the authoritative guard instead of relying solely on regex.
- **Risk**: LOW
- **Confidence**: MED — The regex-based validation is imperfect by design; the question is whether a real bypass exists. Using `AccessMode.READ` would make the question moot.
- **Fix sketch**: Pass `default_access_mode=neo4j.READ_ACCESS` to `driver.session()` in `execute_cypher_query`. Keep the regex validation as a fast-fail pre-check but delegate the authoritative check to Neo4j itself.

### [BUG-03] Relationship type filter in expand_node_query vulnerable to Cypher injection

- **Evidence**: [`src/app/api/graph/v1/query.py:290-291`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L290-L291) — `type_list = "|".join(relationship_types)` is interpolated directly into an f-string Cypher query template: `f"MATCH (m)-[r{relationship_filter}]->(n)"`. If `relationship_types` contains a crafted string like `WORKS_ON]->(m) DELETE m //`, it would inject arbitrary Cypher.
- **Impact**: An attacker who can control the `relationship_types` parameter (via the expand API) could execute arbitrary write Cypher on the Neo4j database.
- **Effort**: S — Validate that each relationship type matches `^[A-Z_]+$` before interpolation.
- **Risk**: MED — The fix is straightforward but requires careful input validation.
- **Confidence**: HIGH — String interpolation into Cypher is clearly visible. No validation or sanitization exists on the input.
- **Fix sketch**: Add `if not re.match(r'^[A-Z_][A-Z_0-9]*$', rt) for rt in relationship_types: raise ValueError(...)` before building the filter string.

### [BUG-04] `_handle_person` in neo4j_sink has massive code duplication across providers

- **Evidence**: [`src/connectors/consumers/sinks/neo4j_sink.py:412-572`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/connectors/consumers/sinks/neo4j_sink.py#L412-L572) — The three provider branches (`github`, `jira`, `confluence`) each repeat the same ~30-line pattern: extract attrs → call `person_cache.get_or_create_person()` → check dedup → rehome stub → queue identity mapping → merge relationships. The only differences are which attrs are extracted (`login` vs `account_id`), the `provider` string, and the identity key.
- **Impact**: A bug fix or behavior change to Person handling must be applied in 3 places. The 160-line function is the longest in the module and hard to review. One branch could silently diverge from the others (e.g., `confluence` sets `url`, `jira` does not — is this intentional?).
- **Effort**: M — Extract a shared `_upsert_person_via_cache(session, signal, person_cache, ...)` helper parameterized by provider-specific field mapping.
- **Risk**: LOW — Refactoring with existing test coverage.
- **Confidence**: HIGH — Three near-identical blocks are clearly visible.
- **Fix sketch**: Create a `_PersonMapping` dataclass with fields `{provider, external_id_attr, url_attr, ...}` and a `PROVIDER_MAPPINGS` dict. Collapse the three branches into one loop body.

---

## 2. Security

### [SEC-01] `include_secrets` query parameter exposes decrypted credentials without authentication

- **Evidence**: [`src/app/api/connectors/v1/router.py:62-63`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/router.py#L62-L63), [`router.py:97-98`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/router.py#L97-L98), [`service.py:298-300`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/service.py#L298-L300) — The `include_secrets=True` query parameter causes `decrypt()` to return plaintext credentials (GitHub tokens, Jira API tokens, email passwords) in the HTTP response. There is no authentication middleware on any route. Two TODO comments acknowledge this: `"This should be replaced with a proper role-based access control check"`.
- **Impact**: Anyone with network access to the API can read all stored credentials in plaintext by appending `?include_secrets=true` to the GET endpoint. This is a **critical** credential exposure vector.
- **Effort**: S — Short-term: remove the `include_secrets` query parameter from public routes entirely. Secrets should only be read server-side (e.g., by internal sync/consumer code).
- **Risk**: LOW — The parameter is only used in two code paths: `_test_atlassian_mcp_connection` (which can call `get_connector` internally) and the external API. Removing from the router doesn't break internal callers.
- **Confidence**: HIGH — Direct code evidence with TODO comments confirming it.
- **Fix sketch**: Remove `include_secrets` from `get_connector` and `list_config_items` router signatures. For internal callers that need secrets, add a private service function that bypasses the router.

### [SEC-02] `allow_dangerous_requests=True` on LangChain Neo4j chain

- **Evidence**: [`src/app/ai_agent/chains/neo4j_chain.py:304`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/ai_agent/chains/neo4j_chain.py#L304) — `GraphCypherQAChain.from_llm(..., allow_dangerous_requests=True)`. This flag disables LangChain's built-in safety checks for generated Cypher queries.
- **Impact**: The LLM can generate and execute arbitrary Cypher, including write operations. While the UI context is "analytics", a prompt injection in user chat could cause data mutation or deletion. The feature-flag `FF_NEO4J_USE_PROVIDER_PIPELINE` gates a separate path but the LangChain path uses this dangerous flag.
- **Effort**: M — Add a post-generation validation step that checks the LLM-generated Cypher against `validate_read_only_query()` before execution, or use Neo4j read-only sessions.
- **Risk**: MED — Changing the chain behavior could break some LLM-generated queries that use advanced syntax.
- **Confidence**: HIGH — Flag is explicitly set.
- **Fix sketch**: Wrap the chain's `run()` in a helper that extracts the generated Cypher, validates it with `validate_read_only_query()`, and only then executes via a read-only session. Alternatively, use `read_only=True` on the Neo4j session.

### [SEC-03] No authentication or authorization on any API endpoint

- **Evidence**: [`src/app/main.py`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/main.py) — No auth middleware, no `Depends(get_current_user)`, no API key validation. All routes (connectors CRUD, graph execute, chat stream, connector test) are fully public.
- **Impact**: Any network-accessible client can read/write connector configurations, execute arbitrary graph queries, stream LLM responses, and delete data. Combined with SEC-01, this enables credential theft.
- **Effort**: L — Adding auth is a cross-cutting concern touching all routers. Start with API key middleware as a quick win.
- **Risk**: MED — Adding auth will break any existing client integrations that don't send credentials.
- **Confidence**: HIGH — No auth code exists anywhere in the codebase.
- **Fix sketch**: Add a simple API key middleware (`X-API-Key` header checked against `settings.API_KEY`) as a first layer. Plan a proper OAuth/JWT flow separately.

---

## 3. Performance

### [PERF-01] Neo4j driver per-request (see BUG-01)

Covered in BUG-01 above. The performance impact is the primary concern.

### [PERF-02] `_to_db_relationships` executes one Cypher query per relationship for resolution

- **Evidence**: [`src/connectors/consumers/sinks/neo4j_sink.py:131-182`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/connectors/consumers/sinks/neo4j_sink.py#L131-L182) — For each relationship in a signal, the function runs up to 3 separate `session.run()` queries to resolve the target node (by email, URL, or identity mapping). A PullRequest signal with 10 relationships → 10–30 queries just for resolution, before any merge operations.
- **Impact**: For a typical GitHub sync of 100 PRs with ~8 relationships each, this produces 800–2400 extra resolution queries. This is a classic N+1 pattern inside the consumer pipeline.
- **Effort**: M — Batch-resolve all targets upfront with a single `UNWIND $targets AS t OPTIONAL MATCH ...` query, then look up results in a local dict.
- **Risk**: MED — Requires careful handling of the resolution priority order (email > URL > identity mapping > wba_format fallback).
- **Confidence**: HIGH — Each `session.run()` is visible inside the loop.
- **Fix sketch**: Collect all `(target.email, target.url, target.id)` tuples, run one batched resolution query with `UNWIND`, build a `{key: resolved_id}` dict, then iterate without further queries.

### [PERF-03] Collaboration network query is synchronous and blocking

- **Evidence**: [`src/app/api/graph/v1/router.py:190-308`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/router.py#L190-L308) — The `get_collaboration_network` endpoint is `async def` but calls `service.get_collaboration_network(config)` synchronously. The service layer eventually calls `execute_cypher_query()` which uses `driver.session()` (synchronous Neo4j driver) — this blocks the entire asyncio event loop.
- **Impact**: During a collaboration network computation (which can take seconds for large graphs), all other async requests on the same worker are stalled.
- **Effort**: S — Wrap the service call in `asyncio.to_thread()`, matching the pattern already used in `consume_queue()`.
- **Risk**: LOW — `asyncio.to_thread()` is already used elsewhere in the codebase.
- **Confidence**: HIGH — Synchronous Neo4j calls inside async route handlers are clearly visible.
- **Fix sketch**: `response = await asyncio.to_thread(service.get_collaboration_network, config)`.

---

## 4. Test Coverage

### [TEST-01] Zero unit tests for security-critical validation code

- **Evidence**: No test file for `validate_read_only_query()` in [`query.py`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/graph/v1/query.py#L27-L79). The function is the sole defense against write queries through the graph API. 83 test files exist but none cover this function.
- **Impact**: The comment-stripping bypass (BUG-02) and any future regressions in the validation logic would go undetected.
- **Effort**: S — Write ~15 parameterized test cases covering: valid reads, all write keywords, comment injection, empty/null input, APOC patterns.
- **Risk**: LOW
- **Confidence**: HIGH — Grep for `validate_read_only` in tests/ returns no results.
- **Fix sketch**: Create `tests/test_graph_query_validation.py` with `@pytest.mark.parametrize` over valid and invalid queries.

### [TEST-02] No tests for `_handle_person` cross-provider dedup logic

- **Evidence**: [`tests/test_neo4j_sink_confluence.py`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/tests/test_neo4j_sink_confluence.py) exists but the complex person dedup logic in `_handle_person` (780 lines of critical identity resolution) has no direct unit tests covering the 3-way provider merge, the `_rehome_person_stub` migration, or the dedup vs non-dedup paths.
- **Impact**: Identity dedup is the core differentiator of the system. A regression could create orphaned Person stubs, broken relationships, or data loss.
- **Effort**: M — Create a dedicated test module with mock Neo4j sessions testing each dedup scenario.
- **Risk**: LOW
- **Confidence**: MED — Some integration tests may exercise these paths indirectly; direct unit tests are missing.
- **Fix sketch**: Create `tests/test_neo4j_sink_person_dedup.py` with scenarios: same-email cross-provider merge, stub rehoming, no-cache fallback, relationship re-attachment.

### [TEST-03] No test infrastructure for auth (SEC-03 prerequisite)

- **Evidence**: No test helpers for authenticated requests, no auth fixtures, no middleware tests.
- **Impact**: When auth is eventually added (SEC-03), there will be no regression safety net.
- **Effort**: S — Create a `conftest.py` fixture that mocks an auth header.
- **Risk**: LOW
- **Confidence**: HIGH

---

## 5. Tech Debt & Architecture

### [DEBT-01] `process_single_pr.py` is a 318-line function with deep nesting

- **Evidence**: [`src/connectors/producers/github/process_single_pr.py`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/connectors/producers/github/process_single_pr.py) — A single function `process_single_pr` at 318 lines does: author fetch, review fetch, reviewer data fetch, merger extraction, requested reviewer fetch, commit processing (with nested error handling), comment aggregation across 3 sources, user data batch fetch, and finally Person signal emission for 5 different role types. Each role's Person signal emission is a copy-pasted pattern.
- **Impact**: Any change to PR signal processing requires understanding the entire 318-line flow. The 5 Person signal emission blocks (author, reviewers, requested_reviewers, commenters, merger) are duplicated logic.
- **Effort**: M — Extract `_emit_person_if_new()` helper, split comment fetching into a separate function, extract commit processing.
- **Risk**: LOW — Pure refactoring with existing test coverage in `tests/producers/github/test_process_single_pr.py`.
- **Confidence**: HIGH
- **Fix sketch**: Create `_emit_person_signals(persons: dict, published: set, _pub, pr_number)` that handles the dedup+publish loop. Extract `_fetch_and_emit_pr_commits()` and `_fetch_pr_comments()` as standalone async helpers.

### [DEBT-02] `_MCPClientBase._run_sync` uses Thread+Queue for async-to-sync bridge

- **Evidence**: [`src/app/ai_agent/mcp_integration/client_manager.py:35-57`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/ai_agent/mcp_integration/client_manager.py#L35-L57) — When called from an async context, `_run_sync` spawns a daemon thread that runs `anyio.run()` inside it, then blocks the caller on a `Queue.get()`. The daemon thread is joined after, but `join()` with no timeout can deadlock if the MCP SDK hangs.
- **Impact**: A stuck MCP server causes the calling thread to hang indefinitely. The `request_timeout_seconds` on the HTTP client may not propagate to the session initialization phase.
- **Effort**: S — Add `worker.join(timeout=self.request_timeout_seconds + 5)` and raise `TimeoutError` if the thread is still alive.
- **Risk**: LOW
- **Confidence**: HIGH — Missing timeout is clearly visible.
- **Fix sketch**: `worker.join(timeout=self.request_timeout_seconds + 5); if worker.is_alive(): raise TimeoutError(...)`.

### [DEBT-03] Logging uses f-strings instead of `%s` formatting throughout

- **Evidence**: ~50+ instances across `src/app/` — e.g., [`router.py:52`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/router.py#L52) `logger.debug(f"[router.list_connectors] Returning {len(result)} connectors")`. F-string logging eagerly formats the string even when the log level would suppress it. With `LOG_LEVEL=INFO`, all DEBUG f-strings still pay the formatting cost.
- **Impact**: Minor performance waste; more importantly, it's inconsistent — some modules use `%s` correctly (neo4j_sink), others use f-strings. This is a codebase hygiene issue, not a critical bug.
- **Effort**: M — Global find-and-replace with careful testing. Could be automated with a linting rule.
- **Risk**: LOW
- **Confidence**: HIGH — Visible in dozens of files.
- **Fix sketch**: Enable `pylint` rule `W1203` (logging-fstring-interpolation) and fix flagged lines. Lower priority than other items.

---

## 6. Dependencies & Migrations

### [DEP-01] `requests` imported synchronously in logger for Slack notifications

- **Evidence**: [`src/common/logger.py:8`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/common/logger.py#L8) — `import requests` at module top level. The `requests.post()` call in `MyAppLogger.error()` (line 181) is synchronous. When running inside the async FastAPI process, this blocks the event loop on every error log that has Slack notifications enabled.
- **Impact**: If `ENABLE_SLACK_NOTIFICATION=1` and an error occurs, the `requests.post()` with `timeout=10` blocks the event loop for up to 10 seconds. During error storms, this could cascade into full application unresponsiveness.
- **Effort**: S — Use `asyncio.to_thread()` or switch to an async HTTP client. Or defer to a background queue.
- **Risk**: LOW
- **Confidence**: HIGH — Synchronous `requests.post` in a logger called from async code.
- **Fix sketch**: Replace with `httpx.AsyncClient` or wrap in `asyncio.to_thread`. Better yet, post to a background queue that drains asynchronously.

---

## 7. DX & Tooling

### [DX-01] `.env.example` has duplicated and conflicting entries

- **Evidence**: [`.env.example:79-84`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/.env.example#L79-L84) and [`.env.example:153-158`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/.env.example#L153-L158) — `LOG_FORMAT`, `LOG_LEVEL`, `ENABLE_FILE_LOGGING`, `LOG_DIR`, and `PYTHONPATH` are defined twice with different values. The first block says `LOG_FORMAT=text` / `LOG_LEVEL=DEBUG`, the second says `LOG_FORMAT=JSON` / `LOG_LEVEL=INFO`.
- **Impact**: Developers copying `.env.example` get confused about which values are canonical. The last definition wins in most `.env` parsers, so the "Docker" values silently override the "local dev" values.
- **Effort**: S — Deduplicate and organize by section with clear comments for local vs Docker overrides.
- **Risk**: LOW
- **Confidence**: HIGH
- **Fix sketch**: Keep one definition per variable with a comment indicating the default. Add a separate `.env.docker.example` if Docker needs different values.

### [DX-02] No `AGENTS.md` or `CLAUDE.md` at project root

- **Evidence**: No `.agents/AGENTS.md` or root-level equivalent exists. The project rules are scattered across `.github/copilot-instructions.md`.
- **Impact**: Agent-based development tools (including this one) lack project-specific conventions, leading to inconsistent code generation.
- **Effort**: S — Create `.agents/AGENTS.md` consolidating conventions from `copilot-instructions.md`.
- **Risk**: LOW
- **Confidence**: HIGH
- **Fix sketch**: Create the file, referencing the existing instructions.

---

## 8. Direction — Features & Where to Take This Next

### [DIR-01] Atlassian MCP connector stores config in DB but GitHub MCP doesn't

- **Evidence**: [`service.py:527-551`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/service.py#L527-L551) — `_test_github_mcp_connection` reads config entirely from `settings` (env vars). `_test_atlassian_mcp_connection` reads from both DB config and settings with DB taking priority. The Atlassian connector has full DB-backed CRUD for `server_url` and `token` (with encryption); GitHub MCP has none.
- **Impact**: Users must restart the application to change GitHub MCP credentials. The UI already has a connector management page that works for Atlassian but not GitHub.
- **Effort**: M — Add `CONNECTOR_CONFIG_SENSITIVE_FIELDS` / `CONNECTOR_CONFIG_ALLOWED_FIELDS` entries for `github_mcp` mirroring the Atlassian pattern. Add DB-fallback logic to `_test_github_mcp_connection`.
- **Confidence**: HIGH — Asymmetry is clear in code.
- **Fix sketch**: Mirror the `atlassian_mcp` pattern for `github_mcp` in `service.py`.

### [DIR-02] Email connector has no actual implementation

- **Evidence**: [`service.py:459-477`](file:///home/shuva/github/shuvabrata/work-behavior-analytics-ai/src/app/api/connectors/v1/service.py#L459-L477) — `test_connection` for email falls through to the stub: `return {"success": True, "message": "Connection verified (stub)"}`. The `email` connector has full CRUD config (SMTP/IMAP host/port/credentials) but no producer, consumer, or actual sync logic.
- **Impact**: Users can configure email settings in the UI and get a misleading "connected" status, but no data is ever synced.
- **Effort**: L — Implementing a real email producer is a significant feature.
- **Confidence**: HIGH — Stub code is explicit.
- **Fix sketch**: At minimum, implement a real `test_connection` that attempts IMAP login. Full sync is a separate initiative.

---

## Prioritization Summary

| # | Finding | Category | Priority | Effort | Risk | Confidence |
|---|---------|----------|----------|--------|------|------------|
| 1 | [SEC-01] include_secrets exposes credentials | Security | **P0** | S | LOW | HIGH |
| 2 | [SEC-03] No authentication on API | Security | **P1** | L | MED | HIGH |
| 3 | [BUG-03] Cypher injection via relationship_types | Security/Bug | **P1** | S | MED | HIGH |
| 4 | [SEC-02] allow_dangerous_requests on Neo4j chain | Security | **P1** | M | MED | HIGH |
| 5 | [BUG-01] Neo4j driver per-request | Perf/Bug | **P1** | S | LOW | HIGH |
| 6 | [TEST-01] No tests for query validation | Tests | **P1** | S | LOW | HIGH |
| 7 | [PERF-03] Sync Neo4j in async route handlers | Perf | **P2** | S | LOW | HIGH |
| 8 | [PERF-02] N+1 relationship resolution in sink | Perf | **P2** | M | MED | HIGH |
| 9 | [BUG-04] Person handler duplication | Debt | **P2** | M | LOW | HIGH |
| 10 | [TEST-02] No person dedup tests | Tests | **P2** | M | LOW | MED |
| 11 | [DEBT-01] 318-line process_single_pr | Debt | **P3** | M | LOW | HIGH |
| 12 | [DEBT-02] MCP client thread join no timeout | Bug | **P2** | S | LOW | HIGH |
| 13 | [DEP-01] Sync requests in logger | Perf | **P3** | S | LOW | HIGH |
| 14 | [DX-01] Duplicate .env.example entries | DX | **P3** | S | LOW | HIGH |
| 15 | [DX-02] No AGENTS.md | DX | **P3** | S | LOW | HIGH |
| 16 | [DEBT-03] F-string logging | Debt | **P3** | M | LOW | HIGH |
| 17 | [DIR-01] GitHub MCP config asymmetry | Direction | **P3** | M | LOW | HIGH |
| 18 | [DIR-02] Email connector is stub | Direction | **P3** | L | LOW | HIGH |
| 19 | [BUG-02] Query validation comment bypass | Bug | **P3** | S | LOW | MED |

---

## Findings Considered and Not Reported

- **Broad `except Exception` usage**: ~50+ instances across the codebase. Most are in chain/MCP code where fail-open is intentional (documented via `# noqa: BLE001`). The pattern is a conscious design choice for resilience, not a bug.
- **`sys.exit()` in modules**: All instances are in CLI scripts and consumer entry points, not in the FastAPI app. This is correct behavior.
- **Missing type stubs for `community.community_louvain`**: Minor DX issue, not worth a finding.
- **`load_dotenv()` in `factory.py`**: Called at import time, but harmless since the app already loads env via Pydantic settings.
