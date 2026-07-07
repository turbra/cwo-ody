# cwo-ody — Complex Work Orchestration skill for Odysseus

An Odysseus-importable adaptation of
[complex-work-orchestration](https://github.com/gprocunier/complex-work-orchestration):
the CWO core loop (prompt coach → routing → Markdown workgraph → evidence-based
closure → sprint continuation) driven from Odysseus chat.

## Import

In the Odysseus web UI: Skills → Import from URL → paste
`https://github.com/turbra/cwo-ody`. The whole repo is the bundle
(budget-guarded by `tests/test_bundle_budget.py`).

## Verify after import

Switch to **AGENT mode** (chat mode fabricates results) and enable bash.
Ask: "plan a two-service refactor". The agent runs `python3 $CWO_SKILL_ROOT/scripts/cwo_chat.py start 'plan a two-service refactor' --workspace "$PWD"`, then pastes the message block to you and prints the next command. When you reply, the agent runs that command with your reply substituted, relays the blocks, and repeats until done. In a fresh conversation, ask "continue the sprint" — the agent finds the workgraph and resumes the same way.

## Local models

Odysseus treats skill text as untrusted context, so multi-step protocol adherence varies by model; v1.2.0 moves the protocol into `scripts/cwo_chat.py` so the agent only ever runs one command and pastes output. If an agent still freehand-plans, prompt it explicitly: "Run $CWO_SKILL_ROOT/scripts/cwo_chat.py start '<goal>' with your bash tool and paste the output."

## State model

Workgraphs are Markdown files stored under `<workspace>/.cwo/` in the pod
(reduced durability vs. upstream's Beads backend — by design; the pod has
no `bd`).

## Development

`python3 -m unittest discover -s tests` — stdlib only, no third-party deps.
Upstream pin and vendored-file list: `references/upstream-pin.md`.
