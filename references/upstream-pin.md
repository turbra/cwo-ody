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
