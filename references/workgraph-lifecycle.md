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
