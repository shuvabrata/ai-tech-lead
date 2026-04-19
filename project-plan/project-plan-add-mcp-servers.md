## Execution Tracker: GitHub and Jira MCP Server Integration

This document is the execution tracker for adding GitHub and Jira MCP servers to the existing AI agent workflow. The implementation will extend the current message augmentation pipeline, keep the existing chat API unchanged, use read-only MCP operations, and run MCP servers as dedicated Docker Compose services over HTTP/SSE.

## Status Legend

- `[NS]` Not started
- `[IP]` In progress
- `[BL]` Blocked
- `[DN]` Done

## Overall Status

- Project status: `[IP]` Phase 1–2 complete, Phase 3 started
- Current phase: `Phase 3`
- Next gate: Validate official GitHub and Jira MCP server images before container integration
- Stop rule: Do not begin the next phase until the current phase verification gate passes

## Locked Decisions

- Use off-the-shelf MCP servers first
- Keep the current augmentation pipeline and add MCP as a new augmentation source
- When both Neo4j and MCP are relevant, collect context from both and pass both results to the LLM for final response generation
- Do not use LangGraph in the first iteration
- Use LLM-driven tool selection and tool calling
- Keep all MCP operations read-only
- Keep the existing chat REST API unchanged
- Use environment variables for MCP credentials in the first iteration
- Add independent feature flags for GitHub MCP and Jira MCP
- Run MCP servers as Docker Compose services over HTTP/SSE
- Start with OpenAI only in v1 for tool-enabled provider support
- Keep the current synchronous application shape and wrap async behavior internally where needed
- Validate the official MCP server images and their SSE and health-check behavior during implementation

## Scope

- Included: GitHub read operations for issues, pull requests, commits, and code
- Included: Jira read operations for issues, tickets, boards, and sprints
- Included: MCP context injection into the existing chat workflow
- Excluded: Write operations to GitHub or Jira
- Excluded: Credential management via connectors database
- Excluded: LangGraph orchestration
- Excluded: Frontend changes

## Target Architecture

1. Keep [app/ai_agent/ai_agent.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/ai_agent.py) as the main chat entry point.
2. Extend [app/ai_agent/chains/chains.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/chains.py) so `augment_message()` can invoke both Neo4j augmentation and MCP augmentation using explicit multi-source composition.
3. Add an MCP chain that discovers tools from enabled MCP servers, sends tool definitions to the LLM, executes selected MCP calls, formats the returned context, and returns MCP context in a shared augmentation envelope.
4. Keep final answer generation inside the existing provider flow so API behavior remains stable.
5. When both Neo4j and MCP produce context, combine both into a bounded shared context block and pass that to the final LLM response generation step.
6. Run `github-mcp` and `jira-mcp` as separate Compose services and connect to them over SSE URLs from the app container.

## Phase 0: Finalize Execution Baseline

- Phase status: `[DN]`
- Goal: Freeze the plan structure so implementation can proceed without ambiguity.
- Entry criteria: None

**Steps**

1. `[DN]` Confirm augmentation-pipeline architecture instead of LangGraph.
2. `[DN]` Confirm Docker Compose plus HTTP/SSE deployment model for MCP servers.
3. `[DN]` Confirm read-only scope for GitHub and Jira MCP operations.
4. `[DN]` Convert the plan into a gated execution tracker.

**Deliverables**

- This execution tracker is present and becomes the source of truth for status updates.

**Verification gate**

1. The plan has explicit phase statuses.
2. Each phase has step-level statuses.
3. Each phase has its own verification section.
4. Each phase has an exit gate that must pass before moving forward.

**Exit criteria**

- Mark Phase 0 as `[DN]` only after the tracker structure is accepted for execution.

## Phase 1: Foundation and Configuration

- Phase status: `[DN]`
- Goal: Add the minimum application-level structure needed to support MCP integration without changing runtime behavior yet.
- Entry criteria: Phase 0 verification gate passed.

**Steps**

