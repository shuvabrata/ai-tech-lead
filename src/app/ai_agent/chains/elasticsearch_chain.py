"""Elasticsearch augmentation chain for entity search and discovery.

Fires for search and discovery intent (find, list, filter entities by keyword,
name, identifier, status, priority, or date range). Does NOT fire for graph
traversal or relationship queries — those are handled by the Neo4j chain.

Flow per request:
1. Relevance gate (LLM YES/NO) — cheap call using ES criteria only.
2. Query generation (LLM structured JSON) — full schema prompt, outputs SearchRequest.
3. service.search() — fast synchronous ES call.
4. Format results into a bounded context block for the LLM.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from app.api.search.v1.model import SearchRequest, SearchResponse
from app.api.search.v1.service import search as es_search
from app.settings import settings
from common.logger import logger

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_ES_PROMPT: str = ""


def _load_es_prompt() -> str:
    """Load the ES schema and query generation prompt from es_prompt.md."""
    prompt_file = Path(__file__).parent.parent / "es_prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    logger.warning("es_prompt.md not found at %s", prompt_file)
    return ""


# Load once at module import — same pattern as neo4j_chain.py
_ES_PROMPT = _load_es_prompt()

# Relevance gate prompt (short; no schema to keep the call cheap)
_RELEVANCE_GATE_PROMPT = """\
Determine whether this question is a search or discovery request — the user wants to
find, list, look up, or filter entities (people, issues, PRs, repos, commits, etc.)
by keyword, name, identifier, status, priority, or date range.

