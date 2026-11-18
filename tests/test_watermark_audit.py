"""Tests for the report-only watermark audit (scripts/watermark_audit.py, _audit_lib.py)."""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "human", "scripts")
sys.path.insert(0, SCRIPTS)
import _audit_lib as audit  # noqa: E402
import _update_lib as ulib  # noqa: E402

CLI = os.path.join(SCRIPTS, "watermark_audit.py")


def flagged(text):
    return {(f.category) for f in audit.audit_text(text).findings if f.verdict != "context-ok"}


class DetectionTests(unittest.TestCase):
    def test_clean_text_has_no_findings(self):
        for t in ("Plain sentence.", "Hola, ¿qué tal? Mañana « test » „Română” ăâîșț", "日本語のテキスト", "x = 1  # code"):
            self.assertEqual(audit.audit_text(t).findings, [], t)

    def test_delta_categories_are_flagged(self):
        cases = {
            "variation-selector": ["a︀b", "a\U000E0100b", "a᠋b"],
            "combining-joiner": ["a͏b"],
            "noncharacter": ["a﷐b", "a￿b"],
            "reserved-ignorable": ["a￰b", "a\U000E0080b", "a⁥b"],
            "private-use": ["ab"],
            "deprecated-format": ["a⁪b"],
            "script-filler": ["a឴b", "aᅟb"],
        }
        for cat, samples in cases.items():
            for s in samples:
                self.assertIn(cat, flagged(s), repr(s))

    def test_cleaner_categories_still_reported(self):
        self.assertTrue(flagged("a​b"))
        self.assertTrue(flagged("a\U000E0041b"))

    def test_legitimate_context_is_not_flagged(self):
        legit = ["👍️", "1️⃣", "漢\U000E0100", "ᠠ᠋ᠠ", "é͏̀",
                 "ក឴", "한ᅟ한"]
        for s in legit:
            self.assertEqual(flagged(s), set(), repr(s))

    def test_homoglyph_only_inside_latin_words(self):
        self.assertIn("homoglyph", flagged("pаssword"))
        self.assertIn("homoglyph", flagged("hellｏ"))
        self.assertEqual(flagged("привет мир"), set())   # whole Cyrillic words are normal
        self.assertEqual(flagged("ｆｕｌｌｗｉｄｔｈ"), set())  # all-fullwidth word, no ASCII

    def test_positions(self):
        f = audit.audit_text("ab\ncd⁪").findings[0]
        self.assertEqual((f.line, f.col), (2, 3))

    def test_audit_never_modifies_input(self):
        s = "a​︀b"
        audit.audit_text(s)
        self.assertEqual(s, "a​︀b")


class CleanAgreesWithAuditTests(unittest.TestCase):
    def clean(self, t):
        import _clean_lib as lib
        return lib.clean_text(t).text

    def test_clean_removes_flagged_carriers(self):
        for t in ("a\ufe00b", "a\U000E0100b", "a\u034fb", "a\ufdd0b", "a\ufff0b", "a\u206ab", "a\u17b4b", "a\u115fb"):
            self.assertEqual(self.clean(t), "ab", repr(t))

    def test_clean_keeps_legitimate_sequences(self):
        for t in ("▶\ufe0f", "👍\ufe0f", "1\ufe0f\u20e3", "漢\U000E0100", "e\u0301\u034f\u0300", "한\u115f한"):
            self.assertEqual(self.clean(t), t, repr(t))

    def test_clean_never_changes_look_alikes_or_private_use(self):
        for t in ("p\u0430ssword", "a\ue000b"):
            self.assertEqual(self.clean(t), t)

    def test_no_flagged_finding_survives_a_clean(self):
        t = "x\ufe00 y\u034f z\u206a w\ufdd0 ok \u200b"
        self.assertEqual([f for f in audit.audit_text(self.clean(t)).findings if f.verdict == "flagged"], [])

    def test_protected_code_is_not_modified(self):
        import _clean_lib as lib
        t = "`a\ufe00b` y a\ufe00b"
        r = lib.clean_text(t, protected=lib.code_spans(t))
        self.assertEqual(r.text, "`a\ufe00b` y ab")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", CLI, *args], capture_output=True, text=True, timeout=30)

    def test_text_file_report_and_file_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.txt")
            data = "hola​ pаss\n".encode()
            open(p, "wb").write(data)
            r = self.run_cli(p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("FLAGGED", r.stdout)
            self.assertIn("NOT checked", r.stdout)
            self.assertEqual(open(p, "rb").read(), data)
            self.assertEqual(os.listdir(d), ["n.txt"])  # nothing written

    def test_clean_file_never_claims_absence(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.txt")
            open(p, "w").write("nada raro")
            r = self.run_cli(p)
            self.assertIn("not proof", r.stdout)

    def test_json_output(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.txt")
            open(p, "w", encoding="utf-8").write("a︀b")
            out = json.loads(self.run_cli(p, "--json").stdout)
            self.assertEqual(out["findings"][0]["category"], "variation-selector")

    def test_docx_text_is_audited(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.docx")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml", "<w:document><w:t>hi​ there</w:t></w:document>")
            r = self.run_cli(p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("ZERO WIDTH SPACE", r.stdout)

    def test_png_reports_provenance_presence_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            import struct, zlib
            def chunk(t, b):
                return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
            png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                   + chunk(b"caBX", b"x") + chunk(b"IEND", b""))
            open(p, "wb").write(png)
            r = self.run_cli(p)
            self.assertIn("C2PA content credentials: PRESENT", r.stdout)
            self.assertIn("validity is not checked", r.stdout)

    def test_bad_input_exit_1(self):
        self.assertEqual(self.run_cli("/nonexistent/file.txt").returncode, 1)


class PluginInstallModeTests(unittest.TestCase):
    def test_plugin_cache_is_detected_and_never_self_updated(self):
        with tempfile.TemporaryDirectory() as d:
            skill = os.path.join(d, "plugins", "cache", "human-touch", "human-touch", "2.4.0", "skills", "human")
            os.makedirs(skill)
            self.assertEqual(ulib.detect_install_mode(skill), "plugin")
            other = os.path.join(d, "skills", "human")
            os.makedirs(other)
            self.assertNotEqual(ulib.detect_install_mode(other), "plugin")


if __name__ == "__main__":
    unittest.main()