1. `[DN]` Add the MCP SDK dependency in [requirements.txt](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/requirements.txt).
2. `[DN]` Add MCP feature flags and connection settings in [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py).
3. `[DN]` Add credential env settings for GitHub and Jira in [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py).
4. `[DN]` Add MCP server URL settings in [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py).
5. `[DN]` Create the MCP package structure under `app/ai_agent/mcp/`.
6. `[DN]` Add placeholder exports in the MCP package without wiring runtime behavior yet.
7. `[DN]` Unify feature-flag access through [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) instead of module-level `os.getenv()` reads in chain code.
8. `[DN]` Standardize provider and model environment variable naming so new MCP settings do not repeat existing config drift.

**Deliverables**

- Dependency declaration for MCP support
- Settings model updated for MCP configuration
- MCP package structure created

**Verification**

1. Install dependencies successfully in the project environment.
2. Import [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) without runtime errors.
3. Confirm default settings load correctly when MCP env vars are unset.
4. Confirm explicit env vars override defaults as expected.
5. Confirm the new MCP package imports successfully.
6. Confirm chain feature flags are read from `settings` rather than import-time environment snapshots.
7. Confirm the chosen model env vars are consistent between application code and Docker Compose.

**Exit gate**

- Do not start Phase 2 until all Phase 1 verification steps pass.

## Phase 2: Provider Contract for Tool Use

- Phase status: `[DN]`
- Goal: Extend the provider interface so MCP-related tool definitions and tool call responses can be supported safely.
- Entry criteria: Phase 1 verification gate passed.

**Steps**

1. `[DN]` Review the current provider contract in [app/ai_agent/providers/base.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/providers/base.py).
2. `[DN]` Decide whether to extend `chat_completion()` or add a separate tool-enabled completion method.
3. `[DN]` Implement the provider contract update in [app/ai_agent/providers/base.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/providers/base.py).
4. `[DN]` Update the OpenAI provider implementation to support tool definitions and tool-call responses.
5. `[DN]` Preserve backward compatibility for the existing non-tool chat path.
6. `[DN]` Explicitly scope v1 provider support to OpenAI only.
7. `[DN]` Add a future follow-up note in this document to review support for custom providers after OpenAI v1 is stable.

**Deliverables**

- Stable provider interface for tool-enabled completions
- Updated OpenAI provider implementation
- No regression in normal chat completion behavior
- Explicit OpenAI-only v1 boundary for tool-enabled flow

**Verification**

1. Existing non-tool chat calls still work without code changes in current callers.
2. Tool-enabled completion can return a structured response that the MCP chain can consume.
3. Token counting behavior remains intact.
4. Existing provider tests still pass or are updated with equivalent coverage.
5. The non-tool provider path used by current chat flow remains unchanged for existing callers.

**Exit gate**

- Do not start Phase 3 until the provider contract is stable and verified.

## Phase 3: Docker Compose MCP Services

- Phase status: `[IP]`
- Goal: Run GitHub and Jira MCP servers as dedicated services reachable from the app container.
- Entry criteria: Phase 2 verification gate passed.

**Steps**

1. `[NS]` Validate the official GitHub MCP server image, transport mode, SSE endpoint path, and health-check behavior.
2. `[NS]` Validate the official Jira MCP server image, transport mode, SSE endpoint path, and health-check behavior.
3. `[NS]` Add a `github-mcp` service to [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml).
4. `[NS]` Configure GitHub MCP service for SSE transport on an internal port.
5. `[NS]` Pass GitHub credentials into the GitHub MCP service through environment variables.
6. `[NS]` Add a `jira-mcp` service to [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml).
7. `[NS]` Configure Jira MCP service for SSE transport on an internal port.
8. `[NS]` Pass Jira credentials into the Jira MCP service through environment variables.
9. `[NS]` Add health checks for both MCP services based on validated image behavior.
10. `[NS]` Add service dependencies or startup ordering so the app does not connect before MCP services are ready.

**Deliverables**

- GitHub MCP container service
- Jira MCP container service
- Internal service URLs for both MCP endpoints
- Health checks and startup coordination
- Validation notes for the chosen official images and endpoint contracts

**Verification**

1. `docker compose config` validates successfully.
2. `docker compose up` starts both MCP containers without crash loops.
3. Both MCP services pass their health checks.
4. The app container can resolve service names over the Compose network.
5. SSE endpoints are reachable from inside the app container.
6. The verified image-specific health checks and endpoint paths are captured in the tracker before Phase 4 begins.

