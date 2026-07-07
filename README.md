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
Ask: "plan a two-service refactor". The agent locates the imported skill
at `/app/data/skills/imported/complex-work-orchestration/`, bootstraps via `cwo_doctor.py`,
coaches your goal, asks numbered questions, and saves the workgraph as
`~/.cwo/workgraph-<slug>.md`. In a fresh conversation, ask "continue the
sprint" — the agent resumes from the workgraph. Return the doctor JSON with
`"ok": true` if the skill root is inaccessible.

## State model

Workgraphs are Markdown files stored under `<workspace>/.cwo/` in the pod
(reduced durability vs. upstream's Beads backend — by design; the pod has
no `bd`).

## Development

`python3 -m unittest discover -s tests` — stdlib only, no third-party deps.
Upstream pin and vendored-file list: `references/upstream-pin.md`.
