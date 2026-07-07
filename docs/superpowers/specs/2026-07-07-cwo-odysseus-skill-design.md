# CWO Skill for Odysseus — Design

**Date:** 2026-07-07
**Repo:** https://github.com/turbra/cwo-ody
**Upstream:** https://github.com/gprocunier/complex-work-orchestration (CWO)
**Target:** https://github.com/pewdiepie-archdaemon/odysseus deployed on OpenShift (no Odysseus code changes)

## Goal

Adapt the CLI-oriented Complex Work Orchestration (CWO) skill into a first-class
Odysseus skill: importable through the Odysseus web front end's skill importer,
and usable from the chat interface. The main gap being closed is that CWO's
operator prompt options (coach levers, gate opt-ins, routing declarations) are
CLI flags today and are not surfaced in Odysseus chat.

## Decisions (settled during brainstorming)

1. **Execution model:** the skill runs real vendored CWO scripts via the
   Odysseus agent's `python`/`bash` subprocess tools. Gates stay real, not
   imitated in prose.
2. **Import path:** develop directly in `github.com/turbra/cwo-ody`; Odysseus's
   `import-from-url` is GitHub-only and imports this repo directly. The
   self-hosted GitLab repo is retired for this purpose.
3. **Scope (v1):** core loop only — prompt coach → routing → Markdown workgraph
   scaffold → execution guidance → evidence-based closure → sprint
   continuation/resume.
4. **Chat UX:** agent-mediated Q&A. The agent runs the coach, surfaces open
   questions in one numbered chat message with defaults marked, maps plain-
   language answers back to flags, and shows the final orchestration packet
   before starting work.
5. **Upstream tracking:** vendored copies with a recorded source commit
   (`references/upstream-pin.md`). No sync script in v1; updates are manual,
   reviewed diffs.

## Constraints discovered in Odysseus

- Skill format: directory of `SKILL.md` (YAML frontmatter: `name`,
  `description`, `version`, `category`, `tags`, `requires_toolsets`, `status`,
  …) plus optional reference sub-files, stored at
  `data/skills/<category>/<name>/`. Parsed by
  `services/memory/skill_format.py`.
- Progressive disclosure: the chat agent sees an "Available skills" index; it
  reads `SKILL.md` via the `manage_skills` tool (`view`) and sub-files via
  `view_ref`.
- Importer limits (`services/memory/skill_importer.py`): GitHub hosts only;
  ≤ 64 files, ≤ 2 MB total, ≤ 400 KB per file; allowed suffixes include
  `.md .py .sh .yaml .yml .json .toml`.
- The agent has streaming `bash` and `python` subprocess tools, so bundled
  scripts are executable in the pod.
- `requires_toolsets` frontmatter hides the skill when a required toolset is
  inactive.

## Architecture

`cwo-ody` **is** the importable bundle:

```
cwo-ody/
├── SKILL.md                  # Odysseus frontmatter + agent operating guide (router)
├── README.md                 # humans: purpose, import instructions, upstream note
├── scripts/
│   ├── coach_prompt.py       # vendored from CWO, adapted
│   ├── route_work.py
│   ├── scaffold_workgraph.py
│   ├── summarize_resume_state.py
│   ├── continue_sprint.py
│   └── cwo_core/             # only the modules the five entry points import
├── policy/
│   └── routing-policy.yaml
├── references/
│   ├── chat-protocol.md      # the agent-mediated Q&A protocol in detail
│   ├── workgraph-lifecycle.md
│   └── upstream-pin.md       # vendored-from CWO commit manifest
├── templates/
│   └── markdown-workgraph.md
├── tests/                    # vendored+new unittest suite
└── .github/workflows/ci.yml
```

Budget estimate: ~25–30 files, well inside the 64-file/2 MB cap.

### Key adaptations to vendored code

