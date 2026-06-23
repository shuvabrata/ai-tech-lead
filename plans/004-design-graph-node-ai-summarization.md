# Plan 004: Design Graph Node AI Summarization

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 5b3a7f7..HEAD`
> If the codebase has fundamentally changed its UI layout for the graph page,
> STOP.

## Status

- **Priority**: P3
- **Effort**: M (Spike/Design)
- **Risk**: LOW
- **Depends on**: none
- **Category**: feature
- **Planned at**: commit `c832d0c`, 2026-06-20
- **Issue**: https://github.com/shuvabrata/work-behavior-analytics-ai/issues/166

## Why this matters

Currently, the application displays collaboration graphs and provides an AI chat interface separately. By integrating AI summarization directly into the graph node interaction (e.g., clicking a person node and seeing an AI-generated summary of their recent activity, key PRs, and top collaborators), we provide immediate, high-value contextual insights. This bridges the gap between raw graph visualization and AI reasoning.

## Current state

- The graph visualization is powered by Dash Cytoscape.
- Node clicks currently trigger standard Dash callbacks (e.g., `src/app/dash_app/pages/graph/callbacks/context_menu.py`).
- The AI agent (`src/app/ai_agent/`) is used primarily via the chat endpoint.

## Commands you will need

None required for a design plan other than reading the codebase.

## Scope

**In scope**:
- Prototyping/designing the API endpoint for node summarization.
- Designing the UI integration (e.g., adding an "AI Summary" tab or button in the node details panel).

**Out of scope**:
- Full production implementation in this single plan. This is a design/spike plan.

## Steps

### Step 1: Define the AI prompt and chain
Create a markdown document or a spike branch documenting a new LangChain chain in `src/app/ai_agent/chains/summarization_chain.py`.
The chain should take a `node_id` and its adjacent subgraph (retrieved via Neo4j) and prompt the LLM to summarize the entity's context.

### Step 2: Define the API surface
Design a FastAPI endpoint `GET /api/v1/graph/nodes/{wba_id}/summary` that invokes this chain.

### Step 3: Design the UI integration
Document how the Dash frontend will fetch and display this summary. Considerations:
- Use a `dcc.Loading` spinner since LLM calls can take 2-5 seconds.
- Place it in the existing Details Panel when a node is clicked.

## Done criteria

- [ ] A design document or spike PR is created detailing the prompt, endpoint, and UI changes.
- [ ] `plans/README.md` status row updated.

## STOP conditions
- N/A for a design plan.
