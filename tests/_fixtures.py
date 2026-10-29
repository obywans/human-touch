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
