"""MCP client — spawns the MCP server as a stdio subprocess and exposes
its tools as LangChain-compatible tools via ``langchain-mcp-adapters``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

_SERVER_NAME = "dvdrental"
_SRC_DIR = str(Path(__file__).resolve().parent.parent)


def _server_env() -> dict[str, str]:
    """Build the env for the spawned server, guaranteeing ``src`` is on PYTHONPATH."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if _SRC_DIR not in parts:
        parts.insert(0, _SRC_DIR)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _build_client() -> MultiServerMCPClient:
    """Build a ``MultiServerMCPClient`` pointed at our stdio MCP server."""
    return MultiServerMCPClient(
        {
            _SERVER_NAME: {
                "command": sys.executable,
                "args": ["-m", "tools.mcp_server"],
                "transport": "stdio",
                "env": _server_env(),
            }
        }
    )


async def get_mcp_tools() -> list[BaseTool]:
    """Return all MCP tools exposed by the DVD Rental server."""
    client = _build_client()
    return await client.get_tools()