- **Markdown workgraphs are the only state backend.** All `bd`/Beads code
  paths are removed or unreachable; no vendored module imports
  `cwo_core.beads` at runtime (test-enforced). `scaffold_workgraph.py`
  defaults to `--format markdown-workgraph`; `continue_sprint.py` and
  `summarize_resume_state.py` operate on workgraph files only.
- **Workspace location:** workgraph files live in a work directory inside the
  pod. Exact path is an implementation-plan decision after verifying what the
  importer preserves and what the subprocess tools use as cwd; the skill must
  not depend on paths outside what Odysseus already provides.
- **JSON is the machine contract.** The agent always invokes coach/route with
  `--format json` and parses output (the JSON already contains the summary
  fields that upstream's `--brief` text mode renders); text rendering is for
  humans in the terminal, not for the agent.
- **Sensitivity floor survives:** the agent asks for or infers a
  `--data-sensitivity` declaration whenever the heuristic flags above public,
  and passes it explicitly. Declarations can raise, never lower (upstream
  semantics).

## Chat interaction flow

1. **Trigger** — SKILL.md "When to Use" keys on orchestration-shaped requests
   (multi-step work, planning, sprint continuation, risk/gate questions);
   trivial single-step asks are explicitly out of scope (upstream small-task
   calibration).
2. **Coach run** — `python3 scripts/coach_prompt.py --format json "<goal>"`.
3. **Surface options** — one chat message: recommendation summary (route, task
   class, risk, sensitivity) + open questions (parallelism, context depth,
   validation/publish gates) as a numbered list with defaults marked.
4. **Map answers** — plain-language replies → documented flags → re-run
   coach/router → show final orchestration packet before starting.
5. **Execute** — scaffold Markdown workgraph, save to workspace, work through
   items, update statuses in the file with evidence notes at closure.
6. **Continue/resume** — later conversation: `continue_sprint.py
   --markdown-workgraph <path>` → relay the next-issue brief (ready/blocked,
   why-next) in chat.

## Error handling

- Scripts keep upstream's fail-closed convention: bad input → non-zero exit,
  one-line stderr reason. SKILL.md instructs the agent to relay stderr
  verbatim, not improvise around failures.
- Missing/corrupt workgraph → existing "not a CWO Markdown workgraph" error;
  agent offers to re-scaffold.
- Python toolset off → `requires_toolsets` hides the skill (unreachable
  state).
- Sensitivity ≥ restricted → agent must not send content to external model
  APIs and says why. The advisory-boundary framing from upstream's trust model
  is restated for chat in `references/chat-protocol.md`: these gates verify
  the scripted path; they cannot physically prevent a bypass.

## Testing & CI

- Vendored unittest subset (path-adjusted): coach/route JSON contract tests,
  workgraph scaffold/parse round-trip, continue-sprint ranking/blockers.
- New `tests/test_bundle_budget.py`: ≤ 64 files, ≤ 2 MB total, ≤ 400 KB per
  file, only importer-allowed suffixes — the importability constraint is
  enforced, not remembered.
- New test: no vendored module imports `cwo_core.beads` at runtime.
- GitHub Actions: `python3 -m compileall .` + `python3 -m unittest discover`
  on ubuntu-latest. Stdlib-only, matching both upstream's rule and the pod.

## Out of scope (v1)

Contractor packets, returns scoring, audit chain, quotas/waivers, ChatGPT
browser lane, Beads/`bd`, expert catalog, site/docs generation, any change to
Odysseus itself.

## Acceptance criteria

1. Pasting the repo URL into Odysseus "import from URL" imports the skill
   without errors and it appears in the skills index.
2. In chat, an orchestration-shaped request leads the agent to run the coach
   and present the options message (levers + defaults) as designed.
3. User answers produce a final packet; a Markdown workgraph file is created
   in the pod.
4. "Continue the sprint" in a fresh conversation produces a correct next-issue
   brief from that workgraph.
5. CI green; bundle-budget test enforces importability.
