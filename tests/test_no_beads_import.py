"""The Odysseus pod has no `bd`; Beads must be unreachable.

Two guards: (1) cwo_core/beads.py is not vendored at all; (2) no vendored
Python file imports cwo_core.beads.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
IMPORT_RE = re.compile(r"^\s*(from|import)\s+(cwo_core\.)?beads\b", re.M)


class NoBeadsTests(unittest.TestCase):
    def test_beads_module_not_vendored(self) -> None:
        self.assertFalse((SCRIPTS / "cwo_core" / "beads.py").exists())

    def test_no_module_imports_beads(self) -> None:
        offenders = [
            str(p.relative_to(REPO_ROOT))
            for p in SCRIPTS.rglob("*.py")
            if IMPORT_RE.search(p.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_cwo_core_package_imports(self) -> None:
        import sys
        sys.path.insert(0, str(SCRIPTS))
        try:
            import cwo_core.coach    # noqa: F401
            import cwo_core.routing  # noqa: F401
            import cwo_core.workgraph_markdown  # noqa: F401
        finally:
            sys.path.remove(str(SCRIPTS))


if __name__ == "__main__":
    unittest.main()
