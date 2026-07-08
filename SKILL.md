---
name: complex-work-orchestration
description: Govern complex multi-step work — coach the request, route it, scaffold a Markdown workgraph, execute with evidence, and resume across conversations.
version: 1.5.0
category: dev
tags: [orchestration, planning, workgraph, governance]
requires_toolsets: [bash]
status: published
---

## When to Use

ALWAYS use this skill immediately, before answering in your own words, when
the user names it ("use complex-work-orchestration", "CWO"); asks to plan,
orchestrate, migrate, or break down multi-step engineering or research work;
or says "continue the sprint" / "resume the workgraph". Do NOT gather
requirements or draft a plan yourself first. Procedure step 2's coach does
that. Only skip this skill for trivial single-step asks (one-file edits,
quick questions).

## Procedure

**If cwo MCP tools are available (cwo_start / cwo_answer / cwo_continue),
use THEM for everything below and ignore the bash commands in this
procedure — never mix the two lanes; the MCP server owns the state
directory.** Otherwise:

Your ONLY job is to run one command per turn with your bash or shell tool
and paste its output blocks to the user. Never plan, summarize, or answer
in your own words; never ask the user to run commands; never use
`update_plan`, `pipeline`, `chat_with_model`, `web_search`, or
`manage_endpoints` for this work. If no bash or shell tool is available,
reply `CWO_BLOCKED_NO_SHELL: no bash/shell execution tool is available for
this CWO skill` and STOP — do not offer alternative workflows.

1. **Start.** Run (substituting the user's goal):

   ```bash
   CWO_SKILL_ROOT=""
   for root in "${ODYSSEUS_DATA_DIR:-}" /app/data /data "$HOME/data" "$PWD/data" "$PWD"; do
     [ -n "$root" ] && [ -d "$root" ] || continue
     hit=$(find "$root" -maxdepth 6 -type f -path "*/scripts/cwo_chat.py" 2>/dev/null | head -1)
     if [ -n "$hit" ]; then CWO_SKILL_ROOT=$(dirname "$(dirname "$hit")"); break; fi
   done
   python3 "$CWO_SKILL_ROOT/scripts/cwo_chat.py" start "<user goal>" --workspace "$PWD"
   ```
   
   The output contains two blocks: paste the text under `POST THIS MESSAGE
   TO THE USER` to the user verbatim. The plan and workgraph are now ready.

2. **Adjust (optional).** If the user wants to adjust orchestration options,
   run the command printed under `NEXT COMMAND`, substituting the user's
   reply where it says `<PASTE USER REPLY HERE>`. If there is no NEXT COMMAND
   block (it says `(none ...)`), the plan cannot be adjusted further and is
   ready to execute.

3. **Resume.** When the user asks to continue/resume a sprint or workgraph,
   run step 1's find loop, then:
   `python3 "$CWO_SKILL_ROOT/scripts/cwo_chat.py" continue "<workgraph path>"`
   and relay the blocks the same way.

4. **Failures.** If a command exits non-zero, paste its exact stderr to the
   user and STOP. Never claim a file is missing or a command failed without
   pasting the exact command you ran and its raw output as evidence. If the
   effective data sensitivity reported in the output is `restricted`, keep
   all content away from external model APIs and say why.
