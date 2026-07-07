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

Ask the Odysseus agent to "run the CWO doctor check". It should locate the
skill root and print a JSON result with `"ok": true`.

## State model

Workgraphs are Markdown files stored under `<workspace>/.cwo/` in the pod
(reduced durability vs. upstream's Beads backend — by design; the pod has
no `bd`).

## Development

`python3 -m unittest discover -s tests` — stdlib only, no third-party deps.
Upstream pin and vendored-file list: `references/upstream-pin.md`.
