#!/usr/bin/env python3
# scripts/cwo_doctor.py
"""Self-check sentinel for the CWO Odysseus skill.

The Odysseus agent's bootstrap locates this file to discover the installed
skill root, then runs it to prove the bundle is intact and executable
before any real CWO command. Fail-closed: exit 1 on any problem.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

DOCTOR_RESULT_TYPE = "cwo-odysseus-doctor"
SKILL_VERSION = "1.1.3"

# Extended by later milestones; keep sorted. SKILL.md is listed because a
# truncated import (Odysseus drops files silently at its caps) is the main
# failure this check exists to catch.
REQUIRED_FILES = [
    "SKILL.md",
    "bundle-manifest.txt",
    "policy/routing-policy.yaml",
    "references/chat-protocol.md",
    "references/workgraph-lifecycle.md",
    "scripts/coach_prompt.py",
    "scripts/continue_sprint.py",
    "scripts/cwo_core/__init__.py",
    "scripts/cwo_core/coach.py",
    "scripts/cwo_core/policy.py",
    "scripts/cwo_core/paths.py",
    "scripts/cwo_core/routing.py",
    "scripts/cwo_core/routing_signals.py",
    "scripts/cwo_core/synthesis.py",
    "scripts/cwo_core/util.py",
    "scripts/cwo_core/waivers.py",
    "scripts/cwo_core/workgraph_markdown.py",
    "scripts/cwo_doctor.py",
    "scripts/route_work.py",
    "scripts/scaffold_workgraph.py",
    "scripts/summarize_resume_state.py",
    "templates/markdown-workgraph.md",
]


def check(root: Path) -> dict:
    errors: list[str] = []
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    if sys.version_info < (3, 9):
        errors.append(f"python >= 3.9 required, found {platform.python_version()}")
    return {
        "doctor_result_type": DOCTOR_RESULT_TYPE,
        "ok": not missing and not errors,
        "python_version": platform.python_version(),
        "skill_root": str(root),
        "skill_version": SKILL_VERSION,
        "missing_files": missing,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CWO Odysseus skill self-check.")
    parser.add_argument("--root", type=Path, help="Skill root override (default: two levels above this script).")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON (the only mode; flag kept for call-shape parity).")
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    result = check(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
