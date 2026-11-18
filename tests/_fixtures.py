"""Builders for the tests of the technical cleaning tools.

Every sample file is assembled in memory from a few bytes, so the repository
holds no binary fixtures. Nothing here touches the network.
"""
import io
import struct
import zipfile
import zlib


def _enc(v):
    if isinstance(v, str):
        b = v.encode() + b"\0"
        return 2, len(b), b
    if isinstance(v, int):
        return 3, 1, struct.pack("<H", v)
    if v[0] == "long":
        return 4, 1, struct.pack("<I", v[1])
    if v[0] == "rat":
        b = b"".join(struct.pack("<II", int(f * 1000000), 1000000) for f in v[1])
        return 5, len(v[1]), b
    if v[0] == "undef":
        return 7, len(v[1]), v[1]
    raise TypeError(v)


def _ifd(entries, base):
    table, data = struct.pack("<H", len(entries)), b""
    data_off = base + 2 + 12 * len(entries) + 4
    for tag, v in sorted(entries.items()):
        typ, cnt, b = _enc(v)
        if len(b) <= 4:
            table += struct.pack("<HHI", tag, typ, cnt) + b.ljust(4, b"\0")
        else:
            table += struct.pack("<HHII", tag, typ, cnt, data_off + len(data))
            data += b + (b"\0" if len(b) % 2 else b"")
    return table + struct.pack("<I", 0) + data


def build_exif(ifd0, exif=None, gps=None):
    ifd0 = dict(ifd0)
    if exif:
        ifd0[0x8769] = ("long", 0)
    if gps:
        ifd0[0x8825] = ("long", 0)
    off = 8 + len(_ifd(ifd0, 8))
    exif_b = gps_b = b""
    if exif:
        ifd0[0x8769] = ("long", off)
        exif_b = _ifd(exif, off)
        off += len(exif_b)
    if gps:
        ifd0[0x8825] = ("long", off)
        gps_b = _ifd(gps, off)
    return b"II*\0" + struct.pack("<I", 8) + _ifd(ifd0, 8) + exif_b + gps_b


SAMPLE_EXIF = dict(
    ifd0={0x010F: "Acme", 0x0110: "PhoneX 12", 0x013B: "Ana Pérez", 0x0112: 6, 0x0131: "EditorPro 3"},
    exif={0xA431: "SN-12345", 0x9003: "2026:01:02 03:04:05"},
    gps={1: "N", 2: ("rat", [36, 30, 0]), 3: "W", 4: ("rat", [4, 57, 0])},
)
SCAN = b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00" + b"\x12\x34\x56\x78" + b"\xff\xd9"
ICC = b"ICC_PROFILE\0\x01\x01" + b"FAKEPROFILE"


def seg(marker, payload):
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def build_jpeg(exif=True, xmp=True, comment=True, iptc=False, c2pa=False, orientation=6):
    parts = [b"\xff\xd8", seg(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0")]
    if exif:
        sample = dict(SAMPLE_EXIF)
        sample["ifd0"] = {**sample["ifd0"], 0x0112: orientation}
        parts.append(seg(0xE1, b"Exif\0\0" + build_exif(**sample)))
    if xmp:
        xml = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description>'
               "<dc:creator><rdf:Seq><rdf:li>Ana Pérez</rdf:li></rdf:Seq></dc:creator>"
               "<xmp:CreatorTool>EditorPro 3</xmp:CreatorTool></rdf:Description></rdf:RDF></x:xmpmeta>")
        parts.append(seg(0xE1, b"http://ns.adobe.com/xap/1.0/\0" + xml.encode()))
    parts.append(seg(0xE2, ICC))
    if iptc:
        rec = b"\x1c\x02\x50" + struct.pack(">H", 8) + b"Ana Pere"
        parts.append(seg(0xED, b"Photoshop 3.0\0" + b"8BIM" + b"\x04\x04" + b"\0\0" + struct.pack(">I", len(rec)) + rec))
    if comment:
        parts.append(seg(0xFE, b"made by Ana at home"))
    if c2pa:
        parts.append(seg(0xEB, b"JP\x00\x00\x00\x01jumb....c2pa....manifest"))
    parts.append(SCAN)
    return b"".join(parts)


def png_chunk(typ, data):
    return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)


def build_png(text=True, exif=True, c2pa=False):
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    out = [b"\x89PNG\r\n\x1a\n", png_chunk(b"IHDR", ihdr)]
    if text:
        out += [png_chunk(b"tEXt", b"Author\0Ana Perez"), png_chunk(b"iTXt", b"Comment\0\0\0\0\0hola desde casa"),
                png_chunk(b"tIME", struct.pack(">HBBBBB", 2026, 1, 2, 3, 4, 5))]
    if exif:
        out.append(png_chunk(b"eXIf", build_exif(**SAMPLE_EXIF)))
    if c2pa:
        out.append(png_chunk(b"caBX", b"jumb....c2pa...."))
    out += [png_chunk(b"IDAT", idat), png_chunk(b"IEND", b"")]
    return b"".join(out)


