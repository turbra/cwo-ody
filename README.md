# cwo-ody - Complex Work Orchestration skill for Odysseus

An Odysseus-importable adaptation of
[complex-work-orchestration](https://github.com/gprocunier/complex-work-orchestration):
the CWO core loop (prompt coach -> routing -> Markdown workgraph -> evidence-based
closure -> sprint continuation) driven from Odysseus chat.

## Import

In the Odysseus web UI: Skills → Import from URL → paste
`https://github.com/turbra/cwo-ody`. The whole repo is the bundle
(budget-guarded by `tests/test_bundle_budget.py`).

## Verify after import

Confirm the imported skill shows version `1.1.4`. Switch to **AGENT mode**
(chat mode fabricates results) and enable bash. Ask:
`Use complex-work-orchestration: plan a migration of our two internal services to the new auth system.`
The agent locates the imported skill at `/app/data/skills/imported/cwo-ody/`,
bootstraps via `cwo_doctor.py`, coaches your goal, asks numbered questions,
and saves the workgraph as `~/.cwo/workgraph-<slug>.md`. In a fresh
conversation, ask "continue the sprint" - the agent resumes from the
workgraph. If the skill root is inaccessible, the agent must report the
failure output and stop instead of claiming `"ok": true`.

This skill does not require a `manage_skills` tool or a direct CWO function.
If Odysseus reports that no direct tool exists, tries `pipeline`, or reports
`manage_skills` is unavailable instead of running bash, delete/re-import and
confirm the imported version is `1.1.4`.

## State model

Workgraphs are Markdown files stored under `<workspace>/.cwo/` in the pod
(reduced durability vs. upstream's Beads backend - by design; the pod has
no `bd`).

## Development

`python3 -m unittest discover -s tests` — stdlib only, no third-party deps.
Upstream pin and vendored-file list: `references/upstream-pin.md`.
