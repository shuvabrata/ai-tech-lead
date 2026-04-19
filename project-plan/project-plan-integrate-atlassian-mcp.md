## Execution Tracker: Atlassian MCP Server Integration

This document is the execution tracker for integrating the Atlassian Rovo MCP Server into the existing AI agent workflow. The implementation extends the current multi-source augmentation pipeline to add Jira and Confluence context alongside the existing GitHub MCP integration. No new Docker Compose service is required — the Atlassian MCP server is a cloud-hosted service at `https://mcp.atlassian.com/v1/mcp`.

## Status Legend

- `[NS]` Not started
- `[IP]` In progress
- `[BL]` Blocked
- `[DN]` Done

## Overall Status

- Project status: `[NS]`
- Current phase: Phase 0
- Next gate: Phase 0 verification
- Stop rule: Stop if Atlassian org admin has not enabled API token authentication for Rovo MCP — this is a hard prerequisite

## Locked Decisions

- Use the official Atlassian Rovo MCP Server at `https://mcp.atlassian.com/v1/mcp` (cloud-hosted, no self-hosted Docker image available)
- Use `streamable_http_client` transport — same as GitHub MCP; the `/sse` endpoint is deprecated upstream
- Use Bearer token auth with a Rovo MCP scoped API token — not a standard Jira API token
- Collapse `ATLASSIAN_MCP_USERNAME` and `ATLASSIAN_MCP_API_TOKEN` into a single `ATLASSIAN_MCP_TOKEN` setting to align with the GitHub pattern
- No new Docker Compose service is needed; remove the stale default URL referencing `http://jira-mcp:9090/sse`
- Keep all operations read-only (Atlassian MCP supports write operations but they are out of scope)
- Reuse the existing `MCPClientManager` patterns from the GitHub integration; add a parallel `AtlassianMCPClientManager`
- Namespace tool names from each backend (`github__<tool>` and `atlassian__<tool>`) to prevent collisions in the tool executor
- Keep the existing chat REST API unchanged
- Use environment variables for credentials
- Atlassian Cloud only — self-hosted Jira Server and Data Center are not supported by this MCP server

## Scope

- Included: Jira read operations (search issues, get issue details, list projects, list sprints)
- Included: Confluence read operations (search pages, get page content, list spaces)
- Included: Atlassian MCP context injection into the existing augmentation pipeline
- Included: Multi-backend tool discovery and routing in the tool executor
- Excluded: Write operations to Jira or Confluence
- Excluded: Compass integration (can be revisited later)
- Excluded: OAuth 2.1 flow (headless API token path only)
- Excluded: Credential management via connectors database
- Excluded: Frontend changes

## Prerequisites

Before implementation begins, the following must be confirmed out-of-band:

1. The Atlassian org admin has enabled API token authentication for Rovo MCP in Atlassian Administration
2. A Rovo MCP scoped API token has been generated and is available
3. The Atlassian Cloud site URL is known (e.g., `https://yoursite.atlassian.net`)

## Target Architecture

1. Keep [app/ai_agent/ai_agent.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/ai_agent.py) unchanged as the chat entry point.
2. Add `AtlassianMCPClientManager` to [app/ai_agent/mcp_integration/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/client_manager.py), following the same structure as `MCPClientManager`.
3. Update [app/ai_agent/mcp_integration/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/tool_executor.py) to aggregate tools from both GitHub and Atlassian backends with namespacing, and route execution to the correct backend.
4. Update [app/ai_agent/chains/mcp_chain.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/mcp_chain.py) to generalize the relevance check so it triggers on Jira, Confluence, and Compass queries in addition to GitHub queries.
5. The multi-source composition in [app/ai_agent/chains/chains.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/chains.py) requires no changes — it already handles multiple envelopes.

## Phase 0: Finalize Execution Baseline

