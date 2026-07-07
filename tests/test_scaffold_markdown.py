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
