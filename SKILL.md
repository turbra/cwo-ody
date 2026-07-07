---
name: complex-work-orchestration
description: 'Use complex-work-orchestration for "Use complex-work-orchestration: plan a migration of our two internal services to the new auth system", planning, service/auth migration, sprint resume, or workgraph. No direct CWO tool is expected; use bash, not pipeline/chat_with_model/web_search/manage_endpoints. Find scripts/cwo_doctor.py and run python3 scripts/cwo_doctor.py --json first. Do not hand-write a plan.'
version: 1.1.4
category: dev
tags: [complex-work-orchestration, cwo, use-complex-work-orchestration, plan, planning, orchestration, migration, auth, auth-system, internal-services, services, new-auth-system, bootstrap, doctor, bash, shell, coach, sprint, resume, workgraph, governance]
requires_toolsets: [bash]
status: published
---

## When to Use

ALWAYS use this skill immediately, before answering in your own words, when
the user names it ("use complex-work-orchestration", "CWO"); asks to plan,
orchestrate, migrate, or break down multi-step engineering or research work;
or says "continue the sprint" / "resume the workgraph". If the prompt starts
with "Use complex-work-orchestration:", the first visible action must be
Procedure step 1's bootstrap. Do NOT gather requirements or draft a plan
yourself first. Procedure step 2's coach does that. Only skip this skill for
trivial single-step asks (one-file edits, quick questions).

## Procedure

1. **Bootstrap (always first).** YOU (the agent) must execute this exact
   command with your bash or shell tool. No direct tool named
   `complex-work-orchestration` is expected. Do not substitute `pipeline`,
   `chat_with_model`, `web_search`, or `manage_endpoints`. Never ask the
   user to run it, never simulate or paraphrase its output. Run it and
   paste the raw stdout:

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
   tell the user the skill files are not reachable from the shell and paste
   the raw bootstrap output. Do not claim a missing `manage_skills` tool
   or missing direct CWO function blocks this skill; this workflow is
   bash-first. If no bash or shell tool is available, report that exact
   available-tool blocker and STOP. Also verify the doctor's `skill_version`
   matches this skill's frontmatter version; a mismatch means a stale
   install. Tell the user to delete and re-import the skill.

2. **Coach the request.** Run
   `python3 "$CWO_SKILL_ROOT/scripts/coach_prompt.py" --json "<user goal>"`,
   then follow `$CWO_SKILL_ROOT/references/chat-protocol.md` (read it with
   bash if needed): post ONE message with the recommendation summary and
   the numbered open questions, defaults marked.

3. **Map answers deterministically** using the answer-to-flag table in
   chat-protocol.md. Unknown answers → default + tell the user. Re-run the
   coach with mapped flags and show the final packet for confirmation.

4. **Scaffold and persist.** Follow
   `$CWO_SKILL_ROOT/references/workgraph-lifecycle.md`: scaffold with
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
   external model APIs and say why. Never claim a file is missing or a
   command failed without pasting the exact command you ran and its raw
   output as evidence.