- Phase status: `[NS]`
- Goal: Confirm prerequisites, validate the Atlassian MCP endpoint behavior, and freeze the implementation plan before writing any code.
- Entry criteria: None

**Steps**

1. `[NS]` Confirm the Atlassian org admin prerequisite: API token authentication enabled for Rovo MCP.
2. `[NS]` Validate the cloud endpoint `https://mcp.atlassian.com/v1/mcp` responds to an MCP `initialize` request using `streamable_http_client` with a valid Rovo MCP scoped token.
3. `[NS]` Confirm tool listing returns non-empty results for Jira and/or Confluence with the test token.
4. `[NS]` Confirm read-only scope is enforced in the token configuration.
5. `[NS]` Accept this tracker as the execution baseline.

**Deliverables**

- Validated endpoint behavior and auth contract documented in this tracker
- Confirmation that `streamable_http_client` works with the Atlassian endpoint (same as GitHub, no `sse_client` needed)

**Verification gate**

1. A manual `initialize` call to `https://mcp.atlassian.com/v1/mcp` succeeds with a valid token.
2. Tool listing returns at least one Jira or Confluence tool.
3. The token scope is read-only.

**Exit criteria**

- Mark Phase 0 as `[DN]` only after endpoint validation evidence is captured in the progress log.

## Phase 1: Settings and Configuration Cleanup

- Phase status: `[NS]`
- Goal: Align the settings model with the validated Atlassian MCP auth contract and remove stale configuration inherited from the initial Jira placeholder.
- Entry criteria: Phase 0 verification gate passed.

**Steps**

1. `[NS]` Remove `ATLASSIAN_MCP_URL` and `ATLASSIAN_MCP_USERNAME` from [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) — these reflect the old Basic Auth assumption and are not used.
2. `[NS]` Add `ATLASSIAN_MCP_TOKEN: str = ""` to [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) — the single Rovo MCP scoped Bearer token.
3. `[NS]` Update `ATLASSIAN_MCP_SERVER_URL` default from `"http://jira-mcp:9090/sse"` to `"https://mcp.atlassian.com/v1/mcp"` in [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py).
4. `[NS]` Update the test in [tests/test_mcp_integration_comprehensive.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/tests/test_mcp_integration_comprehensive.py) to assert `ATLASSIAN_MCP_TOKEN` exists instead of the removed fields.
5. `[NS]` Verify no other code references `ATLASSIAN_MCP_URL`, `ATLASSIAN_MCP_USERNAME`, or `ATLASSIAN_MCP_API_TOKEN`.

**Deliverables**

- Settings model aligned with the Atlassian Bearer token auth pattern
- No stale settings referencing old Basic Auth fields

**Verification**

1. Import [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) without errors.
2. Confirm `ATLASSIAN_MCP_TOKEN` is present and defaults to empty string.
3. Confirm `ATLASSIAN_MCP_SERVER_URL` defaults to `https://mcp.atlassian.com/v1/mcp`.
4. Confirm removed fields (`ATLASSIAN_MCP_URL`, `ATLASSIAN_MCP_USERNAME`, `ATLASSIAN_MCP_API_TOKEN`) are gone.
5. All existing tests pass.

**Exit gate**

- Do not start Phase 2 until all Phase 1 verification steps pass.

## Phase 2: Atlassian MCP Client Layer

- Phase status: `[NS]`
- Goal: Add an `AtlassianMCPClientManager` to the existing client module, following the same patterns as the GitHub client.
- Entry criteria: Phase 1 verification gate passed.

**Steps**

