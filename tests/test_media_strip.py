#!/usr/bin/env python3
"""Tests for metadata inspection and removal in EPUB, HTML, MP3 and MP4/M4A files (version 3.1.0).

Usage: python3 tests/test_media_strip.py

Every sample file is built in memory by tests/_fixtures.py. Nothing here uses the network.
"""
import contextlib
import io
import json
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
            f.write(data)
        return p

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def listing(self):
        return sorted(os.listdir(self.tmp.name))

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = metadata_inspect.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def inspect(self, name, data):
        return meta.detect_and_inspect(name, data)

    def strip(self, name, data, *extra):
        """Run strip --confirm on a copy of `data`. Return (rc, out, err, new_bytes_or_None)."""
        src = self.write(name, data)
        rc, out, err = self.cli("strip", src, "--confirm", *extra)
        base, ext = os.path.splitext(src)
        new = base + ".nometa" + ext
        return rc, out, err, (self.read(new) if os.path.exists(new) else None)

    def values(self, ins):
        return {i["key"]: i["value"] for i in ins["items"]}


# --- EPUB -------------------------------------------------------------------------------------------

class EpubTests(Base):
    def test_inspect_lists_the_opf_fields_and_ignores_comments(self):
        ins = self.inspect("a.epub", fx.build_epub())
        v = self.values(ins)
        self.assertEqual(ins["format"], "EPUB")
        self.assertEqual(v["dc:creator"], "Ana Pérez")
        self.assertIn("calibre", v["dc:contributor"])
        self.assertEqual(v["dc:publisher"], "Editorial Acme SL")
        self.assertEqual(v["dc:rights"], "Copyright Ana Pérez 2026")
        self.assertIn("libro.docx", v["dc:source"])
        self.assertEqual(v["meta dcterms:modified"], "2026-01-03T00:00:00Z")
        self.assertEqual(v["meta generator"], "Sigil 1.9")
        self.assertIn("meta calibre:title_sort", v)
        self.assertNotIn("Not live", json.dumps(ins))
        self.assertEqual(ins["blocks"], {"creator": 3, "publisher": 1, "rights": 1, "software": 2, "dates": 2})
        self.assertTrue(ins["not_checked"])

    def test_epub_is_found_without_the_extension(self):
        self.assertEqual(self.inspect("book.bin", fx.build_epub())["format"], "EPUB")

    def test_strip_removes_names_and_keeps_title_language_identifier(self):
        rc, out, err, new = self.strip("a.epub", fx.build_epub())
        self.assertEqual(rc, 0, err)
        opf = zipfile.ZipFile(io.BytesIO(new)).read("OEBPS/content.opf").decode("utf-8")
        for gone in ("Ana Pérez", "Editorial Acme", "Copyright", "Sigil", "calibre", "file-as", "dcterms:modified",
                     "2026-01-02T03"):
            self.assertNotIn(gone, opf)
        for kept in ("<dc:title>Informe de prueba</dc:title>", "<dc:language>es</dc:language>",
                     "urn:uuid:12345678-1234-1234-1234-123456789abc", '<meta name="cover" content="cover-image"/>',
                     "dc:source"):
            self.assertIn(kept, opf)
        self.assertIn("Kept: dc:title, dc:language and dc:identifier", out)
        self.assertIn("Removed:", out)

    def test_zip_layout_mimetype_first_stored_and_parts_identical(self):
        for stored in (True, False):
            src = fx.build_epub(mimetype_stored=stored)
            rc, _o, err, new = self.strip(f"s{stored}.epub", src)
            self.assertEqual(rc, 0, err)
            zin, zout = zipfile.ZipFile(io.BytesIO(src)), zipfile.ZipFile(io.BytesIO(new))
            self.assertIsNone(zout.testzip())
            first = zout.infolist()[0]
            self.assertEqual((first.filename, first.compress_type), ("mimetype", zipfile.ZIP_STORED))
            self.assertEqual(zout.read("mimetype"), b"application/epub+zip")
            self.assertEqual(zin.namelist(), zout.namelist())
            for n in zin.namelist():
                if n != "OEBPS/content.opf":
                    self.assertEqual(zin.read(n), zout.read(n), n)
            self.assertNotEqual(zin.read("OEBPS/content.opf"), zout.read("OEBPS/content.opf"))

    def test_only_one_block(self):
        rc, _o, err, new = self.strip("a.epub", fx.build_epub(), "--only", "publisher")
        self.assertEqual(rc, 0, err)
        opf = zipfile.ZipFile(io.BytesIO(new)).read("OEBPS/content.opf").decode("utf-8")
        self.assertNotIn("Editorial Acme", opf)
        self.assertIn("Ana Pérez", opf)

    def test_refinement_of_a_removed_creator_goes_with_it_but_other_meta_stays(self):
        opf = fx.OPF.replace('<meta name="cover"', '<meta refines="#bookid" property="identifier-type">uuid</meta>\n    <meta name="cover"')
        _rc, _o, _e, new = self.strip("a.epub", fx.build_epub(opf=opf), "--only", "creator")
        out = zipfile.ZipFile(io.BytesIO(new)).read("OEBPS/content.opf").decode("utf-8")
        self.assertNotIn("Pérez, Ana", out)
        self.assertIn("identifier-type", out)

    def test_dry_run_writes_nothing_and_original_is_unchanged(self):
        data = fx.build_epub()
        src = self.write("a.epub", data)
        rc, out, _e = self.cli("strip", src)
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertEqual(self.listing(), ["a.epub"])
        self.cli("strip", src, "--confirm")
        self.assertEqual(self.read(src), data)

    def test_existing_output_is_never_overwritten(self):
        src = self.write("a.epub", fx.build_epub())
        keep = self.write("o.epub", b"keep me")
        rc, _o, err = self.cli("strip", src, "--confirm", "--output", keep)
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.read(keep), b"keep me")

    def test_second_strip_has_nothing_to_remove(self):
        _rc, _o, _e, new = self.strip("a.epub", fx.build_epub())
        src = self.write("b.epub", new)
        rc, out, _e = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to remove", out)
        self.assertEqual(self.listing(), ["a.epub", "a.nometa.epub", "b.epub"])

    def test_damaged_and_unsafe_files_are_refused_with_a_message(self):
        bad = {
            "notzip.epub": b"this is not a zip file",
            "nocontainer.epub": fx.build_epub().replace(b"META-INF/container.xml", b"META-INF/containex.xml"),
            "badmime.epub": fx.build_epub().replace(b"application/epub+zip", b"application/x-nothing!!"),
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("mimetype", b"application/epub+zip")
            z.writestr("../evil.txt", b"x")
        bad["unsafe.epub"] = buf.getvalue()
        for name, data in bad.items():
            src = self.write(name, data)
            rc, _o, err = self.cli("strip", src, "--confirm")
            self.assertIn(rc, (1, 2), name)
            self.assertTrue(err.strip(), name)
        self.assertEqual(len(self.listing()), len(bad))  # nothing was written

    def test_encrypted_zip_entry_is_refused(self):
        data = bytearray(fx.build_epub())
        # set the "encrypted" bit in the central directory entry of OEBPS/ch1.xhtml
        i = data.index(b"PK\x01\x02", data.index(b"OEBPS/ch1.xhtml") - 100)
        while bytes(data[i + 46:i + 46 + 15]) != b"OEBPS/ch1.xhtml":
            i = data.index(b"PK\x01\x02", i + 4)
        data[i + 8] |= 1
        src = self.write("enc.epub", bytes(data))
        rc, _o, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("encrypted", err)

    def test_oversize_archive_is_refused(self):
        old = meta.MAX_ZIP_TOTAL
        meta.MAX_ZIP_TOTAL = 100
        self.addCleanup(setattr, meta, "MAX_ZIP_TOTAL", old)
        src = self.write("a.epub", fx.build_epub())
        rc, _o, err = self.cli("inspect", src)
        self.assertEqual(rc, 1)
        self.assertIn("unreasonable size", err)

    def test_signature_part_needs_break_provenance(self):
        data = fx.build_epub(signed=True)
        src = self.write("a.epub", data)
        rc, _o, err = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 2)
        self.assertEqual(self.listing(), ["a.epub"])
        rc, _o, _e = self.cli("strip", src, "--confirm", "--break-provenance")
        self.assertEqual(rc, 0)