**Exit gate**

- Do not start Phase 4 until both MCP services are healthy and reachable from the app container.

## Phase 4: MCP Client Layer

- Phase status: `[NS]`
- Goal: Add a reusable client layer for discovering and calling tools from enabled MCP servers.
- Entry criteria: Phase 3 verification gate passed.

**Steps**

1. `[NS]` Add [app/ai_agent/mcp/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp/client_manager.py).
2. `[NS]` Implement SSE-based connection handling for GitHub MCP.
3. `[NS]` Implement SSE-based connection handling for Jira MCP.
4. `[NS]` Add [app/ai_agent/mcp/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp/tool_executor.py).
5. `[NS]` Implement tool listing across enabled servers.
6. `[NS]` Normalize MCP tool metadata into the format expected by the provider layer.
7. `[NS]` Implement tool execution by tool name and arguments.
8. `[NS]` Handle unavailable services and tool-call failures gracefully.
9. `[NS]` Decide and implement the internal async wrapper strategy while preserving the current synchronous application shape.

**Deliverables**

- SSE MCP client manager
- Tool discovery API
- Tool execution API
- Graceful fallback behavior for connection or execution failures
- Internal async-to-sync wrapper approach documented in code or tests

**Verification**

1. The client layer can connect to GitHub MCP when enabled.
2. The client layer can connect to Jira MCP when enabled.
3. Tool listing returns non-empty results for enabled healthy services.
4. Tool execution returns structured results.
5. Connection failures degrade cleanly without crashing the app.
6. The client layer can be called from the current synchronous chat flow without event-loop failures.

**Exit gate**

- Do not start Phase 5 until tool discovery and tool execution both work in isolation.

## Phase 5: MCP Chain Integration

- Phase status: `[NS]`
- Goal: Wire MCP discovery and tool execution into the existing augmentation pipeline.
- Entry criteria: Phase 4 verification gate passed.

**Steps**

1. `[NS]` Add [app/ai_agent/chains/mcp_chain.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/mcp_chain.py).
2. `[NS]` Implement `augment_message_with_mcp(user_message, provider)`.
3. `[NS]` Add the LLM-driven tool selection loop with a bounded iteration count.
4. `[NS]` Format MCP tool results into bounded prompt context.
5. `[NS]` Skip MCP augmentation cleanly when no MCP feature flags are enabled.
6. `[NS]` Skip MCP augmentation cleanly when services are unavailable or no tools are relevant.
7. `[NS]` Update [app/ai_agent/chains/chains.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/chains.py) to invoke MCP augmentation.
8. `[NS]` Preserve existing Neo4j augmentation behavior.
9. `[NS]` Replace single-path augmentation dispatch with explicit multi-source composition.
10. `[NS]` Define and implement a shared augmentation envelope for Neo4j and MCP context.
11. `[NS]` Combine Neo4j and MCP context into one bounded final prompt block when both are relevant.

**Deliverables**

- MCP augmentation chain
- Updated augmentation dispatcher
- Bounded and safe prompt context injection
- Shared multi-source augmentation format for Neo4j and MCP

**Verification**

1. A prompt unrelated to GitHub or Jira does not trigger MCP context unnecessarily.
2. A GitHub-related prompt can trigger tool discovery and tool execution.
3. A Jira-related prompt can trigger tool discovery and tool execution.
4. The augmentation output remains well-formed and token-bounded.
5. Existing Neo4j-only behavior still works.
6. When both Neo4j and MCP are relevant, both context sources are included in the final augmented prompt.
7. Multi-source context remains bounded and does not break final answer generation.

**Exit gate**

- Do not start Phase 6 until the MCP chain works correctly inside the augmentation pipeline.

## Phase 6: Chat Flow Validation

- Phase status: `[NS]`
- Goal: Validate the integrated behavior through the existing chat entry points.
- Entry criteria: Phase 5 verification gate passed.

**Steps**

