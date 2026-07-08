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


def render_start_post(result: dict, session: dict) -> str:
    """Render the POST block for the start command."""
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

    lines.extend(["", "## Your Choices", ""])

    # Add interactive questions
    questions = session.get("questions", [])
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q.get('question')}")
        for option in q.get("options", []):
            label = option.get("label", "")
            is_default = "(Recommended)" in label or "Default" in label
            marker = " (default)" if is_default else ""
            lines.append(f"   - {label}{marker}")

    lines.extend([
        "",
        "Reply with your choices, or say \"defaults\".",
    ])

    return "\n".join(lines)


def render_start_next(session_path: Path) -> str:
    """Render the NEXT block for the start command."""
    abs_path = str(session_path.resolve())
    return "\n".join([
        NEXT_DELIMITER,
        "",
        f'python3 "{Path(__file__).resolve()}" answer "<PASTE USER REPLY HERE>" --session "{abs_path}"',
    ])


def render_answer_post(session: dict, flags_info: dict, used_defaults: list[str], workgraph_path: Path) -> str:
    """Render the POST block for the answer command."""
    lines = [
        POST_DELIMITER,
        "",
        "## Configuration Complete",
        "",
        f"Goal: {session.get('goal')}",
        "",
        "## Chosen Options",
        "",
    ]

    # Show chosen flags
    for key, value in flags_info.items():
        if key == "parallelism":
            # Parallelism is shown but not stored in session flags
            lines.append(f"- Parallelism: {value}")
        elif key in ["scaffold_size", "data_sensitivity", "beads_context_depth"]:
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


def render_answer_next() -> str:
    """Render the NEXT block for the answer command."""
    return "\n".join([
        NEXT_DELIMITER,
        "",
        "(none — session complete. To resume later: python3 \"<abs path to cwo_chat.py>\" continue \"<abs workgraph path>\")",
    ])


def render_continue_post(continuation_brief: dict) -> str:
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

    return "\n".join(lines)


def render_continue_next(workgraph_path: Path) -> str:
    """Render the NEXT block for the continue command."""
    abs_path = str(workgraph_path.resolve())
    return "\n".join([
        NEXT_DELIMITER,
        "",
        f'(none — work the recommended item, update its Status in "{abs_path}", then rerun: python3 "{Path(__file__).resolve()}" continue "{abs_path}")',
    ])


def run_start(goal: str, workspace: Path) -> str:
    """Start a new CWO session and return rendered output.

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

    session = {
        "version": 1,
        "goal": goal,
        "slug": slug,
        "questions": result.get("interactive_questions", []),
        "flags": {},
    }
    save_session(session_path, session)

    # Step 4: Render output
    post = render_start_post(result, session)
    next_cmd = render_start_next(session_path)

    return f"{post}\n\n{next_cmd}"


def run_answer(reply: str, session_path: Path | None, workspace: Path) -> str:
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

    # Step 2: Load session
    session = load_session(session_path)

    # Step 3: Map reply
    flags, used_defaults = map_reply(reply, session.get("questions", []))

    # Step 4: Prepare workspace
    if session_path.parent.parent != workspace:
        workspace = session_path.parent.parent  # .cwo is parent of session file

    # Step 5: Re-run classify_work and scaffold
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

    # Step 6: Write workgraph file
    slug = session.get("slug")
    workgraph_path = workspace / ".cwo" / f"workgraph-{slug}.md"
    with open(workgraph_path, "w") as f:
        f.write(workgraph_markdown)

    # Step 7: Update session JSON
    session["flags"] = {
        k: v for k, v in flags.items() if k != "parallelism"
    }
    session["workgraph"] = str(workgraph_path.resolve())
    if "parallelism" in flags:
        session["parallelism"] = flags["parallelism"]
    save_session(session_path, session)

    # Step 8: Render output
    post = render_answer_post(session, flags, used_defaults, workgraph_path)
    next_cmd = render_answer_next()

    return f"{post}\n\n{next_cmd}"


def run_continue(workgraph_path: Path | None, workspace: Path, epic: str = "epic") -> str:
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

    # Step 2: Validate workgraph exists
    if not workgraph_path.exists():
        raise CwoChatError(f"Workgraph file not found: {workgraph_path}")

    # Step 3: Load and process
    raw_items = load_markdown_items(workgraph_path, epic)
    continuation_brief = build_continuation_brief(
        raw_items, epic_id=epic, sprint_id=None, source="markdown-workgraph"
    )

    # Step 4: Render output
    post = render_continue_post(continuation_brief)
    next_cmd = render_continue_next(workgraph_path)

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