# --- HTML -------------------------------------------------------------------------------------------

class HtmlTests(Base):
    REMOVED = [b'<meta name="author" content="Ana P\xc3\xa9rez">', b'<meta name="generator" content="Hugo 0.120">',
               b'<meta property="og:site_name" content="Blog de Ana">',
               b'<meta property="article:author" content="https://example.com/ana">',
               b'<meta name="copyright" content="Ana P\xc3\xa9rez">']

    def test_inspect_counts_blocks_and_ignores_comment_script_style(self):
        ins = self.inspect("a.html", fx.HTML_PAGE)
        self.assertEqual(ins["blocks"], {"meta-identity": 3, "meta-software": 1, "meta-social": 1})
        self.assertNotIn("in comment", json.dumps(ins))
        self.assertTrue(ins["not_checked"])

    def test_strip_removes_the_chosen_tags_and_keeps_every_other_byte(self):
        rc, out, err, new = self.strip("a.html", fx.HTML_PAGE)
        self.assertEqual(rc, 0, err)
        expected = fx.HTML_PAGE
        for tag in self.REMOVED:
            self.assertEqual(expected.count(tag), 1)
            expected = expected.replace(tag, b"")
        self.assertEqual(new, expected)
        self.assertIn(b"\r\n", new)
        self.assertTrue(new.endswith(b"\xe9"))  # a byte that is not valid UTF-8 is kept
        for kept in (b'<meta charset="utf-8">', b"og:title", b'name="description"', b"in comment", b"in script", b"in style"):
            self.assertIn(kept, new)
        self.assertEqual(self.read(os.path.join(self.tmp.name, "a.html")), fx.HTML_PAGE)

    def test_only_one_block(self):
        rc, _o, _e, new = self.strip("a.html", fx.HTML_PAGE, "--only", "meta-software")
        self.assertEqual(rc, 0)
        self.assertEqual(new, fx.HTML_PAGE.replace(self.REMOVED[1], b""))

    def test_dry_run_and_existing_output(self):
        src = self.write("a.html", fx.HTML_PAGE)
        rc, out, _e = self.cli("strip", src)
        self.assertEqual((rc, self.listing()), (0, ["a.html"]))
        self.assertIn("DRY RUN", out)
        keep = self.write("o.html", b"keep")
        self.assertEqual(self.cli("strip", src, "--confirm", "--output", keep)[0], 1)
        self.assertEqual(self.read(keep), b"keep")

    def test_page_without_these_tags_has_nothing_to_remove(self):
        src = self.write("a.html", b'<meta charset="utf-8"><p>x</p>')
        rc, out, _e = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to remove", out)
        self.assertEqual(self.listing(), ["a.html"])

    def test_utf16_page_is_refused(self):
        src = self.write("a.html", '<meta name="author" content="Ana">'.encode("utf-16"))
        rc, _o, err = self.cli("strip", src, "--confirm")
        self.assertIn(rc, (1, 2))
        self.assertEqual(self.listing(), ["a.html"])

    def test_person_names_in_open_graph_are_social_block(self):
        page = (b'<meta property="og:book:author" content="Ana">\n<meta property="og:profile:first_name" content="Ana">\n'
                b'<meta property="og:title" content="T">\n')
        _rc, _o, _e, new = self.strip("p.html", page)
        self.assertEqual(new, b'\n\n<meta property="og:title" content="T">\n')


