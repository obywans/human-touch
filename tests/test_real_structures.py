#!/usr/bin/env python3
"""Tests of metadata removal on real file structures: JPEG, PNG, DOCX and exit codes.

Usage: python3 tests/test_real_structures.py

The files are built in memory by tests/_fixtures.py. Each test runs the command
line of metadata_inspect.py, reads the new file and compares its bytes.
"""
import contextlib
import io
import os
import struct
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

    def strip(self, name, data, *extra):
        src = self.write(name, data)
        rc, out, err = self.cli("strip", src, "--confirm", *extra)
        self.assertEqual(rc, 0, err)
        base, ext = os.path.splitext(name)
        return self.read(os.path.join(self.tmp.name, base + ".nometa" + ext))


class TestJpegRealStructure(Base):
    def test_every_block_removed_and_scan_data_identical(self):
        data = fx.build_jpeg(iptc=True)
        before = meta.inspect_jpeg(data)
        keys = {i["key"] for i in before["items"]}
        for k in ("GPS position", "Make", "Model", "BodySerialNumber", "dc:creator", "Comment"):
            self.assertIn(k, keys)
        new = self.strip("a.jpg", data)
        after = meta.inspect_jpeg(new)
        self.assertEqual(after["items"], [])
        self.assertTrue(new.endswith(fx.SCAN))
        self.assertEqual(new[-len(fx.SCAN):], data[-len(fx.SCAN):])
        for secret in (b"SN-12345", b"Acme", b"PhoneX", b"made by Ana", b"Ana P", b"Ana Pere"):
            self.assertNotIn(secret, new)
        self.assertIn(fx.ICC, new)

    def test_each_block_alone(self):
        data = fx.build_jpeg(iptc=True)
        for block, secret in (("exif", b"SN-12345"), ("xmp", b"EditorPro 3</xmp"), ("iptc", b"Ana Pere"),
                              ("comment", b"made by Ana")):
            new = self.strip(block + ".jpg", data, "--only", block)
            self.assertNotIn(secret, new, block)
            self.assertTrue(new.endswith(fx.SCAN), block)
            self.assertLess(len(new), len(data), block)


class TestPngRealStructure(Base):
    def chunks(self, data):
        pos, out = 8, []
        while pos < len(data):
            n = struct.unpack(">I", data[pos:pos + 4])[0]
            out.append((data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]))
            pos += 12 + n
        return out

    def test_text_exif_time_removed_and_image_chunks_identical(self):
        data = fx.build_png()
        kinds = [c[0] for c in self.chunks(data)]
        for k in (b"tEXt", b"iTXt", b"eXIf", b"tIME"):
            self.assertIn(k, kinds)
        new = self.strip("a.png", data)
        after = self.chunks(new)
        self.assertEqual([c[0] for c in after], [b"IHDR", b"IDAT", b"IEND"])
        before = dict(self.chunks(data))
        self.assertEqual(dict(after)[b"IDAT"], before[b"IDAT"])
        self.assertEqual(dict(after)[b"IHDR"], before[b"IHDR"])
        self.assertEqual(meta.inspect_png(new)["items"], [])

    def test_png_checksums_stay_valid(self):
        import zlib
        new = self.strip("a.png", fx.build_png())
        pos = 8
        while pos < len(new):
            n = struct.unpack(">I", new[pos:pos + 4])[0]
            body = new[pos + 4:pos + 8 + n]
            self.assertEqual(struct.unpack(">I", new[pos + 8 + n:pos + 12 + n])[0], zlib.crc32(body) & 0xFFFFFFFF)
            pos += 12 + n


class TestDocxRealStructure(Base):
    def docx_with_comments(self):
        base = zipfile.ZipFile(io.BytesIO(fx.build_docx()))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in base.namelist():
                z.writestr(n, base.read(n))
            z.writestr("word/comments.xml", '<w:comments xmlns:w="w"><w:comment w:author="Luis Gómez">'
                       "<w:p><w:r><w:t>check this</w:t></w:r></w:p></w:comment></w:comments>")
        return buf.getvalue()

    def test_core_and_app_fields_removed_comment_part_stays(self):
        data = self.docx_with_comments()
        new = self.strip("a.docx", data)
        zin, zout = zipfile.ZipFile(io.BytesIO(data)), zipfile.ZipFile(io.BytesIO(new))
        self.assertEqual(zin.namelist(), zout.namelist())
        core, app = zout.read("docProps/core.xml").decode(), zout.read("docProps/app.xml").decode()
        for secret in ("Ana Pérez", "Luis Gómez", "Informe"):
            self.assertNotIn(secret, core)
        self.assertNotIn("Acme SL", app)
        self.assertIn("Word", app)
        self.assertIn("check this", zout.read("word/comments.xml").decode())
        self.assertIn("Luis Gómez", zout.read("word/comments.xml").decode())
        for n in ("word/document.xml", "word/media/image1.png", "[Content_Types].xml"):
            self.assertEqual(zin.read(n), zout.read(n), n)
        self.assertEqual(meta.inspect_ooxml(new, "OOXML (docx)")["blocks"].get("people", 0), 0)


class TestExitCodes(Base):
    def test_exit_0_on_success_and_on_dry_run(self):
        src = self.write("a.jpg", fx.build_jpeg())
        self.assertEqual(self.cli("inspect", src)[0], 0)
        self.assertEqual(self.cli("strip", src)[0], 0)
        self.assertEqual(self.cli("strip", src, "--confirm")[0], 0)

    def test_exit_1_on_error(self):
        self.assertEqual(self.cli("inspect", os.path.join(self.tmp.name, "missing.jpg"))[0], 1)
        src = self.write("a.jpg", fx.build_jpeg())
        self.assertEqual(self.cli("strip", src, "--only", "nonsense", "--confirm")[0], 1)

    def test_exit_2_on_refusal(self):
        src = self.write("a.jpg", fx.build_jpeg(c2pa=True))
        rc, _, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertEqual(os.listdir(self.tmp.name), ["a.jpg"])
        html = self.write("a.html", b"<p>x</p>")
        self.assertEqual(self.cli("strip", html, "--confirm")[0], 2)
        pdf = self.write("e.pdf", fx.build_pdf_real(encrypt=True))
        self.assertEqual(self.cli("strip", pdf, "--confirm")[0], 2)


if __name__ == "__main__":
    unittest.main()
