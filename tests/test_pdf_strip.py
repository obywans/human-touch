#!/usr/bin/env python3
"""Tests for PDF metadata removal (metadata_inspect.py strip on a PDF).

Usage: python3 tests/test_pdf_strip.py

The PDF files are built in memory by tests/_fixtures.py. One optional test
uses pdftotext and is skipped when pdftotext is not installed.
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "human", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import metadata_inspect  # noqa: E402
import _meta_lib as meta  # noqa: E402
import _fixtures as fx  # noqa: E402


class PdfBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, data):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = metadata_inspect.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def strip_file(self, data, *extra):
        src = self.write("a.pdf", data)
        rc, out, err = self.cli("strip", src, "--confirm", *extra)
        return src, rc, out, err

    def stripped(self, data, *extra):
        src, rc, out, err = self.strip_file(data, *extra)
        self.assertEqual(rc, 0, err)
        return self.read(os.path.join(self.tmp.name, "a.nometa.pdf"))


def page_stream(data):
    return re.search(rb"stream\n(BT .*? ET)\nendstream", data, re.DOTALL).group(1)


def startxrefs(data):
    return re.findall(rb"startxref\s+(\d+)", data)


class TestPdfStrip(PdfBase):
    def test_removes_all_info_fields_and_xmp(self):
        data = fx.build_pdf_real()
        before = meta.inspect_pdf(data)
        keys = {i["key"] for i in before["items"]}
        for k in ("Title", "Author", "Creator", "Producer", "CreationDate", "ModDate"):
            self.assertIn(k, keys)
        self.assertEqual(before["blocks"], {"info": 1, "xmp": 1})
        new = self.stripped(data)
        after = meta.inspect_pdf(new)
        self.assertEqual(after["items"], [])
        self.assertEqual(after["blocks"], {})
        for secret in (b"Chromium", b"Skia", b"Ana Perez", b"D:2026", b"Plan", b"0041006E"):
            self.assertNotIn(secret, new)
        self.assertIn(b"/Trapped /False", new)

    def test_same_length_same_startxref_same_page_stream(self):
        data = fx.build_pdf_real()
        new = self.stripped(data)
        self.assertEqual(len(new), len(data))
        self.assertEqual(startxrefs(new), startxrefs(data))
        self.assertEqual(page_stream(new), page_stream(data))
        self.assertEqual(new.count(b" obj"), data.count(b" obj"))
        for m in re.finditer(rb"(\d+) 0 obj", data):
            self.assertEqual(new[m.start():m.end()], data[m.start():m.end()])

    def test_nested_parentheses_and_escapes(self):
        info = b"<< /Title (a (b (c)) \\) \\( d) /Author (x\\\\) /Subject (tail) /Trapped /False >>"
        new = self.stripped(fx.build_pdf_real(info=info, xmp=False))
        self.assertEqual(meta.inspect_pdf(new)["items"], [])
        self.assertIn(b"/Title ()", new)
        self.assertIn(b"/Author ()", new)
        self.assertIn(b"/Subject ()", new)
        self.assertNotIn(b"tail", new)
        self.assertIn(b"/Trapped /False", new)

    def test_nested_parentheses_are_read_in_full_by_inspection(self):
        info = b"<< /Title (a (b) c) /Author (Ana) >>"
        values = {i["key"]: i["value"] for i in meta.inspect_pdf(fx.build_pdf_real(info=info, xmp=False))["items"]}
        self.assertEqual(values["Title"], "a (b) c")
        self.assertEqual(values["Author"], "Ana")

    def test_hexadecimal_string_is_blanked(self):
        data = fx.build_pdf_real(info=b"<< /Author <FEFF0041006E0061> /Producer <48656C6C6F> >>", xmp=False)
        self.assertEqual(self.values(meta.inspect_pdf(data))["Author"], "Ana")
        new = self.stripped(data)
        self.assertIn(b"/Author <>", new)
        self.assertIn(b"/Producer <>", new)
        self.assertEqual(meta.inspect_pdf(new)["items"], [])

    @staticmethod
    def values(ins):
        return {i["key"]: i["value"] for i in ins["items"]}

    def test_two_revisions_both_copies_blanked_and_reported(self):
        data = fx.build_pdf_real(revisions=2)
        self.assertEqual(data.count(b"%%EOF"), 2)
        before = meta.inspect_pdf(data)
        self.assertEqual(before["blocks"]["info"], 2)
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(rc, 0, err)
        self.assertIn("2 of 2 object copies blanked", out)
        new = self.read(os.path.join(self.tmp.name, "a.nometa.pdf"))
        self.assertNotIn(b"Revision 2 title", new)
        self.assertNotIn(b"Chromium", new)
        self.assertNotIn(b"Ana Perez", new.replace(b"<rdf:li>", b""))
        self.assertEqual(len(new), len(data))
        self.assertEqual(startxrefs(new), startxrefs(data))
        self.assertEqual(meta.inspect_pdf(new)["blocks"], {})

    def test_encrypted_file_refused_nothing_written(self):
        data = fx.build_pdf_real(encrypt=True)
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(rc, 2)
        self.assertIn("encrypted", err)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])
        with self.assertRaises(meta.StripRefused):
            meta.strip_pdf(data, {"info", "xmp"})

    def test_info_in_compressed_object_stream_refused_with_clear_message(self):
        data = fx.build_pdf_real(objstm=True).replace(b"/Root 1 0 R", b"/Root 1 0 R /Info 12 0 R")
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(rc, 2)
        self.assertIn("compressed object stream", err)
        self.assertIn("Nothing was written", err)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])

    def test_signed_file_refused_without_break_provenance(self):
        data = fx.build_pdf_real(signed=True)
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(rc, 2)
        self.assertIn("digital signature", err)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])

    def test_signed_file_handled_with_break_provenance_and_warns(self):
        data = fx.build_pdf_real(signed=True)
        src, rc, out, err = self.strip_file(data, "--break-provenance")
        self.assertEqual(rc, 0, err)
        self.assertIn("no longer validate", out)
        new = self.read(os.path.join(self.tmp.name, "a.nometa.pdf"))
        self.assertEqual(meta.inspect_pdf(new)["items"], [])
        self.assertTrue(meta.inspect_pdf(new)["provenance"]["signatures"])

    def test_dry_run_writes_nothing(self):
        src = self.write("a.pdf", fx.build_pdf_real())
        rc, out, err = self.cli("strip", src)
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])

    def test_original_unchanged(self):
        data = fx.build_pdf_real(revisions=2)
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(self.read(src), data)

    def test_existing_output_never_overwritten(self):
        src = self.write("a.pdf", fx.build_pdf_real())
        existing = self.write("o.pdf", b"keep me")
        rc, out, err = self.cli("strip", src, "--confirm", "--output", existing)
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(existing), b"keep me")
        self.assertIn("already exists", err)

    def test_only_blocks_option(self):
        data = fx.build_pdf_real()
        new = self.stripped(data, "--only", "xmp")
        after = meta.inspect_pdf(new)
        self.assertEqual(after["blocks"], {"info": 1})
        self.assertIn(b"Chromium", new)
        self.assertNotIn(b"Ana Perez", new)

    def test_xmp_too_short_for_empty_element_becomes_spaces(self):
        packet = b'<?xpacket begin="x"?><a>Ana Perez</a><?xpacket end="w"?>'
        data = fx.build_pdf_real(xmp=False).replace(
            b"trailer", b"20 0 obj\n<< /Type /Metadata /Subtype /XML /Length %d >>\nstream\n" % len(packet)
            + packet + b"\nendstream\nendobj\ntrailer", 1)
        new, removed = meta.strip_pdf(data, {"xmp"})
        self.assertEqual(len(new), len(data))
        self.assertNotIn(b"Ana", new)
        self.assertIn(b'<?xpacket end="w"?>', new)

    def test_xmp_inside_an_image_stream_is_not_touched(self):
        packet = b'<?xpacket begin="x"?><a>Ana Perez</a><?xpacket end="w"?>'
        img = (b"20 0 obj\n<< /Type /XObject /Subtype /Image /Filter /DCTDecode /Length %d >>\nstream\n" % len(packet)
               + packet + b"\nendstream\nendobj\n")
        data = fx.build_pdf_real(xmp=False).replace(b"trailer", img + b"trailer", 1)
        ins = meta.inspect_pdf(data)
        self.assertNotIn("xmp", ins["blocks"])
        new, _ = meta.strip_pdf(data, {"info", "xmp"})
        self.assertIn(packet, new)

    def test_pdf_without_metadata_says_nothing_to_remove(self):
        data = fx.build_pdf_real(info=b"<< /Trapped /False >>", xmp=False)
        src, rc, out, err = self.strip_file(data)
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to remove", out)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])

    def test_strip_is_idempotent(self):
        once = self.stripped(fx.build_pdf_real())
        self.assertEqual(meta.inspect_pdf(once)["blocks"], {})

    def test_report_states_limits(self):
        src, rc, out, err = self.strip_file(fx.build_pdf_real())
        self.assertIn("page content, embedded images, fonts and objects inside compressed object streams "
                      "are not changed or checked", out)
        text = meta.format_inspection(meta.inspect_pdf(fx.build_pdf_real()), "a.pdf")
        self.assertIn("Removal works for the Info dictionary", text)
        self.assertNotIn("not supported", text)
        self.assertIn("Removable blocks: info, xmp", text)

    def test_strip_supported_true_for_pdf(self):
        self.assertTrue(meta.strip_supported(meta.inspect_pdf(fx.build_pdf_real())))

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_pdftotext_gives_same_text(self):
        data = fx.build_pdf_real(revisions=2)
        new = self.stripped(data)
        a = self.write("before.pdf", data)
        b = self.write("after.pdf", new)
        ta = subprocess.run(["pdftotext", a, "-"], capture_output=True).stdout
        tb = subprocess.run(["pdftotext", b, "-"], capture_output=True).stdout
        self.assertIn(b"Hello PDF world", ta)
        self.assertEqual(ta, tb)


if __name__ == "__main__":
    unittest.main()
