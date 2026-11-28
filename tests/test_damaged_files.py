#!/usr/bin/env python3
"""Damaged and hostile files must end in a clear error, never in a Python traceback.

Found by cutting and corrupting the fixtures of tests/_fixtures.py: a PNG cut right after its
signature, and ZIP-based files (DOCX, EPUB) with a bad compressed stream, a bad header or an
unsupported compression method.
"""
from __future__ import annotations

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

import _fixtures as F  # noqa: E402
import _meta_lib as meta  # noqa: E402
import file_clean  # noqa: E402
import metadata_inspect  # noqa: E402

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def corrupt_stream(data: bytes) -> bytes:
    """Flip bytes in the middle of the first compressed member of a ZIP."""
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
        info = [i for i in z.infolist() if i.compress_type == zipfile.ZIP_DEFLATED][0]
    start = info.header_offset + 30 + len(info.filename.encode()) + 4
    b = bytearray(data)
    for i in range(start, min(start + 12, len(b))):
        b[i] ^= 0xFF
    return bytes(b)


def set_compression(data: bytes, method: int) -> bytes:
    """Declare an unsupported compression method in every local header and every central directory entry
    (zipfile reads the method from the central directory)."""
    b = bytearray(data)
    for sig, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        i = 0
        while True:
            i = b.find(sig, i)
            if i < 0:
                break
            struct.pack_into("<H", b, i + offset, method)
            i += 4
    return bytes(b)


class TestDamagedFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ht-test-damaged-")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)

    def write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def run_main(self, main, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue() + err.getvalue()

    def test_png_with_only_a_signature_can_be_stripped_without_a_crash(self):
        ins = meta.detect_and_inspect("a.png", PNG_SIG)
        out, removed = meta.strip("a.png", PNG_SIG, ins, set())
        self.assertEqual(out, PNG_SIG)
        self.assertEqual(removed, [])

    def test_damaged_zip_files_raise_value_error_only(self):
        for name, good in (("a.docx", F.build_docx()), ("a.epub", F.build_epub())):
            for label, bad in (("stream", corrupt_stream(good)), ("method", set_compression(good, 99)),
                               ("cut", good[: len(good) // 2])):
                with self.subTest(file=name, damage=label):
                    # A damaged file must be refused with ValueError: it must not parse as if it were fine.
                    with self.assertRaises(ValueError):
                        ins = meta.detect_and_inspect(name, bad)
                        self.assertTrue(meta.strip_supported(ins))
                        meta.strip(name, bad, ins, {b for b in ins["blocks"] if ins["blocks"][b]})

    def test_cli_tools_report_damaged_files_with_exit_code_1(self):
        for name, good in (("a.docx", F.build_docx()), ("a.epub", F.build_epub())):
            p = self.write(name, corrupt_stream(good))
            for main, argv in ((metadata_inspect.main, ["inspect", p]), (file_clean.main, [p, "--scan"])):
                with self.subTest(file=name, tool=main.__module__):
                    if main is file_clean.main and name.endswith(".epub"):
                        continue  # file_clean does not read EPUB: exit code 2 (unsupported), covered elsewhere
                    rc, text = self.run_main(main, argv)
                    self.assertEqual(rc, 1, text)
                    self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
