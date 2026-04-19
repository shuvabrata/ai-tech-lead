"""MCP chain module for GitHub-aware tool selection and context augmentation."""

from __future__ import annotations

import json
from typing import Any

from app.ai_agent.mcp_integration.tool_executor import execute_tool_call, list_available_tools
from app.common.logger import logger
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


def _check_mcp_relevance(user_message: str, provider: Any) -> bool:
    """Use the configured provider to decide if MCP/GitHub tools are likely useful."""
    relevance_prompt = f"""Determine whether this question requires GitHub repository context.

Question: {user_message}

Respond with only YES or NO.
Use YES only if the user asks about GitHub code, pull requests, commits, branches, issues, or repositories.
"""

    try:
        answer = provider.chat_completion([{"role": "user", "content": relevance_prompt}])
        return "YES" in answer.strip().upper()
    except Exception as exc:  # noqa: BLE001 - fallback to safe behavior
        logger.warning(f"Failed MCP relevance check: {exc}")
        return False


def augment_message_with_mcp(user_message: str, provider: Any) -> dict[str, Any]:
    """Augment a user message with GitHub MCP tool context.

    Returns a stable envelope that can be composed with other augmentation sources.
    """
    envelope: dict[str, Any] = {
        "source": "mcp",
        "enabled": settings.GITHUB_MCP_ENABLED,
        "applied": False,
        "context": "",
        "tool_calls": [],
    }

    if not settings.GITHUB_MCP_ENABLED:
        return envelope

    if provider is None:
        from app.ai_agent.providers import get_provider

        provider = get_provider()

    if not _check_mcp_relevance(user_message, provider):
        logger.info("MCP augmentation skipped: message not GitHub-relevant")
        return envelope

    tools = list_available_tools()
    if not tools:
        logger.info("MCP augmentation skipped: no tools available")
        envelope["error"] = "no_tools_available"
        return envelope

    available_tool_names = [tool.get("function", {}).get("name", "") for tool in tools]
    logger.debug(
        "MCP tool discovery complete: available_tools=%s",
        ", ".join(name for name in available_tool_names if name),
    )

    max_iterations = max(1, settings.MAX_MCP_ITERATIONS)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You can call GitHub MCP tools to gather context. "
                "Only call tools that are necessary for the user request."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    collected_results: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        try:
            response = provider.chat_completion_with_tools(messages=messages, tools=tools)
        except NotImplementedError:
            logger.info("MCP augmentation skipped: provider does not support tool calling")
            envelope["error"] = "provider_tool_calling_not_supported"
            return envelope
        except Exception as exc:  # noqa: BLE001 - keep chat flow resilient
            logger.warning(f"MCP tool selection failed: {exc}")
            envelope["error"] = "tool_selection_failed"
            return envelope

        content = (response.get("content") or "").strip()
        tool_calls = response.get("tool_calls") or []

        if tool_calls:
            selected_tool_names = [call.get("name", "") for call in tool_calls]
            logger.info(
                "MCP tool selection: iteration=%s selected_tools=%s",
                iteration,
                ", ".join(name for name in selected_tool_names if name),
            )
        else:
            logger.info("MCP tool selection: iteration=%s selected_tools=none", iteration)

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
            break

        for call in tool_calls:
            name = call.get("name", "")
            arguments = call.get("arguments") or {}
            logger.info("MCP tool execution started: tool=%s", name)
            logger.debug("MCP tool execution arguments: tool=%s args=%s", name, arguments)
            execution_result = execute_tool_call(name, arguments)
            collected_results.append(execution_result)
            logger.info(
                "MCP tool execution finished: tool=%s status=%s",
                name,
                execution_result.get("status", "unknown"),
            )

            tool_content = execution_result.get("result")
            if tool_content is None:
                tool_content = {"error": execution_result.get("error", "execution_failed")}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(tool_content, default=str),
                }
            )

    if not collected_results:
        return envelope

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
    return envelope
