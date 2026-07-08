#!/usr/bin/env python3
"""MCP adapter for the CWO relay.

Exposes the relay verbs as MCP tools so Odysseus delivers them through the
model's trusted function-schema list instead of untrusted skill text
(Odysseus issue #2959). Requires the `mcp` package at RUNTIME only — it is
present in the Odysseus pod; this module stays importable without it so the
skill's test suite runs anywhere.

Register in Odysseus: Settings -> MCP servers -> add, transport stdio,
command `python3`, args `[<abs path to this file>]`, optional env
CWO_WORKSPACE=<state dir>. See references/mcp-setup.md.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwo_chat import CwoChatError, run_answer, run_continue, run_start

SERVER_NAME = "cwo"


def default_workspace() -> Path:
    env = os.environ.get("CWO_WORKSPACE", "").strip()
    return Path(env) if env else Path.cwd()


TOOLS: list[dict] = [
    {
        "name": "cwo_start",
        "description": (
            "Start a Complex Work Orchestration session for a multi-step goal: "
            "coaches the request, returns a summary plus numbered option "
            "questions to relay to the user verbatim. Call this FIRST whenever "
            "the user asks to plan, orchestrate, migrate, or break down "
            "multi-step engineering or research work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The user's goal, verbatim."},
                "workspace": {"type": "string", "description": "Optional state directory; defaults to the server's CWO_WORKSPACE."},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "cwo_answer",
        "description": (
            "Continue the CWO session after the user answers the option "
            "questions (or says 'defaults'). Maps the reply, scaffolds the "
            "Markdown workgraph, returns the final packet with the workgraph "
            "path. Call with the user's reply verbatim."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reply": {"type": "string", "description": "The user's reply, verbatim."},
                "session": {"type": "string", "description": "Optional session file path; defaults to the newest session."},
                "workspace": {"type": "string", "description": "Optional state directory."},
            },
            "required": ["reply"],
        },
    },
    {
        "name": "cwo_continue",
        "description": (
            "Resume a CWO sprint: reads the Markdown workgraph and returns the "
            "recommended next work item with blockers. Call when the user asks "
            "to continue or resume a sprint/workgraph."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workgraph": {"type": "string", "description": "Optional workgraph path; defaults to the newest workgraph."},
                "workspace": {"type": "string", "description": "Optional state directory."},
            },
            "required": [],
        },
    },
]


def _ws(arguments: dict) -> Path:
    raw = str(arguments.get("workspace") or "").strip()
    return Path(raw) if raw else default_workspace()


def handle_tool(name: str, arguments: dict) -> str:
    """Dispatch one tool call; returns the text result (never raises)."""
    try:
        if name == "cwo_start":
            return run_start(str(arguments["goal"]), _ws(arguments), transport="mcp")
        if name == "cwo_answer":
            session = str(arguments.get("session") or "").strip()
            return run_answer(
                str(arguments["reply"]),
                Path(session) if session else None,
                _ws(arguments),
                transport="mcp",
            )
        if name == "cwo_continue":
            workgraph = str(arguments.get("workgraph") or "").strip()
            return run_continue(
                Path(workgraph) if workgraph else None,
                _ws(arguments),
                transport="mcp",
            )
        return f"error: unknown tool {name!r}"
    except CwoChatError as exc:
        return f"CWO error: {exc}"
    except KeyError as exc:
        return f"error: missing required argument {exc}"


def main() -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError:
        raise SystemExit(
            "cwo_mcp_server requires the `mcp` package (present in the "
            "Odysseus pod). Install `mcp` or run inside Odysseus."
        )

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(**t) for t in TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        return [TextContent(type="text", text=handle_tool(name, dict(arguments or {})))]

    async def run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
