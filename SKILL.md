---
name: complex-work-orchestration
description: Govern complex multi-step work — coach the request, route it, scaffold a Markdown workgraph, execute with evidence, and resume across conversations.
version: 0.1.0
category: dev
tags: [orchestration, planning, workgraph, governance]
requires_toolsets: [bash]
status: published
---

## When to Use

Use for multi-step engineering or research work that needs planning,
routing, or resumption across conversations: "plan this feature",
"orchestrate this migration", "continue the sprint", or any request with
several dependent workstreams. Do NOT use for trivial single-step asks
(one-file edits, quick questions) — answer those directly.

## Procedure

1. **Bootstrap (always first).** Locate the installed skill root and prove
   it is executable by running this exact bash command:

   ```bash
   CWO_SKILL_ROOT=""
   for root in "${ODYSSEUS_DATA_DIR:-}" /app/data /data "$HOME/data" "$PWD/data" "$PWD"; do
     [ -n "$root" ] && [ -d "$root" ] || continue
     hit=$(find "$root" -maxdepth 6 -type f -path "*/scripts/cwo_doctor.py" 2>/dev/null | head -1)
     if [ -n "$hit" ]; then CWO_SKILL_ROOT=$(dirname "$(dirname "$hit")"); break; fi
   done
   echo "CWO_SKILL_ROOT=$CWO_SKILL_ROOT"
   python3 "$CWO_SKILL_ROOT/scripts/cwo_doctor.py" --json
   ```

   If `ok` is not `true`, STOP: report the doctor JSON to the user verbatim
   and do not run any other CWO command. If the skill root cannot be found,
   read the reference `upstream-pin.md` via manage_skills view_ref and tell
   the user the skill files are not reachable from the shell.

2. Later milestones add the coach/route/workgraph procedure here.
