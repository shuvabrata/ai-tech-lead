"""MCP chain module for multi-backend tool selection and context augmentation."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from app.ai_agent.mcp_integration.tool_executor import execute_tool_call, list_available_tools, _build_atlassian_manager
from common.logger import logger
from app.settings import settings


def _truncate_text(text: str, limit: int = 4000) -> str:
    """Bound context size to avoid oversized prompt injection."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... [truncated]"


def _tool_result_to_text(result: dict[str, Any]) -> str:
    """Convert one MCP tool result payload into compact prompt-friendly text."""
    status = result.get("status", "unknown")
    tool_name = result.get("tool_name", "unknown_tool")

    if status != "success":
        error = result.get("error", "tool_execution_failed")
        return f"Tool: {tool_name}\nStatus: {status}\nError: {error}"

    payload = result.get("result") or {}
    structured = payload.get("structured_content")
    content = payload.get("content") or []

    lines = [f"Tool: {tool_name}", "Status: success"]
    if structured:
        lines.append(f"Structured: {_truncate_text(json.dumps(structured, default=str), 2200)}")

    if content:
        lines.append(f"Content: {_truncate_text(json.dumps(content, default=str), 1600)}")

    return "\n".join(lines)


def _enabled_backends() -> list[str]:
    """Return a list of currently enabled MCP backend labels."""
    backends: list[str] = []
    if settings.GITHUB_MCP_ENABLED:
        backends.append("GitHub")
    # Use DB-driven enablement for Atlassian MCP
    try:
        if _build_atlassian_manager().atlassian_enabled:
            backends.append("Atlassian")
    except Exception:
        pass
    return backends


def _check_mcp_relevance(user_message: str, provider: Any) -> bool:
    """Use the configured provider to decide if MCP tools are likely useful."""
    backends = _enabled_backends()
    if not backends:
        return False

    criteria: list[str] = []
    if settings.GITHUB_MCP_ENABLED:
        criteria.append("- GitHub code, pull requests, commits, branches, issues, or repositories")
    if "Atlassian" in backends:
        criteria.append("- Jira issues/tickets/sprints/epics/boards, Confluence pages/spaces/docs, or Atlassian project context")

    criteria_text = "\n".join(criteria)

    relevance_prompt = f"""Determine whether this question requires MCP context from enabled backends.

Enabled MCP backends: {", ".join(backends)}

Question: {user_message}

Respond with only YES or NO.
Use YES only if the user asks about any of the following:
{criteria_text}
"""

    try:
        answer = provider.chat_completion([{"role": "user", "content": relevance_prompt}])
        return "YES" in answer.strip().upper()
    except Exception as exc:  # noqa: BLE001 - fallback to safe behavior
        logger.warning(f"Failed MCP relevance check: {exc}")
        return False