# --- MP3 --------------------------------------------------------------------------------------------

class Mp3Tests(Base):
    def test_inspect_reads_v2_frames_and_v1(self):
        ins = self.inspect("a.mp3", fx.build_mp3())
        v = self.values(ins)
        self.assertEqual(ins["format"], "MP3")
        self.assertEqual(v["TPE1 Artist"], "Ana Pérez ÿ")
        self.assertEqual(v["TALB Album"], "Disco")
        self.assertEqual(v["TIT2 Title"], "Cancion")
        self.assertEqual(v["TSSE Encoding software"], "LAME 3.100")
        self.assertEqual(v["TENC Encoded by"], "Ana")
        self.assertEqual(v["COMM Comment"], "hecho en casa")
        self.assertEqual(v["TXXX owner"], "Ana Perez")
        self.assertIn("present", v["APIC Picture"])
        self.assertEqual(v["artist"], "Ana Perez")
        self.assertEqual(ins["blocks"], {"id3v2": 1, "id3v1": 1})
        self.assertIn("APEv2", " ".join(ins["not_checked"]))

    def test_strip_keeps_the_audio_frames_byte_identical(self):
        cases = {"v22": dict(version=2), "v23": dict(version=3), "v24": dict(version=4),
                 "v23-unsync": dict(version=3, unsync=True), "v24-unsync": dict(version=4, unsync=True),
                 "v24-footer": dict(version=4, footer=True), "v24-footer-unsync": dict(version=4, footer=True, unsync=True),
                 "no-padding": dict(version=3, padding=0)}
        for label, kw in cases.items():
            with self.subTest(label):
                data = fx.build_mp3(**kw)
                rc, out, err, new = self.strip(label + ".mp3", data)
                self.assertEqual(rc, 0, err)
                self.assertEqual(new, fx.AUDIO)
                self.assertIn("id3v2", out)
                self.assertIn("id3v1", out)

    def test_unsynchronised_tag_is_read_correctly(self):
        for kw in (dict(version=3, unsync=True), dict(version=4, footer=True)):
            self.assertEqual(self.values(self.inspect("a.mp3", fx.build_mp3(**kw)))["TPE1 Artist"], "Ana Pérez ÿ")

    def test_only_one_tag(self):
        data = fx.build_mp3()
        _rc, _o, _e, only_v1 = self.strip("a.mp3", data, "--only", "id3v1")
        self.assertEqual(only_v1, data[:-128])
        _rc, _o, _e, only_v2 = self.strip("b.mp3", data, "--only", "id3v2")
        self.assertEqual(only_v2, fx.AUDIO + data[-128:])

    def test_file_with_only_v1_or_no_tag(self):
        ins = self.inspect("a.mp3", fx.build_mp3(v2=False))
        self.assertEqual(ins["blocks"], {"id3v1": 1})
        src = self.write("n.mp3", fx.AUDIO)
        rc, out, _e = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to remove", out)

    def test_dry_run_and_existing_output(self):
        src = self.write("a.mp3", fx.build_mp3())
        rc, out, _e = self.cli("strip", src)
        self.assertEqual((rc, self.listing()), (0, ["a.mp3"]))
        self.assertIn("audio frames stay byte-identical", out)
        keep = self.write("o.mp3", b"keep")
        self.assertEqual(self.cli("strip", src, "--confirm", "--output", keep)[0], 1)
        self.assertEqual(self.read(keep), b"keep")

    def test_damaged_tags_are_refused_with_a_message(self):
        good = fx.build_mp3(version=4, footer=True)
        bad = {"cut.mp3": good[:30],
               "nofooter.mp3": good.replace(b"3DI", b"XXX", 1),
               "version.mp3": b"ID3\x09\x00\x00\x00\x00\x00\x10" + b"\0" * 32,
               "syncsafe.mp3": b"ID3\x03\x00\x00\xff\x7f\x7f\x7f" + b"\0" * 32}
        for name, data in bad.items():
            src = self.write(name, data)
            rc, _o, err = self.cli("strip", src, "--confirm")
            self.assertEqual(rc, 1, name)
            self.assertIn("damaged", err + "unsupported")
            self.assertTrue(err.strip())
        self.assertEqual(len(self.listing()), len(bad))

    def test_c2pa_in_the_tag_is_refused_and_never_removed(self):
        frame = fx._id3_frame(b"GEOB", b"\x00application/c2pa\x00\x00c2pa\x00jumb....", 3)
        body = frame + b"\0" * 8
        size = len(body)
        ss = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
        data = b"ID3\x03\x00\x00" + ss + body + fx.AUDIO
        src = self.write("a.mp3", data)
        self.assertEqual(self.cli("strip", src, "--confirm")[0], 2)
        self.assertEqual(self.cli("strip", src, "--confirm", "--break-provenance")[0], 2)
        self.assertEqual(self.cli("strip", src, "--confirm", "--break-provenance", "--remove-provenance")[0], 2)
        self.assertEqual(self.listing(), ["a.mp3"])


