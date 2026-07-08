# CWO Odysseus Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the CWO core loop (coach → route → Markdown workgraph → resume/continue) as an Odysseus-importable skill in `github.com/turbra/cwo-ody`, with a chat-mediated Q&A protocol replacing CLI flags.

**Architecture:** The repo root *is* the import bundle. Milestone 0 builds a vertical slice (SKILL.md + `cwo_doctor.py` sentinel + budget test) and proves live import + execution on the deployed Odysseus before any CWO code is vendored. Milestone 1 vendors the dependency closure of five upstream entry points, adapted to Markdown-only state (no `bd`/Beads).

**Tech Stack:** Python 3 stdlib only. `unittest`. GitHub Actions CI. Upstream pin: `gprocunier/complex-work-orchestration` commit `5416d71` (PR #3 head; fetchable via `git fetch origin pull/3/head`).

## Global Constraints

- Stdlib-only runtime; no third-party deps anywhere (matches upstream rule and the Odysseus pod).
- Import budget (Odysseus `skill_importer.py` truncates SILENTLY): ≤ 55 tracked files (cap 64), ≤ 1,800,000 bytes total (cap 2 MB), ≤ 400,000 bytes per file, relative paths ≤ 4 segments (walker stops below directory depth 4), suffixes only from: `.md .txt .json .yaml .yml .py .sh .toml .js .ts .css .html .xml .csv`.
- No vendored module may import `cwo_core.beads` (test-enforced); `cwo_core/beads.py` is NOT vendored.
- Vendored files are copied from the pin commit and modified only as specified; record every vendored file in `references/upstream-pin.md`.
- SKILL.md frontmatter must parse with Odysseus's minimal YAML (scalars, inline `[a, b]` lists only): keys `name`, `description`, `version`, `category`, `tags`, `requires_toolsets`, `status`.
- All work happens in `/home/freemem/redhat/cwo-ody` on branch `main` (new repo; no PR flow requested — commit directly).
- Working checkout of upstream for copying: `git clone https://github.com/gprocunier/complex-work-orchestration.git /tmp/cwo-upstream && cd /tmp/cwo-upstream && git fetch origin pull/3/head && git checkout 5416d71` (do this once in Task 6; reuse after).

---

## Milestone 0 — vertical slice

### Task 1: Bundle manifest + budget test

**Files:**
- Create: `bundle-manifest.txt`
- Create: `tests/test_bundle_budget.py`

**Interfaces:**
- Produces: `bundle-manifest.txt` — one repo-relative path per line, sorted, `#` comments allowed. Every later task that adds/removes a tracked file MUST update it.
- Produces: `REPO_ROOT` discovery pattern used by all tests: `Path(__file__).resolve().parents[1]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle_budget.py
"""Import-budget guard.

Odysseus's skill importer SILENTLY truncates bundles: its GitHub walker
stops collecting at 64 files / 2 MB and does not recurse below directory
depth 4. "Under the limit" is therefore not enough — this test asserts the
EXACT tracked-file manifest so an accidental addition (or a file the
importer would drop) fails CI loudly.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "bundle-manifest.txt"

MAX_FILES = 55            # margin under the importer's 64
MAX_TOTAL_BYTES = 1_800_000   # margin under 2_000_000
MAX_FILE_BYTES = 400_000
MAX_PATH_SEGMENTS = 4     # importer stops below directory depth 4
ALLOWED_SUFFIXES = (
    ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".toml",
    ".js", ".ts", ".css", ".html", ".xml", ".csv",
)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, text=True,
        capture_output=True, check=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line.strip())


def manifest_files() -> list[str]:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    return sorted(l.strip() for l in lines if l.strip() and not l.startswith("#"))


class BundleBudgetTests(unittest.TestCase):
    def test_tracked_files_match_manifest_exactly(self) -> None:
        tracked = tracked_files()
        manifest = manifest_files()
        self.assertEqual(
            tracked, manifest,
            "git-tracked files diverge from bundle-manifest.txt; "
            "update the manifest deliberately when adding/removing files",
        )

    def test_file_count_within_margin(self) -> None:
        self.assertLessEqual(len(tracked_files()), MAX_FILES)

    def test_total_and_per_file_bytes(self) -> None:
        total = 0
        for rel in tracked_files():
            size = (REPO_ROOT / rel).stat().st_size
            self.assertLessEqual(size, MAX_FILE_BYTES, rel)
            total += size
        self.assertLessEqual(total, MAX_TOTAL_BYTES)

    def test_path_depth_and_suffixes(self) -> None:
        for rel in tracked_files():
            self.assertLessEqual(
                len(Path(rel).parts), MAX_PATH_SEGMENTS,
                f"{rel}: too deep; the importer would silently drop it",
            )
            name = Path(rel).name.lower()
            if name in {"license", "readme.md", "skill.md"}:
                continue
            self.assertTrue(
                name.endswith(ALLOWED_SUFFIXES),
                f"{rel}: suffix not importable by Odysseus",
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/freemem/redhat/cwo-ody && python3 -m unittest tests.test_bundle_budget -v`
Expected: FAIL — `FileNotFoundError` for `bundle-manifest.txt` (manifest doesn't exist yet).

- [ ] **Step 3: Write the manifest**

```
# bundle-manifest.txt — every git-tracked file, one per line, sorted.
# tests/test_bundle_budget.py asserts exact equality with `git ls-files`.
bundle-manifest.txt
docs/superpowers/plans/2026-07-07-cwo-odysseus-skill.md
docs/superpowers/specs/2026-07-07-cwo-odysseus-skill-design.md
tests/test_bundle_budget.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/freemem/redhat/cwo-ody && git add -A && python3 -m unittest tests.test_bundle_budget -v`
Expected: 4 tests, OK. (`git add` first — the test reads `git ls-files`.)

- [ ] **Step 5: Commit**

```bash
cd /home/freemem/redhat/cwo-ody && git add -A && git commit -m "feat: bundle manifest + import-budget guard test"
```

---

### Task 2: cwo_doctor.py self-check sentinel

**Files:**
- Create: `scripts/cwo_doctor.py`
- Create: `tests/test_cwo_doctor.py`
- Modify: `bundle-manifest.txt` (add the two new paths, keep sorted)

**Interfaces:**
- Produces: `scripts/cwo_doctor.py` — CLI: `python3 scripts/cwo_doctor.py --json [--root PATH]`. Prints one JSON object: `{"doctor_result_type": "cwo-odysseus-doctor", "ok": bool, "python_version": "3.x.y", "skill_root": "<abs path>", "missing_files": [..], "errors": [..]}`. Exit 0 iff `ok`. Default root = two directories above the script file.
- Produces: module constant `REQUIRED_FILES: list[str]` (repo-relative). Task 12 extends this list.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cwo_doctor.py
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPO_ROOT / "scripts" / "cwo_doctor.py"


class CwoDoctorTests(unittest.TestCase):
    def run_doctor(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(DOCTOR), "--json", *args],
            text=True, capture_output=True,
        )

    def test_ok_on_intact_repo(self) -> None:
        proc = self.run_doctor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["doctor_result_type"], "cwo-odysseus-doctor")
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_files"], [])
        self.assertEqual(Path(result["skill_root"]), REPO_ROOT)

    def test_fails_closed_on_broken_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_doctor("--root", tmp)
            self.assertEqual(proc.returncode, 1)
            result = json.loads(proc.stdout)
            self.assertFalse(result["ok"])
            self.assertIn("SKILL.md", result["missing_files"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cwo_doctor -v`
Expected: FAIL/ERROR — doctor script does not exist.

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
# scripts/cwo_doctor.py
"""Self-check sentinel for the CWO Odysseus skill.

The Odysseus agent's bootstrap locates this file to discover the installed
skill root, then runs it to prove the bundle is intact and executable
before any real CWO command. Fail-closed: exit 1 on any problem.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

DOCTOR_RESULT_TYPE = "cwo-odysseus-doctor"

# Extended by later milestones; keep sorted. SKILL.md is listed because a
# truncated import (Odysseus drops files silently at its caps) is the main
# failure this check exists to catch.
REQUIRED_FILES = [
    "SKILL.md",
    "bundle-manifest.txt",
    "scripts/cwo_doctor.py",
]


def check(root: Path) -> dict:
    errors: list[str] = []
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    if sys.version_info < (3, 9):
        errors.append(f"python >= 3.9 required, found {platform.python_version()}")
    return {
        "doctor_result_type": DOCTOR_RESULT_TYPE,
        "ok": not missing and not errors,
        "python_version": platform.python_version(),
        "skill_root": str(root),
        "missing_files": missing,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CWO Odysseus skill self-check.")
    parser.add_argument("--root", type=Path, help="Skill root override (default: two levels above this script).")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON (the only mode; flag kept for call-shape parity).")
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    result = check(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add `SKILL.md` placeholder requirement note**

`REQUIRED_FILES` lists `SKILL.md`, which Task 3 creates. Until then `test_ok_on_intact_repo` fails — that ordering is deliberate (it proves the doctor detects the missing file). Run now:

Run: `python3 -m unittest tests.test_cwo_doctor -v`
Expected: `test_fails_closed_on_broken_tree` PASS; `test_ok_on_intact_repo` FAIL with `missing_files` containing `SKILL.md`. Proceed — Task 3 turns it green.

- [ ] **Step 5: Update manifest and commit**

Add `scripts/cwo_doctor.py` and `tests/test_cwo_doctor.py` to `bundle-manifest.txt` (sorted). Then:

```bash
git add -A && python3 -m unittest tests.test_bundle_budget -v && git commit -m "feat: add cwo_doctor self-check sentinel (red until SKILL.md lands)"
```

---

### Task 3: SKILL.md (milestone-0 version), upstream pin, README

**Files:**
- Create: `SKILL.md`
- Create: `references/upstream-pin.md`
- Create: `README.md`
- Modify: `bundle-manifest.txt`

**Interfaces:**
- Produces: SKILL.md frontmatter contract (`name: complex-work-orchestration`) and the `CWO_SKILL_ROOT` bootstrap snippet that Task 5's live test exercises and Task 12 keeps verbatim.

- [ ] **Step 1: Write SKILL.md**

````markdown
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
````

- [ ] **Step 2: Write references/upstream-pin.md**

```markdown
# Upstream pin

Vendored files in this skill are copied from
https://github.com/gprocunier/complex-work-orchestration
at commit `5416d71` (PR #3 head, 2026-07-06).

Update procedure (manual, no sync script by design): re-copy the files
listed below from a newer upstream commit, re-apply the adaptations
described in docs/superpowers/specs/2026-07-07-cwo-odysseus-skill-design.md,
update this pin, run the test suite.

## Vendored files

(none yet — milestone 0 contains no upstream code)
```

- [ ] **Step 3: Write README.md**

```markdown
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
```

- [ ] **Step 4: Update manifest; run all tests**

Add `SKILL.md`, `README.md`, `references/upstream-pin.md` to `bundle-manifest.txt` (sorted). Run:

Run: `git add -A && python3 -m unittest discover -s tests -v`
Expected: all tests PASS (doctor's `test_ok_on_intact_repo` now green — SKILL.md exists).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: milestone-0 SKILL.md with bootstrap, upstream pin, README"
```

---

### Task 4: CI workflow + push

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `bundle-manifest.txt`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 -m compileall -q .
      - run: python3 -m unittest discover -s tests -v
```

- [ ] **Step 2: Update manifest, verify, commit, push**

Add `.github/workflows/ci.yml` to `bundle-manifest.txt`. Run: `git add -A && python3 -m unittest discover -s tests -v` — expected PASS. Then:

```bash
git commit -am "ci: compileall + unittest on ubuntu-latest"
git push -u origin main
```

- [ ] **Step 3: Confirm CI green**

Run: `gh run watch --repo turbra/cwo-ody $(gh run list --repo turbra/cwo-ody -L1 --json databaseId -q '.[0].databaseId')`
Expected: conclusion `success`.

---

### Task 5: LIVE CHECKPOINT — import + execute on deployed Odysseus (user-assisted)

**Files:** none (findings recorded in `references/upstream-pin.md` commit message or spec amendment if the bootstrap needs changing).

This is the milestone-0 gate from the spec: prove the chat agent can locate and execute the vendored scripts after a real web-UI import. It needs the user's Odysseus instance.

- [ ] **Step 1: Ask the user to import** `https://github.com/turbra/cwo-ody` via Skills → Import from URL, and confirm the skill appears in the index.
- [ ] **Step 2: Ask the user to prompt the agent** with: "Use the complex-work-orchestration skill: run its bootstrap and doctor check, and paste the JSON result."
- [ ] **Step 3: Evaluate.** PASS = doctor JSON with `"ok": true` and a real `skill_root` path. If the bootstrap failed to find the root: get the actual skill-storage path from the user (visible in the agent's find output or Odysseus config), extend the bootstrap's candidate-root list in SKILL.md, push, re-import, repeat.
- [ ] **Step 4: Record the outcome** — commit any bootstrap fix with message `fix: bootstrap candidate roots per live Odysseus layout (<path>)`. Do not proceed to Milestone 1 until this gate passes.

---

## Milestone 1 — vendored core loop

### Task 6: Vendor cwo_core + policy files

**Files:**
- Create: `scripts/cwo_core/__init__.py`, `scripts/cwo_core/coach.py`, `scripts/cwo_core/routing.py`, `scripts/cwo_core/routing_signals.py`, `scripts/cwo_core/policy.py`, `scripts/cwo_core/paths.py`, `scripts/cwo_core/util.py`, `scripts/cwo_core/waivers.py`, `scripts/cwo_core/synthesis.py`, `scripts/cwo_core/workgraph_markdown.py` (copied from pin)
- Create: `policy/contracting-controls.yaml`, `policy/execution-environments.yaml`, `policy/executor-registry.yaml`, `policy/expert-registry.yaml`, `policy/peer-review-policy.yaml`, `policy/provider-registry.yaml`, `policy/routing-policy.yaml`, `policy/share-boundaries.yaml`, `policy/synthesis-policy.yaml`, `policy/zero-trust-consensus-policy.yaml` (copied from pin)
- Create: `tests/test_no_beads_import.py`
- Modify: `scripts/cwo_core/paths.py` (one function), `bundle-manifest.txt`

**Interfaces:**
- Produces: importable `cwo_core` package rooted at `scripts/`; `cwo_core.routing.classify_work(...)`, `cwo_core.coach.coach_orchestration_prompt(...)`, `cwo_core.workgraph_markdown` constants — all unchanged upstream signatures.
- Consumes: upstream clone at pin (Global Constraints).

- [ ] **Step 1: Write the failing guard test**

```python
# tests/test_no_beads_import.py
"""The Odysseus pod has no `bd`; Beads must be unreachable.

Two guards: (1) cwo_core/beads.py is not vendored at all; (2) no vendored
Python file imports cwo_core.beads.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
IMPORT_RE = re.compile(r"^\s*(from|import)\s+(cwo_core\.)?beads\b", re.M)


class NoBeadsTests(unittest.TestCase):
    def test_beads_module_not_vendored(self) -> None:
        self.assertFalse((SCRIPTS / "cwo_core" / "beads.py").exists())

    def test_no_module_imports_beads(self) -> None:
        offenders = [
            str(p.relative_to(REPO_ROOT))
            for p in SCRIPTS.rglob("*.py")
            if IMPORT_RE.search(p.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_cwo_core_package_imports(self) -> None:
        import sys
        sys.path.insert(0, str(SCRIPTS))
        try:
            import cwo_core.coach    # noqa: F401
            import cwo_core.routing  # noqa: F401
            import cwo_core.workgraph_markdown  # noqa: F401
        finally:
            sys.path.remove(str(SCRIPTS))


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest tests.test_no_beads_import -v` — expected FAIL (`cwo_core` doesn't exist).

- [ ] **Step 2: Copy the files from the pin**

```bash
test -d /tmp/cwo-upstream || git clone https://github.com/gprocunier/complex-work-orchestration.git /tmp/cwo-upstream
git -C /tmp/cwo-upstream fetch origin pull/3/head && git -C /tmp/cwo-upstream checkout 5416d71
cd /home/freemem/redhat/cwo-ody
mkdir -p scripts/cwo_core policy
for m in __init__ coach routing routing_signals policy paths util waivers synthesis workgraph_markdown; do
  cp /tmp/cwo-upstream/scripts/cwo_core/$m.py scripts/cwo_core/$m.py
done
for p in contracting-controls execution-environments executor-registry expert-registry peer-review-policy provider-registry routing-policy share-boundaries synthesis-policy zero-trust-consensus-policy; do
  cp /tmp/cwo-upstream/policy/$p.yaml policy/$p.yaml
done
```

- [ ] **Step 3: Adapt paths.py**

Upstream `_find_repo_root` requires a `schemas/` dir, which this bundle doesn't ship. Edit `scripts/cwo_core/paths.py`:

```python
# old
def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "policy").is_dir() and (candidate / "scripts").is_dir() and (candidate / "schemas").is_dir():
            return candidate
    raise RuntimeError(f"could not resolve repository root from {start}")

# new
def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "policy").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError(f"could not resolve repository root from {start}")
```

- [ ] **Step 4: Verify**

Run: `python3 -m compileall -q scripts && python3 -m unittest tests.test_no_beads_import -v`
Expected: compile clean; 3 tests PASS.

- [ ] **Step 5: Update manifest, record vendored files, commit**

Add all 20 new files + the test to `bundle-manifest.txt`. In `references/upstream-pin.md`, replace `(none yet — milestone 0 contains no upstream code)` with the 20 vendored paths (one bullet each; mark `paths.py` as "adapted: repo-root check drops schemas/ requirement"). Run full suite (`python3 -m unittest discover -s tests -v`, expected PASS), then:

```bash
git add -A && git commit -m "feat: vendor cwo_core closure + policy set from upstream 5416d71"
```

---

### Task 7: Vendor coach_prompt.py + route_work.py with their tests

**Files:**
- Create: `scripts/coach_prompt.py`, `scripts/route_work.py` (verbatim from pin — neither imports beads)
- Create: `tests/test_prompt_coach.py`, `tests/test_route_work.py` (from pin, pruned)
- Modify: `bundle-manifest.txt`, `references/upstream-pin.md`

**Interfaces:**
- Produces: `python3 scripts/coach_prompt.py --json "<text>"` → JSON with keys `interactive_questions`, `enabled_levers`, `disabled_levers`, `route`, `recommended_orchestration_level`, `beads_context_depth`, `workerbee_parallelism`, `warnings` (upstream contract, unchanged). `python3 scripts/route_work.py --json "<text>"` → route JSON.
- Flags relied on by later tasks: `--data-sensitivity {public,redacted,internal,restricted}`, `--beads-context-depth {none,summary,focused,heavy,audit}`, `--model-synthesis`, `--scaffold-size {full,tight}`, `--brief`.

- [ ] **Step 1: Copy scripts and tests**

```bash
cd /home/freemem/redhat/cwo-ody
cp /tmp/cwo-upstream/scripts/coach_prompt.py scripts/
cp /tmp/cwo-upstream/scripts/route_work.py scripts/
cp /tmp/cwo-upstream/tests/test_prompt_coach.py tests/
cp /tmp/cwo-upstream/tests/test_route_work.py tests/
```

- [ ] **Step 2: Run the vendored tests; prune out-of-scope cases**

Run: `python3 -m unittest tests.test_prompt_coach tests.test_route_work -v 2>&1 | tail -20`

Upstream test files may reference repo features this bundle doesn't vendor (validator scans, retired-alias guards, sample shell scripts under `examples/`). For each failing/erroring test method, apply exactly one of:
- the test only touches vendored behavior → fix its path assumptions (`ROOT / "scripts"` layout is identical, so most pass unchanged);
- the test exercises non-vendored surface (imports a module outside the vendored set, shells to a non-vendored script, or asserts on files like `SKILL.md` sections of upstream) → DELETE the whole test method and note it in the file's docstring: `Pruned from upstream: <method names> (exercise non-vendored surface).`

Do not weaken assertions of surviving tests. Re-run until green.

- [ ] **Step 3: Verify contract manually**

Run: `python3 scripts/coach_prompt.py --json "Refactor deployment scripts and update the docs." | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(d)[:6]); print([q['id'] for q in d['interactive_questions']])"`
Expected: key list starting `['beads_context_depth', ...]` and question ids including `workerbee_parallelism`.

- [ ] **Step 4: Manifest + pin doc + full suite**

Add the 4 files to `bundle-manifest.txt` and to the vendored list in `references/upstream-pin.md` (tests marked "pruned: see docstring"). Run: `git add -A && python3 -m unittest discover -s tests -v` — expected PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: vendor coach_prompt + route_work with pruned upstream tests"
```

---

### Task 8: Vendor + adapt scaffold_workgraph.py (Markdown-only)

**Files:**
- Create: `scripts/scaffold_workgraph.py` (from pin, adapted)
- Create: `tests/test_scaffold_markdown.py` (new, focused)
- Modify: `bundle-manifest.txt`, `references/upstream-pin.md`

**Interfaces:**
- Produces: `python3 scripts/scaffold_workgraph.py --title T --description D --dry-run --format markdown-workgraph` → Markdown workgraph on stdout (agent redirects to a file). `--format` choices become `["cwo", "markdown-workgraph"]`, default `markdown-workgraph`. Non-`--dry-run` invocation exits 2 with a clear error (no Beads in this skill).
- Consumes: `cwo_core.routing.classify_work`, `cwo_core.workgraph_markdown` (Task 6); flags mirror coach (Task 7).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold_markdown.py
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = REPO_ROOT / "scripts" / "scaffold_workgraph.py"


def run_scaffold(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), *args], text=True, capture_output=True,
    )


class ScaffoldMarkdownTests(unittest.TestCase):
    def test_dry_run_defaults_to_markdown_workgraph(self) -> None:
        proc = run_scaffold("--title", "Fallback Smoke", "--description", "x", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Reduced durability fallback", proc.stdout)
        self.assertIn("## Work Items", proc.stdout)

    def test_non_dry_run_refuses_without_beads(self) -> None:
        proc = run_scaffold("--title", "Live", "--description", "x")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--dry-run", proc.stderr)

    def test_beads_graph_format_removed(self) -> None:
        proc = run_scaffold("--title", "T", "--dry-run", "--format", "beads-graph")
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest tests.test_scaffold_markdown -v` — expected ERROR (script missing).

- [ ] **Step 2: Copy and adapt**

`cp /tmp/cwo-upstream/scripts/scaffold_workgraph.py scripts/`, then three edits:

Edit 1 — delete the beads import block (top of file):
```python
# delete these lines entirely
from cwo_core.beads import (
    add_dependency,
    create_bead,
)
```

Edit 2 — in `main()`, change the `--format` argument:
```python
# old
    parser.add_argument(
        "--format",
        choices=["cwo", "beads-graph", "markdown-workgraph"],
        default="cwo",
        help=(
            "Dry-run output format. 'cwo' is the internal scaffold; "
            "'beads-graph' can be used with bd create --graph; "
            "'markdown-workgraph' is a reduced-durability fallback."
        ),
    )
# new
    parser.add_argument(
        "--format",
        choices=["cwo", "markdown-workgraph"],
        default="markdown-workgraph",
        help=(
            "Dry-run output format. 'markdown-workgraph' is the Odysseus "
            "state file; 'cwo' is the internal scaffold JSON."
        ),
    )
```

Edit 3 — replace everything in `main()` after the `--dry-run` output block (from `if args.format != "cwo":` through the end of the `try/except` that calls `create_bead`/`try_dep`) with:

```python
    parser.error(
        "this Odysseus skill has no Beads backend; use --dry-run "
        "--format markdown-workgraph and save stdout to a workgraph file"
    )
```

Then delete the now-unused helpers `beads_graph_plan`, `try_dep`, and `recovery_summary` (and any other function `python3 -m compileall` + a `grep -n "<name>(" scripts/scaffold_workgraph.py` shows has no remaining caller). Keep `markdown_workgraph_plan` and `planned_graph` intact.

- [ ] **Step 3: Verify**

Run: `python3 -m compileall -q scripts && python3 -m unittest tests.test_scaffold_markdown tests.test_no_beads_import -v`
Expected: PASS (6 tests).

- [ ] **Step 4: Manifest + pin doc + full suite**

Add both files to `bundle-manifest.txt`; add `scripts/scaffold_workgraph.py` to `references/upstream-pin.md` marked "adapted: beads import/exec removed, markdown-workgraph default". Run full suite — PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: vendor scaffold_workgraph adapted to markdown-only state"
```

---

### Task 9: Vendor + adapt summarize_resume_state.py

**Files:**
- Create: `scripts/summarize_resume_state.py` (from pin, adapted)
- Create: `tests/test_summarize_resume_state.py` (from pin, pruned to markdown tests)
- Modify: `bundle-manifest.txt`, `references/upstream-pin.md`

**Interfaces:**
- Produces: `python3 scripts/summarize_resume_state.py --markdown-workgraph <path>` (the flag becomes REQUIRED); exports `coerce_items`, `parse_markdown_workgraph`, `markdown_values` unchanged (Task 10 imports them).

- [ ] **Step 1: Copy files**

```bash
cp /tmp/cwo-upstream/scripts/summarize_resume_state.py scripts/
cp /tmp/cwo-upstream/tests/test_summarize_resume_state.py tests/
```

- [ ] **Step 2: Adapt the script**

Edit 1 — delete `from cwo_core.beads import run_bd` and the `bd_json` helper (`def bd_json(...)` near the top) plus every function that calls `bd_json`/`run_bd` (the bd summary path in `main()`); `parse_markdown_workgraph`, `coerce_items`, `markdown_values`, `summarize`, and `summarize_markdown_workgraph` stay.

Edit 2 — in `main()`, make markdown the only mode:
```python
# old (shape at pin: bd-based summary with markdown fallback when beads unavailable)
#   parser.add_argument("--markdown-workgraph", ...)
#   ... beads_unavailable detection ...
#   if beads_unavailable and args.markdown_workgraph:
#       summarize_markdown_workgraph(args.markdown_workgraph, args.open_limit)
# new main() body after argparse setup:
    parser.add_argument(
        "--markdown-workgraph",
        type=Path,
        required=True,
        help="Path to the Markdown workgraph state file (the only backend in this skill).",
    )
    args = parser.parse_args()
    summarize_markdown_workgraph(args.markdown_workgraph, args.open_limit)
```
(Keep `--ready-limit`/`--open-limit` arguments; delete bd-only arguments if any remain.)

- [ ] **Step 3: Prune the vendored test file**

Same rule as Task 7 Step 2: keep the markdown-workgraph tests; DELETE test methods that shell `bd`, monkeypatch `run_bd`, or assert on the bd summary path; record pruned names in the docstring. If a kept test invoked the CLI without `--markdown-workgraph`, update it to pass a temp workgraph file (reuse the inline workgraph text from upstream's markdown tests).

Run: `python3 -m unittest tests.test_summarize_resume_state tests.test_no_beads_import -v`
Expected: PASS.

- [ ] **Step 4: Manifest + pin doc + full suite** (same procedure as Task 8 Step 4; adaptation note: "bd path removed; --markdown-workgraph required").

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: vendor summarize_resume_state as markdown-only resume"
```

---

### Task 10: Vendor + adapt continue_sprint.py

**Files:**
- Create: `scripts/continue_sprint.py` (from pin, adapted)
- Create: `tests/test_continue_sprint.py` (from pin, pruned)
- Modify: `bundle-manifest.txt`, `references/upstream-pin.md`

**Interfaces:**
- Produces: `python3 scripts/continue_sprint.py --epic <key> --markdown-workgraph <path> [--format json]` → sprint-continuation brief (upstream JSON contract: `recommended_next_issue`, `ready_issues`, `blocked_issues`, `why_next`, `warnings`, `resume_commands`).
- Consumes: `parse_markdown_workgraph`, `coerce_items` from Task 9's module.

- [ ] **Step 1: Copy files**

```bash
cp /tmp/cwo-upstream/scripts/continue_sprint.py scripts/
cp /tmp/cwo-upstream/tests/test_continue_sprint.py tests/
```

- [ ] **Step 2: Adapt the script**

Edit 1 — delete `from cwo_core.beads import run_bd`, the `bd_json` helper, and `load_beads_items` (whole function).

Edit 2 — in `main()`, make `--markdown-workgraph` required and drop the beads branch:
```python
# old
    parser.add_argument(
        "--markdown-workgraph",
        type=Path,
        help="Use a reduced-durability Markdown workgraph fallback instead of Beads state.",
    )
    ...
    if args.markdown_workgraph:
        raw_items = load_markdown_items(args.markdown_workgraph, args.epic)
        source = "markdown-workgraph"
    else:
        raw_items = load_beads_items(args.epic)
        source = "beads"
# new
    parser.add_argument(
        "--markdown-workgraph",
        type=Path,
        required=True,
        help="Path to the Markdown workgraph state file (the only backend in this skill).",
    )
    ...
    raw_items = load_markdown_items(args.markdown_workgraph, args.epic)
    source = "markdown-workgraph"
```

Edit 3 — in `build_continuation_brief`, the beads-mode `resume_commands` list references `bd ready ...`; replace the whole `resume_commands` construction with only the markdown variant:
```python
    resume_commands = [
        "keep the workgraph file updated as items close",
        f"python3 scripts/continue_sprint.py --epic {epic_id} --markdown-workgraph <path>",
    ]
```
(Delete the `if source == "markdown-workgraph": resume_commands = [...]` override — it's now the only case.)

- [ ] **Step 3: Prune the vendored test file**

Keep: ranking tests, blocker/guard-label tests, markdown CLI test, epic-exclusion and lane-blocking tests (all pure-dict or markdown-based). DELETE: `test_cwo_continue_reads_real_bd_dependency_objects` (live bd), `test_cwo_entrypoint_runs_continue_text_mode` (shells `scripts/cwo.py`, not vendored), and any test asserting `bd ready` inside `resume_commands` (update instead if it's otherwise markdown-scoped). Docstring-record prunes.

Run: `python3 -m unittest tests.test_continue_sprint tests.test_no_beads_import -v`
Expected: PASS.

- [ ] **Step 4: Manifest + pin doc + full suite** (procedure as before; note "markdown-only; beads loader removed").

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: vendor continue_sprint as markdown-only continuation advisor"
```

---

### Task 11: Chat protocol references + workgraph template

**Files:**
- Create: `references/chat-protocol.md`
- Create: `references/workgraph-lifecycle.md`
- Create: `templates/markdown-workgraph.md`
- Modify: `bundle-manifest.txt`

**Interfaces:**
- Produces: the deterministic answer-to-flag table (spec requirement). Task 12's SKILL.md Procedure points at these by filename via `manage_skills view_ref`.

- [ ] **Step 1: Write references/chat-protocol.md**

````markdown
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
     `route.route`, `route.risk`, `route.data_sensitivity`)
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
| `workerbee_parallelism` | "Parallelize with subagents?" | `review-subagents` | "review"/"default" → record `review-subagents`; "heavy" → `heavy-review-subagents`; "no"/"none"/"main thread" → `no-subagents`. No CLI flag — record the value in the final packet message; it directs how YOU execute (whether you fan out work). |
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
````

- [ ] **Step 2: Write references/workgraph-lifecycle.md**

````markdown
# Workgraph lifecycle

State backend: ONE Markdown file per epic, stored at
`<workspace>/.cwo/workgraph-<slug>.md` where `<workspace>` is the path
returned by the get_workspace tool and `<slug>` is kebab-case from the
epic title. Reduced durability vs. upstream Beads — treat the file as the
single source of truth and update it in place.

## Create

```bash
mkdir -p "<workspace>/.cwo"
python3 "$CWO_SKILL_ROOT/scripts/scaffold_workgraph.py" \
  --title "<Epic title>" --description "<one-line>" \
  --dry-run --format markdown-workgraph <mapped flags> \
  > "<workspace>/.cwo/workgraph-<slug>.md"
```

Then show the user the final packet: epic title, chosen levers, item list,
and the ABSOLUTE workgraph path (required — a fresh conversation resumes
from that path).

## Execute

Work items in dependency order. After finishing an item, edit its
`- Status:` field in the file (`open` → `closed`) and append an evidence
line under the item: commands run, artifacts changed, residual risk.
Item format is defined by scripts/cwo_core/workgraph_markdown.py (Type,
Lane, Labels, Depends on lanes fields).

## Resume / continue

```bash
python3 "$CWO_SKILL_ROOT/scripts/summarize_resume_state.py" \
  --markdown-workgraph "<workspace>/.cwo/workgraph-<slug>.md"
python3 "$CWO_SKILL_ROOT/scripts/continue_sprint.py" \
  --epic <epic-key> --markdown-workgraph "<workspace>/.cwo/workgraph-<slug>.md" --format json
```

Relay `recommended_next_issue` + `why_next` + blocked list in chat. If the
user names no workgraph, `ls "<workspace>/.cwo/"` and ask which one.
````

- [ ] **Step 3: Write templates/markdown-workgraph.md**

Generate it from the real scaffolder so the template can never drift from the code:

```bash
python3 scripts/scaffold_workgraph.py --title "Example Epic" \
  --description "Template produced by scaffold_workgraph.py at the upstream pin." \
  --dry-run --format markdown-workgraph > templates/markdown-workgraph.md
```

- [ ] **Step 4: Manifest + full suite + commit**

Add the 3 files to `bundle-manifest.txt`. Run: `git add -A && python3 -m unittest discover -s tests -v` — PASS. Then:

```bash
git commit -am "feat: chat protocol with answer-to-flag table, lifecycle reference, template"
```

---

### Task 12: Final SKILL.md Procedure + doctor extension + version bump

**Files:**
- Modify: `SKILL.md` (replace Procedure step 2 placeholder; bump `version: 1.0.0`)
- Modify: `scripts/cwo_doctor.py` (`REQUIRED_FILES`)
- Modify: `tests/test_cwo_doctor.py` (one new assertion)
- Modify: `README.md` (usage section), `bundle-manifest.txt` (no new files — verify only)

**Interfaces:**
- Consumes: everything above. Produces the final operator-facing surface.

- [ ] **Step 1: Extend the doctor (test first)**

Add to `tests/test_cwo_doctor.py` inside `CwoDoctorTests`:

```python
    def test_required_files_cover_core_loop(self) -> None:
        from pathlib import Path
        import importlib.util
        spec = importlib.util.spec_from_file_location("cwo_doctor", DOCTOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        required = set(mod.REQUIRED_FILES)
        for rel in [
            "scripts/coach_prompt.py",
            "scripts/route_work.py",
            "scripts/scaffold_workgraph.py",
            "scripts/summarize_resume_state.py",
            "scripts/continue_sprint.py",
            "scripts/cwo_core/routing.py",
            "policy/routing-policy.yaml",
            "references/chat-protocol.md",
            "references/workgraph-lifecycle.md",
        ]:
            self.assertIn(rel, required)
```

Run: `python3 -m unittest tests.test_cwo_doctor -v` — expected FAIL. Then extend `REQUIRED_FILES` in `scripts/cwo_doctor.py` with those nine paths (keep sorted). Re-run — PASS.

- [ ] **Step 2: Replace SKILL.md Procedure step 2**

Replace the placeholder line `2. Later milestones add the coach/route/workgraph procedure here.` with:

```markdown
2. **Coach the request.** Run
   `python3 "$CWO_SKILL_ROOT/scripts/coach_prompt.py" --json "<user goal>"`,
   then follow the reference `chat-protocol.md` (manage_skills view_ref
   path=references/chat-protocol.md): post ONE message with the
   recommendation summary and the numbered open questions, defaults marked.

3. **Map answers deterministically** using the answer-to-flag table in
   chat-protocol.md. Unknown answers → default + tell the user. Re-run the
   coach with mapped flags and show the final packet for confirmation.

4. **Scaffold and persist.** Follow `workgraph-lifecycle.md`: scaffold with
   `--dry-run --format markdown-workgraph`, save to
   `<workspace>/.cwo/workgraph-<slug>.md` (get the workspace path from the
   get_workspace tool), and always tell the user the absolute path.

5. **Execute with evidence.** Work items in dependency order; update each
   item's Status field and append evidence lines as you close it.

6. **Resume / continue.** On "continue the sprint": run summarize_resume_state
   and continue_sprint against the workgraph file (commands in
   workgraph-lifecycle.md) and relay the recommended-next brief.

7. **Failures.** Relay script stderr verbatim; never fabricate results.
   If effective data sensitivity is restricted, keep content away from
   external model APIs and say why.
```

Bump frontmatter `version: 0.1.0` → `version: 1.0.0`.

- [ ] **Step 3: Update README usage**

Replace the "Verify after import" section body with a short worked example: import → "plan a two-service refactor" → agent asks the numbered coach questions → workgraph saved under `<workspace>/.cwo/` → "continue the sprint" in a new conversation resumes it. Keep it under 25 lines.

- [ ] **Step 4: Full verification**

Run: `git add -A && python3 -m compileall -q . && python3 -m unittest discover -s tests -v`
Expected: all PASS, budget test green (manifest unchanged this task — confirm).

- [ ] **Step 5: Commit + push**

```bash
git commit -am "feat: v1 SKILL.md procedure, doctor covers core loop, README usage"
git push && gh run watch --repo turbra/cwo-ody $(gh run list --repo turbra/cwo-ody -L1 --json databaseId -q '.[0].databaseId')
```
Expected: CI success.

---

### Task 13: LIVE CHECKPOINT — end-to-end acceptance on deployed Odysseus (user-assisted)

Maps 1:1 to the spec's acceptance criteria. Needs the user's instance.

- [ ] **Step 1: Re-import** `https://github.com/turbra/cwo-ody` in the web UI (delete the milestone-0 skill first if Odysseus doesn't overwrite). Confirm the skill index shows it. *(criterion 1)*
- [ ] **Step 2: Coach flow.** User prompts: "Use complex-work-orchestration: plan a migration of our two internal services to the new auth system." PASS = agent runs bootstrap+doctor, then coach, and posts one message with summary + numbered questions + marked defaults. *(criterion 2)*
- [ ] **Step 3: Packet + workgraph.** User answers (e.g. "defaults, tight graph"). PASS = agent shows final packet including the absolute workgraph path, and `<workspace>/.cwo/workgraph-*.md` exists in the pod. *(criterion 3)*
- [ ] **Step 4: Fresh-conversation resume.** New conversation: "continue the sprint from <path>". PASS = agent relays a correct next-issue brief (recommended item + blocker reasons). *(criterion 4)*
- [ ] **Step 5: Record.** Criteria 5–6 are CI + this checkpoint. Fix any failure at the responsible task (bootstrap → SKILL.md, mapping → chat-protocol.md, state → lifecycle doc), re-push, re-test. When all four live steps pass, tag: `git tag v1.0.0 && git push --tags`.

---

## Self-review notes

- Spec coverage: bootstrap (T2/T3/T5), silent-truncation manifest test (T1), tight SKILL.md + references (T3/T11/T12), deterministic mapping table (T11), workspace convention (T11), `requires_toolsets: [bash]` (T3), vertical slice first (T1–T5 gate), live smoke criteria (T5/T13), no-beads guarantee (T6 test + T8–T10 adaptations), sensitivity floor conduct (T11).
- Types/names cross-checked: `CWO_SKILL_ROOT`, `REQUIRED_FILES`, `parse_markdown_workgraph`, flag names match the pin's actual argparse definitions (verified against 5416d71 during planning).
- Known judgment calls for executors: upstream test pruning (T7/T9/T10) follows one explicit rule — delete tests exercising non-vendored surface, never weaken surviving assertions.

---

## Milestone 2 — v1.2.0 local-model relay (added after live-gate findings)

Design basis (approved in-session): Odysseus wraps skill text as untrusted
context, so multi-step protocol adherence cannot be demanded of local models.
Fix at the right altitude: one relay driver script executes the protocol;
the model runs one command per turn and pastes output.

### Task 14: Revert overfit, keep legit fixes
Revert from the 1.1.1–1.1.7 series: acceptance-prompt-stuffed description,
tag spam, INDEX_TRIGGER_CONTRACT_TERMS/relevance-threshold test additions in
tests/test_bundle_budget.py, README "imported/cwo-ody" path error (correct:
imported/complex-work-orchestration). Keep: manage_skills removal,
$CWO_SKILL_ROOT-relative reference reads, forbidden-substitute naming
(update_plan/pipeline/chat_with_model), CWO_BLOCKED_NO_SHELL blocker,
em-dash→ascii README edits. Restore description to the 1.0.0 one-liner and
tags to [orchestration, planning, workgraph, governance].

### Task 15: scripts/cwo_chat.py relay driver (TDD)
Subcommands start/answer/continue; POST/NEXT-COMMAND delimited output;
deterministic answer→flag mapping table in code; session state + workgraph
under <workspace>/.cwo/ (workspace = --workspace or $PWD); wraps existing
coach/route/scaffold/summarize/continue scripts as libraries or subprocesses;
stdlib only; tests/test_cwo_chat.py covers a full scripted 3-turn session.

### Task 16: Relay SKILL.md + docs + version 1.2.0
SKILL.md Procedure collapses to relay form (~15 lines, bootstrap folded into
cwo_chat start); doctor REQUIRED_FILES += scripts/cwo_chat.py; SKILL_VERSION
and frontmatter → 1.2.0 (lockstep test exists); README weak-model section;
manifest update; push; CI green. Live acceptance retest follows as Task 13
(retry) with qwen3-30b.

---

## Milestone 3 — v1.3.0 MCP adapter (approved after #2959/#4008 analysis)

Rationale: Odysseus delivers skill text as untrusted context (#2959), so local
models ignore it; MCP tool schemas enter the trusted function list. Expose the
relay verbs as MCP tools. The `mcp` SDK exists in the Odysseus pod (bundled
servers use it) but NOT in dev/CI — the server module must import it lazily so
the test suite stays dependency-free.

### Task 17: Refactor cwo_chat.py into importable functions
run_start(goal, workspace) -> str, run_answer(reply, session_path|None,
workspace) -> str, run_continue(workgraph_path|None, workspace) -> str; CLI
subcommands become thin printers of these. Add newest-file default discovery
(session-*.json / workgraph-*.md under <workspace>/.cwo) used when the path
arg is None. All existing tests stay green; add unit tests for the discovery
defaults and for direct function calls (no subprocess).

### Task 18: scripts/cwo_mcp_server.py + docs + v1.3.0
TOOLS schema (plain dicts: cwo_start/cwo_answer/cwo_continue) + HANDLERS
mapping importable without the mcp package; guarded `import mcp` with a clean
main()-time error when absent; stdio server wiring mirrors Odysseus's bundled
mcp_servers/*.py pattern; CWO_WORKSPACE env default. Tool-result text says
"call cwo_answer with the user's reply" instead of NEXT COMMAND. Tests:
handler round-trips without mcp; skipIf-guarded SDK smoke when mcp present.
references/mcp-setup.md (registration walkthrough) + README section; doctor
REQUIRED_FILES += cwo_mcp_server.py; version 1.3.0 lockstep; manifest; push;
CI. Live registration + unprompted acceptance retest remains user-side.
