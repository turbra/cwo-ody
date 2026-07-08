# Chat protocol: surfacing CWO options in Odysseus

> **v1.4.0:** `scripts/cwo_chat.py` implements this protocol in code — the
> agent calls `cwo_start` once and receives the complete plan, workgraph path,
> and recommended defaults in a single turn. Optional adjustments are then made
> via `cwo_answer`. This document remains the human-readable specification of
> the mapping the script applies.

## Trust boundary (read first)

These scripts verify the scripted path only. Nothing here can physically
prevent an agent or operator from bypassing them; the gates are honest
about being advisory. Never present a CWO risk/sensitivity result as a
hard guarantee.

## The default-first flow

1. Run: `python3 "$CWO_SKILL_ROOT/scripts/cwo_chat.py start "<user goal text>"`
   (or via MCP: call `cwo_start` with the user's goal text)
2. Parse JSON response. The output includes:
   - summary line: recommended orchestration level, route class, risk,
     data sensitivity (fields: `recommended_orchestration_level`,
     `route.route`, `route.risk_level`, `route.data_sensitivity`)
   - the complete plan and workgraph file path (ready to use)
   - an "Adjustable levers" section describing optional parameters and their
     current defaults (drawn from `enabled_levers`)
3. Post the summary and workgraph path to the user. The defaults are already
   applied and optimal for the detected scenario.
4. **Optional:** If the user requests adjustments (e.g., "use tight graph"
   or "activate synthesis"), map their request using the adjustment vocabulary
   table below and call `cwo_answer` with the mapped flags. Re-run to apply
   the new settings and relay the updated summary (see workgraph-lifecycle.md).

## Adjustment vocabulary

This table applies **only** when the user requests adjustments to the defaults.
It maps their natural-language request to the CLI flags used in `cwo_answer`.

| lever id | natural-language request | default | accepted answers → flag/value |
|---|---|---|---|
| `workerbee_parallelism` | "parallelize with subagents?" or "use main thread?" | coach's recommended option | "review"/"default" → record `review-subagents`; "heavy" → `heavy-review-subagents`; "no"/"none"/"main thread" → `no-subagents`. No CLI flag — record the value in the final packet message; it directs how YOU execute (whether you fan out work). |
| `beads_context_depth` | "how much prior context?" or "read full history?" | coach's `beads_context_depth` value | "none"/"summary"/"focused"/"heavy"/"audit" → `--beads-context-depth <value>` |
| `model_synthesis` (appears in `enabled_levers` when relevant) | "activate synthesis lane?" | off | "yes"/"synthesis" → `--model-synthesis`; "no" → omit |
| `scaffold_size` | "tight or full graph?" | `full` | "full" → `--scaffold-size full`; "tight"/"small" → `--scaffold-size tight` |
| data sensitivity (always confirm when route JSON shows `data_sensitivity` above `public` with `data_sensitivity_source: heuristic`) | "confirm sensitivity?" | heuristic value | "public"/"redacted"/"internal"/"restricted" → `--data-sensitivity <value>`. Declarations can RAISE the effective level, never lower it (script-enforced). |
| external contracting | not offered in v1.4.0 | off | never pass `--external-ok` in v1.4.0; if the user asks for external contractor dispatch, say it is out of scope of this skill version |

## Sensitivity conduct

If effective sensitivity is `restricted`: do not send task content to any
external model API configured in Odysseus; say so explicitly and keep the
work in the local conversation.

## Failure conduct

Every script failure: relay stderr to the user verbatim, then propose the
next step (usually re-scaffold or fix the workgraph path). Never invent a
result a script refused to produce.
