#!/usr/bin/env python3
"""Regression test for tests/style_report.py.

Usage: python3 tests/test_style_report.py

Covers a real bug found by review and fixed: an empty (but present)
tests/recorded/<case>.txt file was treated as real data instead of as "no
output", producing a fabricated "kept" casing label and a spurious 0.0 in
the pairwise-similarity average -- the opposite of the missing-file case,
which is correctly excluded. Runs the real script as a subprocess against a
throwaway copy of tests/, so it exercises the actual file end to end.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


class TestEmptyRecordedFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="style-report-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scratch_tests = Path(self.tmp) / "tests"
        shutil.copytree(TESTS_DIR, self.scratch_tests)

    def run_script(self):
        result = subprocess.run(
            [sys.executable, str(self.scratch_tests / "style_report.py")],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode, result.stdout

    def test_empty_file_is_reported_as_empty_not_fabricated(self):
        emptied = self.scratch_tests / "recorded" / "01-generic-ai-en.txt"
        emptied.write_text("", encoding="utf-8")

        rc, out = self.run_script()
        self.assertEqual(rc, 0)
        lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("01-generic-ai-en")}
        self.assertIn("(empty recorded output)", lines["01-generic-ai-en"])
        self.assertNotIn("kept", lines["01-generic-ai-en"])

    def test_missing_file_still_handled_as_before(self):
        missing = self.scratch_tests / "recorded" / "16-technical-es.txt"
        missing.unlink()

        rc, out = self.run_script()
        self.assertEqual(rc, 0)
        lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("16-technical-es")}
        self.assertIn("(no recorded output)", lines["16-technical-es"])


if __name__ == "__main__":
    unittest.main()
