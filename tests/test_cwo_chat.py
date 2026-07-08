#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CWO_CHAT = REPO_ROOT / "scripts" / "cwo_chat.py"

# Add scripts directory to path for importing functions
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def run_cwo_chat(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CWO_CHAT), *args], text=True, capture_output=True,
    )


class CwoChatTests(unittest.TestCase):
    def test_start_emits_post_and_next_blocks(self) -> None:
        """Test that start command emits both POST and NEXT blocks with required content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = run_cwo_chat(
                "start",
                "expand the documentation for the public API endpoints",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check for delimiter blocks
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", proc.stdout)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", proc.stdout)

            # Check for required content in POST block
            self.assertIn("Reply with your choices", proc.stdout)
            self.assertIn("(default)", proc.stdout)  # Mark for default option

            # Session file should exist
            cwo_dir = Path(tmpdir) / ".cwo"
            self.assertTrue(cwo_dir.exists())
            session_files = list(cwo_dir.glob("session-*.json"))
            self.assertEqual(len(session_files), 1)

            # Session file should parse as JSON with required keys
            with open(session_files[0]) as f:
                session = json.load(f)
            self.assertIn("version", session)
            self.assertIn("goal", session)
            self.assertIn("slug", session)
            self.assertIn("questions", session)
            self.assertIn("flags", session)

    def test_start_next_command_names_answer_and_session(self) -> None:
        """Test that NEXT block contains answer subcommand and absolute session path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = run_cwo_chat(
                "start",
                "document the API",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Extract NEXT block
            next_block = proc.stdout.split("===== NEXT COMMAND (run after the user replies) =====")[1].strip()

            # Should contain "answer" subcommand
            self.assertIn("answer", next_block)

            # Should contain absolute path to session
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)
            session_path = str(session_files[0].resolve())
            self.assertIn(session_path, next_block)

    def test_answer_defaults_creates_workgraph(self) -> None:
        """Test that answer with 'defaults' creates a workgraph file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start
            proc = run_cwo_chat(
                "start",
                "implement the authentication system",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get session path
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)
            session_path = str(session_files[0].resolve())

            # Now run answer with defaults
            proc = run_cwo_chat("answer", "defaults", "--session", session_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check for delimiter blocks
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", proc.stdout)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", proc.stdout)

            # Workgraph file should exist
            workgraph_files = list((Path(tmpdir) / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)

            # Check content
            with open(workgraph_files[0]) as f:
                content = f.read()
            self.assertIn("Reduced durability fallback", content)
            self.assertIn("## Work Items", content)

            # POST block should contain absolute workgraph path
            self.assertIn(str(workgraph_files[0].resolve()), proc.stdout)

    def test_answer_maps_tight_and_sensitivity(self) -> None:
        """Test that answer properly maps tight scaffold size and sensitivity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start
            proc = run_cwo_chat(
                "start",
                "add new features",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get session path
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            session_path = str(session_files[0].resolve())

            # Run answer with tight and internal sensitivity
            proc = run_cwo_chat(
                "answer",
                "tight graph, internal data",
                "--session", session_path
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check session JSON for mapped flags
            with open(session_path) as f:
                session = json.load(f)
            self.assertEqual(session.get("flags", {}).get("scaffold_size"), "tight")
            self.assertEqual(session.get("flags", {}).get("data_sensitivity"), "internal")

            # POST block should note non-default choices
            self.assertIn("scaffold_size", proc.stdout)
            self.assertIn("data_sensitivity", proc.stdout)

    def test_answer_missing_session_fails_closed(self) -> None:
        """Test that answer with nonexistent session fails cleanly."""
        proc = run_cwo_chat(
            "answer",
            "defaults",
            "--session", "/nonexistent/session.json"
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(len(proc.stderr) > 0)
        # Should not contain a traceback
        self.assertNotIn("Traceback", proc.stderr)

    def test_continue_recommends_next(self) -> None:
        """Test that continue recommends next work item."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Full start + answer flow
            proc = run_cwo_chat(
                "start",
                "build the new feature",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            session_path = str(session_files[0].resolve())

            proc = run_cwo_chat("answer", "defaults", "--session", session_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get workgraph path
            workgraph_files = list((Path(tmpdir) / ".cwo").glob("workgraph-*.md"))
            workgraph_path = str(workgraph_files[0].resolve())

            # Run continue
            proc = run_cwo_chat("continue", workgraph_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check for delimiter blocks
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", proc.stdout)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", proc.stdout)

            # POST should contain recommended item id and "why" text
            self.assertIn("Recommended", proc.stdout)

            # NEXT should contain "rerun this continue command"
            next_block = proc.stdout.split("===== NEXT COMMAND (run after the user replies) =====")[1].strip()
            self.assertIn("continue", next_block)

    def test_continue_missing_file_fails_closed(self) -> None:
        """Test that continue with nonexistent workgraph fails cleanly."""
        proc = run_cwo_chat("continue", "/nonexistent/workgraph.md")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(len(proc.stderr) > 0)
        # Should not contain a traceback
        self.assertNotIn("Traceback", proc.stderr)

    def test_answer_maps_heavy_subagents_precedence(self) -> None:
        """Test that heavy subagents matches before generic subagent pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start
            proc = run_cwo_chat(
                "start",
                "scale the system",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get session path
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)
            session_path = str(session_files[0].resolve())

            # Run answer with "heavy subagents please"
            proc = run_cwo_chat(
                "answer",
                "heavy subagents please",
                "--session", session_path
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check session JSON for parallelism directive
            with open(session_path) as f:
                session = json.load(f)
            self.assertEqual(session.get("parallelism"), "heavy-review-subagents",
                           "heavy subagents should map to 'heavy-review-subagents'")

    def test_answer_maps_no_subagents(self) -> None:
        """Test that no subagents maps correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start
            proc = run_cwo_chat(
                "start",
                "run in main thread",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get session path
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)
            session_path = str(session_files[0].resolve())

            # Run answer with "no subagents"
            proc = run_cwo_chat(
                "answer",
                "no subagents",
                "--session", session_path
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check session JSON for parallelism directive
            with open(session_path) as f:
                session = json.load(f)
            self.assertEqual(session.get("parallelism"), "no-subagents",
                           "no subagents should map to 'no-subagents'")

    def test_run_functions_importable_and_return_text(self) -> None:
        """Test that run_start/run_answer/run_continue are importable and return text."""
        from cwo_chat import run_start, run_answer, run_continue, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Test run_start
            output = run_start("test goal", workspace)
            self.assertIsInstance(output, str)
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", output)

            # Session file should exist
            session_files = list((workspace / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)

    def test_answer_discovers_newest_session(self) -> None:
        """Test that run_answer discovers newest session when session_path is None."""
        from cwo_chat import run_start, run_answer

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a session via run_start
            run_start("test goal", workspace)

            # Call run_answer without providing session_path
            output = run_answer("defaults", None, workspace)
            self.assertIsInstance(output, str)
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", output)

            # Workgraph should be created
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)

            # Output should contain the absolute workgraph path
            self.assertIn(str(workgraph_files[0].resolve()), output)

    def test_continue_discovers_newest_workgraph(self) -> None:
        """Test that run_continue discovers newest workgraph when workgraph_path is None."""
        from cwo_chat import run_start, run_answer, run_continue

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create session and workgraph via run_start and run_answer
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Call run_continue without providing workgraph_path
            output = run_continue(None, workspace)
            self.assertIsInstance(output, str)
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertIn("Recommended", output)

    def test_discovery_fails_closed_when_empty(self) -> None:
        """Test that run_answer and run_continue raise CwoChatError when nothing is found."""
        from cwo_chat import run_answer, run_continue, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Try run_answer on empty workspace
            with self.assertRaises(CwoChatError) as ctx:
                run_answer("defaults", None, workspace)
            self.assertIn("run start first", str(ctx.exception))

            # Try run_continue on empty workspace
            with self.assertRaises(CwoChatError) as ctx:
                run_continue(None, workspace)
            self.assertIn("run start and answer first", str(ctx.exception))

    def test_cli_answer_without_session_flag_uses_discovery(self) -> None:
        """Test that CLI answer without --session flag uses discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start
            proc = run_cwo_chat(
                "start",
                "test discovery",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Run answer WITHOUT --session flag
            proc = run_cwo_chat(
                "answer",
                "defaults",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check for delimiter blocks
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", proc.stdout)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", proc.stdout)

            # Workgraph should exist
            workgraph_files = list((Path(tmpdir) / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)


if __name__ == "__main__":
    unittest.main()