CORE = ('<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="c" xmlns:dc="d">'
        "<dc:title>Informe</dc:title><dc:creator>Ana Pérez</dc:creator>"
        "<cp:lastModifiedBy>Luis Gómez</cp:lastModifiedBy></cp:coreProperties>")
APP = '<?xml version="1.0"?><Properties xmlns="a"><Application>Word</Application><Company>Acme SL</Company></Properties>'


def build_docx(body_text="Hola\u200b mundo\u00a0!", signed=False, tracked_author="Luis Gómez"):
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="w"><w:body><w:p>'
           f'<w:r><w:t>{body_text}</w:t></w:r><w:r><w:t>\u00a0fin</w:t></w:r>'
           f'<w:ins w:author="{tracked_author}"><w:r><w:t>nuevo</w:t></w:r></w:ins></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
        z.writestr("word/media/image1.png", b"\x89PNG-not-really")
        z.writestr("docProps/core.xml", CORE)
        z.writestr("docProps/app.xml", APP)
        if signed:
            z.writestr("_xmlsignatures/sig1.xml", "<Signature/>")
    return buf.getvalue()


def build_pdf(author="Ana Pérez", text="Hello PDF world", signed=False):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    info = "<< /Author (" + author + ") /Producer (TestGen 1) >>"
    objs.append(info.encode("latin-1"))
    if signed:
        objs.append(b"<< /Type /Sig /Filter /Adobe.PPKLite /ByteRange [0 10 20 30] >>")
    out, offsets = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


PAGE_TEXT = "Hello PDF world"
INFO_FULL = (b"<< /Title (Plan \\(draft\\) (v2) \\\\ end) /Author <FEFF0041006E0061> /Creator (Chromium) "
             b"/Producer (Skia/PDF m120) /CreationDate (D:20261118101010+01'00') "
             b"/ModDate (D:20261118111111+01'00') /Trapped /False >>")
XMP_PACKET = (b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
              b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description>'
              b"<dc:creator><rdf:Seq><rdf:li>Ana Perez</rdf:li></rdf:Seq></dc:creator>"
              b"</rdf:Description></rdf:RDF></x:xmpmeta>" + b" " * 200 + b'<?xpacket end="w"?>')


def build_pdf_real(info=INFO_FULL, xmp=True, revisions=1, encrypt=False, objstm=False, signed=False, text=PAGE_TEXT):
    """A PDF with the structures that real files have: Info dictionary with nested
    parentheses, escapes and a hexadecimal string, an uncompressed XMP packet and
    incremental revisions (each one has its own trailer, xref table and Info copy)."""
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R" + (b" /Metadata 7 0 R" if xmp else b"") + b" >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
            4: b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    if not objstm:
        objs[6] = info
    if xmp:
        objs[7] = b"<< /Type /Metadata /Subtype /XML /Length %d >>\nstream\n" % len(XMP_PACKET) + XMP_PACKET + b"\nendstream"
    if objstm:
        objs[8] = b"<< /Type /ObjStm /N 1 /First 4 /Length 10 /Filter /FlateDecode >>\nstream\nxxxxxxxxxx\nendstream"
    if signed:
        objs[9] = b"<< /Type /Sig /Filter /Adobe.PPKLite /ByteRange [0 10 20 30] >>"
    out, offsets = b"%PDF-1.4\n", {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += b"%d 0 obj\n" % n + objs[n] + b"\nendobj\n"
    size = max(objs) + 1
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for n in range(1, size):
        out += (b"%010d 00000 n \n" % offsets[n]) if n in offsets else b"0000000000 00000 f \n"
    enc = b" /Encrypt << /Filter /Standard /V 1 /R 2 /O (x) /U (y) /P -4 >>" if encrypt else b""
    info_ref = b"" if objstm else b" /Info 6 0 R"
    out += b"trailer\n<< /Size %d /Root 1 0 R%s%s >>\nstartxref\n%d\n%%%%EOF\n" % (size, info_ref, enc, xref)
    prev = xref
    for rev in range(2, revisions + 1):
        new_info = b"<< /Title (Revision %d title) /Author (Ana Perez) /ModDate (D:2026111%d) >>" % (rev, rev)
        off = len(out)
        out += b"6 0 obj\n" + new_info + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n6 1\n%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R /Prev %d >>\nstartxref\n%d\n%%%%EOF\n" % (size, prev, xref)
        prev = xref
    return out


# --- EPUB, HTML, MP3, MP4 (version 3.1.0) --------------------------------------------------------------

OPF = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
       '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n'
       '    <dc:identifier id="bookid">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>\n'
       '    <dc:title>Informe de prueba</dc:title>\n'
       '    <dc:language>es</dc:language>\n'
       '    <dc:creator id="cre1" opf:role="aut">Ana Pérez</dc:creator>\n'
       '    <meta refines="#cre1" property="file-as">Pérez, Ana</meta>\n'
       '    <dc:contributor opf:role="bkp">calibre (5.44.0) [https://calibre-ebook.com]</dc:contributor>\n'
       '    <dc:publisher>Editorial Acme SL</dc:publisher>\n'
       '    <dc:rights>Copyright Ana Pérez 2026</dc:rights>\n'
       '    <dc:source>C:\\Users\\ana\\libro.docx</dc:source>\n'
       '    <dc:date>2026-01-02T03:04:05+00:00</dc:date>\n'
       '    <meta property="dcterms:modified">2026-01-03T00:00:00Z</meta>\n'
       '    <meta name="calibre:title_sort" content="Informe de prueba"/>\n'
       '    <meta name="generator" content="Sigil 1.9"/>\n'
       '    <meta name="cover" content="cover-image"/>\n'
       '    <!-- <dc:creator>Not live</dc:creator> -->\n'
       '  </metadata>\n  <manifest/>\n</package>\n')
