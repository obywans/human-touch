#!/usr/bin/env python3
"""Regression tests for tests/check_outputs.py.

Usage: python3 tests/test_check_outputs.py

Covers a real bug found by review and fixed: without Unicode normalization,
NFC and NFD renderings of the same accented text (visually identical,
byte-for-byte different) made the checker both miss a kept fact that was
really there, and worse, let a banned phrase through undetected when it
happened to be in the other normal form. Also covers the checker's own
documented clean-failure behavior for a missing directory or case file.
"""
import io
import os
import sys
import unicodedata
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import check_outputs as co  # noqa: E402


class TestUnicodeNormalization(unittest.TestCase):
    def setUp(self):
        self._saved_cases = co.EXPECT["cases"]
        co.EXPECT["cases"] = dict(self._saved_cases)

    def tearDown(self):
        co.EXPECT["cases"] = self._saved_cases

    def test_nfd_output_still_satisfies_an_nfc_must_keep(self):
        nfc_word = unicodedata.normalize("NFC", "café")
        nfd_word = unicodedata.normalize("NFD", "café")
        self.assertNotEqual(nfc_word, nfd_word)  # sanity: genuinely different bytes

        co.EXPECT["cases"]["t-nfd-keep"] = {"must_keep": [nfc_word], "must_not": [], "claims": []}
        text = f"I had some {nfd_word} this morning.\n"
        self.assertEqual(co.check("t-nfd-keep", text), [])

    def test_nfd_must_not_phrase_is_still_caught(self):
        nfc_phrase = unicodedata.normalize("NFC", "creme de la creme")
        nfd_phrase = unicodedata.normalize("NFD", nfc_phrase)

        co.EXPECT["cases"]["t-nfd-mustnot"] = {"must_keep": [], "must_not": [nfc_phrase], "claims": []}
        text = f"This is the {nfd_phrase} of desserts.\n"
        problems = co.check("t-nfd-mustnot", text)
        self.assertTrue(any("creme de la creme" in p for p in problems), problems)

    def test_nfd_claim_form_is_still_matched(self):
        nfc_form = unicodedata.normalize("NFC", "année")
        nfd_form = unicodedata.normalize("NFD", nfc_form)

        co.EXPECT["cases"]["t-nfd-claim"] = {"must_keep": [], "must_not": [], "claims": [[nfc_form]]}
        text = f"Cette {nfd_form} a été excellente.\n"
        self.assertEqual(co.check("t-nfd-claim", text), [])


class TestCleanFailureModes(unittest.TestCase):
    def run_main(self, argv):
        old_argv = sys.argv
        sys.argv = ["check_outputs.py"] + argv
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                rc = co.main()
        finally:
            sys.argv = old_argv
        return rc, buf.getvalue()

    def test_missing_directory_fails_cleanly(self):
        rc, out = self.run_main(["/no/such/directory/at/all"])
        self.assertEqual(rc, 1)
        self.assertIn("file not found", out)
        self.assertNotIn("Traceback", out)

    def test_no_arguments_prints_usage(self):
        rc, out = self.run_main([])
        self.assertEqual(rc, 2)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
