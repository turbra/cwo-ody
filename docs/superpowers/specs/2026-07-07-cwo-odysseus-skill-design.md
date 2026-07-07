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
  `.md .py .sh .yaml .yml .json .toml`. **The directory walker silently
  truncates**: it `break`s when the file/byte caps are hit and stops recursing
  below directory depth 4 — it does not error. The bundle must therefore stay
  well under the caps (target ≤ 55 files) and ≤ 3 directory levels deep, and
  the budget test must assert the exact expected file manifest, not just
  "under limit".
- The agent has streaming `bash` and `python` subprocess tools. The `python`
  tool executes isolated snippets; `bash` starts in the active workspace and
  is not sandboxed, so **script execution keys on `bash`** (`bash` runs
  `python3 <script>`).
- `requires_toolsets` frontmatter hides the skill when a required toolset is
  inactive; the toolset vocabulary is the tool-section keys (verified:
  `bash`, `python` are literal keys), so the skill declares
  `requires_toolsets: [bash]`.
- `get_workspace` is a built-in tool returning the absolute path of the active
  workspace folder; file tools are confined to it and the shell starts there.

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
- **Skill-root bootstrap (execution path):** imported files land under
  Odysseus's skill storage (`data/skills/<category>/<name>/`), while `bash`
  starts in the agent workspace — the two are different directories. SKILL.md's
  Procedure therefore begins with a deterministic bootstrap: one `bash`
  command that locates the installed skill root by searching the candidate
  data roots for a unique sentinel file (`scripts/cwo_doctor.py`), exports it
  as `CWO_SKILL_ROOT`, and runs `python3 "$CWO_SKILL_ROOT/scripts/cwo_doctor.py"
  --json` to prove executability (Python version, script tree intact, policy
  readable) before any real command. If a deployment prevents direct
  execution from skill storage, the documented contingency is materializing
  `scripts/` into the workspace via `manage_skills view_ref` — contingency
  only, not the primary path. The vertical-slice milestone (below) proves the
  primary path live before more code is vendored.
- **Workspace location (settled):** workgraph files live under
  `<workspace>/.cwo/` where `<workspace>` is the path returned by
  `get_workspace` — e.g. `<workspace>/.cwo/workgraph-<slug>.md`. The final
  orchestration packet shown to the user always includes the workgraph's
  absolute path so a fresh conversation can resume it.
- **JSON is the machine contract.** The agent always invokes coach/route with
  `--json` (upstream's actual flag) and parses output (the JSON already
  contains the summary fields that upstream's `--brief` text mode renders);
  text rendering is for humans in the terminal, not for the agent.
- **Sensitivity floor survives:** the agent asks for or infers a
  `--data-sensitivity` declaration whenever the heuristic flags above public,
  and passes it explicitly. Declarations can raise, never lower (upstream
  semantics).

### SKILL.md shape

Odysseus's parser and skills index favor a small set of known sections. The
SKILL.md stays tight: frontmatter, a short **When to Use**, and a **Procedure**
of numbered steps (bootstrap → coach → surface options → map answers →
execute → continue), each step pointing into `references/` for detail. Deep
protocol content lives in `references/chat-protocol.md` and
`references/workgraph-lifecycle.md`; no reliance on arbitrary CWO-style
headings being surfaced in the index.

### Answer-to-flag mapping (deterministic)

`references/chat-protocol.md` contains a mapping table — one row per coach
question: question id, what the agent asks in chat, default, accepted
plain-language answers, the exact flag/JSON field each answer maps to, and the
re-run command. The agent must use this table rather than inventing mappings;
anything not in the table is answered with the default plus a note to the
user.

## Chat interaction flow

1. **Trigger** — SKILL.md "When to Use" keys on orchestration-shaped requests
   (multi-step work, planning, sprint continuation, risk/gate questions);
   trivial single-step asks are explicitly out of scope (upstream small-task
   calibration).
2. **Coach run** — `python3 scripts/coach_prompt.py --json "<goal>"`.
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
- New `tests/test_bundle_budget.py`: asserts the **exact expected file
  manifest** (tracked files == a checked-in manifest list), ≤ 55 files
  (margin under the 64 cap), ≤ 2 MB total, ≤ 400 KB per file, ≤ 3 directory
  levels deep, only importer-allowed suffixes — because the importer truncates
  silently, "under limit" alone is not enough.
- New test: no vendored module imports `cwo_core.beads` at runtime.
- New `scripts/cwo_doctor.py` self-check used by the bootstrap; unit-tested
  (reports python version, tree integrity, policy readability as JSON).
- GitHub Actions: `python3 -m compileall .` + `python3 -m unittest discover`
  on ubuntu-latest. Stdlib-only, matching both upstream's rule and the pod.

## Build order: vertical slice first

Milestone 0 (before vendoring the full script set): SKILL.md +
`scripts/cwo_doctor.py` + one reference + the bundle-budget/manifest test.
Import that into the live Odysseus deployment and prove in chat that the agent
can locate the skill root and execute the doctor script from wherever the
importer stores files. This resolves the execution-path unknown — the design's
biggest risk — before more CWO code is copied. Milestone 1 vendors the core
loop; milestone 2 adds continuation/resume polish.

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
5. CI green; bundle-budget/manifest test enforces importability.
6. Live smoke test on the deployed Odysseus: after web-UI import, the chat
   agent locates and executes `cwo_doctor.py` successfully (milestone 0 gate,
   re-verified at v1).