1. `[NS]` Add `AtlassianMCPClientManager` dataclass to [app/ai_agent/mcp_integration/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/client_manager.py).
2. `[NS]` Fields: `atlassian_server_url`, `atlassian_token`, `atlassian_enabled`, `request_timeout_seconds`.
3. `[NS]` Implement `_with_atlassian_session()` using `streamable_http_client` and Bearer token auth — same pattern as `_with_github_session()`.
4. `[NS]` Reuse `_run_sync()` from `MCPClientManager` — extract it to a shared base or mixin if it is duplicated.
5. `[NS]` Implement `check_connection()` returning the same structured status shape as the GitHub manager.
6. `[NS]` Implement `list_tools()` returning normalized tool dicts in provider function-schema format.
7. `[NS]` Implement `call_tool(tool_name, arguments)` returning the same result envelope shape as the GitHub manager.
8. `[NS]` Handle disabled, unavailable, and tool-error states with the same graceful fallback shape.
9. `[NS]` Export `AtlassianMCPClientManager` from [app/ai_agent/mcp_integration/__init__.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/__init__.py).

**Deliverables**

- `AtlassianMCPClientManager` with connection, tool discovery, and tool execution
- Graceful degradation on auth failure, timeout, and disabled state
- Shared async-to-sync bridge (no duplication of `_run_sync` if avoidable)

**Verification**

1. `python -m py_compile app/ai_agent/mcp_integration/client_manager.py` passes.
2. With a valid Rovo MCP token, `list_tools()` returns a non-empty list.
3. With a valid token, `call_tool()` for a known Jira tool returns a structured success result.
4. With an invalid or missing token, `check_connection()` returns `status: unavailable` without raising.
5. With `atlassian_enabled=False`, all methods return the disabled status shape immediately.

**Exit gate**

- Do not start Phase 3 until tool discovery and execution both work against the live Atlassian endpoint.

## Phase 3: Multi-Backend Tool Executor

- Phase status: `[NS]`
- Goal: Extend the tool executor to aggregate tools from both GitHub and Atlassian backends with namespacing, and route execution to the correct backend.
- Entry criteria: Phase 2 verification gate passed.

**Steps**

1. `[NS]` Define the namespacing convention in [app/ai_agent/mcp_integration/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/tool_executor.py): `github__<tool_name>` for GitHub tools, `atlassian__<tool_name>` for Atlassian tools.
2. `[NS]` Update `_build_manager()` or add `_build_atlassian_manager()` to construct the Atlassian manager from settings.
3. `[NS]` Update `list_available_tools()` to call both managers when their respective flags are enabled, prefix each tool's `function.name` with the backend namespace, and return the combined list.
4. `[NS]` Update `execute_tool_call(tool_name, arguments)` to strip the namespace prefix, identify the target backend, and route the call to the correct manager.
5. `[NS]` Handle the case where a tool name has no recognized prefix — return a structured error without raising.
6. `[NS]` Ensure GitHub-only behavior is unchanged when `ATLASSIAN_MCP_ENABLED=False`.

**Deliverables**

- Namespaced tool list aggregated from both backends
- Execution routing by namespace prefix
- No behavioral regression for GitHub-only path

**Verification**

1. With only GitHub enabled, `list_available_tools()` returns only `github__` prefixed tools.
2. With only Atlassian enabled, `list_available_tools()` returns only `atlassian__` prefixed tools.
3. With both enabled, tools from both backends appear in the combined list.
4. `execute_tool_call("github__list_commits", ...)` routes to the GitHub manager.
5. `execute_tool_call("atlassian__search_issues", ...)` routes to the Atlassian manager.
6. `execute_tool_call("unknown__tool", ...)` returns a structured error without crashing.

**Exit gate**

- Do not start Phase 4 until multi-backend discovery and routing are verified.

## Phase 4: MCP Chain Generalization

- Phase status: `[NS]`
- Goal: Update the MCP chain to recognize Jira and Confluence queries as MCP-relevant, alongside existing GitHub query detection.
- Entry criteria: Phase 3 verification gate passed.

**Steps**