CONTAINER = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
             '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')


def build_epub(opf=OPF, extra=None, mimetype_stored=True, signed=False):
    """A valid EPUB layout: mimetype first and stored, container.xml, an OPF, one chapter."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", (2026, 1, 2, 3, 4, 5)), b"application/epub+zip",
                   compress_type=zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("META-INF/container.xml", (2026, 1, 2, 3, 4, 5)), CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("OEBPS/content.opf", (2026, 1, 2, 3, 4, 5)), opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("OEBPS/ch1.xhtml", (2026, 1, 2, 3, 4, 5)),
                   "<html><body><p>Capítulo uno</p></body></html>", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("OEBPS/cover.jpg", (2026, 1, 2, 3, 4, 5)), build_jpeg(), compress_type=zipfile.ZIP_STORED)
        if signed:
            z.writestr("META-INF/signatures.xml", "<signatures/>")
        for name, body in (extra or {}).items():
            z.writestr(name, body)
    return buf.getvalue()


HTML_PAGE = ('<!DOCTYPE html>\r\n<html lang="es">\r\n<head>\r\n<meta charset="utf-8">\r\n'
             '<meta name="author" content="Ana Pérez">\r\n'
             '<meta name="generator" content="Hugo 0.120">\r\n'
             '<meta property="og:site_name" content="Blog de Ana">\r\n'
             "<meta property='og:title' content='Hola'>\r\n"
             '<meta name="description" content="Una página">\r\n'
             '<meta property="article:author" content="https://example.com/ana">\r\n'
             '<meta name="copyright" content="Ana Pérez">\r\n'
             '<style>/* <meta name="author" content="in style"> */</style>\r\n'
             '<!-- <meta name="generator" content="in comment"> -->\r\n'
             '<script>var s = \'<meta name="author" content="in script">\';</script>\r\n'
             '</head>\r\n<body><p>Hóla mundo \xe9</p></body>\r\n</html>\r\n').encode("utf-8") + b"\xe9"


def id3_unsync(b):
    return b.replace(b"\xff", b"\xff\x00")


def _id3_frame(fid, payload, version):
    if version == 2:
        return fid + len(payload).to_bytes(3, "big") + payload
    size = len(payload).to_bytes(4, "big") if version == 3 else bytes(
        [(len(payload) >> 21) & 0x7F, (len(payload) >> 14) & 0x7F, (len(payload) >> 7) & 0x7F, len(payload) & 0x7F])
    return fid + size + b"\0\0" + payload


AUDIO = b"\xff\xfb\x90\x00" + bytes(range(1, 200)) * 3 + b"\xff\xfb\x90\x00" + b"\xff\x00\xe0" * 20


def build_mp3(version=3, unsync=False, footer=False, v1=True, v2=True, audio=AUDIO, padding=16):
    """MP3 with an ID3v2 tag (2.2, 2.3 or 2.4), optional footer and unsynchronisation, optional ID3v1 tag."""
    names = {2: (b"TP1", b"TAL", b"TT2", b"COM", b"PIC"), 3: (b"TPE1", b"TALB", b"TIT2", b"COMM", b"APIC")}
    n = names.get(version, names[3])
    t = lambda s: b"\x00" + s.encode("latin-1")  # noqa: E731
    frames = [_id3_frame(n[0], t("Ana P\xe9rez \xff"), version), _id3_frame(n[1], t("Disco"), version),
              _id3_frame(n[2], t("Cancion"), version), _id3_frame(n[3], b"\x00eng" + b"\x00" + b"hecho en casa", version),
              _id3_frame(n[4], b"\x00image/jpeg\x00\x03\x00" + b"\xff\xd8JPEGDATA", version)]
    if version >= 3:
        frames += [_id3_frame(b"TSSE", t("LAME 3.100"), version), _id3_frame(b"TENC", t("Ana"), version),
                   _id3_frame(b"TXXX", b"\x00owner\x00Ana Perez", version)]
    body = b"".join(frames) + b"\x00" * padding
    flags = 0
    if unsync:
        flags |= 0x80
        body = id3_unsync(body)
    if footer:
        flags |= 0x10
    size = len(body)
    ss = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    tag = b"ID3" + bytes([version, 0, flags]) + ss + body
    if footer:
        tag += b"3DI" + bytes([version, 0, flags]) + ss
    out = (tag if v2 else b"") + audio
    if v1:
        out += (b"TAG" + b"Cancion".ljust(30, b"\0") + b"Ana Perez".ljust(30, b"\0") + b"Disco".ljust(30, b"\0")
                + b"2026" + b"hecho".ljust(28, b"\0") + b"\0\x07" + b"\x11")
    return out


def _atom(typ, payload=b""):
    return (len(payload) + 8).to_bytes(4, "big") + typ + payload


def _ilst_item(typ, text):
    data = _atom(b"data", b"\x00\x00\x00\x01" + b"\x00\x00\x00\x00" + text.encode("utf-8"))
    return _atom(typ, data)


MDAT = b"MEDIADATA" * 20


def build_mp4(udta=True, c2pa=False, brand=b"M4A ", c2pa_in_udta=False, moov_meta=False, udta_keys=False):
    """MP4/M4A with ftyp, moov (mvhd, trak with stco, udta with meta/ilst and (c) xyz) and mdat after moov.
    The stco value is the real offset of the media data, so a change of any size shows up."""
    ftyp = _atom(b"ftyp", brand + b"\0\0\0\0" + brand + b"isom")
    mvhd = _atom(b"mvhd", b"\0" * 100)

    def moov_with(stco_val):
        stco = _atom(b"stco", b"\0\0\0\0" + (1).to_bytes(4, "big") + stco_val.to_bytes(4, "big"))
        trak = _atom(b"trak", _atom(b"mdia", _atom(b"minf", _atom(b"stbl", stco))))
        parts = [mvhd, trak]
        if udta:
            ilst = _atom(b"ilst", _ilst_item(b"\xa9nam", "Mi cancion") + _ilst_item(b"\xa9ART", "Ana Perez")
                         + _ilst_item(b"\xa9too", "Lavf58.76.100") + _ilst_item(b"\xa9day", "2026-01-02")
                         + _ilst_item(b"\xa9cmt", "grabado en casa"))
            meta = _atom(b"meta", b"\0\0\0\0" + _atom(b"hdlr", b"\0" * 20) + ilst)
            xyz_text = b"+36.5000-004.9500/"
            xyz = _atom(b"\xa9xyz", len(xyz_text).to_bytes(2, "big") + b"\x15\xc7" + xyz_text)
            extra = _atom(b"uuid", C2PA_ID + b"jumb c2pa") if c2pa_in_udta else b""
            if udta_keys:  # numeric item types with a keys atom, as ffmpeg writes with -movflags use_metadata_tags
                keys = _atom(b"keys", b"\0\0\0\0" + (1).to_bytes(4, "big") + _atom(b"mdta", b"artist"))
                meta = _atom(b"meta", b"\0\0\0\0" + _atom(b"hdlr", b"\0" * 20) + keys
                             + _atom(b"ilst", _ilst_item((1).to_bytes(4, "big"), "Ana Perez")))
            parts.append(_atom(b"udta", meta + xyz + extra))
        if moov_meta:  # QuickTime style, as written by iPhones: keys + ilst with numeric item types
            names = [b"com.apple.quicktime.make", b"com.apple.quicktime.location.ISO6709"]
            keys = _atom(b"keys", b"\0\0\0\0" + len(names).to_bytes(4, "big")
                         + b"".join(_atom(b"mdta", n) for n in names))
            ilst = _atom(b"ilst", _ilst_item((1).to_bytes(4, "big"), "Apple")
                         + _ilst_item((2).to_bytes(4, "big"), "+36.5000-004.9500+010.000/"))
            parts.append(_atom(b"meta", _atom(b"hdlr", b"\0" * 20) + keys + ilst))
        return _atom(b"moov", b"".join(parts))

    off = len(ftyp) + len(moov_with(0)) + 8
    top = [ftyp, moov_with(off), _atom(b"mdat", MDAT)]
    if c2pa:
        top.append(_atom(b"uuid", C2PA_ID + b"jumb c2pa manifest"))
    return b"".join(top)


C2PA_ID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
