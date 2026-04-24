"""Phase 0 validation script: test Atlassian Rovo MCP endpoint connectivity and tool listing.

Usage:
    python scripts/validate_atlassian_mcp.py

Reads ATLASSIAN_MCP_TOKEN and ATLASSIAN_MCP_SERVER_URL from the environment (or .env file).
"""

from __future__ import annotations

import sys
import json

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Load .env so we can run this standalone
from dotenv import load_dotenv
import os
load_dotenv()

ATLASSIAN_MCP_TOKEN = os.getenv("ATLASSIAN_MCP_TOKEN", "")
ATLASSIAN_MCP_SERVER_URL = os.getenv("ATLASSIAN_MCP_SERVER_URL", "https://mcp.atlassian.com/v1/mcp")
TIMEOUT_SECONDS = 30


async def _validate() -> None:
    if not ATLASSIAN_MCP_TOKEN:
        print("ERROR: ATLASSIAN_MCP_TOKEN is not set.")
        sys.exit(1)

    print(f"Endpoint : {ATLASSIAN_MCP_SERVER_URL}")
    print(f"Token    : {ATLASSIAN_MCP_TOKEN[:8]}{'*' * (len(ATLASSIAN_MCP_TOKEN) - 8)}")
    print()

    headers = {"Authorization": f"Bearer {ATLASSIAN_MCP_TOKEN}"}
    timeout = httpx.Timeout(TIMEOUT_SECONDS)

    print("Step 1: Opening MCP session and calling initialize()...")
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
        async with streamable_http_client(ATLASSIAN_MCP_SERVER_URL, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                print(f"  Server name   : {getattr(init_result.serverInfo, 'name', 'unknown')}")
                print(f"  Server version: {getattr(init_result.serverInfo, 'version', 'unknown')}")
                print()

                print("Step 2: Listing available tools...")
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, "tools") else []
                print(f"  Tool count: {len(tools)}")
                print()

                if tools:
                    print("Step 3: Sample tools (first 10):")
                    for tool in tools[:10]:
                        name = getattr(tool, "name", "?")
                        desc = getattr(tool, "description", "") or ""
                        print(f"  - {name}: {desc[:80]}")
                    print()

                    print("Step 4: Full tool names (for namespace planning):")
                    all_names = [getattr(t, "name", "?") for t in tools]
                    print(json.dumps(all_names, indent=2))
                else:
                    print("WARNING: No tools returned. Check token scope and Rovo MCP admin settings.")


def main() -> None:
    try:
        anyio.run(_validate)
        print("\nPhase 0 validation PASSED.")
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error: {exc.response.status_code} {exc.response.text}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\nValidation FAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
