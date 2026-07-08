#!/usr/bin/env python3
"""Tests for cwo_mcp_server.py.

Tests run without the mcp package installed (CI constraint); mcp-specific
schema checks are skipIf-guarded.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = REPO_ROOT / "scripts" / "cwo_mcp_server.py"

# Add scripts directory to path for importing functions
sys.path.insert(0, str(REPO_ROOT / "scripts"))


class CwoMcpServerTests(unittest.TestCase):
    def test_tools_schema_shape(self) -> None:
        """Test TOOLS has exactly the 3 names; every entry has name/description/inputSchema."""
        # Import the module
        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Check tools count
        self.assertEqual(len(mod.TOOLS), 3, f"Expected 3 tools, got {len(mod.TOOLS)}")

        # Check tool names
        names = {t["name"] for t in mod.TOOLS}
        expected_names = {"cwo_start", "cwo_answer", "cwo_continue"}
        self.assertEqual(names, expected_names)

        # Check each tool has required fields
        for tool in mod.TOOLS:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("inputSchema", tool)
            # Check inputSchema structure
            schema = tool["inputSchema"]
            self.assertIn("type", schema)
            self.assertIn("properties", schema)
            self.assertIn("required", schema)
            # Verify no workspace property in any tool (v1.4.1: server-controlled only)
            self.assertNotIn("workspace", schema.get("properties", {}), f"Tool {tool['name']} should not have 'workspace' property")

        # Check required lists
        tools_by_name = {t["name"]: t for t in mod.TOOLS}
        self.assertEqual(set(tools_by_name["cwo_start"]["inputSchema"]["required"]), {"goal"})
        self.assertEqual(set(tools_by_name["cwo_answer"]["inputSchema"]["required"]), {"reply"})
        self.assertEqual(set(tools_by_name["cwo_continue"]["inputSchema"]["required"]), set())

    def test_handle_tool_start_answer_continue_round_trip(self) -> None:
        """Test handle_tool start->answer->continue flow with default-first and MCP wording."""
        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Start (now returns complete plan with workgraph)
            with mock.patch.dict(os.environ, {"CWO_WORKSPACE": tmpdir}):
                result = mod.handle_tool("cwo_start", {"goal": "test goal"})
            self.assertNotIn("error", result)
            self.assertIn("POST THIS MESSAGE TO THE USER", result)
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", result)
            # Check for default-first content
            self.assertIn("Applied Defaults", result)
            self.assertIn("Workgraph", result)
            self.assertIn("Adjustable Levers", result)
            # Check for MCP transport wording (not CLI wording)
            self.assertIn("plan is ready", result)
            self.assertNotIn("python3", result)
            # Check for universal ask_user guidance with mcp: prefix (v1.4.3)
            self.assertIn("Whenever you present the user with choices", result)
            self.assertIn("ask_user", result)
            self.assertIn("mcp: ", result)
            self.assertIn("Agent Guidance", result)
            self.assertIn("Other free-text field", result)
            # Workgraph should be created
            cwo_dir = Path(tmpdir) / ".cwo"
            workgraph_files = sorted(cwo_dir.glob("workgraph-*.md"), key=lambda p: p.stat().st_mtime)
            self.assertGreater(len(workgraph_files), 0)

            # Answer with adjustment
            session_files = sorted(cwo_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime)
            self.assertGreater(len(session_files), 0)
            session_path = str(session_files[-1])

            with mock.patch.dict(os.environ, {"CWO_WORKSPACE": tmpdir}):
                result = mod.handle_tool(
                    "cwo_answer",
                    {"reply": "tight graph", "session": session_path}
                )
            self.assertNotIn("error", result)
            self.assertIn("Configuration Complete", result)
            # Check workgraph path is in result
            self.assertIn(".md", result)
            # Check for MCP transport wording
            self.assertIn("===== NEXT COMMAND (run after the user replies) =====", result)
            self.assertIn("session complete", result)

            # Continue
            workgraph_files = sorted(cwo_dir.glob("workgraph-*.md"), key=lambda p: p.stat().st_mtime)
            self.assertGreater(len(workgraph_files), 0)
            workgraph_path = str(workgraph_files[-1])

            with mock.patch.dict(os.environ, {"CWO_WORKSPACE": tmpdir}):
                result = mod.handle_tool("cwo_continue", {"workgraph": workgraph_path})
            self.assertNotIn("error", result)
            self.assertIn("Recommended", result)
            # Check for mcp: tip in continue (v1.4.2)
            self.assertIn("mcp:", result)

    def test_handle_tool_ignores_workspace_argument(self) -> None:
        """Test that handle_tool ignores workspace argument and uses CWO_WORKSPACE env."""
        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmpdir_a:
            with tempfile.TemporaryDirectory() as tmpdir_b:
                # Patch CWO_WORKSPACE to tmpdir_a
                with mock.patch.dict(os.environ, {"CWO_WORKSPACE": tmpdir_a}):
                    # Call handle_tool with workspace argument pointing to tmpdir_b
                    # (which should be ignored)
                    result = mod.handle_tool(
                        "cwo_start",
                        {"goal": "test goal", "workspace": tmpdir_b}
                    )
                # Workspace argument should be ignored
                self.assertNotIn("error", result)
                self.assertIn("POST THIS MESSAGE TO THE USER", result)

                # Verify session/workgraph files are created under tmpdir_a, not tmpdir_b
                cwo_dir_a = Path(tmpdir_a) / ".cwo"
                cwo_dir_b = Path(tmpdir_b) / ".cwo"

                # tmpdir_a should have files
                self.assertTrue(cwo_dir_a.exists(), f"CWO dir should exist under tmpdir_a: {tmpdir_a}")
                workgraph_files_a = list(cwo_dir_a.glob("workgraph-*.md"))
                self.assertGreater(
                    len(workgraph_files_a), 0,
                    "Workgraph should be created under CWO_WORKSPACE (tmpdir_a)"
                )

                # tmpdir_b should NOT have files
                self.assertFalse(
                    cwo_dir_b.exists(),
                    f"CWO dir should NOT exist under tmpdir_b (workspace argument was ignored): {tmpdir_b}"
                )

    def test_handle_tool_errors_are_text_not_raises(self) -> None:
        """Test error handling returns text, never raises."""
        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"CWO_WORKSPACE": tmpdir}):
                # Unknown tool name
                result = mod.handle_tool("unknown_tool", {})
                self.assertIn("error: unknown tool", result)

                # cwo_answer with no session in empty workspace
                result = mod.handle_tool("cwo_answer", {"reply": "test"})
                self.assertIn("CWO error:", result)

                # Missing required argument
                result = mod.handle_tool("cwo_start", {})
                self.assertIn("error: missing required argument", result)

    def test_module_importable_without_mcp(self) -> None:
        """Test the module imports fine without mcp package installed."""
        # Fresh import should work without mcp
        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)

        # Should not raise during module import/exec
        spec.loader.exec_module(mod)

        # TOOLS should be accessible
        self.assertIsNotNone(mod.TOOLS)
        self.assertEqual(len(mod.TOOLS), 3)

        # handle_tool should work without mcp
        result = mod.handle_tool("cwo_start", {"goal": "test"})
        # Should not raise, should return text (error or valid response)
        self.assertIsInstance(result, str)

    @unittest.skipIf(importlib.util.find_spec("mcp") is None, "mcp not installed")
    def test_mcp_sdk_wiring(self) -> None:
        """Test schema compatibility with mcp SDK (only runs if mcp is installed)."""
        from mcp.types import Tool

        spec = importlib.util.spec_from_file_location("cwo_mcp_server", MCP_SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Try to construct Tool from each TOOLS entry
        for tool_dict in mod.TOOLS:
            try:
                tool = Tool(**tool_dict)
                self.assertIsNotNone(tool)
            except Exception as e:
                self.fail(f"Failed to construct Tool from {tool_dict['name']}: {e}")


if __name__ == "__main__":
    unittest.main()
