#!/usr/bin/env python3
"""CWO relay driver: turn the CWO protocol into one-command-per-turn.

Local models in Odysseus cannot follow a multi-step protocol from skill text
(Odysseus wraps skill content as untrusted context by design). This relay
driver moves the whole protocol into code: the agent's job per turn becomes
"run one command, paste its output". Each command prints the exact chat
message to post AND the exact next command to run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Add sibling scripts directory to path for in-process imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwo_doctor import check
from cwo_core.coach import coach_orchestration_prompt
from cwo_core.routing import classify_work
from scaffold_workgraph import planned_graph, markdown_workgraph_plan
from continue_sprint import load_markdown_items, build_continuation_brief

# Output delimiters
POST_DELIMITER = "===== POST THIS MESSAGE TO THE USER ====="
NEXT_DELIMITER = "===== NEXT COMMAND (run after the user replies) ====="


class CwoChatError(Exception):
    """Exception raised by cwo_chat functions."""
    pass

# Answer-to-flag mapping table
REPLY_MAPPING = {
    "beads_context_depth": ["none", "summary", "focused", "heavy", "audit"],
    "scaffold_size": {
        "tight": "tight",
        "small": "tight",
        "full": "full",
    },
    "data_sensitivity": ["public", "redacted", "internal", "restricted"],
    "parallelism": {
        "heavy-review-subagents": ["heavy subagent", "heavy subagents"],
        "no-subagents": ["no subagent", "no subagents", "main thread"],
        "review-subagents": ["subagent"],
    },
}


def slug_from_text(text: str) -> str:
    """Generate a kebab-case slug from the first 6 words of text."""
    words = text.split()[:6]
    slug = "-".join(words)
    # Replace non-alphanumeric with dash
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower())
    # Strip dashes
    slug = slug.strip("-")
    # Limit to 60 chars
    return slug[:60]


def discover_newest_session(workspace: Path) -> Path:
    """Discover the newest session-*.json file in <workspace>/.cwo/"""
    cwo_dir = workspace / ".cwo"
    if not cwo_dir.exists():
        raise CwoChatError(
            f"no CWO session found under {workspace}/.cwo — run start first"
        )

    sessions = sorted(cwo_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sessions:
        raise CwoChatError(
            f"no CWO session found under {workspace}/.cwo — run start first"
        )
    return sessions[0]


def discover_newest_workgraph(workspace: Path) -> Path:
    """Discover the newest workgraph-*.md file in <workspace>/.cwo/"""
    cwo_dir = workspace / ".cwo"
    if not cwo_dir.exists():
        raise CwoChatError(
            f"no workgraph found under {workspace}/.cwo — run start and answer first"
        )

    workgraphs = sorted(cwo_dir.glob("workgraph-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not workgraphs:
        raise CwoChatError(
            f"no workgraph found under {workspace}/.cwo — run start and answer first"
        )
    return workgraphs[0]


def load_session(path: Path) -> dict:
    """Load and validate session JSON."""
    try:
        with open(path) as f:
            session = json.load(f)
        # Validate required keys
        for key in ["version", "goal", "slug", "questions", "flags"]:
            if key not in session:
                raise ValueError(f"missing required key: {key}")
        return session
    except FileNotFoundError as e:
        raise CwoChatError(f"Error loading session from {path}: {e}") from None
    except (json.JSONDecodeError, ValueError) as e:
        raise CwoChatError(f"Error loading session from {path}: {e}") from None


def save_session(path: Path, session: dict) -> None:
    """Save session JSON to file."""
    with open(path, "w") as f:
        json.dump(session, f, indent=2, sort_keys=True)


def extract_option_value(label: str) -> str:
    """Extract the value from an option label."""
    # If label contains "(Recommended)" or "Default:", extract preceding text
    # Otherwise, return the label as-is but lowercased and cleaned
    match = re.search(r"^(.+?)\s*(?:\(.*\).*)?$", label)
    if match:
        return match.group(1).strip().lower()
    return label.lower().strip()


def map_reply(reply: str, questions: list) -> tuple[dict, list[str]]:
    """Map user reply to flags and track which defaults were used."""
    flags = {}
    used_defaults = []
    reply_lower = reply.lower()

    # Check for "defaults" - use all defaults
    if "default" in reply_lower:
        return {}, ["all defaults (user said 'defaults')"]

    # Extract beads_context_depth
    for value in REPLY_MAPPING["beads_context_depth"]:
        if re.search(rf"\b{value}\b", reply_lower):
            flags["beads_context_depth"] = value
            break
    if "beads_context_depth" not in flags:
        used_defaults.append("beads_context_depth")

    # Extract scaffold_size
    for pattern, value in REPLY_MAPPING["scaffold_size"].items():
        if re.search(rf"\b{pattern}\b", reply_lower):
            flags["scaffold_size"] = value
            break
    if "scaffold_size" not in flags:
        used_defaults.append("scaffold_size")

    # Extract model_synthesis (synthesis without "no synthesis")
    if re.search(r"\bsynthesis\b", reply_lower) and not re.search(r"\bno synthesis\b", reply_lower):
        flags["model_synthesis"] = True
    else:
        flags["model_synthesis"] = False
        if not re.search(r"\bsynthesis\b", reply_lower):
            used_defaults.append("model_synthesis")

    # Extract data_sensitivity
    for value in REPLY_MAPPING["data_sensitivity"]:
        if re.search(rf"\b{value}\b", reply_lower):
            flags["data_sensitivity"] = value
            break
    if "data_sensitivity" not in flags:
        used_defaults.append("data_sensitivity")

    # Extract parallelism (NOT stored in flags, returned separately as execution directive)
    parallelism = None
    for directive, patterns in REPLY_MAPPING["parallelism"].items():
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern)}\b", reply_lower):
                parallelism = directive
                break
        if parallelism:
            break
    if parallelism:
        flags["parallelism"] = parallelism
    else:
        used_defaults.append("parallelism")

    return flags, used_defaults


def get_recommended_option(question: dict) -> dict | None:
    """Extract the recommended option from a question."""
    for option in question.get("options", []):
        label = option.get("label", "")
        if "(Recommended)" in label or "Default" in label:
            return option
    # Fallback: return first option
    options = question.get("options", [])
    return options[0] if options else None


def extract_recommended_flags(questions: list, coach_result: dict | None = None) -> dict:
    """Extract recommended flags from coaching questions and coach result.

    Args:
        questions: List of interactive questions from coach
        coach_result: Full coach result to extract scaffold_sizing and other top-level values
    """
    flags = {}

    # Extract scaffold_size from coach_result's scaffold_sizing
    if coach_result:
        scaffold_sizing = coach_result.get("scaffold_sizing", {})
        if isinstance(scaffold_sizing, dict):
            recommended_size = scaffold_sizing.get("recommended_size")
            if recommended_size:
                flags["scaffold_size"] = recommended_size

        # Extract data_sensitivity from route if available
        route = coach_result.get("route", {})
        if isinstance(route, dict):
            data_sensitivity = route.get("data_sensitivity")
            if data_sensitivity:
                flags["data_sensitivity"] = data_sensitivity

        # Extract model_synthesis from coach result
        model_synthesis = coach_result.get("model_synthesis")
        if model_synthesis is not None:
            flags["model_synthesis"] = model_synthesis if isinstance(model_synthesis, bool) else (str(model_synthesis).lower() in ["true", "yes", "on"])

        # Extract beads_context_depth from coach result
        beads_depth = coach_result.get("beads_context_depth")
        if beads_depth:
            flags["beads_context_depth"] = beads_depth

    # Extract from interactive questions
    for q in questions:
        question_id = q.get("id", "")
        recommended = get_recommended_option(q)
        if not recommended:
            continue

        value = recommended.get("value")

        # Use the structured value if available
        if value:
            if question_id == "workerbee_parallelism":
                flags["parallelism"] = value
            elif question_id == "beads_context_depth" and "beads_context_depth" not in flags:
                flags["beads_context_depth"] = value
            elif question_id == "model_synthesis" and "model_synthesis" not in flags:
                flags["model_synthesis"] = value if isinstance(value, bool) else (str(value).lower() in ["true", "yes", "on"])
            elif question_id == "data_sensitivity" and "data_sensitivity" not in flags:
                flags["data_sensitivity"] = value

    return flags


def get_alternative_values(question_id: str) -> list[str]:
    """Get the list of alternative values for a lever based on question_id."""
    alternatives = {
        "scaffold_size": ["full", "tight"],
        "beads_context_depth": ["none", "summary", "focused", "heavy", "audit"],
        "data_sensitivity": ["public", "redacted", "internal", "restricted"],
        "model_synthesis": ["on", "off"],
        "workerbee_parallelism": ["review", "heavy", "none"],
    }
    return alternatives.get(question_id, [])


def render_start_post(result: dict, session: dict, workgraph_path: Path, applied_flags: dict, transport: str = "cli") -> str:
    """Render the POST block for the start command with applied defaults and workgraph."""
    lines = [
        POST_DELIMITER,
        "",
        "## Orchestration Options",
        "",
        f"Recommended orchestration level: {result.get('recommended_orchestration_level')}",
    ]

    route = result.get("route", {})
    if isinstance(route, dict):
        lines.append(f"Route: {route.get('route')}")
        lines.append(f"Task class: {route.get('task_class')}")
        lines.append(f"Risk level: {route.get('risk_level')}")
        lines.append(f"Data sensitivity: {route.get('data_sensitivity')}")

    # Applied defaults
    lines.extend(["", "## Applied Defaults", ""])
    for key, value in applied_flags.items():
        if key == "parallelism":
            lines.append(f"- Parallelism: {value}")
        else:
            lines.append(f"- {key}: {value}")

    # Workgraph path
    lines.extend(["", "## Workgraph", ""])
    lines.append(f"{workgraph_path.resolve()}")

    # Adjustable levers
    lines.extend(["", "## Adjustable Levers", ""])
    questions = session.get("questions", [])
    for q in questions:
        question_id = q.get("id", "")
        label = q.get("question", "")
        current = applied_flags.get(question_id if question_id != "workerbee_parallelism" else "parallelism")
        alternatives = get_alternative_values(question_id)

        if alternatives:
            alts_str = ", ".join(alternatives)
            lines.append(f"- {label}: {current} (alternatives: {alts_str})")

    # Add agent guidance for clickable options (MCP only)
    if transport == "mcp":
        lines.extend(["", "## Agent Guidance", ""])
        lines.append("Whenever you present the user with choices or ask whether to proceed, use your ask_user tool: 2-6 options, EVERY label prefixed 'mcp: ' (this host requires it; an Other free-text field is added automatically). When a selection arrives, act on it (adjustments -> cwo_answer; next item -> cwo_continue; work -> do it). For this plan, example option labels: 'mcp: accept defaults', 'mcp: tight graph', 'mcp: no subagents', 'mcp: heavy context'.")

    # Add work-item execution guidance for mcp transport
    if transport == "mcp":
        lines.extend(["", "## Work Item Execution", ""])
        lines.append("Work items are executed by YOU (the agent): do the item's work, then edit its Status line in the workgraph file, then call cwo_continue for the next item.")

    return "\n".join(lines)


def render_start_next(transport: str = "cli") -> str:
    """Render the NEXT block for the start command."""
    if transport == "mcp":
        return "\n".join([
            NEXT_DELIMITER,
            "",
            "(none — plan is ready. Adjust via cwo_answer, or resume later via cwo_continue.)",
        ])
    return "\n".join([
        NEXT_DELIMITER,
        "",
        "(none — plan is ready. Adjust via cwo_answer, or resume later via cwo_continue.)",
    ])


def render_answer_post(session: dict, flags_info: dict, used_defaults: list[str], workgraph_path: Path, changed_levers: list[str] | None = None, transport: str = "cli") -> str:
    """Render the POST block for the answer command."""
    lines = [
        POST_DELIMITER,
        "",
        "## Configuration Complete",
        "",
        f"Goal: {session.get('goal')}",
        "",
    ]

    # Show changed levers if any
    if changed_levers:
        lines.extend(["Changed:", ""])
        for lever in changed_levers:
            lines.append(f"- {lever}")
        lines.append("")
        # Add agent guidance for further adjustments (MCP only)
        if transport == "mcp":
            lines.append("You may offer further adjustments via ask_user (2-6 options, every label prefixed 'mcp: '), or proceed to work the items.")
            lines.append("")

    lines.extend(["## Chosen Options", ""])

    # Show chosen flags
    for key, value in flags_info.items():
        if key == "parallelism":
            # Parallelism is shown but not stored in session flags
            lines.append(f"- Parallelism: {value}")
        elif key in ["scaffold_size", "data_sensitivity", "beads_context_depth", "model_synthesis"]:
            default_marker = " (non-default)" if key not in used_defaults else ""
            lines.append(f"- {key}: {value}{default_marker}")

    if used_defaults:
        lines.extend(["", "Defaults used:"])
        for default in used_defaults:
            lines.append(f"- {default}")

    lines.extend([
        "",
        "## Workgraph Created",
        "",
        f"Workgraph: {workgraph_path.resolve()}",
        "",
        "## Work Items",
        "",
    ])

    # Parse and list work items from workgraph
    with open(workgraph_path) as f:
        content = f.read()

    # Extract ### <id>: <title> sections
    for match in re.finditer(r"^### ([^:]+):\s*(.+?)$", content, re.MULTILINE):
        item_id = match.group(1).strip()
        title = match.group(2).strip()
        lines.append(f"- {item_id}: {title}")

    return "\n".join(lines)


def render_answer_next(transport: str = "cli") -> str:
    """Render the NEXT block for the answer command."""
    if transport == "mcp":
        return "\n".join([
            NEXT_DELIMITER,
            "",
            "(none — session complete. To resume later call the cwo_continue tool.)",
        ])
    return "\n".join([
        NEXT_DELIMITER,
        "",
        "(none — session complete. To resume later: python3 \"<abs path to cwo_chat.py>\" continue \"<abs workgraph path>\")",
    ])


def render_continue_post(continuation_brief: dict, transport: str = "cli") -> str:
    """Render the POST block for the continue command."""
    lines = [
        POST_DELIMITER,
        "",
        "## Sprint Continuation",
        "",
        f"Epic: {continuation_brief.get('epic_id')}",
        f"Goal: {continuation_brief.get('sprint_goal')}",
        "",
        "## Recommended Next Issue",
        "",
    ]

    recommended = continuation_brief.get("recommended_next_issue")
    if recommended:
        lines.append(f"- ID: {recommended.get('id')}")
        lines.append(f"- Title: {recommended.get('title')}")
        lines.append(f"- Why: {continuation_brief.get('why_next')}")
    else:
        lines.append("No ready issue available")
        lines.append(f"- Why: {continuation_brief.get('why_next')}")

    lines.extend(["", "## Ready Issues", ""])
    for item in continuation_brief.get("ready_issues", [])[:5]:
        lines.append(f"- {item.get('id')}: {item.get('title')}")
    if not continuation_brief.get("ready_issues"):
        lines.append("- none")

    lines.extend(["", "## Blocked Issues", ""])
    for item in continuation_brief.get("blocked_issues", [])[:5]:
        lines.append(f"- {item.get('id')}: {item.get('title')}")
        for reason in item.get("blockers", []):
            lines.append(f"  - {reason}")
    if not continuation_brief.get("blocked_issues"):
        lines.append("- none")

    warnings = continuation_brief.get("warnings", [])
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")

    # Add agent guidance for user choices (MCP only)
    if transport == "mcp":
        lines.extend(["", "## Agent Guidance", ""])
        lines.append("Whenever you present the user with choices or ask whether to proceed, use your ask_user tool: 2-6 options, EVERY label prefixed 'mcp: ' (this host requires it; an Other free-text field is added automatically). When a selection arrives, act on it.")

    # Add work-item execution guidance and typing tip for mcp transport
    if transport == "mcp":
        lines.extend(["", "## Work Item Execution", ""])
        lines.append("Work items are executed by YOU (the agent): do the item's work, then edit its Status line in the workgraph file, then call cwo_continue for the next item.")
        lines.append("")
        lines.append("Tip for the user: start typed follow-ups with 'mcp:' so this host routes them to tools.")

    return "\n".join(lines)


def render_continue_next(workgraph_path: Path, transport: str = "cli") -> str:
    """Render the NEXT block for the continue command."""
    if transport == "mcp":
        return "\n".join([
            NEXT_DELIMITER,
            "",
            "(none — work the recommended item, update its Status in workgraph, then call cwo_continue again)",
        ])
    abs_path = str(workgraph_path.resolve())
    return "\n".join([
        NEXT_DELIMITER,
        "",
        f'(none — work the recommended item, update its Status in "{abs_path}", then rerun: python3 "{Path(__file__).resolve()}" continue "{abs_path}")',
    ])


def run_start(goal: str, workspace: Path, transport: str = "cli") -> str:
    """Start a new CWO session and return rendered output.

    Applies recommended defaults, scaffolds workgraph immediately.
    Raises CwoChatError if doctor check fails or other issues occur.
    """
    workspace = Path(workspace).resolve()

    # Step 1: Run doctor check
    skill_root = Path(__file__).resolve().parents[1]
    doctor_result = check(skill_root)
    if not doctor_result.get("ok"):
        # Doctor JSON is raised as the error message
        doctor_json = json.dumps(doctor_result, indent=2)
        raise CwoChatError(doctor_json)

    # Step 2: Run coach in-process
    result = coach_orchestration_prompt(
        goal,
        external_ok=False,
        allow_disclosure_escalation=False,
        local_ok=False,
        prefer_local=False,
        local_profile=None,
        share_boundary="no-outside-sharing",
        data_sensitivity=None,
        requested_roles=[],
        file_paths=[],
        stage=None,
        unattended=False,
        execution_environment=None,
        model_synthesis=False,
        scaffold_size=None,
        beads_context_depth=None,
    )

    # Step 3: Create .cwo directory and session file
    cwo_dir = workspace / ".cwo"
    cwo_dir.mkdir(parents=True, exist_ok=True)

    slug = slug_from_text(goal)
    session_path = cwo_dir / f"session-{slug}.json"

    # Step 4: Extract and apply recommended defaults
    questions = result.get("interactive_questions", [])
    applied_flags = extract_recommended_flags(questions, result)

    # Step 5: Scaffold workgraph with applied defaults
    scaffold_size = applied_flags.get("scaffold_size", "full")
    classify_kwargs = {
        "external_ok": False,
        "allow_disclosure_escalation": False,
        "local_ok": False,
        "prefer_local": False,
        "local_profile": None,
        "share_boundary": "no-outside-sharing",
        "data_sensitivity": applied_flags.get("data_sensitivity"),
        "requested_roles": [],
        "execution_environment": None,
        "model_synthesis": applied_flags.get("model_synthesis", False),
        "beads_context_depth": applied_flags.get("beads_context_depth"),
    }
    route = classify_work(goal, **classify_kwargs)
    plan = planned_graph(goal, route, scaffold_size=scaffold_size)
    workgraph_markdown = markdown_workgraph_plan(goal, plan)

    # Step 6: Write workgraph file
    workgraph_path = cwo_dir / f"workgraph-{slug}.md"
    with open(workgraph_path, "w") as f:
        f.write(workgraph_markdown)

    # Step 7: Save session with applied flags and workgraph path
    session = {
        "version": 1,
        "goal": goal,
        "slug": slug,
        "questions": questions,
        "flags": {k: v for k, v in applied_flags.items() if k != "parallelism"},
        "workgraph": str(workgraph_path.resolve()),
    }
    if "parallelism" in applied_flags:
        session["parallelism"] = applied_flags["parallelism"]
    save_session(session_path, session)

    # Step 8: Render output
    post = render_start_post(result, session, workgraph_path, applied_flags, transport)
    next_cmd = render_start_next(transport)

    return f"{post}\n\n{next_cmd}"


def run_answer(reply: str, session_path: Path | None, workspace: Path, transport: str = "cli") -> str:
    """Answer coaching questions and return rendered output.

    If session_path is None, discover the newest session file in workspace.
    Raises CwoChatError if no session is found or other issues occur.
    """
    workspace = Path(workspace).resolve()

    # Step 1: Discover or use provided session path
    if session_path is None:
        session_path = discover_newest_session(workspace)
    else:
        session_path = Path(session_path).resolve()
        # Validate explicitly provided session exists
        if not session_path.exists():
            # Try to discover newest as fallback for error message
            newest_path = None
            try:
                newest_path = discover_newest_session(workspace)
            except CwoChatError:
                pass  # No session at all, just report the missing explicit one

            if newest_path:
                raise CwoChatError(f"session not found: {session_path}. Omit the session argument to use the newest session (newest: {newest_path.resolve()})")
            else:
                raise CwoChatError(f"session not found: {session_path}. Omit the session argument to use the newest session")

    # Step 2: Load session
    session = load_session(session_path)

    # Step 3: Map reply
    flags, used_defaults = map_reply(reply, session.get("questions", []))

    # Step 4: Prepare workspace
    if session_path.parent.parent != workspace:
        workspace = session_path.parent.parent  # .cwo is parent of session file

    # Step 5: Compute changed levers (compare new flags with stored flags)
    previous_flags = session.get("flags", {})
    changed_levers = []
    for key, new_value in flags.items():
        if key != "parallelism":
            old_value = previous_flags.get(key)
            if old_value != new_value:
                changed_levers.append(f"{key}: {old_value} → {new_value}")

    # Step 6: Re-run classify_work and scaffold
    goal = session.get("goal")
    scaffold_size = flags.get("scaffold_size", "full")
    classify_kwargs = {
        "external_ok": False,
        "allow_disclosure_escalation": False,
        "local_ok": False,
        "prefer_local": False,
        "local_profile": None,
        "share_boundary": "no-outside-sharing",
        "data_sensitivity": flags.get("data_sensitivity"),
        "requested_roles": [],
        "execution_environment": None,
        "model_synthesis": flags.get("model_synthesis", False),
        "beads_context_depth": flags.get("beads_context_depth"),
    }
    route = classify_work(goal, **classify_kwargs)
    plan = planned_graph(goal, route, scaffold_size=scaffold_size)
    workgraph_markdown = markdown_workgraph_plan(goal, plan)

    # Step 7: Write workgraph file
    slug = session.get("slug")
    workgraph_path = workspace / ".cwo" / f"workgraph-{slug}.md"
    with open(workgraph_path, "w") as f:
        f.write(workgraph_markdown)

    # Step 8: Update session JSON
    session["flags"] = {
        k: v for k, v in flags.items() if k != "parallelism"
    }
    session["workgraph"] = str(workgraph_path.resolve())
    if "parallelism" in flags:
        session["parallelism"] = flags["parallelism"]
    save_session(session_path, session)

    # Step 9: Render output
    post = render_answer_post(session, flags, used_defaults, workgraph_path, changed_levers if changed_levers else None, transport)
    next_cmd = render_answer_next(transport)

    return f"{post}\n\n{next_cmd}"


def run_continue(workgraph_path: Path | None, workspace: Path, epic: str = "epic", transport: str = "cli") -> str:
    """Continue a sprint and return rendered output.

    If workgraph_path is None, discover the newest workgraph file in workspace.
    Raises CwoChatError if no workgraph is found or other issues occur.
    """
    workspace = Path(workspace).resolve()

    # Step 1: Discover or use provided workgraph path
    if workgraph_path is None:
        workgraph_path = discover_newest_workgraph(workspace)
    else:
        workgraph_path = Path(workgraph_path).resolve()
        # Step 2: Validate explicitly provided workgraph exists
        if not workgraph_path.exists():
            # Try to discover newest as fallback for error message
            newest_path = None
            try:
                newest_path = discover_newest_workgraph(workspace)
            except CwoChatError:
                pass  # No workgraph at all, just report the missing explicit one

            if newest_path:
                raise CwoChatError(f"workgraph not found: {workgraph_path}. Call cwo_continue with no workgraph argument to use the newest workgraph automatically (newest: {newest_path.resolve()})")
            else:
                raise CwoChatError(f"workgraph not found: {workgraph_path}. Call cwo_continue with no workgraph argument to use the newest workgraph automatically")

    # Step 3: Load and process
    raw_items = load_markdown_items(workgraph_path, epic)
    continuation_brief = build_continuation_brief(
        raw_items, epic_id=epic, sprint_id=None, source="markdown-workgraph"
    )

    # Step 4: Render output
    post = render_continue_post(continuation_brief, transport)
    next_cmd = render_continue_next(workgraph_path, transport)

    return f"{post}\n\n{next_cmd}"


def main() -> None:
    parser = argparse.ArgumentParser(description="CWO relay driver for weak local models.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand")

    # start subcommand
    start_parser = subparsers.add_parser("start", help="Start a new CWO session")
    start_parser.add_argument("goal", help="User goal text")
    start_parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace path (default: cwd)")

    # answer subcommand
    answer_parser = subparsers.add_parser("answer", help="Answer coaching questions")
    answer_parser.add_argument("reply", help="User reply text")
    answer_parser.add_argument("--session", type=Path, default=None, help="Session file path (default: discover newest)")
    answer_parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace path (default: cwd)")

    # continue subcommand
    continue_parser = subparsers.add_parser("continue", help="Continue a sprint")
    continue_parser.add_argument("workgraph", nargs="?", default=None, help="Workgraph file path (default: discover newest)")
    continue_parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace path (default: cwd)")
    continue_parser.add_argument("--epic", default="epic", help="Epic ID (default: epic)")

    args = parser.parse_args()

    try:
        if args.command == "start":
            output = run_start(args.goal, args.workspace)
            print(output)
        elif args.command == "answer":
            output = run_answer(args.reply, args.session, args.workspace)
            print(output)
        elif args.command == "continue":
            output = run_continue(args.workgraph, args.workspace, args.epic)
            print(output)
    except CwoChatError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
