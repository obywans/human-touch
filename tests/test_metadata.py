#!/usr/bin/env python3
"""Tests for the Metadata Inspector (skills/human/scripts/metadata_inspect.py).

Usage: python3 tests/test_metadata.py

Covers EXIF/XMP/IPTC/comment reading in JPEG, PNG text/EXIF chunks, Office
document properties, PDF info and signatures, HTML meta; the consent gate
(dry run by default, nothing written without --confirm); preservation of C2PA
and signatures (refusal, no removal even when overridden); preservation of
image data, colour profile and orientation; and honest reporting of what was
not checked.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "human", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import metadata_inspect  # noqa: E402
import _meta_lib as meta  # noqa: E402
import _fixtures as fx  # noqa: E402


class Base(unittest.TestCase):
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

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = metadata_inspect.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def inspect(self, name, data):
        return meta.detect_and_inspect(name, data)

    @staticmethod
    def values(ins):
        return {i["key"]: i["value"] for i in ins["items"]}


class TestJpeg(Base):
    def test_exif_xmp_comment_found_and_explained(self):
        ins = self.inspect("a.jpg", fx.build_jpeg(iptc=True))
        v = self.values(ins)
        self.assertEqual(v["Make"], "Acme")
        self.assertEqual(v["Model"], "PhoneX 12")
        self.assertEqual(v["Artist"], "Ana Pérez")
        self.assertEqual(v["BodySerialNumber"], "SN-12345")
        self.assertEqual(v["GPS position"], "36.500000, -4.950000")
        self.assertEqual(v["dc:creator"], "Ana Pérez")
        self.assertEqual(v["Comment"], "made by Ana at home")
        self.assertEqual(v["By-line (photographer)"], "Ana Pere")
        loc = next(i for i in ins["items"] if i["key"] == "GPS position")
        self.assertTrue(loc["personal"])
        self.assertIn("photo was taken", loc["explanation"])
        self.assertFalse(next(i for i in ins["items"] if i["key"] == "Software")["personal"])

    def test_report_states_what_was_not_checked(self):
        text = meta.format_inspection(self.inspect("a.jpg", fx.build_jpeg()), "a.jpg")
        self.assertIn("NOT checked", text)
        self.assertIn("signature validity", text)

    def test_clean_jpeg_reports_no_fields_but_not_an_absence_guarantee(self):
        ins = self.inspect("a.jpg", fx.build_jpeg(exif=False, xmp=False, comment=False))
        self.assertEqual(ins["items"], [])
        text = meta.format_inspection(ins)
        self.assertIn("in the regions that were checked", text)
        self.assertNotIn("no metadata at all", text.lower())

    def test_dry_run_writes_nothing(self):
        src = self.write("a.jpg", fx.build_jpeg())
        rc, out, _ = self.cli("strip", src)
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertEqual(os.listdir(self.tmp.name), ["a.jpg"])

    def test_strip_with_consent_keeps_pixels_icc_and_orientation(self):
        original = fx.build_jpeg(orientation=6)
        src = self.write("a.jpg", original)
        rc, out, _ = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read(src), original)  # original untouched
        new = self.read(os.path.join(self.tmp.name, "a.nometa.jpg"))
        ins = self.inspect("n.jpg", new)
        v = self.values(ins)
        for gone in ("Make", "Artist", "BodySerialNumber", "GPS position", "dc:creator", "Comment"):
            self.assertNotIn(gone, v)
        self.assertTrue(new.endswith(fx.SCAN))  # image data identical
        self.assertIn(fx.ICC, new)  # colour profile kept
        segs = meta.jpeg_segments(new)
        exif = next(s for s in segs if s["payload"].startswith(b"Exif\0\0"))
        _, orientation, _ = meta.parse_exif(exif["payload"][6:])
        self.assertEqual(orientation, 6)  # still displays upright
        self.assertIn("Re-inspection", out)

    def test_only_selects_blocks(self):
        src = self.write("a.jpg", fx.build_jpeg())
        rc, out, _ = self.cli("strip", src, "--only", "comment", "--confirm")
        self.assertEqual(rc, 0)
        v = self.values(self.inspect("n", self.read(os.path.join(self.tmp.name, "a.nometa.jpg"))))
        self.assertNotIn("Comment", v)
        self.assertIn("Make", v)

    def test_unknown_block_rejected(self):
        src = self.write("a.jpg", fx.build_jpeg(iptc=False))
        rc, _, err = self.cli("strip", src, "--only", "iptc", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("not present", err)

    def test_c2pa_detected_and_strip_refused(self):
        src = self.write("c.jpg", fx.build_jpeg(c2pa=True))
        ins = self.inspect("c.jpg", self.read(src))
        self.assertIs(ins["provenance"]["c2pa"], True)
        self.assertIn("NOT validated", meta.format_inspection(ins))
        rc, _, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED", err)
        self.assertEqual(os.listdir(self.tmp.name), ["c.jpg"])

    def test_break_provenance_still_never_removes_c2pa(self):
        src = self.write("c.jpg", fx.build_jpeg(c2pa=True))
        rc, out, _ = self.cli("strip", src, "--confirm", "--break-provenance")
        self.assertEqual(rc, 0, out)
        self.assertIn("no longer validate", out)
        new = self.read(os.path.join(self.tmp.name, "c.nometa.jpg"))
        self.assertIs(self.inspect("n.jpg", new)["provenance"]["c2pa"], True)
        self.assertNotIn("Make", self.values(self.inspect("n.jpg", new)))

    def test_truncated_and_garbage_jpeg_fail_cleanly(self):
        good = fx.build_jpeg()
        for bad in (good[:30], b"\xff\xd8garbage-without-markers"):
            src = self.write("t.jpg", bad)
            rc, _, err = self.cli("inspect", src)
            self.assertEqual(rc, 1, bad[:6])
            self.assertTrue(err.startswith("error:"))


class TestPng(Base):
    def test_text_exif_time_found(self):
        v = self.values(self.inspect("a.png", fx.build_png()))
        self.assertEqual(v["Author"], "Ana Perez")
        self.assertEqual(v["Comment"], "hola desde casa")
        self.assertEqual(v["LastModified"], "2026-01-02 03:04:05")
        self.assertEqual(v["GPS position"], "36.500000, -4.950000")

    def test_strip_removes_blocks_keeps_image_chunks(self):
        src = self.write("a.png", fx.build_png())
        rc, out, _ = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0, out)
        new = self.read(os.path.join(self.tmp.name, "a.nometa.png"))
        types = [c["type"] for c in meta.png_chunks(new)]
        self.assertEqual(types, [b"IHDR", b"IDAT", b"IEND"])
        self.assertEqual(self.inspect("n.png", new)["items"], [])

    def test_png_c2pa_refused(self):
        src = self.write("c.png", fx.build_png(c2pa=True))
        rc, _, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertIn("C2PA", err)


class TestOffice(Base):
    def test_properties_and_tracked_change_authors_found(self):
        ins = self.inspect("d.docx", fx.build_docx())
        v = self.values(ins)
        self.assertEqual(v["creator"], "Ana Pérez")
        self.assertEqual(v["lastModifiedBy"], "Luis Gómez")
        self.assertEqual(v["Company"], "Acme SL")
        self.assertEqual(v["Reviewer/author names"], "Luis Gómez")
        self.assertTrue(any("embedded media" in n for n in ins["notes"]))
        self.assertIn("metadata of images embedded", " ".join(ins["not_checked"]))

    def test_strip_clears_people_and_org_rest_identical(self):
        data = fx.build_docx()
        src = self.write("d.docx", data)
        rc, out, _ = self.cli("strip", src, "--only", "people,organization", "--confirm")
        self.assertEqual(rc, 0, out)
        new_path = os.path.join(self.tmp.name, "d.nometa.docx")
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(new_path) as b:
            self.assertEqual(a.namelist(), b.namelist())
            for n in a.namelist():
                if n not in ("docProps/core.xml", "docProps/app.xml"):
                    self.assertEqual(a.read(n), b.read(n), n)
            core = b.read("docProps/core.xml").decode()
        self.assertIn("<dc:creator></dc:creator>", core)
        self.assertIn("<dc:title>Informe</dc:title>", core)  # descriptive block was not requested
        v = self.values(self.inspect("n.docx", self.read(new_path)))
        self.assertNotIn("creator", v)
        self.assertNotIn("Company", v)
        self.assertEqual(v["Application"], "Word")
        self.assertIn("Reviewer/author names", v)  # reported as not handled, not silently ignored

    def test_signed_docx_strip_refused(self):
        src = self.write("s.docx", fx.build_docx(signed=True))
        ins = self.inspect("s.docx", self.read(src))
        self.assertTrue(ins["provenance"]["signatures"])
        rc, _, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertIn("digital signature", err)

    def test_xlsx_extension_uses_same_parser(self):
        ins = self.inspect("t.xlsx", fx.build_docx())
        self.assertTrue(ins["format"].startswith("OOXML"))

    def test_not_a_zip(self):
        src = self.write("x.docx", b"hello")
        rc, _, err = self.cli("inspect", src)
        self.assertEqual(rc, 0)  # unknown content: reported as unsupported, with its limits
        self.assertIn("NOT", self.cli("inspect", src)[1] + err)


class TestPdfHtmlOthers(Base):
    def test_pdf_info_and_signature(self):
        ins = self.inspect("a.pdf", fx.build_pdf(signed=True))
        v = self.values(ins)
        self.assertEqual(v["Author"], "Ana Pérez")
        self.assertEqual(v["Producer"], "TestGen 1")
        self.assertTrue(ins["provenance"]["signatures"])
        self.assertIn("compressed object streams", " ".join(ins["not_checked"]))

    def test_pdf_strip_not_supported_writes_nothing(self):
        src = self.write("a.pdf", fx.build_pdf())
        rc, _, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertIn("not supported", err)
        self.assertEqual(os.listdir(self.tmp.name), ["a.pdf"])

    def test_pdf_with_unreadable_info_says_so(self):
        data = fx.build_pdf().replace(b"/Info 6 0 R", b"/Info 99 0 R")
        ins = self.inspect("a.pdf", data)
        self.assertEqual(ins["items"], [])
        self.assertTrue(any("compressed object stream" in n for n in ins["notes"]))

    def test_html_meta(self):
        html = '<meta name="author" content="Ana"><meta name="generator" content="Hugo"><!-- note -->'
        ins = self.inspect("p.html", html.encode())
        self.assertEqual(self.values(ins), {"author": "Ana", "generator": "Hugo"})
        self.assertTrue(any("HTML comment" in n for n in ins["notes"]))

    def test_plain_text_has_no_fields_and_says_what_it_did_not_check(self):
        ins = self.inspect("a.txt", b"hola")
        self.assertEqual(ins["items"], [])
        self.assertIn("file-system metadata", " ".join(ins["not_checked"]))

    def test_unknown_format_is_not_claimed_clean(self):
        ins = self.inspect("v.mp4", b"\x00\x00\x00\x18ftypmp42" + b"c2pa" + b"\x00" * 20)
        self.assertEqual(ins["items"], [])
        self.assertIn("were NOT read", " ".join(ins["not_checked"]))
        self.assertEqual(ins["provenance"]["c2pa"], "possible (heuristic)")
        self.assertIn("does not prove", " ".join(ins["notes"]))

    def test_every_format_declares_a_coverage_statement(self):
        samples = {"a.jpg": fx.build_jpeg(), "a.png": fx.build_png(), "a.docx": fx.build_docx(),
                   "a.pdf": fx.build_pdf(), "a.html": b"<p>x</p>", "a.txt": b"x", "a.bin": b"zzzz"}
        for name, data in samples.items():
            ins = self.inspect(name, data)
            self.assertTrue(ins["checked"] and ins["not_checked"], name)

    def test_json_output(self):
        src = self.write("a.jpg", fx.build_jpeg())
        rc, out, _ = self.cli("inspect", src, "--json")
        self.assertEqual(rc, 0)
        self.assertIn('"GPS position"', out)

    def test_existing_output_not_overwritten(self):
        src = self.write("a.jpg", fx.build_jpeg())
        existing = self.write("o.jpg", b"keep me")
        rc, _, err = self.cli("strip", src, "--confirm", "--output", existing)
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(existing), b"keep me")
        self.assertIn("already exists", err)


if __name__ == "__main__":
    unittest.main()
