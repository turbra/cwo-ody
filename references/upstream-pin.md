# Upstream pin

Vendored files in this skill are copied from
https://github.com/gprocunier/complex-work-orchestration
at commit `5416d71` (PR #3 head, 2026-07-06).

Update procedure (manual, no sync script by design): re-copy the files
listed below from a newer upstream commit, re-apply the adaptations
described in docs/superpowers/specs/2026-07-07-cwo-odysseus-skill-design.md,
update this pin, run the test suite.

## Vendored files

### cwo_core modules (10)

- scripts/cwo_core/__init__.py
- scripts/cwo_core/coach.py
- scripts/cwo_core/paths.py (adapted: repo-root check drops schemas/ requirement)
- scripts/cwo_core/policy.py
- scripts/cwo_core/routing.py
- scripts/cwo_core/routing_signals.py
- scripts/cwo_core/synthesis.py
- scripts/cwo_core/util.py
- scripts/cwo_core/waivers.py
- scripts/cwo_core/workgraph_markdown.py

### Orchestration scripts (5)

- scripts/coach_prompt.py
- scripts/continue_sprint.py (adapted: markdown-only; beads loader removed)
- scripts/route_work.py
- scripts/scaffold_workgraph.py (adapted: beads import/exec removed, markdown-workgraph default)
- scripts/summarize_resume_state.py (adapted: bd path removed; --markdown-workgraph required)

### Policy YAML files (10)

- policy/contracting-controls.yaml
- policy/execution-environments.yaml
- policy/executor-registry.yaml
- policy/expert-registry.yaml
- policy/peer-review-policy.yaml
- policy/provider-registry.yaml
- policy/routing-policy.yaml
- policy/share-boundaries.yaml
- policy/synthesis-policy.yaml
- policy/zero-trust-consensus-policy.yaml

### Tests (4, pruned: see docstring)

- tests/test_continue_sprint.py (pruned: see docstring)
- tests/test_prompt_coach.py
- tests/test_route_work.py
- tests/test_summarize_resume_state.py (no methods pruned; all markdown-workgraph tests retained)

### Tests (new, not vendored)

- tests/test_scaffold_markdown.py