1. `[NS]` Validate the CLI entry path in [app/ai_agent/ai_agent.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/ai_agent.py).
2. `[NS]` Validate the REST chat entry path under the existing chat API.
3. `[NS]` Confirm session handling remains unchanged.
4. `[NS]` Confirm failure of one MCP server does not break the overall chat flow.
5. `[NS]` Confirm disabled feature flags preserve current behavior.

**Deliverables**

- Working chat flow with optional MCP augmentation
- No change to public chat API shape
- Stable behavior under partial MCP failure

**Verification**

1. Create a chat session through the current API and send a GitHub-related prompt.
2. Create a chat session through the current API and send a Jira-related prompt.
3. Send a prompt unrelated to both and confirm baseline behavior.
4. Disable GitHub MCP and confirm Jira MCP still works.
5. Disable Jira MCP and confirm GitHub MCP still works.
6. Disable both and confirm the application falls back to current behavior.

**Exit gate**

- Do not start Phase 7 until integrated chat validation passes across enabled and disabled flag combinations.

## Phase 7: Automated Tests and Regression Coverage

- Phase status: `[NS]`
- Goal: Add sufficient automated coverage so the integration can be maintained safely.
- Entry criteria: Phase 6 verification gate passed.

**Steps**

1. `[NS]` Add unit tests for MCP settings and feature flags.
2. `[NS]` Add unit tests for provider tool-response behavior.
3. `[NS]` Add unit tests for SSE client connection logic.
4. `[NS]` Add unit tests for tool listing and execution behavior.
5. `[NS]` Add unit tests for MCP augmentation loop behavior.
6. `[NS]` Add regression tests for fallback behavior when MCP is disabled or unavailable.
7. `[NS]` Add integration-oriented tests where practical without requiring live credentials.

**Deliverables**

- Unit coverage for MCP-specific logic
- Regression coverage for chat fallback paths
- Practical integration-oriented test coverage

**Verification**

1. New automated tests pass locally.
2. Existing relevant tests continue to pass.
3. Failure cases are covered for unavailable MCP services.
4. Fallback behavior is covered when tool discovery or execution fails.

**Exit gate**

- Do not mark the project execution-complete until the new tests and the relevant existing tests pass.

## Relevant Files

- [app/ai_agent/ai_agent.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/ai_agent.py): main chat orchestration
- [app/ai_agent/chains/chains.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/chains.py): augmentation dispatcher
- [app/ai_agent/chains/neo4j_chain.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/chains/neo4j_chain.py): reference chain structure
- [app/ai_agent/providers/base.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/providers/base.py): provider contract changes
- [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py): MCP configuration
- [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml): MCP services
- [requirements.txt](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/requirements.txt): MCP dependency

## Active Risks

- The current provider interface returns plain text, so tool-enabled completions may require a richer response type or a separate method.
- The MCP SDK is async-first, so sync and async boundaries in the current chain flow must be handled carefully.
- Tool results may become too large for prompt injection unless truncation rules are explicit.
- External MCP service failures must degrade cleanly without breaking baseline chat behavior.

## Future Review Items

- Review support for custom providers after OpenAI-based MCP integration is stable in v1.

## Progress Log