Respond with only YES or NO.
Use YES for: find / search / list / show / look up / filter entities.
Use NO for: relationship traversal ("who reviewed", "what depends on", "how are X and Y \
connected"), graph aggregation ("collaboration score"), or general knowledge questions.
"""

# Max characters for a single string attribute value in the context block
_ATTRIBUTE_TRUNCATE_LIMIT = 200

# HTML em-tag pattern for stripping ES highlights
_EM_TAG_RE = re.compile(r"</?em>")


# ---------------------------------------------------------------------------
# History formatting (shared helper; mirrors neo4j_chain._format_history_block)
# ---------------------------------------------------------------------------

def _format_history(
    conversation_history: list[dict] | None,
    max_turns: int | None = None,
) -> str:
    """Format conversation history as a readable block for LLM prompts.

    Args:
        conversation_history: List of prior {role, content} dicts (system excluded).
        max_turns: If set, only the last ``max_turns`` user+assistant pairs are used.

    Returns:
        A formatted string block with a trailing newline, or empty string when
        history is absent or empty.
    """
    if not conversation_history:
        return ""
    history = conversation_history
    if max_turns is not None:
        history = conversation_history[-(max_turns * 2):]
    lines = ["## Conversation History (most recent last)"]
    for msg in history:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    lines.append("")  # blank line separator before current question
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Relevance gate
# ---------------------------------------------------------------------------

def check_es_relevance(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> bool:
    """Return True if the user message is a search/discovery query.

    Uses a cheap focused LLM call (no schema context) to decide whether the
    ES chain should proceed to query generation.

    Args:
        user_message: The current user message.
        provider: LLM provider instance.
        conversation_history: Optional prior turn dicts for reference resolution.

    Returns:
        True if the message is a search/discovery intent, False otherwise.
        Falls back to False on any exception.
    """
    history_block = _format_history(conversation_history)
    prompt = (
        f"{_RELEVANCE_GATE_PROMPT}\n"
        f"{history_block}"
        f"Question: {user_message}"
    )
    try:
        answer = provider.chat_completion([{"role": "user", "content": prompt}])
        return "YES" in answer.strip().upper()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES relevance check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def generate_search_request(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> SearchRequest | None:
    """Convert a user message into a validated SearchRequest using the LLM.

    Sends the full ES schema prompt plus conversation history to the LLM and
    expects a JSON response matching the SearchRequest shape. Returns None when:
    - The LLM outputs ``{"relevant": false}``
    - The JSON cannot be parsed
    - The parsed object fails basic field validation

    **Never falls back to a raw-message query.** If a valid SearchRequest cannot
    be constructed, the caller treats the chain as not applied.

    Args:
        user_message: The current user message.
        provider: LLM provider instance.
        conversation_history: Optional prior turn dicts for reference resolution.

    Returns:
        A validated SearchRequest (with full=True and page_size from settings),
        or None on any failure.
    """
    history_block = _format_history(conversation_history)
    prompt = (
        f"{_ES_PROMPT}\n"
        f"{history_block}"
        f"## Current Question\n{user_message}\n\n"
        "Output only the JSON object:"
    )
    try:
        raw = provider.chat_completion([{"role": "user", "content": prompt}])
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES query generation LLM call failed: %s", exc)
        return None

    # Strip markdown fences if the LLM wraps the JSON despite instructions
    cleaned = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("ES query generation returned invalid JSON: %s | raw=%s", exc, raw[:200])
        return None

    if not isinstance(parsed, dict):
        logger.warning("ES query generation returned non-dict JSON: %s", type(parsed))
        return None

    # Explicit not-relevant signal from the LLM
    if parsed.get("relevant") is False:
        logger.debug("ES query generation: LLM signalled not relevant")
        return None

    # Validate and build SearchRequest — unknown keys are silently dropped
    _VALID_FIELDS = {"q", "entity_type", "source", "status", "priority", "date_from", "date_to"}
    filtered = {k: v for k, v in parsed.items() if k in _VALID_FIELDS and v is not None}

    try:
        request = SearchRequest(
            **filtered,
            full=True,
            page_size=settings.ES_CHAIN_MAX_RESULTS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES query generation produced invalid SearchRequest: %s | parsed=%s", exc, filtered)
        return None

    logger.debug("ES chain generated SearchRequest: %s", request.model_dump(exclude_none=True))
    return request


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def _truncate_attribute(value: Any, limit: int = _ATTRIBUTE_TRUNCATE_LIMIT) -> str:
    """Return value as a string, truncating long strings with an ellipsis."""
    text = str(value)
    if len(text) > limit:
        return f"{text[:limit]}\u2026"
    return text


def _strip_em_tags(text: str) -> str:
    """Remove HTML <em>/<em> tags from an ES highlight snippet."""
    return _EM_TAG_RE.sub("", text)


def _format_results(response: SearchResponse) -> str:
    """Convert a SearchResponse into a plain-text context block for the LLM.

    Each result is numbered and includes:
    - wba_id, entity_type and source (parsed from wba_id)
    - url and event_time when present
    - highlight snippet (em tags stripped)
    - all attributes from the full=True response, string values truncated at
      200 chars to prevent context overflow

    Args:
        response: SearchResponse with full=True results.

    Returns:
        Formatted string block, or empty string when no results.
    """
    if not response.results:
        return ""

    lines: list[str] = [
        f"Total matches: {response.total} (showing top {len(response.results)})"
    ]

    for i, result in enumerate(response.results, start=1):
        # Parse source and entity_type from wba_id: "{source}::{entity_type}::{raw_id}"
        parts = result.wba_id.split("::", 2)
        source_label = parts[0] if len(parts) > 0 else "unknown"
        entity_type_label = parts[1] if len(parts) > 1 else "unknown"

        lines.append(f"\n### {i}. {result.wba_id}")
        lines.append(f"Type: {entity_type_label} | Source: {source_label}")
        if result.url:
            lines.append(f"URL: {result.url}")
        if result.event_time:
            lines.append(f"Event time: {result.event_time}")
        if result.highlight:
            lines.append(f"Match: {_strip_em_tags(result.highlight)}")

        # Include all stored attributes (full=True), truncating long strings
        if result.attributes:
            # Skip fields already shown above or internal fields
            _SKIP_FIELDS = {"wba_id", "id", "url", "event_time"}
            for key, value in result.attributes.items():
                if key in _SKIP_FIELDS or value is None:
                    continue
                lines.append(f"{key}: {_truncate_attribute(value)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Streaming chain
# ---------------------------------------------------------------------------

async def augment_message_with_es_stream(
    user_message: str,
    provider: Any,
    conversation_history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Async generator that augments a message with Elasticsearch entity context.

    Follows the chain streaming generator contract:
    - Yields ``thinking_chunk`` events at each step.
    - Yields a ``thinking_end`` event when processing is complete.
    - Yields an ``augmented_message`` event carrying the ES envelope dict.

    The chain is a no-op (applied=False) when ELASTICSEARCH_ENABLED is false,
    when the relevance gate does not fire, when the LLM cannot generate a valid
    SearchRequest, or when ES returns zero results.

    Args:
        user_message: The current user message.
        provider: LLM provider instance.
        conversation_history: Optional prior turn dicts for reference resolution.

    Yields:
        dict: SSE-compatible event dictionaries.
    """
    _not_applied: dict = {"source": "elasticsearch", "applied": False, "context": ""}

    if not settings.ELASTICSEARCH_ENABLED:
        yield {"type": "augmented_message", "content": _not_applied}
        return

    # ── Step 1: Relevance gate ────────────────────────────────────────────────
    yield {"type": "thinking_chunk", "content": "Checking if query requires entity search\u2026"}
    try:
        is_relevant = await asyncio.wait_for(
            asyncio.to_thread(check_es_relevance, user_message, provider, conversation_history),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("ES relevance check timed out: %.80s", user_message)
        yield {"type": "thinking_chunk", "content": "Entity search relevance check timed out; skipping."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES relevance check error: %s", exc)
        yield {"type": "thinking_chunk", "content": f"Entity search check failed: {exc}"}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    if not is_relevant:
        logger.debug("ES augmentation skipped: message not search-relevant")
        yield {"type": "thinking_chunk", "content": "Query does not require entity search."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    # ── Step 2: Query generation ──────────────────────────────────────────────
    yield {"type": "thinking_chunk", "content": "Generating Elasticsearch search request\u2026"}
    try:
        search_request = await asyncio.wait_for(
            asyncio.to_thread(generate_search_request, user_message, provider, conversation_history),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("ES query generation timed out: %.80s", user_message)
        yield {"type": "thinking_chunk", "content": "Search request generation timed out; skipping."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES query generation error: %s", exc)
        yield {"type": "thinking_chunk", "content": f"Search request generation failed: {exc}"}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    if search_request is None:
        logger.debug("ES augmentation skipped: could not generate valid SearchRequest")
        yield {"type": "thinking_chunk", "content": "Could not generate a valid search request."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    # ── Step 3: Execute search ────────────────────────────────────────────────
    yield {"type": "thinking_chunk", "content": "Searching for relevant entities\u2026"}
    try:
        response: SearchResponse = es_search(search_request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ES search execution failed: %s", exc)
        yield {"type": "thinking_chunk", "content": f"Elasticsearch search failed: {exc}"}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    if not response.results:
        logger.debug("ES augmentation skipped: no results for request=%s", search_request.model_dump(exclude_none=True))
        yield {"type": "thinking_chunk", "content": "No matching entities found."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": _not_applied}
        return

    # ── Step 4: Format and yield ──────────────────────────────────────────────
    context_block = _format_results(response)
    logger.info(
        "ES augmentation applied: total_hits=%d returned=%d query=%s",
        response.total,
        len(response.results),
        search_request.model_dump(exclude_none=True, exclude={"full", "page_size", "page"}),
    )
    yield {"type": "thinking_end"}
    yield {
        "type": "augmented_message",
        "content": {
            "source": "elasticsearch",
            "applied": True,
            "context": context_block,
            "query": search_request.model_dump(exclude_none=True, exclude={"full", "page_size", "page"}),
            "total_hits": response.total,
        },
    }
