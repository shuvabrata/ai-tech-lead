# Elasticsearch Augmentation Chain — Project Plan

## Objective

Add Elasticsearch as a third augmentation chain in the AI chat pipeline, complementing the
existing Neo4j (graph traversal) and MCP (live external data) chains. The ES chain fires for
**search and discovery intent** — keyword lookup, entity-by-attribute queries, person name
searches — and enriches the LLM prompt with matching WBA entity context before generation.

Simultaneously wire **conversation history** into all three chains so pronoun and entity
references resolve correctly across multi-turn conversations ("What Jira issues is she
assigned to?" resolves "she" from a prior turn).

---

## Design Decisions

| Decision | Resolved |
|---|---|
| Chain firing scope | ES fires for find/search/filter/lookup intent; NOT for relationship traversal or graph aggregation |
| Division of responsibility | Neo4j = graph traversal; ES = keyword/attribute search; MCP = live external data |
| Overlap | Gates designed to be mutually exclusive by intent; soft overlap is acceptable |
| Query generation | LLM generates structured `SearchRequest` JSON (two LLM calls: gate + gen, consistent with other chains) |
| LangChain ES | Evaluated and skipped — no value over existing `service.search()` for structured attribute search |
| Invalid JSON fallback | None — if LLM output fails schema validation, chain returns `applied=False` silently. Never fall back to raw user message |
| Schema context | Static curated prompt in `src/app/ai_agent/es_prompt.md` (alongside `neo4j_prompt.md`) |
| Results | Top 5 by default (`ES_CHAIN_MAX_RESULTS`); `full=True`; long text fields truncated at 200 chars |
| ES-only composer | No special case — always routes through `_compose_multi_source_message` |
| Chain order | Neo4j → **ES** → MCP |
| Conversation history | `AUGMENTATION_HISTORY_TURNS=5`; single shared setting; all three chains use it |
| History slice | Last `AUGMENTATION_HISTORY_TURNS × 2` messages from session (system msg excluded) |
| History in Neo4j + MCP | All three chains wired in this implementation (not deferred) |

---

## 1. Settings

Add to `src/app/settings.py` following the existing pydantic-settings pattern:

| Variable | Default | Description |
|---|---|---|
| `AUGMENTATION_HISTORY_TURNS` | `5` | Number of prior conversation turns passed to all augmentation chains for pronoun/reference resolution. One turn = one user + one assistant message. |
| `ES_CHAIN_MAX_RESULTS` | `5` | Maximum number of ES hits to include in the context block passed to the LLM. |

`ELASTICSEARCH_ENABLED`, `ELASTICSEARCH_URL`, and `ELASTIC_PASSWORD` are already defined.

---

## 2. Conversation History Threading

### 2.1 History slice — `src/app/ai_agent/ai_agent.py`

In `stream_chat()`, before calling `augment_message_stream`, compute the history slice:

```python
raw_history = _chat_sessions.get(session_id, [])
non_system = [m for m in raw_history if m["role"] != "system"]
history_window = non_system[-(settings.AUGMENTATION_HISTORY_TURNS * 2):]
```

Pass `conversation_history=history_window` to `augment_message_stream`.

### 2.2 Signature update — `src/app/ai_agent/chains/chains.py`

```python
async def augment_message_stream(
    user_message: str,
    provider=None,
    conversation_history: list[dict] | None = None,
) -> AsyncIterator[dict]:
```

`conversation_history` is passed through to all three chain calls. The existing Neo4j
special-case path (single-envelope early return) is preserved unchanged.

### 2.3 Neo4j chain history — `src/app/ai_agent/chains/neo4j_chain.py`

- `check_neo4j_relevance(user_message, provider, conversation_history=None)`:
  prepend a formatted conversation block to the relevance prompt before the current message.
- `_query_neo4j_with_provider_pipeline(user_message, provider, graph, conversation_history=None)`:
  prepend history to the Cypher generation prompt so entity references resolve.
- `augment_message_with_neo4j_stream(user_message, provider, conversation_history=None)`:
  threads `conversation_history` through to the above two functions.

LangChain path (`GraphCypherQAChain`) does not receive history in this implementation —
it constructs its own messages internally.

### 2.4 MCP chain history — `src/app/ai_agent/chains/mcp_chain.py`

- `_check_mcp_relevance(user_message, provider, conversation_history=None)`:
  prepend history to the relevance prompt.
- `augment_message_with_mcp_stream(user_message, provider, conversation_history=None)`:
  seed the tool-selection `messages` list with history turns before the current user message,
  so the LLM picks tools with full conversational context.

---

## 3. ES Schema Prompt File

Create `src/app/ai_agent/es_prompt.md` alongside the existing `neo4j_prompt.md` and
`llm_neo4j_prompt.md`. This file is loaded once at module import by `elasticsearch_chain.py`.

The prompt must contain:

1. **Purpose statement** — explain the LLM's role: determine if the user is searching for
   entities, and if so generate a `SearchRequest` JSON.
2. **Output contract** — two possible outputs only:
   - `{"relevant": false}` — when the question is not a search/discovery query
   - A `SearchRequest` JSON object — when it is
3. **Relevance criteria**
   - **Fire**: find / search / list / show / look up / filter entities by keyword, name,
     identifier, status, priority, or date range
   - **Do not fire**: questions requiring relationship traversal ("who reviewed X", "how are
     X and Y connected", "what depends on", "collaboration between"), graph aggregation
     ("collaboration score"), or questions answerable purely from context already provided
4. **Entity type registry** (all 13 pairs):

   | Source | Entity Types |
   |---|---|
   | `github` | `Repository`, `Branch`, `Commit`, `PullRequest`, `Person`, `Team`, `File` |
   | `jira` | `Project`, `Issue`, `Epic`, `Initiative`, `Sprint`, `Person` |

5. **Key searchable fields** per entity type — `summary`, `title`, `key`, `name`, `login`,
   `email`, `message`, `path`, `description`, `branch_name`, `sha`, `full_name`
6. **Categorical filter fields and known values**:
   - `status`: `open`, `closed`, `merged`, `active`, `inactive`, `In Progress`, `Done`,
     `To Do`, `In Review`
   - `priority`: `Highest`, `High`, `Medium`, `Low`, `Lowest`
   - `source`: `github`, `jira`
   - `entity_type`: any value from the registry above
7. **`SearchRequest` JSON schema** (all fields optional):
   ```
   {
     "q":           "<free-text keywords — only the meaningful terms, not the full sentence>",
     "entity_type": "<entity type from registry or null>",
     "source":      "<github|jira or null>",
     "status":      "<categorical exact match or null>",
     "priority":    "<categorical exact match or null>",
     "date_from":   "<ISO 8601 or null>",
     "date_to":     "<ISO 8601 or null>"
   }
   ```
8. **`q` field guidance** — extract only the meaningful search terms, not filler words.
   Negative queries ("non-security", "not related to payments") should omit the negated
   term from `q` and use other filters where possible. When intent is purely about
   structured filters (e.g. "show me all open high priority bugs"), `q` may be null.
9. **History usage instruction** — resolve pronouns and entity references from prior turns
   before generating the `SearchRequest`.

---

## 4. Elasticsearch Chain

### 4.1 Location

```
src/app/ai_agent/chains/elasticsearch_chain.py
```

### 4.2 Public interface

```python
def check_es_relevance(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> bool

def generate_search_request(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> SearchRequest | None

async def augment_message_with_es_stream(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> AsyncIterator[dict]
```

### 4.3 `check_es_relevance`

Relevance gate — mirrors `check_neo4j_relevance` in structure.

1. Build prompt: formatted history block + ES relevance criteria (from `es_prompt.md`) +
   current user message.
2. Call `provider.chat_completion([{"role": "user", "content": prompt}])`.
3. Return `True` if `"YES"` in `response.strip().upper()`, else `False`.
4. On any exception: log warning, return `False`.

The prompt is a short focused YES/NO question — not the full schema prompt. The schema
context is reserved for the query generation step to keep the gate call cheap.

### 4.4 `generate_search_request`

Query generation — called only after the relevance gate returns `True`.

1. Build prompt: formatted history block + full `es_prompt.md` (schema + output contract) +
   current user message.
2. Call `provider.chat_completion([{"role": "user", "content": prompt}])`.
3. Parse response as JSON (`json.loads`).
4. If parsed value is `{"relevant": false}` → return `None`.
5. Validate parsed object against the `SearchRequest` field set (no extra required fields;
   unknown keys are ignored). If validation fails → log warning, return `None`.
6. Construct and return a `SearchRequest` with `full=True` and
   `page_size=settings.ES_CHAIN_MAX_RESULTS`.
7. Log the generated request at `DEBUG` level (analogous to `neo4j_query` logging).
8. On any exception: log warning, return `None`.

**Constraint**: if the function cannot produce a valid `SearchRequest` for any reason, it
returns `None`. The caller never falls back to a raw-message query.

### 4.5 `_format_results`

Converts a `SearchResponse` into a plain-text context block for the LLM.

- Header: `Total matches: {total} (showing top {n})`
- Per result (numbered):
  - `wba_id`, entity type and source parsed from `wba_id` (`{source}::{entity_type}::{raw_id}`)
  - `url` and `event_time` if present
  - `highlight` snippet (with `<em>` tags stripped to plain `**bold**` or left as-is)
  - All `attributes` fields from the `full=True` response; string values longer than
    200 characters are truncated with `…`
- Empty response → returns empty string (chain sets `applied=False`)

### 4.6 `augment_message_with_es_stream`

Follows the streaming generator contract: `thinking_chunk*` → `thinking_end` →
`augmented_message`.

```
Guard: ELASTICSEARCH_ENABLED=false
  → yield augmented_message{applied: False}

Step 1 — Relevance gate (asyncio.to_thread, 30s timeout)
  → thinking_chunk("Checking if query requires entity search…")
  → not relevant
       → thinking_chunk("Query does not require entity search.")
       → thinking_end
       → augmented_message{applied: False}

Step 2 — Query generation (asyncio.to_thread, 30s timeout)
  → thinking_chunk("Generating Elasticsearch search request…")
  → None returned (invalid / not relevant)
       → thinking_chunk("Could not generate a valid search request.")
       → thinking_end
       → augmented_message{applied: False}

Step 3 — Execute search (fast, synchronous service.search())
  → thinking_chunk("Searching for relevant entities…")
  → 0 results
       → thinking_chunk("No matching entities found.")
       → thinking_end
       → augmented_message{applied: False}

Step 4 — Format and yield
  → thinking_end
  → augmented_message{
       content: {
         source: "elasticsearch",
         context: <formatted_results>,
         applied: True,
         query: <SearchRequest dict>,
         total_hits: <int>,
       }
     }

Any exception at any step
  → log warning
  → thinking_chunk("Elasticsearch search failed: <error>")
  → thinking_end
  → augmented_message{applied: False}
```

---

## 5. chains.py Integration

### 5.1 ES block insertion

Insert between the Neo4j block and the MCP block:

```python
if settings.ELASTICSEARCH_ENABLED:
    async for event in augment_message_with_es_stream(
        user_message, provider=provider, conversation_history=conversation_history
    ):
        if event["type"] == "augmented_message":
            es_content = event["content"]
            if isinstance(es_content, dict) and es_content.get("applied"):
                envelopes.append(es_content)
                sources_used.append({
                    "type": "elasticsearch",
                    "applied": True,
                    "query": es_content.get("query"),
                    "total_hits": es_content.get("total_hits"),
                })
            else:
                sources_used.append({"type": "elasticsearch", "applied": False})
        else:
            yield event
```

### 5.2 Composer behaviour

ES envelopes always flow through `_compose_multi_source_message` — no special-case
early return. The ES context block is structured entity data (not a natural-language
answer), so it must be composed with the user question and any other active envelopes.

The existing Neo4j single-envelope special case is preserved unchanged.

---

## 6. Implementation Checklist

### Phase 1 — Settings & signature
- [ ] Add `AUGMENTATION_HISTORY_TURNS: int = 5` to `src/app/settings.py`
- [ ] Add `ES_CHAIN_MAX_RESULTS: int = 5` to `src/app/settings.py`
- [ ] Update `augment_message_stream()` signature in `chains.py` to accept `conversation_history: list[dict] | None = None`
- [ ] Compute history slice in `stream_chat()` in `ai_agent.py`; pass to `augment_message_stream`

### Phase 2 — History wiring into Neo4j and MCP (parallel with Phase 1)
- [ ] Add `conversation_history=None` param to `check_neo4j_relevance()` and prepend history to relevance prompt
- [ ] Add `conversation_history=None` param to `_query_neo4j_with_provider_pipeline()` and prepend history to Cypher generation prompt
- [ ] Add `conversation_history=None` param to `augment_message_with_neo4j_stream()` and thread through
- [ ] Add `conversation_history=None` param to `_check_mcp_relevance()` and prepend history to relevance prompt
- [ ] Add `conversation_history=None` param to `augment_message_with_mcp_stream()`; seed tool-selection `messages` list with history turns
- [ ] Update `chains.py` to pass `conversation_history=conversation_history` to both existing chain calls

### Phase 3 — ES schema prompt file (parallel with Phases 1 and 2)
- [ ] Create `src/app/ai_agent/es_prompt.md` with full entity registry, searchable fields, categorical values, `SearchRequest` schema, relevance criteria, and history resolution instruction

### Phase 4 — ES chain implementation (depends on Phases 1 and 3)
- [ ] Create `src/app/ai_agent/chains/elasticsearch_chain.py`
- [ ] Implement `load_es_prompt()` and `_format_history()`
- [ ] Implement `check_es_relevance()` with YES/NO gate prompt and exception fallback
- [ ] Implement `generate_search_request()` with JSON parsing, schema validation, DEBUG logging, and no-fallback constraint
- [ ] Implement `_format_results()` with `full=True` attributes, 200-char truncation, highlight inclusion
- [ ] Implement `augment_message_with_es_stream()` following the four-step flow above

### Phase 5 — chains.py integration (depends on Phase 4)
- [ ] Import `augment_message_with_es_stream` in `chains.py`
- [ ] Insert ES block between Neo4j and MCP blocks with `ELASTICSEARCH_ENABLED` guard

### Phase 6 — Tests
- [ ] Create `tests/test_elasticsearch_chain.py` with:
  - Unit: `check_es_relevance` — returns `True` for search queries, `False` for traversal queries (mock provider)
  - Unit: `generate_search_request` — returns valid `SearchRequest` for clear search query
  - Unit: `generate_search_request` — returns `None` for `{"relevant": false}` output
  - Unit: `generate_search_request` — returns `None` for malformed JSON
  - Unit: `_format_results` — truncates description at 200 chars; includes highlight snippet
  - Unit: `_format_history` — formats last N turns; returns empty string for `None`
  - Integration (marker `elasticsearch`): full chain with live ES using `wbatst::` prefixed test documents; gate fires correctly; search returns and formats results

---

## 7. Verification

1. `pytest -m unit tests/test_elasticsearch_chain.py -q` — all unit tests pass
2. `pytest -m unit tests/ -q` — existing tests unaffected (all new params default to `None`)
3. "Find all high priority Jira bugs" → ES chain fires; Neo4j and MCP do not
4. "Who reviewed Alice's PRs?" → Neo4j fires; ES does not
5. Multi-turn: "Tell me about Alice" → "What Jira issues is she assigned to?" → ES resolves "she" = Alice from history
6. "Fetch me non-security related issues" → ES generates a useful `SearchRequest` (not a raw query containing "non security")
7. `ELASTICSEARCH_ENABLED=false` → ES block is a no-op; other chains and tests unaffected

---

## 8. Excluded Scope

- Parallel chain execution (Neo4j + ES concurrent) — deferred, existing sequential architecture preserved
- LangChain ES integration — evaluated and skipped; no value over `service.search()` for structured attribute search
- Per-chain history window settings — single `AUGMENTATION_HISTORY_TURNS` knob covers all chains
- Graph-from-ES-chain navigation (surfacing `wba_id` links in chat responses) — deferred
- LangChain path history threading for Neo4j (`GraphCypherQAChain` constructs its own messages internally)
