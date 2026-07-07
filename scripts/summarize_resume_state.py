#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from cwo_core.workgraph_markdown import (
    FIELD_DEPENDS_ON_LANES,
    FIELD_LABELS,
    FIELD_LANE,
    FIELD_TYPE,
    WORKGRAPH_FALLBACK_MARKER,
    WORKGRAPH_ITEMS_HEADING,
    normalize_field_label,
)

WORKGRAPH_HEADING_RE = re.compile(r"^###\s+([^:\n]+):\s*(.+?)\s*$")
WORKGRAPH_FIELD_RE = re.compile(r"^-\s+([^:]+):\s*(.+?)\s*$")


def coerce_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ["issues", "items", "data"]:
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


def labels(item: dict[str, Any]) -> str:
    raw = item.get("labels", [])
    return ",".join(str(label) for label in raw) if isinstance(raw, list) else str(raw)


def field(item: dict[str, Any], *names: str) -> str:
    for name in names:
        if item.get(name) is not None:
            return str(item[name])
    return ""


def summarize(title: str, items: list[dict[str, Any]], limit: int) -> None:
    print(f"## {title}")
    if not items:
        print("None reported.\n")
        return
    for item in items[:limit]:
        print(f"- {field(item, 'id', 'issue_id')} {field(item, 'title', 'summary')} [{field(item, 'status') or 'unknown'}; {labels(item)}]")
    print()


def markdown_values(value: str) -> list[str]:
    if value.strip() == "none":
        return []
    return [match.strip() for match in re.findall(r"`([^`]+)`", value)]


def parse_markdown_workgraph(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"could not read Markdown workgraph {path}: {exc}") from exc

    if WORKGRAPH_FALLBACK_MARKER not in text or WORKGRAPH_ITEMS_HEADING not in text:
        raise SystemExit(f"{path} is not a CWO Markdown workgraph fallback")

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = WORKGRAPH_HEADING_RE.match(line)
        if heading:
            current = {
                "id": heading.group(1).strip(),
                "title": heading.group(2).strip(),
                "status": "markdown-fallback",
                "labels": [],
            }
            items.append(current)
            continue
        if current is None:
            continue
        field_match = WORKGRAPH_FIELD_RE.match(line)
        if not field_match:
            continue
        name = normalize_field_label(field_match.group(1))
        value = field_match.group(2).strip()
        if name == normalize_field_label(FIELD_LABELS):
            current["labels"] = markdown_values(value)
        elif name == normalize_field_label(FIELD_TYPE):
            current["type"] = ", ".join(markdown_values(value)) or value
        elif name == normalize_field_label(FIELD_LANE):
            current["lane"] = ", ".join(markdown_values(value)) or value
        elif name == normalize_field_label(FIELD_DEPENDS_ON_LANES):
            current["depends_on_lanes"] = markdown_values(value)

    if not items:
        raise SystemExit(f"{path} does not contain any Markdown workgraph items")
    return items


def summarize_markdown_workgraph(path: Path, limit: int) -> None:
    print("## Markdown workgraph fallback")
    print(
        "Beads state was unavailable, so this summary is reduced-durability fallback state. "
        "Do not treat it as shared ready-work or contractor handoff authority.\n"
    )
    print(f"Resume fallback: `python3 scripts/summarize_resume_state.py --markdown-workgraph {path}`\n")
    summarize("Markdown workgraph items", parse_markdown_workgraph(path), limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize orchestration resume from Markdown workgraph.")
    parser.add_argument("--open-limit", type=int, default=20)
    parser.add_argument(
        "--markdown-workgraph",
        type=Path,
        required=True,
        help="Path to the Markdown workgraph state file (the only backend in this skill).",
    )
    args = parser.parse_args()

    print("# Orchestration Resume State\n")
    summarize_markdown_workgraph(args.markdown_workgraph, args.open_limit)


if __name__ == "__main__":
    main()