- `2026-04-19` `[DN]` Initial MCP integration plan created
- `2026-04-19` `[DN]` Architecture decision finalized: extend augmentation pipeline instead of using LangGraph
- `2026-04-19` `[DN]` Deployment decision finalized: run MCP servers in Docker Compose over HTTP/SSE instead of stdio subprocesses
- `2026-04-19` `[IP]` Execution tracker structure created with gated phases and step-level statuses
- `2026-04-19` `[DN]` Multi-source policy finalized: when Neo4j and MCP are both relevant, collect both and pass both to the final LLM response step
- `2026-04-19` `[DN]` Provider scope finalized for v1: OpenAI first, custom providers deferred to future review
- `2026-04-19` `[DN]` Integration strategy finalized: keep current synchronous shape and wrap async internally where needed
- `2026-04-19` `[DN]` Phase 3 updated to validate official MCP images and endpoint behavior before container integration
- `2026-04-19` `[DN]` Phase 0 completed and accepted as the execution baseline
- `2026-04-19` `[IP]` Phase 1 started with dependency setup as the first active step
- `2026-04-19` `[DN]` Phase 1 Step 1 completed: pinned `mcp[cli]==1.27.0` and verified install on Python 3.14.2
- `2026-04-19` `[IP]` Phase 1 Step 2 started: add MCP feature flags and connection settings
- `2026-04-19` `[DN]` Phase 1 Step 2 completed: added MCP feature flags and `MAX_MCP_ITERATIONS` in settings
- `2026-04-19` `[IP]` Phase 1 Step 3 started: add GitHub and Jira MCP credential env settings
- `2026-04-19` `[DN]` Phase 1 Step 3 completed: added and MCP-prefixed credential settings (`GITHUB_MCP_TOKEN`, `JIRA_MCP_URL`, `JIRA_MCP_USERNAME`, `JIRA_MCP_API_TOKEN`)
- `2026-04-19` `[IP]` Phase 1 Step 4 started: add MCP server URL settings
- `2026-04-19` `[DN]` Phase 1 Step 4 completed: added `GITHUB_MCP_SERVER_URL` and `JIRA_MCP_SERVER_URL` with Docker Compose defaults
- `2026-04-19` `[IP]` Phase 1 Step 5 started: create MCP package structure under `app/ai_agent/mcp/`
- `2026-04-19` `[DN]` Phase 1 Step 5 completed: created `app/ai_agent/mcp/` package with placeholder modules
- `2026-04-19` `[DN]` Phase 1 Step 6 completed: added placeholder MCP exports without runtime wiring
- `2026-04-19` `[IP]` Phase 1 Step 7 started: unify chain feature-flag reads through settings
- `2026-04-19` `[DN]` Phase 1 Step 7 completed: chain dispatcher now reads Neo4j feature flag via `settings` instead of import-time `os.getenv()`
- `2026-04-19` `[IP]` Phase 1 Step 8 started: standardize provider and model env variable naming
- `2026-04-19` `[DN]` Phase 1 Step 8 completed: standardized on `LLM_MODEL` as canonical while retaining `OPENAI_MODEL` and `CUSTOM_MODEL` in Docker Compose for backward compatibility
- `2026-04-19` `[DN]` Phase 1 verification complete: `pip install -r requirements.txt` succeeded with pinned `mcp[cli]==1.27.0`
- `2026-04-19` `[DN]` Phase 1 verification complete: MCP defaults and explicit env overrides validated via `Settings(_env_file=None, ...)`
- `2026-04-19` `[DN]` Phase 1 verification complete: MCP package imports validated and chain flags confirmed to read from `settings`
- `2026-04-19` `[DN]` Phase 1 completed; execution advanced to Phase 2
- `2026-04-19` `[IP]` Phase 2 Step 1 started: review provider contract for tool-enabled completion flow
- `2026-04-19` `[DN]` Phase 2 Step 1 completed: provider contract and call-sites reviewed
- `2026-04-19` `[DN]` Phase 2 Step 2 completed: chose separate tool-enabled provider method to preserve existing `chat_completion()` behavior
- `2026-04-19` `[DN]` Phase 2 Step 3 completed: added `chat_completion_with_tools()` extension to base provider contract
- `2026-04-19` `[DN]` Phase 2 Step 4 completed: implemented OpenAI `chat_completion_with_tools()` with structured tool-call payload
- `2026-04-19` `[DN]` Phase 2 Step 5 completed: existing non-tool chat path preserved unchanged
- `2026-04-19` `[DN]` Phase 2 Step 6 completed: implementation remains OpenAI-first for v1
- `2026-04-19` `[DN]` Phase 2 Step 7 completed: added future review note for custom provider support
- `2026-04-19` `[DN]` Phase 2 verification complete: created 17-test suite covering provider contract backward compatibility
- `2026-04-19` `[DN]` Phase 2 verification complete: all 17 provider contract tests pass (backward compatibility + tool method)
- `2026-04-19` `[DN]` Phase 2 verification complete: tool-enabled method returns correct structured response (content, tool_calls, finish_reason)
- `2026-04-19` `[DN]` Phase 2 verification complete: existing non-tool chat path unchanged for all current callers
- `2026-04-19` `[DN]` Phase 2 completed; execution advanced to Phase 3