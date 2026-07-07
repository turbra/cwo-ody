# Chat protocol: surfacing CWO options in Odysseus

## Trust boundary (read first)

These scripts verify the scripted path only. Nothing here can physically
prevent an agent or operator from bypassing them; the gates are honest
about being advisory. Never present a CWO risk/sensitivity result as a
hard guarantee.

## The Q&A loop

1. Run: `python3 "$CWO_SKILL_ROOT/scripts/coach_prompt.py" --json "<user goal text>"`
2. Parse JSON. Post ONE chat message containing:
   - summary line: recommended orchestration level, route class, risk,
     data sensitivity (fields: `recommended_orchestration_level`,
     `route.route`, `route.risk_level`, `route.data_sensitivity`)
   - each entry of `interactive_questions` as a numbered question with its
     options; mark the option whose label contains "(Recommended)" as the
     default
   - one line: "Reply with choices or 'defaults'."
3. Map answers using the table below. Anything not in the table → use the
   default and tell the user you did.
4. Re-run the coach with the mapped flags appended; show the user the
   summary + `paste_ready_prompt`; on confirmation, scaffold (see
   workgraph-lifecycle.md).

## Answer-to-flag table

| question id | asked as | default | accepted answers → flag/value |
|---|---|---|---|
| `workerbee_parallelism` | "Parallelize with subagents?" | coach's recommended option (label contains "(Recommended)") | "review"/"default" → record `review-subagents`; "heavy" → `heavy-review-subagents`; "no"/"none"/"main thread" → `no-subagents`. No CLI flag — record the value in the final packet message; it directs how YOU execute (whether you fan out work). |
| `beads_context_depth` | "How much prior context should workers read?" | coach's `beads_context_depth` value | "none"/"summary"/"focused"/"heavy"/"audit" → `--beads-context-depth <value>` |
| `model_synthesis` (appears in `enabled_levers`/questions when relevant) | "Activate the model-synthesis lane?" | off | "yes"/"synthesis" → `--model-synthesis`; "no" → omit |
| `scaffold_size` | "Full graph or tight chain?" | `full` | "full" → `--scaffold-size full`; "tight"/"small" → `--scaffold-size tight` |
| data sensitivity (always confirm when route JSON shows `data_sensitivity` above `public` with `data_sensitivity_source: heuristic`) | "This looks <level>. Confirm sensitivity?" | heuristic value | "public"/"redacted"/"internal"/"restricted" → `--data-sensitivity <value>`. Declarations can RAISE the effective level, never lower it (script-enforced). |
| external contracting | not asked in v1 | off | never pass `--external-ok` in v1; if the user asks for external contractor dispatch, say it is out of scope of this skill version |

## Sensitivity conduct

If effective sensitivity is `restricted`: do not send task content to any
external model API configured in Odysseus; say so explicitly and keep the
work in the local conversation.

## Failure conduct

Every script failure: relay stderr to the user verbatim, then propose the
next step (usually re-scaffold or fix the workgraph path). Never invent a
result a script refused to produce.