async def augment_message_with_mcp_stream(
    user_message: str,
    provider: Any,
) -> AsyncIterator[dict]:
    """Async generator that augments a message with MCP context and yields thinking chunks.

    Follows the chain streaming generator contract:
    - Yields ``thinking_chunk`` events at each orchestration step (relevance check,
      tool discovery, tool selection per iteration, tool execution per call).
    - Yields a ``thinking_end`` event when processing is complete.
    - Yields an ``augmented_message`` event carrying the MCP envelope dict.

    Unlike the previous implementation, this function owns the full orchestration
    loop directly rather than delegating to the synchronous ``augment_message_with_mcp``
    via ``asyncio.to_thread``.  Each blocking call is individually wrapped in
    ``asyncio.to_thread`` so that thinking chunks are emitted between every step.

    Args:
        user_message: The user's original message.
        provider: LLM provider instance used for tool selection and relevance checks.

    Yields:
        dict: SSE-compatible event dictionaries.
    """
    backends = _enabled_backends()
    if not backends:
        yield {"type": "augmented_message", "content": {
            "source": "mcp", "enabled": False, "applied": False, "context": "", "tool_calls": [],
        }}
        return

    envelope: dict[str, Any] = {
        "source": "mcp",
        "enabled": True,
        "applied": False,
        "context": "",
        "tool_calls": [],
    }

    if provider is None:
        from app.ai_agent.providers import get_provider  # noqa: PLC0415

        provider = get_provider()

    # ── Step 1: relevance check ───────────────────────────────────────────────
    yield {"type": "thinking_chunk", "content": f"Checking if query needs MCP tools ({', '.join(backends)})..."}
    try:
        is_relevant = await asyncio.wait_for(
            asyncio.to_thread(_check_mcp_relevance, user_message, provider),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.warning("MCP relevance check timed out for message: %.80s", user_message)
        yield {"type": "thinking_chunk", "content": "MCP relevance check timed out; skipping MCP."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP relevance check error: %s", exc)
        yield {"type": "thinking_chunk", "content": f"MCP relevance check failed: {exc}"}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return

    if not is_relevant:
        logger.info("MCP augmentation skipped: message not MCP-relevant")
        yield {"type": "thinking_chunk", "content": "Query does not require MCP tools."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return

    # ── Step 2: tool discovery ────────────────────────────────────────────────
    yield {"type": "thinking_chunk", "content": "Query is relevant — discovering available MCP tools..."}
    try:
        tools = await asyncio.to_thread(list_available_tools)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP tool discovery error: %s", exc)
        envelope["error"] = "tool_discovery_failed"
        yield {"type": "thinking_chunk", "content": f"Tool discovery failed: {exc}"}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return

    if not tools:
        logger.info("MCP augmentation skipped: no tools available")
        envelope["error"] = "no_tools_available"
        yield {"type": "thinking_chunk", "content": "No MCP tools available."}
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return

    available_tool_names = [t.get("function", {}).get("name", "") for t in tools]
    logger.debug(
        "MCP tool discovery complete: available_tools=%s",
        ", ".join(n for n in available_tool_names if n),
    )
    yield {"type": "thinking_chunk", "content": f"Found {len(tools)} tool(s). Selecting relevant tools..."}

    # ── Step 3: tool selection and execution loop ─────────────────────────────
    max_iterations = max(1, settings.MAX_MCP_ITERATIONS)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"You can call MCP tools from enabled backends ({', '.join(backends)}). "
                "Only call tools that are necessary for the user request."
            ),
        },
        {"role": "user", "content": user_message},
    ]
    collected_results: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    provider.chat_completion_with_tools,
                    messages=messages,
                    tools=tools,
                ),
                timeout=30.0,
            )
        except NotImplementedError:
            logger.info("MCP augmentation skipped: provider does not support tool calling")
            envelope["error"] = "provider_tool_calling_not_supported"
            yield {"type": "thinking_chunk", "content": "Provider does not support tool calling; skipping MCP."}
            break
        except asyncio.TimeoutError:
            logger.warning("MCP tool selection timed out at iteration %s", iteration)
            envelope["error"] = "tool_selection_timeout"
            yield {"type": "thinking_chunk", "content": f"Tool selection timed out (iteration {iteration})."}
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP tool selection failed: %s", exc)
            envelope["error"] = "tool_selection_failed"
            yield {"type": "thinking_chunk", "content": f"Tool selection failed: {exc}"}
            break

        content = (response.get("content") or "").strip()
        tool_calls = response.get("tool_calls") or []

        assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("arguments") or {}),
                    },
                }
                for call in tool_calls
            ]
        messages.append(assistant_message)

        if not tool_calls:
            logger.info("MCP tool selection: iteration=%s selected_tools=none", iteration)
            break

        selected_names = [c.get("name", "") for c in tool_calls if c.get("name")]
        logger.info(
            "MCP tool selection: iteration=%s selected_tools=%s",
            iteration,
            ", ".join(selected_names),
        )
        yield {"type": "thinking_chunk", "content": f"Calling: {', '.join(selected_names)}"}

        for call in tool_calls:
            name = call.get("name", "")
            arguments = call.get("arguments") or {}
            logger.info("MCP tool execution started: tool=%s", name)
            logger.debug("MCP tool execution arguments: tool=%s args=%s", name, arguments)

            try:
                execution_result = await asyncio.wait_for(
                    asyncio.to_thread(execute_tool_call, name, arguments),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                execution_result = {
                    "tool_name": name, "status": "error", "error": "execution_timeout",
                    "arguments": arguments, "result": None,
                }
            except Exception as exc:  # noqa: BLE001
                execution_result = {
                    "tool_name": name, "status": "error", "error": str(exc),
                    "arguments": arguments, "result": None,
                }

            collected_results.append(execution_result)
            status = execution_result.get("status", "unknown")
            logger.info("MCP tool execution finished: tool=%s status=%s", name, status)
            yield {"type": "thinking_chunk", "content": f"{name}: {status}"}

            tool_content = execution_result.get("result")
            if tool_content is None:
                tool_content = {"error": execution_result.get("error", "execution_failed")}
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(tool_content, default=str),
            })

    if not collected_results:
        yield {"type": "thinking_end"}
        yield {"type": "augmented_message", "content": envelope}
        return

    context_chunks = [_tool_result_to_text(result) for result in collected_results]
    context_block = _truncate_text("\n\n".join(context_chunks), limit=5000)

    envelope["applied"] = True
    envelope["context"] = context_block
    envelope["tool_calls"] = [
        {"name": result.get("tool_name", ""), "status": result.get("status", "unknown")}
        for result in collected_results
    ]
    logger.info(
        "MCP augmentation applied: executed_tools=%s",
        ", ".join(
            f"{call['name']}({call['status']})"
            for call in envelope["tool_calls"]
            if call.get("name")
        ),
    )
    yield {"type": "thinking_end"}
    yield {"type": "augmented_message", "content": envelope}
