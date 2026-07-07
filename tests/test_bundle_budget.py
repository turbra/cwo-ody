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