# --- MP4 / M4A ----------------------------------------------------------------------------------------

def find_atoms(data, start=0, end=None):
    out, pos, end = [], start, len(data) if end is None else end
    while pos + 8 <= end:
        size = int.from_bytes(data[pos:pos + 4], "big")
        out.append((data[pos + 4:pos + 8], pos, size))
        pos += size
    return out


def stco_value(data):
    i = data.index(b"stco")
    return int.from_bytes(data[i + 16:i + 20], "big")


class Mp4Tests(Base):
    def test_inspect_reads_ilst_and_location(self):
        ins = self.inspect("a.m4a", fx.build_mp4())
        v = self.values(ins)
        self.assertEqual(ins["format"], meta.MP4_FORMAT)
        self.assertEqual(v["©nam"], "Mi cancion")
        self.assertEqual(v["©ART"], "Ana Perez")
        self.assertEqual(v["©too"], "Lavf58.76.100")
        self.assertEqual(v["©day"], "2026-01-02")
        self.assertEqual(v["©cmt"], "grabado en casa")
        self.assertIn("+36.5000-004.9500", v["©xyz"])
        loc = [i for i in ins["items"] if i["key"] == "©xyz"]
        self.assertTrue(all(i["personal"] for i in loc))
        self.assertEqual(ins["blocks"], {"udta": 1})
        self.assertTrue(ins["not_checked"])

    def test_strip_turns_udta_into_free_and_keeps_length_and_offsets(self):
        data = fx.build_mp4()
        rc, out, err, new = self.strip("a.m4a", data)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(new), len(data))
        self.assertEqual(stco_value(new), stco_value(data))
        self.assertEqual(new.index(b"mdat"), data.index(b"mdat"))
        self.assertEqual(new[new.index(b"mdat") - 4:], data[data.index(b"mdat") - 4:])
        self.assertEqual(new[:data.index(b"moov")], data[:data.index(b"moov")])
        self.assertNotIn(b"udta", new)
        self.assertEqual(new.count(b"free"), 1)
        for name in (b"Ana Perez", b"Mi cancion", b"Lavf", b"+36.5000", b"grabado"):
            self.assertNotIn(name, new)
        i = new.index(b"free")
        moov_atoms = find_atoms(new, new.index(b"moov") - 4 + 8, new.index(b"moov") - 4 + int.from_bytes(new[new.index(b"moov") - 4:new.index(b"moov")], "big"))
        self.assertEqual([t for t, _p, _s in moov_atoms], [b"mvhd", b"trak", b"free"])
        self.assertEqual(i - 4, moov_atoms[2][1])
        for field in ("©nam", "©ART", "©too", "©day", "©cmt", "©xyz"):
            self.assertIn(field, out)
        after = self.inspect("x.m4a", new)
        self.assertEqual((after["items"], after["blocks"]), ([], {}))

    def test_strip_also_works_for_mp4_and_mov(self):
        for ext in (".mp4", ".mov", ".m4v"):
            data = fx.build_mp4(brand=b"isom")
            rc, _o, err, new = self.strip("a" + ext, data)
            self.assertEqual(rc, 0, err)
            self.assertEqual(len(new), len(data))

    def test_moov_meta_fields_are_reported_but_not_removed(self):
        data = fx.build_mp4(udta=False, moov_meta=True)
        ins = self.inspect("a.mov", data)
        v = self.values(ins)
        self.assertEqual(v["com.apple.quicktime.make"], "Apple")
        self.assertIn("+36.5000", v["com.apple.quicktime.location.ISO6709"])
        self.assertTrue(any(i["personal"] for i in ins["items"]))
        src = self.write("a.mov", data)
        rc, out, _e = self.cli("strip", src, "--confirm")
        self.assertEqual((rc, self.listing()), (0, ["a.mov"]))  # no udta: nothing to remove
        with_udta = fx.build_mp4(moov_meta=True)
        rc, out, err, new = self.strip("b.m4a", with_udta)
        self.assertEqual(rc, 0, err)
        self.assertIn(b"+36.5000-004.9500+010.000/", new)  # moov/meta is not removed
        self.assertIn("personal field(s) still found", out)

    def test_heic_photo_is_not_treated_as_a_video(self):
        data = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x00\x00\x00\x10meta\x00\x00\x00\x00Exif\x00\x00"
        ins = self.inspect("photo.heic", data)
        self.assertNotEqual(ins["format"], meta.MP4_FORMAT)
        self.assertIn("were NOT read", " ".join(ins["not_checked"]))
        self.assertEqual(self.cli("strip", self.write("photo.heic", data), "--confirm")[0], 2)

    def test_numeric_item_types_use_the_names_from_the_keys_atom(self):
        data = fx.build_mp4(udta_keys=True)
        self.assertEqual(self.values(self.inspect("a.mov", data))["artist"], "Ana Perez")
        rc, out, err, new = self.strip("k.mov", data)
        self.assertEqual(rc, 0, err)
        self.assertNotIn(b"Ana Perez", new)
        self.assertEqual(len(new), len(data))

    def test_file_without_udta_has_nothing_to_remove(self):
        src = self.write("a.mp4", fx.build_mp4(udta=False))
        rc, out, _e = self.cli("strip", src, "--confirm")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to remove", out)
        self.assertEqual(self.listing(), ["a.mp4"])

    def test_dry_run_and_existing_output(self):
        src = self.write("a.m4a", fx.build_mp4())
        rc, out, _e = self.cli("strip", src)
        self.assertEqual((rc, self.listing()), (0, ["a.m4a"]))
        self.assertIn("DRY RUN", out)
        keep = self.write("o.m4a", b"keep")
        self.assertEqual(self.cli("strip", src, "--confirm", "--output", keep)[0], 1)
        self.assertEqual(self.read(keep), b"keep")

    def test_c2pa_atom_is_detected_and_never_removed(self):
        data = fx.build_mp4(c2pa=True)
        ins = self.inspect("a.mp4", data)
        self.assertIs(ins["provenance"]["c2pa"], True)
        src = self.write("a.mp4", data)
        self.assertEqual(self.cli("strip", src, "--confirm")[0], 2)
        self.assertEqual(self.cli("strip", src, "--confirm", "--remove-provenance")[0], 2)
        self.assertEqual(self.listing(), ["a.mp4"])
        rc, out, err = self.cli("strip", src, "--confirm", "--break-provenance")
        self.assertEqual(rc, 0, err)
        new = self.read(os.path.join(self.tmp.name, "a.nometa.mp4"))
        self.assertIn(fx.C2PA_ID, new)  # the C2PA atom is still there
        self.assertEqual(len(new), len(data))

    def test_c2pa_inside_udta_is_refused(self):
        src = self.write("a.mp4", fx.build_mp4(c2pa_in_udta=True))
        self.assertEqual(self.cli("strip", src, "--confirm", "--break-provenance")[0], 2)
        self.assertEqual(self.listing(), ["a.mp4"])

    def test_damaged_files_are_refused_with_a_message(self):
        good = fx.build_mp4()
        i = good.index(b"moov") - 4
        bad = {"big.mp4": good[:i] + (10 ** 6).to_bytes(4, "big") + good[i + 4:],
               "small.mp4": good[:i] + (3).to_bytes(4, "big") + good[i + 4:],
               "cut.mp4": good[:i + 12]}
        for name, data in bad.items():
            src = self.write(name, data)
            rc, _o, err = self.cli("strip", src, "--confirm")
            self.assertEqual(rc, 1, name)
            self.assertIn("damaged", err)
        self.assertEqual(len(self.listing()), len(bad))


