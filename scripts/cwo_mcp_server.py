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

from cwo_chat import CwoChatError, run_answer, run_continue, run_mark, run_start

SERVER_NAME = "cwo"


def default_workspace() -> Path:
    env = os.environ.get("CWO_WORKSPACE", "").strip()
    return Path(env) if env else Path.cwd()


TOOLS: list[dict] = [
    {
        "name": "cwo_start",
        "description": (
            "Start a Complex Work Orchestration session for a multi-step goal: "
            "coaches the request, applies recommended defaults, scaffolds the "
            "Markdown workgraph, and returns the complete plan in one call. "
            "Returns the workgraph path and adjustable levers. Call this FIRST "
            "whenever the user asks to plan, orchestrate, migrate, or break down "
            "multi-step engineering or research work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The user's goal, verbatim."},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "cwo_answer",
        "description": (
            "Adjust CWO orchestration options (optional after cwo_start). "
            "Maps the reply, re-scaffolds the Markdown workgraph with new "
            "settings, and returns the updated workgraph path and changed "
            "levers. Call with the user's adjustment reply verbatim."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reply": {"type": "string", "description": "The user's reply, verbatim."},
                "session": {"type": "string", "description": "Optional session file path; defaults to the newest session."},
            },
            "required": ["reply"],
        },
    },
    {
        "name": "cwo_continue",
        "description": (
            "Resume a CWO sprint: reads the Markdown workgraph and returns the "
            "recommended next work item with blockers. Call when the user asks "
            "to continue or resume a sprint/workgraph. Usually omit the workgraph "
            "parameter — the newest workgraph is found automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workgraph": {"type": "string", "description": "Optional workgraph path; defaults to the newest workgraph."},
            },
            "required": [],
        },
    },
    {
        "name": "cwo_mark",
        "description": (
            "Record completion/progress of a workgraph item: updates its Status "
            "and appends evidence. Call after YOU finish an item's work (status "
            "'closed'), or to mark 'in-progress'/'blocked'. Then call cwo_continue."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "The work item ID to mark."},
                "status": {"type": "string", "description": "New status: 'open', 'in-progress', 'closed', or 'blocked'."},
                "evidence": {"type": "string", "description": "One-line evidence text describing the action or completion."},
                "workgraph": {"type": "string", "description": "Optional workgraph path; defaults to the newest workgraph."},
            },
            "required": ["item_id", "status", "evidence"],
        },
    },
]


def handle_tool(name: str, arguments: dict) -> str:
    """Dispatch one tool call; returns the text result (never raises).

    Workspace is always determined by default_workspace() (CWO_WORKSPACE env
    or cwd); any workspace key in arguments is ignored.
    """
    try:
        ws = default_workspace()
        if name == "cwo_start":
            return run_start(str(arguments["goal"]), ws, transport="mcp")
        if name == "cwo_answer":
            session = str(arguments.get("session") or "").strip()
            return run_answer(
                str(arguments["reply"]),
                Path(session) if session else None,
                ws,
                transport="mcp",
            )
        if name == "cwo_continue":
            workgraph = str(arguments.get("workgraph") or "").strip()
            return run_continue(
                Path(workgraph) if workgraph else None,
                ws,
                transport="mcp",
            )
        if name == "cwo_mark":
            workgraph = str(arguments.get("workgraph") or "").strip()
            return run_mark(
                str(arguments["item_id"]),
                str(arguments["status"]),
                str(arguments["evidence"]),
                ws,
                Path(workgraph) if workgraph else None,
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
