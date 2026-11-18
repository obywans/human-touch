"""Opt-in features: C2PA credential removal (needs --remove-provenance) and homoglyph fixing."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "human", "scripts")
sys.path.insert(0, SCRIPTS)
import _clean_lib as lib  # noqa: E402

META = os.path.join(SCRIPTS, "metadata_inspect.py")
CLEAN = os.path.join(SCRIPTS, "text_clean.py")


def run(script, *args):
    return subprocess.run([sys.executable, "-I", script, *args], capture_output=True, text=True, timeout=30)


def png_with_c2pa():
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Author\0Someone") + chunk(b"caBX", b"jumb-c2pa-data")
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))


def jpeg_with_c2pa():
    def seg(m, payload):
        return b"\xff" + bytes([m]) + struct.pack(">H", len(payload) + 2) + payload
    jumb1 = b"JP\x00\x00\x00\x01" + b"jumb" + b"c2pa" + b"A" * 8
    jumb2 = b"JP\x00\x00\x00\x02" + b"B" * 12   # continuation segment: no "c2pa" text in it
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0")
            + seg(0xFE, b"a comment") + seg(0xEB, jumb1) + seg(0xEB, jumb2)
            + b"\xff\xda\x00\x02" + b"\x00" * 4 + b"\xff\xd9")


class C2paRemovalTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.d, True)

    def write(self, name, data):
        p = os.path.join(self.d, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_default_never_removes_c2pa(self):
        p = self.write("a.png", png_with_c2pa())
        r = run(META, "strip", p, "--only", "c2pa", "--confirm")
        self.assertEqual(r.returncode, 1)
        r = run(META, "strip", p, "--confirm")
        self.assertEqual(r.returncode, 2)  # refused: provenance
        self.assertEqual(sorted(os.listdir(self.d)), ["a.png"])

    def test_png_removal_is_consent_gated_and_complete(self):
        p = self.write("a.png", png_with_c2pa())
        dry = run(META, "strip", p, "--remove-provenance")
        self.assertIn("DRY RUN", dry.stdout)
        self.assertEqual(sorted(os.listdir(self.d)), ["a.png"])
        r = run(META, "strip", p, "--remove-provenance", "--confirm")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        out = os.path.join(self.d, "a.nometa.png")
        data = open(out, "rb").read()
        self.assertNotIn(b"caBX", data)
        self.assertNotIn(b"Someone", data)
        self.assertIn(b"IDAT", data)
        self.assertIn("C2PA content credentials: not found", run(os.path.join(SCRIPTS, "watermark_audit.py"), out).stdout)
        self.assertIn(b"caBX", open(p, "rb").read())  # original untouched
        self.assertIn("not proof", r.stdout)

    def test_jpeg_removal_drops_every_jumbf_segment(self):
        p = self.write("a.jpg", jpeg_with_c2pa())
        r = run(META, "strip", p, "--remove-provenance", "--confirm")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        data = open(os.path.join(self.d, "a.nometa.jpg"), "rb").read()
        self.assertNotIn(b"c2pa", data)
        self.assertNotIn(b"B" * 12, data)
        self.assertNotIn(b"a comment", data)
        self.assertTrue(data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"))
        self.assertIn(b"JFIF", data)

    def test_flag_without_confirm_writes_nothing(self):
        p = self.write("a.jpg", jpeg_with_c2pa())
        run(META, "strip", p, "--remove-provenance")
        self.assertEqual(sorted(os.listdir(self.d)), ["a.jpg"])


class HomoglyphFixTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(lib.clean_text("pаssword").text, "pаssword")

    def test_fixes_inside_latin_words_only(self):
        self.assertEqual(lib.clean_text("pаssword hellｏ", fix_homoglyphs=True).text, "password hello")
        self.assertEqual(lib.clean_text("привет мир", fix_homoglyphs=True).text, "привет мир")

    def test_reported_as_replaced(self):
        r = lib.clean_text("pаss", fix_homoglyphs=True)
        self.assertEqual([(f.category, f.action) for f in r.findings], [("homoglyph", "replaced")])

    def test_cli_option(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("pаssword\n")
            self.assertEqual(run(CLEAN, "clean", p, "--fix-homoglyphs").returncode, 0)
            self.assertEqual(open(os.path.join(d, "t.clean.txt"), encoding="utf-8").read(), "password\n")


if __name__ == "__main__":
    unittest.main()
