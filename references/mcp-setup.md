# MCP Server Setup

## Why MCP?

Odysseus treats skill text as untrusted context by design (Odysseus issue #2959).
This means local models receive CWO's multi-step protocol as narrative text, not
as trusted function schemas — so protocol adherence varies widely by model.

The `cwo_mcp_server.py` adapter moves the three relay verbs (cwo_start,
cwo_answer, cwo_continue) into MCP tools. Once registered, the Odysseus model
receives them on the trusted function-schema list, bypassing the untrusted-text
problem. Local models follow the protocol reliably.

## Registration Steps

1. **Obtain the script path** inside the Odysseus pod:
   - If cwo-ody is imported as a skill: `/app/data/skills/imported/complex-work-orchestration/scripts/cwo_mcp_server.py`
   - If cwo-ody is mounted elsewhere, substitute the correct path.

2. **Open Odysseus Settings** → MCP servers tab.

3. **Add new MCP server**:
   - **Transport**: `stdio`
   - **Command**: `python3`
   - **Args**: `["/full/path/to/cwo_mcp_server.py"]` (substitute the path from step 1)
   - **Environment** (optional): Add `CWO_WORKSPACE` = `/app/data` (or your state dir)
   - Click **Save** and **Reload** MCP servers.

**Important (v1.4.1)**: CWO_WORKSPACE fully determines where all state (sessions, workgraphs) lives. Tool callers cannot override this via `workspace` arguments — the server uses only the environment variable or current working directory. This ensures centralized, server-controlled state management.

4. **Verify**:
   - The MCP servers list should show "cwo" as active.
   - In a new chat, ask the model to plan a task: "plan a two-service refactor"
   - The model should call `cwo_start` (visible in the function call trace).
   - Paste your reply → the model calls `cwo_answer`.
   - Paste recommended item status → the model calls `cwo_continue`.

## Tool Descriptions

### cwo_start
**Call this first** when the user asks to plan, orchestrate, or break down
multi-step work. Returns coaching questions and a routing summary. Pass the
user's goal verbatim.

### cwo_answer
**Call after the user replies** to the cwo_start questions (or says "defaults").
Maps the reply to configuration flags, scaffolds the Markdown workgraph, and
returns the work items plus the workgraph file path.

### cwo_continue
**Call when the user asks to continue or resume** a sprint or workgraph.
Returns the recommended next work item and any blocking issues. The model
should track the workgraph path from the prior cwo_answer call and pass it
(or omit it to auto-discover the newest).

## Expected Flow

1. User: "Plan a large refactor." (on gated hosts, say "plan (mcp)" to trigger MCP)
2. Model calls `cwo_start` with the user's goal.
3. Model relays the complete plan + workgraph file path to the user (done in one turn with defaults applied).
4. Model presents adjustable levers as clickable options via `ask_user`, with labels prefixed "mcp: " (e.g., "mcp: tight graph", "mcp: heavy context"). The Odysseus host's keyword gate ("mcp" passes; others are blocked) requires this prefix so that user clicks route back to tools.
5. **Optional:** User clicks an option or types "mcp: <adjustment>" to adjust orchestration.
6. **Optional:** Model calls `cwo_answer` with the mapped adjustment flags.
7. **Optional:** Model relays the updated plan to the user.
8. User: "Start on item A1."
9. User: "Continue the sprint." (later, in same or fresh chat)
10. Model calls `cwo_continue` (auto-discovers workgraph from workspace).
11. Model relays the next recommended item.

## Troubleshooting

**Server won't start**:
- Verify the path is absolute and readable: `ls -la /path/to/cwo_mcp_server.py`
- Verify Python 3.9+ is installed: `python3 --version`
- Verify the `mcp` package is installed in the Odysseus pod: `python3 -c "import mcp; print(mcp.__version__)"`

**Tools not offered by the model**:
- Reload the MCP server list (Settings → MCP servers → **Reload**).
- Verify the registration path matches the actual import location.
- Check Odysseus logs: server startup errors appear in `~/.odysseus/logs/`.

**Server times out or blocks**:
- The server waits on stdio by design. If it blocks without error, the pod's
  mcp package version may differ from the bundled MCP SDK. Try restarting
  Odysseus and re-registering.

**Verify manually** (from inside the Odysseus pod):
```bash
python3 /app/data/skills/imported/complex-work-orchestration/scripts/cwo_mcp_server.py
# Should block waiting on stdin (correct behavior for MCP stdio transport).
# Press Ctrl-C to exit.
```

## Fallback: CLI Path (No MCP)

If you cannot register MCP in your Odysseus instance, the skill remains
usable via SKILL.md text relay: agents run `cwo_chat.py` directly and paste
output blocks (v1.4.0 behavior). The MCP adapter is optional.
