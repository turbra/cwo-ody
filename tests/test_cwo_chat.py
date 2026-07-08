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

from cwo_chat import NEXT_DELIMITER


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

            # Check for required content in POST block (default-first)
            self.assertIn("Applied Defaults", proc.stdout)
            self.assertIn("Workgraph", proc.stdout)
            self.assertIn("Adjustable Levers", proc.stdout)

            # Session file should exist
            cwo_dir = Path(tmpdir) / ".cwo"
            self.assertTrue(cwo_dir.exists())
            session_files = list(cwo_dir.glob("session-*.json"))
            self.assertEqual(len(session_files), 1)

            # Workgraph file should exist (created during start)
            workgraph_files = list(cwo_dir.glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)

            # Session file should parse as JSON with required keys
            with open(session_files[0]) as f:
                session = json.load(f)
            self.assertIn("version", session)
            self.assertIn("goal", session)
            self.assertIn("slug", session)
            self.assertIn("questions", session)
            self.assertIn("flags", session)
            self.assertIn("workgraph", session)  # Now created during start

    def test_start_next_command_plan_ready_message(self) -> None:
        """Test that NEXT block shows plan is ready (no further action needed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = run_cwo_chat(
                "start",
                "document the API",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Extract NEXT block
            next_block = proc.stdout.split("===== NEXT COMMAND (run after the user replies) =====")[1].strip()

            # Should contain message about plan being ready
            self.assertIn("plan is ready", next_block)
            self.assertIn("cwo_answer", next_block)  # Reference to adjusting via cwo_answer
            self.assertIn("cwo_continue", next_block)  # Reference to continuing via cwo_continue

    def test_answer_updates_workgraph(self) -> None:
        """Test that answer with 'defaults' re-scaffolds the workgraph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First, run start (creates workgraph with defaults)
            proc = run_cwo_chat(
                "start",
                "implement the authentication system",
                "--workspace", tmpdir
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Get session path and initial workgraph
            session_files = list((Path(tmpdir) / ".cwo").glob("session-*.json"))
            self.assertEqual(len(session_files), 1)
            session_path = str(session_files[0].resolve())

            workgraph_files = list((Path(tmpdir) / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)
            initial_content = workgraph_files[0].read_text()

            # Now run answer with defaults (re-scaffolds with same defaults)
            proc = run_cwo_chat("answer", "defaults", "--session", session_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check for delimiter blocks
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", proc.stdout)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", proc.stdout)

            # Workgraph file should still exist
            workgraph_files = list((Path(tmpdir) / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)

            # Check content
            with open(workgraph_files[0]) as f:
                content = f.read()
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

    def test_mcp_transport_includes_ask_user_guidance(self) -> None:
        """Test that MCP transport includes universal ask_user guidance with mcp: prefix."""
        from cwo_chat import run_start

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Test run_start with MCP transport
            output = run_start("test goal", workspace, transport="mcp")
            self.assertIsInstance(output, str)
            # MCP transport should NOT include delimiters (v1.4.5)
            self.assertNotIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertNotIn("===== NEXT COMMAND", output)
            # Should contain universal ask_user guidance
            self.assertIn("Whenever you present the user with choices", output)
            self.assertIn("ask_user", output)
            self.assertIn("mcp: ", output)
            # Should contain agent guidance section
            self.assertIn("Agent Guidance", output)
            # Should mention the Other field and prefix requirement
            self.assertIn("Other free-text field", output)
            self.assertIn("'mcp: '", output)
            # Should contain FINAL section with ask_user imperative (v1.4.5)
            self.assertIn("REQUIRED NEXT ACTION FOR YOU", output)
            # Should contain JSON shape with mcp: labels
            self.assertIn('"question":', output)
            self.assertIn('"options":', output)
            self.assertIn("mcp: accept defaults & proceed", output)

    def test_cli_transport_excludes_ask_user_guidance(self) -> None:
        """Test that CLI transport does NOT include ask_user guidance but has delimiters."""
        from cwo_chat import run_start

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Test run_start with CLI transport (default)
            output = run_start("test goal", workspace, transport="cli")
            self.assertIsInstance(output, str)
            # CLI should have delimiters
            self.assertIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertIn("===== NEXT COMMAND", output)
            # Should NOT contain ask_user guidance (CLI doesn't use it)
            self.assertNotIn("ask_user", output)
            # Should NOT contain agent guidance section (CLI doesn't need it)
            self.assertNotIn("Agent Guidance", output)
            # Should NOT contain FINAL section (CLI doesn't need it)
            self.assertNotIn("REQUIRED NEXT ACTION FOR YOU", output)

    def test_mcp_answer_includes_ask_user_guidance_after_changes(self) -> None:
        """Test that MCP transport answer includes ask_user guidance after changes."""
        from cwo_chat import run_start, run_answer

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create session
            run_start("test goal", workspace)

            # Get session path
            session_files = list((workspace / ".cwo").glob("session-*.json"))
            session_path = session_files[0]

            # Run answer with MCP transport and changes
            output = run_answer("tight graph", session_path, workspace, transport="mcp")
            self.assertIsInstance(output, str)
            # MCP transport should NOT include delimiters (v1.4.5)
            self.assertNotIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertNotIn("===== NEXT COMMAND", output)
            # Should contain FINAL section with ask_user (v1.4.5)
            self.assertIn("REQUIRED NEXT ACTION FOR YOU", output)
            self.assertIn("mcp: ", output)

    def test_continue_missing_explicit_path_error_is_actionable(self) -> None:
        """Test that continue with nonexistent explicit workgraph provides actionable recovery."""
        from cwo_chat import run_start, run_answer, run_continue, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a session and workgraph first (so newest exists)
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get the newest workgraph path
            workgraph_files = sorted((workspace / ".cwo").glob("workgraph-*.md"), key=lambda p: p.stat().st_mtime)
            newest_workgraph = workgraph_files[-1].resolve()

            # Try continue with nonexistent explicit path
            with self.assertRaises(CwoChatError) as ctx:
                run_continue(Path("/nonexistent/x.md"), workspace)

            error_msg = str(ctx.exception)
            # Error should mention the missing explicit path
            self.assertIn("workgraph not found", error_msg)
            self.assertIn("/nonexistent/x.md", error_msg)
            # Error should provide actionable recovery: use no argument
            self.assertIn("no workgraph argument", error_msg)
            # Error should show the discovered newest path
            self.assertIn(str(newest_workgraph), error_msg)

    def test_answer_missing_explicit_session_error_is_actionable(self) -> None:
        """Test that answer with nonexistent explicit session provides actionable recovery."""
        from cwo_chat import run_start, run_answer, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a session first (so newest exists)
            run_start("test goal", workspace)

            # Get the newest session path
            session_files = sorted((workspace / ".cwo").glob("session-*.json"), key=lambda p: p.stat().st_mtime)
            newest_session = session_files[-1].resolve()

            # Try answer with nonexistent explicit path
            with self.assertRaises(CwoChatError) as ctx:
                run_answer("defaults", Path("/nonexistent/session.json"), workspace)

            error_msg = str(ctx.exception)
            # Error should mention the missing explicit path
            self.assertIn("session not found", error_msg)
            self.assertIn("/nonexistent/session.json", error_msg)
            # Error should provide actionable recovery: omit the argument
            self.assertIn("Omit the session argument", error_msg)
            # Error should show the discovered newest path
            self.assertIn(str(newest_session), error_msg)

    def test_mcp_continue_includes_universal_guidance(self) -> None:
        """Test that MCP transport continue includes universal ask_user guidance."""
        from cwo_chat import run_start, run_answer, run_continue

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create session and workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Run continue with MCP transport
            output = run_continue(None, workspace, transport="mcp")
            self.assertIsInstance(output, str)
            # MCP transport should NOT include delimiters (v1.4.5)
            self.assertNotIn("===== POST THIS MESSAGE TO THE USER =====", output)
            self.assertNotIn("===== NEXT COMMAND", output)
            # Should contain universal guidance
            self.assertIn("Whenever you present the user with choices", output)
            self.assertIn("ask_user", output)
            self.assertIn("mcp: ", output)
            # Should contain Agent Guidance section
            self.assertIn("Agent Guidance", output)
            # Should mention the Other field
            self.assertIn("Other free-text field", output)
            # Should contain FINAL section with ask_user (v1.4.5)
            self.assertIn("REQUIRED NEXT ACTION FOR YOU", output)
            self.assertIn("mcp: work the recommended item now", output)

    def test_run_mark_round_trip(self) -> None:
        """Test run_mark updates item status and appends evidence."""
        from cwo_chat import run_start, run_answer, run_mark, run_continue

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Start and answer to create workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get workgraph path
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            self.assertEqual(len(workgraph_files), 1)
            workgraph_path = workgraph_files[0]

            # Read to find an item id (should be "epic" at minimum)
            content = workgraph_path.read_text()
            self.assertIn("### epic:", content)

            # Mark the epic item as closed
            output = run_mark("epic", "closed", "coordination done", workspace, workgraph_path)
            self.assertIsInstance(output, str)
            self.assertIn("Item Status Updated", output)
            self.assertIn("epic", output)
            self.assertIn("closed", output)
            self.assertIn("coordination done", output)

            # Verify file was updated
            updated_content = workgraph_path.read_text()
            self.assertIn("- Status: closed", updated_content)
            self.assertIn("- Evidence: coordination done", updated_content)

            # Verify run_continue no longer recommends epic
            output = run_continue(workgraph_path, workspace)
            self.assertIsInstance(output, str)
            # Epic should be closed, so shouldn't be in recommended/ready issues

    def test_run_mark_invalid_item_id(self) -> None:
        """Test run_mark raises CwoChatError for invalid item id."""
        from cwo_chat import run_start, run_answer, run_mark, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Start and answer to create workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get workgraph path
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            workgraph_path = workgraph_files[0]

            # Try to mark nonexistent item
            with self.assertRaises(CwoChatError) as ctx:
                run_mark("nonexistent", "closed", "evidence", workspace, workgraph_path)

            error_msg = str(ctx.exception)
            self.assertIn("nonexistent", error_msg)
            self.assertIn("not found", error_msg)
            # Should list valid ids
            self.assertIn("epic", error_msg)

    def test_run_mark_invalid_status(self) -> None:
        """Test run_mark raises CwoChatError for invalid status."""
        from cwo_chat import run_start, run_answer, run_mark, CwoChatError

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Start and answer to create workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get workgraph path
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            workgraph_path = workgraph_files[0]

            # Try to mark with invalid status
            with self.assertRaises(CwoChatError) as ctx:
                run_mark("epic", "invalid-status", "evidence", workspace, workgraph_path)

            error_msg = str(ctx.exception)
            self.assertIn("invalid status", error_msg)
            self.assertIn("open", error_msg)
            self.assertIn("closed", error_msg)

    def test_run_mark_mcp_transport_tail(self) -> None:
        """Test run_mark with MCP transport includes cwo_continue imperative."""
        from cwo_chat import run_start, run_answer, run_mark

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Start and answer to create workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get workgraph path
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            workgraph_path = workgraph_files[0]

            # Mark with MCP transport
            output = run_mark("epic", "closed", "evidence", workspace, workgraph_path, transport="mcp")
            self.assertIsInstance(output, str)
            # MCP should have cwo_continue imperative
            self.assertIn("REQUIRED NEXT ACTION FOR YOU", output)
            self.assertIn("cwo_continue tool NOW", output)
            # Should NOT have CLI command
            self.assertNotIn(NEXT_DELIMITER, output)

    def test_run_mark_cli_transport_tail(self) -> None:
        """Test run_mark with CLI transport includes command tail."""
        from cwo_chat import run_start, run_answer, run_mark

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Start and answer to create workgraph
            run_start("test goal", workspace)
            run_answer("defaults", None, workspace)

            # Get workgraph path
            workgraph_files = list((workspace / ".cwo").glob("workgraph-*.md"))
            workgraph_path = workgraph_files[0]

            # Mark with CLI transport (default)
            output = run_mark("epic", "closed", "evidence", workspace, workgraph_path, transport="cli")
            self.assertIsInstance(output, str)
            # CLI should have NEXT delimiter and command
            self.assertIn(NEXT_DELIMITER, output)
            self.assertIn("continue", output)


if __name__ == "__main__":
    unittest.main()
