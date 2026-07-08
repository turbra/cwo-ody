from __future__ import annotations

import json
import re
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

    def test_required_files_cover_core_loop(self) -> None:
        from pathlib import Path
        import importlib.util
        spec = importlib.util.spec_from_file_location("cwo_doctor", DOCTOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        required = set(mod.REQUIRED_FILES)
        for rel in [
            "scripts/coach_prompt.py",
            "scripts/cwo_chat.py",
            "scripts/cwo_mcp_server.py",
            "scripts/route_work.py",
            "scripts/scaffold_workgraph.py",
            "scripts/summarize_resume_state.py",
            "scripts/continue_sprint.py",
            "scripts/cwo_core/routing.py",
            "scripts/cwo_core/workgraph_markdown.py",
            "policy/routing-policy.yaml",
            "references/chat-protocol.md",
            "references/mcp-setup.md",
            "references/workgraph-lifecycle.md",
        ]:
            self.assertIn(rel, required)

    def test_version_consistency(self) -> None:
        """Verify SKILL.md frontmatter version matches doctor SKILL_VERSION."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("cwo_doctor", DOCTOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        doctor_version = mod.SKILL_VERSION

        skill_md = REPO_ROOT / "SKILL.md"
        content = skill_md.read_text()
        # Parse frontmatter: split on ---, extract second block (between first and second ---)
        frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        self.assertIsNotNone(frontmatter_match, "SKILL.md frontmatter not found")
        frontmatter = frontmatter_match.group(1)

        # Extract version: line
        version_match = re.search(r'^version:\s*(.+)$', frontmatter, re.MULTILINE)
        self.assertIsNotNone(version_match, "version: line not found in SKILL.md frontmatter")
        skill_md_version = version_match.group(1).strip()

        self.assertEqual(skill_md_version, doctor_version,
                        f"SKILL.md version {skill_md_version} does not match doctor SKILL_VERSION {doctor_version}")


if __name__ == "__main__":
    unittest.main()
