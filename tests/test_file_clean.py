#!/usr/bin/env python3
"""Tests for the File Cleaner (skills/human/scripts/file_clean.py).

Usage: python3 tests/test_file_clean.py

Covers TXT, Markdown, HTML, DOCX and PDF handling, the formats it must refuse
(images, unsupported types, signed documents), that the original is never
modified or overwritten, that only text is changed (the rest of a DOCX package
is byte-identical), and clean failures on corrupt input.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "human", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import file_clean  # noqa: E402
import _fixtures as fx  # noqa: E402


class FileCleanBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, data):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = file_clean.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class TestTextFiles(FileCleanBase):
    def test_txt_cleaned_to_new_file(self):
        src = self.write("a.txt", "Hola\u200b mundo\u00a0feliz\r\n")
        before = self.read(src)
        rc, out, _ = self.run_cli(src)
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(src), before)
        self.assertEqual(self.read(os.path.join(self.tmp.name, "a.clean.txt")), b"Hola mundo feliz\r\n")
        self.assertIn("Original left untouched", out)

    def test_markdown_code_protected_automatically(self):
        src = self.write("a.md", "Texto\u200b\n```\nx\u200b\n```\n")
        self.run_cli(src)
        self.assertEqual(self.read(os.path.join(self.tmp.name, "a.clean.md")), "Texto\n```\nx\u200b\n```\n".encode())

    def test_scan_writes_nothing(self):
        src = self.write("a.txt", "a\u200bb")
        rc, out, _ = self.run_cli(src, "--scan")
        self.assertEqual(rc, 0)
        self.assertEqual(os.listdir(self.tmp.name), ["a.txt"])
        self.assertIn("SCAN ONLY", out)

    def test_invalid_utf8_fails_cleanly(self):
        src = self.write("a.txt", b"\xff\xfe bad")
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 1)
        self.assertIn("UTF-8", err)
        self.assertEqual(os.listdir(self.tmp.name), ["a.txt"])


class TestHtml(FileCleanBase):
    HTML = ('<!doctype html><html><head><title>T\u200bx</title><style>p{c:\u200bred}</style></head><body>'
            '<p class="a\u200bb" title="t\u00a0t">Hola\u200b&#8203; mundo&nbsp;ok</p>'
            '<pre>keep\u200bme</pre><code>c\u200bd</code><!-- c\u200bm --><script>var a="\u200b";</script></body></html>')

    def test_only_text_nodes_change(self):
        src = self.write("p.html", self.HTML)
        rc, out, _ = self.run_cli(src)
        self.assertEqual(rc, 0)
        new = self.read(os.path.join(self.tmp.name, "p.clean.html")).decode()
        self.assertIn("<p class=\"a\u200bb\" title=\"t\u00a0t\">Hola mundo&nbsp;ok</p>", new)
        self.assertIn("<title>Tx</title>", new)
        for untouched in ("<pre>keep\u200bme</pre>", "<code>c\u200bd</code>", "<!-- c\u200bm -->",
                          "<style>p{c:\u200bred}</style>", '<script>var a="\u200b";</script>'):
            self.assertIn(untouched, new)
        self.assertIn("left unchanged", out)  # hidden characters in markup are reported, not touched
        self.assertIn("&nbsp;", out)


class TestDocx(FileCleanBase):
    def test_text_cleaned_and_rest_of_package_identical(self):
        src = self.write("d.docx", fx.build_docx())
        rc, out, _ = self.run_cli(src)
        self.assertEqual(rc, 0, out)
        new_path = os.path.join(self.tmp.name, "d.clean.docx")
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(new_path) as b:
            self.assertEqual(a.namelist(), b.namelist())
            self.assertIsNone(b.testzip())
            for n in a.namelist():
                if n != "word/document.xml":
                    self.assertEqual(a.read(n), b.read(n), n)
            doc = b.read("word/document.xml").decode()
        self.assertIn("<w:t>Hola mundo\u00a0!</w:t>", doc)  # NBSP before "!" is French-style, kept
        self.assertNotIn("\u200b", doc)
        self.assertIn('w:author="Luis G\u00f3mez"', doc)  # structure and attributes untouched
        self.assertIn('<w:t xml:space="preserve"> fin</w:t>', doc)  # leading space would otherwise be lost by Word

    def test_signed_docx_refused_unless_explicit(self):
        src = self.write("s.docx", fx.build_docx(signed=True))
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 2)
        self.assertIn("signature", err)
        self.assertEqual(os.listdir(self.tmp.name), ["s.docx"])
        rc, out, _ = self.run_cli(src, "--break-provenance")
        self.assertEqual(rc, 0)
        self.assertIn("no longer validate", out)

    def test_corrupt_docx_fails_cleanly(self):
        src = self.write("c.docx", b"PK\x03\x04 not really a zip")
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 1)
        self.assertEqual(os.listdir(self.tmp.name), ["c.docx"])
        self.assertTrue(err)

    def test_zip_bomb_declared_size_refused(self):
        import io as _io
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", b"a" * 1000)
        src = self.write("b.docx", buf.getvalue())
        with mock.patch.object(file_clean.meta, "MAX_ZIP_TOTAL", 10):
            rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 1)
        self.assertIn("unreasonable size", err)


class TestPdf(FileCleanBase):
    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_text_extracted_to_new_txt_pdf_untouched(self):
        pdf = fx.build_pdf(text="Hello PDF world")
        src = self.write("p.pdf", pdf)
        rc, out, _ = self.run_cli(src)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read(src), pdf)
        self.assertIn(b"Hello PDF world", self.read(os.path.join(self.tmp.name, "p.clean.txt")))
        self.assertIn("NOT preserved", out)

    def test_without_pdftotext_refuses_and_writes_nothing(self):
        src = self.write("p.pdf", fx.build_pdf())
        with mock.patch.object(file_clean.shutil, "which", return_value=None):
            rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 2)
        self.assertIn("pdftotext", err)
        self.assertEqual(os.listdir(self.tmp.name), ["p.pdf"])

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_garbage_pdf_fails_cleanly(self):
        src = self.write("g.pdf", b"%PDF-1.4 garbage")
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 1)
        self.assertEqual(os.listdir(self.tmp.name), ["g.pdf"])


class TestRefusals(FileCleanBase):
    def test_images_have_no_text_layer(self):
        src = self.write("i.png", fx.build_png())
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 2)
        self.assertIn("no OCR", err)
        self.assertIn("metadata_inspect", err)

    def test_unsupported_type(self):
        src = self.write("x.xyz", b"data")
        rc, _, err = self.run_cli(src)
        self.assertEqual(rc, 2)
        self.assertIn("Unsupported", err)

    def test_missing_file(self):
        rc, _, err = self.run_cli(os.path.join(self.tmp.name, "nope.txt"))
        self.assertEqual(rc, 1)
        self.assertIn("not a file", err)

    def test_existing_output_never_overwritten(self):
        src = self.write("a.txt", "a\u200bb")
        out_path = self.write("o.txt", "precious")
        rc, _, err = self.run_cli(src, "--output", out_path)
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(out_path), b"precious")
        self.assertIn("already exists", err)


if __name__ == "__main__":
    unittest.main()