1. `[NS]` Update `_check_mcp_relevance()` in [app/ai_agent/chains/mcp_chain.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/mcp_chain.py) to make the YES/NO criteria dynamic based on which backends are enabled.
2. `[NS]` When `ATLASSIAN_MCP_ENABLED=True`, extend the relevance prompt to trigger YES for questions about Jira issues, tickets, sprints, epics, boards, Confluence pages, spaces, and documentation.
3. `[NS]` When only `GITHUB_MCP_ENABLED=True`, keep the existing GitHub-only relevance prompt unchanged.
4. `[NS]` Confirm the tool selection loop in `augment_message_with_mcp()` works correctly with namespaced tool names returned by the updated executor.
5. `[NS]` Confirm the tool result formatter `_tool_result_to_text()` handles results from both backends without changes (result envelope shape is identical).
6. `[NS]` Update the envelope `source` label from `"mcp"` to `"mcp_github"` / `"mcp_atlassian"` if multi-source labeling is desired, or keep as `"mcp"` for simplicity — decide and implement consistently.

**Deliverables**

- Dynamic relevance check covering both GitHub and Atlassian query patterns
- Tool loop compatible with namespaced tool names
- No regression in GitHub-only behavior

**Verification**

1. A GitHub-related prompt triggers MCP augmentation when only GitHub is enabled.
2. A Jira-related prompt (e.g., "find open bugs in Project Alpha") triggers MCP augmentation when Atlassian is enabled.
3. A Confluence-related prompt triggers MCP augmentation when Atlassian is enabled.
4. An unrelated prompt (e.g., "summarize this text") does not trigger MCP augmentation.
5. When both backends are enabled, a query that spans GitHub and Jira can produce tool calls from both namespaces in the same augmentation pass.

**Exit gate**

- Do not start Phase 5 until the relevance check and tool loop are verified for both backends.

## Phase 5: Chat Flow Validation

- Phase status: `[NS]`
- Goal: Validate end-to-end behavior through the existing chat entry points with Atlassian MCP enabled.
- Entry criteria: Phase 4 verification gate passed.

**Steps**

1. `[NS]` Validate the REST chat entry path with `ATLASSIAN_MCP_ENABLED=True` and a valid Rovo MCP token.
2. `[NS]` Send a Jira-related prompt and confirm Atlassian context appears in the augmented message.
3. `[NS]` Send a Confluence-related prompt and confirm Atlassian context appears in the augmented message.
4. `[NS]` Send a GitHub-related prompt with both backends enabled and confirm only GitHub tools are invoked.
5. `[NS]` Confirm that Atlassian service unavailability (e.g., expired token) does not break the overall chat response.
6. `[NS]` Confirm that disabling `ATLASSIAN_MCP_ENABLED` restores GitHub-only behavior with no Atlassian tool calls.
7. `[NS]` Confirm session handling and message history remain unchanged.

**Deliverables**

- Working chat flow with optional Atlassian MCP augmentation
- No change to public chat API shape
- Stable fallback when Atlassian endpoint is unavailable or token is invalid

**Verification**

1. Jira prompt returns a response that includes Atlassian-sourced context.
2. GitHub prompt returns a response that includes GitHub-sourced context (no Atlassian calls).
3. Invalid token returns a normal chat response without error.
4. Disabled flag returns current GitHub-only behavior.

**Exit gate**

- Do not start Phase 6 until integrated chat validation passes for all flag combinations.

## Phase 6: Automated Tests and Regression Coverage

- Phase status: `[NS]`
- Goal: Add sufficient automated coverage so the Atlassian integration can be maintained safely alongside the existing GitHub tests.
- Entry criteria: Phase 5 verification gate passed.

**Steps**

