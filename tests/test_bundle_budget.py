"""Import-budget guard.

Odysseus's skill importer SILENTLY truncates bundles: its GitHub walker
stops collecting at 64 files / 2 MB and does not recurse below directory
depth 4. "Under the limit" is therefore not enough — this test asserts the
EXACT tracked-file manifest so an accidental addition (or a file the
importer would drop) fails CI loudly.
"""
from __future__ import annotations

import re
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
ODYSSEUS_RELEVANCE_THRESHOLD = 0.25
ACCEPTANCE_PROMPT = (
    "Use complex-work-orchestration: plan a migration of our two internal "
    "services to the new auth system."
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


def tokenize(text: str) -> set[str]:
    return {w.strip('.,!?";:()[]') for w in (text or "").lower().split() if len(w) > 1}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def skill_frontmatter() -> dict[str, object]:
    content = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    result: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key] = [part.strip() for part in value[1:-1].split(",") if part.strip()]
        else:
            result[key] = value
    return result


def odysseus_relevance_score(query: str) -> float:
    fm = skill_frontmatter()
    tags = list(fm.get("tags") or [])
    skill_text = " ".join(
        [
            str(fm.get("name", "")),
            str(fm.get("description", "")),
            " ".join(str(tag) for tag in tags),
            (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8"),
        ]
    )
    query_tokens = tokenize(query)
    score = jaccard(query_tokens, tokenize(skill_text))
    for tag in tags:
        tag_tokens = tokenize(str(tag))
        if tag_tokens and tag_tokens <= query_tokens:
            score = max(score, 0.3) * 1.3
    if query.lower() in str(fm.get("description", "")).lower():
        score = max(score, 0.6)
    return score * 1.08


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

    def test_explicit_cwo_prompt_crosses_odysseus_relevance_threshold(self) -> None:
        score = odysseus_relevance_score(ACCEPTANCE_PROMPT)
        self.assertGreaterEqual(score, ODYSSEUS_RELEVANCE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