class McpAndExitTests(Base):
    def test_json_inspection_of_every_new_format(self):
        for name, data in (("a.epub", fx.build_epub()), ("a.html", fx.HTML_PAGE), ("a.mp3", fx.build_mp3()),
                           ("a.m4a", fx.build_mp4())):
            src = self.write(name, data)
            rc, out, _e = self.cli("inspect", src, "--json")
            self.assertEqual(rc, 0, name)
            j = json.loads(out)
            self.assertTrue(j["not_checked"], name)
            self.assertTrue(j["items"], name)

    def test_inspection_report_keeps_the_not_checked_line(self):
        for name, data in (("a.epub", fx.build_epub()), ("a.html", fx.HTML_PAGE), ("a.mp3", fx.build_mp3()),
                           ("a.m4a", fx.build_mp4())):
            rc, out, _e = self.cli("inspect", self.write(name, data))
            self.assertEqual(rc, 0)
            self.assertIn("NOT checked:", out, name)
            self.assertIn("Removable blocks:", out, name)

    def test_mcp_inspects_the_new_formats_and_stays_read_only(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_mcp  # noqa: E402
        src = self.write("a.mp3", fx.build_mp3())
        out, p = test_mcp.session([test_mcp.INIT, test_mcp.NOTIF,
                                   test_mcp.call(2, "human_metadata_inspect", {"path": src}),
                                   {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}])
        text = out[1]["result"]["content"][0]["text"]
        self.assertIn("Format: MP3", text)
        self.assertIn("NOT checked", text)
        self.assertEqual([t["name"] for t in out[2]["result"]["tools"]],
                         ["human_audit", "human_clean", "human_metadata_inspect"])
        self.assertEqual(self.read(src), fx.build_mp3())


if __name__ == "__main__":
    unittest.main()