1. `[NS]` Add unit tests for `ATLASSIAN_MCP_TOKEN` and `ATLASSIAN_MCP_SERVER_URL` settings defaults and overrides.
2. `[NS]` Add unit tests for `AtlassianMCPClientManager` — disabled path, unavailable path (mock connection failure), and successful tool listing/execution (mock session).
3. `[NS]` Add unit tests for namespaced tool listing — GitHub-only, Atlassian-only, and both-enabled cases.
4. `[NS]` Add unit tests for execution routing by namespace prefix, including the unknown-prefix error case.
5. `[NS]` Add unit tests for the dynamic relevance prompt — confirm Jira/Confluence keywords trigger YES when Atlassian is enabled.
6. `[NS]` Add regression tests confirming GitHub-only behavior is unchanged when `ATLASSIAN_MCP_ENABLED=False`.
7. `[NS]` Add regression tests confirming that Atlassian tool call failures degrade cleanly without breaking the overall augmentation.
8. `[NS]` Confirm all existing MCP tests still pass after the changes.

**Deliverables**

- Unit coverage for `AtlassianMCPClientManager`
- Unit coverage for multi-backend tool executor (namespacing and routing)
- Unit coverage for dynamic relevance check
- Regression coverage for GitHub-only fallback path
- All existing MCP tests passing

**Verification**

1. New tests pass locally: `pytest tests/test_mcp_integration_comprehensive.py tests/test_atlassian_mcp.py -v`
2. Existing MCP test suite still passes: `pytest tests/test_mcp_chain.py tests/test_chains_mcp_composition.py tests/test_chat_flow_phase5_integration.py tests/test_provider_contract_phase2.py -v`
3. Disabled and unavailable Atlassian paths are covered.
4. Tool name collision is prevented and tested.

**Exit gate**

- Do not mark the project execution-complete until all new and existing MCP tests pass.

## Relevant Files

- [app/ai_agent/mcp_integration/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/client_manager.py): add `AtlassianMCPClientManager`
- [app/ai_agent/mcp_integration/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/tool_executor.py): multi-backend aggregation and routing
- [app/ai_agent/chains/mcp_chain.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/mcp_chain.py): dynamic relevance check
- [app/ai_agent/chains/chains.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/chains.py): no changes expected
- [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py): settings cleanup and new `ATLASSIAN_MCP_TOKEN`
- [app/ai_agent/mcp_integration/__init__.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/__init__.py): export `AtlassianMCPClientManager`
- [tests/test_mcp_integration_comprehensive.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/tests/test_mcp_integration_comprehensive.py): update for removed settings fields

## Active Risks

- **Admin prerequisite is a hard blocker**: If the Atlassian org admin has not enabled API token auth for Rovo MCP, no token will work and Phase 0 cannot pass.
- **Cloud endpoint availability**: Unlike GitHub MCP (self-hosted in Docker), the Atlassian MCP endpoint is outside our infrastructure. Network issues or Atlassian outages will affect the live chat flow.
- **Token scope**: Rovo MCP scoped tokens are distinct from standard Jira API tokens. Using the wrong token type will result in auth failures that look identical to network errors.
- **Tool volume**: The Atlassian MCP server may expose a large number of tools across Jira, Confluence, and Compass. If the combined tool list exceeds the LLM's context for tool definitions, the selection step may degrade. Add a tool count cap in Phase 3 if needed.
- **Atlassian Cloud only**: Any Jira Server or Data Center users cannot use this integration. Document this constraint clearly.

## Future Review Items

- Consider adding Compass tool support once Jira and Confluence paths are stable.
- Evaluate OAuth 2.1 flow support for interactive user contexts (currently out of scope).
- Review adding Atlassian as a second backend for the custom provider tool path once it is implemented.

## Progress Log

- `2026-04-19` `[DN]` Validated official Atlassian MCP server: cloud-hosted at `https://mcp.atlassian.com/v1/mcp`, no Docker image, streamable HTTP transport, Bearer token auth
- `2026-04-19` `[DN]` Renamed all `JIRA_MCP_*` settings to `ATLASSIAN_MCP_*` in [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) and updated corresponding tests
- `2026-04-19` `[DN]` Project plan created; execution tracker initialized
- `2026-04-19` `[NS]` Phase 0 not yet started — pending Atlassian org admin prerequisite confirmation
