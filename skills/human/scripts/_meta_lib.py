"""Metadata inspection and (consent-gated) stripping for HumanTouch.

Stdlib only and fully local. Parsers are deliberately small, bounds-checked
and regex-based for XML (no XML parser, so entity-expansion tricks do not
apply). Every inspection records what was actually checked and what was NOT,
because a missing field in a parser that cannot see a region is not proof the
region is empty.

C2PA / digital signatures: this module detects their presence, never
validates them, and never removes them. Stripping other metadata from a file
that carries them invalidates them; callers must refuse unless the user
accepts that explicitly (see metadata_inspect.py).
"""
from __future__ import annotations

import html
import io
import re
import struct
import zipfile
import zlib

MAX_ZIP_TOTAL = 500 * 1024 * 1024
MAX_PART = 50 * 1024 * 1024

# kind -> is the data personal by nature (location, identity, device serials)
PERSONAL_KINDS = {"location", "identity", "device-serial"}


def item(source, key, value, kind, why):
    return {"source": source, "key": key, "value": value, "kind": kind,
            "personal": kind in PERSONAL_KINDS, "explanation": why}


def new_inspection(fmt):
    return {"format": fmt, "checked": [], "not_checked": [], "items": [],
            "provenance": {"c2pa": None, "signatures": []}, "notes": [], "blocks": {}}


# --- EXIF (TIFF structure) ---------------------------------------------------

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

IFD0_TAGS = {
    0x010E: ("ImageDescription", "description", "A free-text description; may name people or places."),
    0x010F: ("Make", "device", "Camera or phone manufacturer."),
    0x0110: ("Model", "device", "Exact camera or phone model."),
    0x0131: ("Software", "software", "Program that created or last saved the file."),
    0x0132: ("DateTime", "time", "When the file was last modified."),
    0x013B: ("Artist", "identity", "The photographer or author name."),
    0x8298: ("Copyright", "identity", "Copyright notice; often deliberately public, review before removing."),
}
XP_TAGS = {0x9C9B: "XPTitle", 0x9C9C: "XPComment", 0x9C9D: "XPAuthor", 0x9C9E: "XPKeywords", 0x9C9F: "XPSubject"}
EXIF_TAGS = {
    0x9003: ("DateTimeOriginal", "time", "When the photo was taken."),
    0x9004: ("DateTimeDigitized", "time", "When the photo was digitised."),
    0x9286: ("UserComment", "description", "Free-text comment."),
    0xA430: ("CameraOwnerName", "identity", "Name of the camera owner."),
    0xA431: ("BodySerialNumber", "device-serial", "Serial number of the camera body; links photos to one device."),
    0xA435: ("LensSerialNumber", "device-serial", "Serial number of the lens; links photos to one device."),
    0xA420: ("ImageUniqueID", "device-serial", "Unique identifier assigned to the image."),
    0xA433: ("LensMake", "device", "Lens manufacturer."),
    0xA434: ("LensModel", "device", "Lens model."),
}


class _Tiff:
    def __init__(self, buf):
        if buf[:2] == b"II":
            self.bo = "little"
        elif buf[:2] == b"MM":
            self.bo = "big"
        else:
            raise ValueError("not a TIFF/EXIF header")
        self.buf = buf
        if self.u(2, 2) != 42:
            raise ValueError("bad TIFF magic")

    def u(self, off, size):
        if off < 0 or off + size > len(self.buf):
            raise ValueError("offset outside EXIF block")
        return int.from_bytes(self.buf[off:off + size], self.bo)

    def ifd(self, off):
        n = min(self.u(off, 2), 512)
        entries = {}
        for k in range(n):
            e = off + 2 + 12 * k
            tag, typ, cnt = self.u(e, 2), self.u(e + 2, 2), self.u(e + 4, 4)
            size = _TYPE_SIZE.get(typ, 1) * cnt
            if size > 1 << 20:
                continue
            start = e + 8 if size <= 4 else self.u(e + 8, 4)
            if start + size > len(self.buf):
                continue
            entries[tag] = (typ, cnt, self.buf[start:start + size])
        return entries, self.u(off + 2 + 12 * n, 4) if off + 2 + 12 * n + 4 <= len(self.buf) else 0

    def ints(self, typ, cnt, raw):
        w = _TYPE_SIZE[typ]
        return [int.from_bytes(raw[i * w:(i + 1) * w], self.bo) for i in range(cnt)]

    def rationals(self, cnt, raw):
        out = []
        for i in range(cnt):
            num = int.from_bytes(raw[i * 8:i * 8 + 4], self.bo)
            den = int.from_bytes(raw[i * 8 + 4:i * 8 + 8], self.bo)
            out.append(num / den if den else 0.0)
        return out


def _ascii(raw):
    return raw.split(b"\0")[0].decode("utf-8", "replace").strip()


def _gps(t, entries):
    def val(tag):
        return entries.get(tag)
    lat, lon = val(2), val(4)
    if not (lat and lon):
        return None
    la = t.rationals(lat[1], lat[2])
    lo = t.rationals(lon[1], lon[2])
    if len(la) < 3 or len(lo) < 3:
        return None
    lat_ref = _ascii(val(1)[2]) if val(1) else "N"
    lon_ref = _ascii(val(3)[2]) if val(3) else "E"
    dlat = (la[0] + la[1] / 60 + la[2] / 3600) * (-1 if lat_ref == "S" else 1)
    dlon = (lo[0] + lo[1] / 60 + lo[2] / 3600) * (-1 if lon_ref == "W" else 1)
    return f"{dlat:.6f}, {dlon:.6f}"


def parse_exif(tiff_bytes, source="EXIF"):
    """Return (items, orientation, extras). Raises ValueError on a broken block."""
    t = _Tiff(tiff_bytes)
    items, orientation, extras = [], None, {"thumbnail": False, "makernote": 0}
    ifd0, ifd1_off = t.ifd(t.u(4, 4))
    for tag, (name, kind, why) in IFD0_TAGS.items():
        if tag in ifd0 and ifd0[tag][0] == 2:
            v = _ascii(ifd0[tag][2])
            if v:
                items.append(item(source, name, v, kind, why))
    for tag, name in XP_TAGS.items():
        if tag in ifd0:
            v = ifd0[tag][2].decode("utf-16-le", "replace").rstrip("\0").strip()
            if v:
                kind = "identity" if name == "XPAuthor" else "description"
                items.append(item(source, name, v, kind, "Windows Explorer metadata field."))
    if 0x0112 in ifd0 and ifd0[0x0112][0] == 3:
        orientation = t.ints(3, 1, ifd0[0x0112][2])[0]
    if 0x8769 in ifd0:
        exif, _ = t.ifd(t.ints(4, 1, ifd0[0x8769][2])[0])
        for tag, (name, kind, why) in EXIF_TAGS.items():
            if tag in exif:
                typ, cnt, raw = exif[tag]
                if tag == 0x9286:
                    v = raw[8:].decode("utf-16-le" if raw[:8].startswith(b"UNICODE") else "utf-8", "replace").strip("\0 ")
                else:
                    v = _ascii(raw) if typ == 2 else raw.hex()
                if v:
                    items.append(item(source, name, v, kind, why))
        if 0x927C in exif:
            extras["makernote"] = exif[0x927C][1]
            items.append(item(source, "MakerNote", f"{exif[0x927C][1]} bytes (vendor-specific, not decoded)",
                              "device-serial", "Vendor data that often contains serial numbers; kept opaque."))
    if 0x8825 in ifd0:
        gps, _ = t.ifd(t.ints(4, 1, ifd0[0x8825][2])[0])
        pos = _gps(t, gps)
        if pos:
            items.append(item(source, "GPS position", pos, "location", "Where the photo was taken (latitude, longitude)."))
    if ifd1_off and ifd1_off < len(tiff_bytes):
        ifd1, _ = t.ifd(ifd1_off)
        if 0x0201 in ifd1:
            extras["thumbnail"] = True
            items.append(item(source, "EmbeddedThumbnail", "present", "other",
                              "A small preview image; it can still show content cropped out of the main image."))
    return items, orientation, extras


def minimal_exif_orientation(orientation):
    """A tiny big-endian EXIF block holding only the Orientation tag."""
    tiff = (b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1)
            + struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0) + b"\x00\x00\x00\x00")
    return b"Exif\0\0" + tiff


# --- XMP ----------------------------------------------------------------------

XMP_FIELDS = [
    ("dc:creator", "identity", "Author name(s)."), ("dc:rights", "identity", "Rights / copyright statement."),
    ("dc:title", "description", "Title."), ("dc:description", "description", "Description."),
    ("dc:subject", "description", "Keywords."), ("xmp:CreatorTool", "software", "Program that created the file."),
    ("xmp:CreateDate", "time", "Creation date."), ("xmp:ModifyDate", "time", "Last modification date."),
    ("photoshop:Credit", "identity", "Credit line."), ("photoshop:City", "location", "City recorded in the file."),
    ("photoshop:Country", "location", "Country recorded in the file."),
    ("photoshop:State", "location", "State or region recorded in the file."),
    ("exif:GPSLatitude", "location", "GPS latitude."), ("exif:GPSLongitude", "location", "GPS longitude."),
    ("aux:SerialNumber", "device-serial", "Camera serial number."), ("aux:Lens", "device", "Lens description."),
    ("xmpMM:DocumentID", "device-serial", "Unique document identifier."),
    ("stEvt:softwareAgent", "software", "Programs that edited the file (edit history)."),
]


def xmp_items(xml, source="XMP"):
    out = []
    for name, kind, why in XMP_FIELDS:
        vals = []
        for m in re.finditer(rf"<{re.escape(name)}\b[^>]*>(.*?)</{re.escape(name)}>", xml, re.DOTALL):
            v = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
            vals.append(" ".join(v.split()))
        for m in re.finditer(rf'\b{re.escape(name)}="([^"]*)"', xml):
            vals.append(html.unescape(m.group(1)))
        vals = [v for v in dict.fromkeys(vals) if v]
        if vals:
            out.append(item(source, name, "; ".join(vals)[:300], kind, why))
    return out


# --- IPTC (Photoshop 8BIM, JPEG APP13) ----------------------------------------

IPTC = {(2, 80): ("By-line (photographer)", "identity"), (2, 116): ("Copyright notice", "identity"),
        (2, 110): ("Credit", "identity"), (2, 115): ("Source", "identity"), (2, 122): ("Writer/editor", "identity"),
        (2, 5): ("Object name / title", "description"), (2, 120): ("Caption", "description"),
        (2, 25): ("Keywords", "description"), (2, 90): ("City", "location"),
        (2, 95): ("Province/state", "location"), (2, 101): ("Country", "location"),
        (2, 92): ("Sublocation", "location")}


def iptc_items(payload, source="IPTC"):
    out, i = [], 0
    if not payload.startswith(b"Photoshop 3.0\0"):
        return out
    i = 14
    while i + 12 <= len(payload) and payload[i:i + 4] == b"8BIM":
        rid = int.from_bytes(payload[i + 4:i + 6], "big")
        nlen = payload[i + 6]
        j = i + 7 + nlen + ((nlen + 1) % 2)
        size = int.from_bytes(payload[j:j + 4], "big")
        data = payload[j + 4:j + 4 + size]
        if rid == 0x0404:
            k = 0
            while k + 5 <= len(data) and data[k] == 0x1C:
                rec, ds = data[k + 1], data[k + 2]
                ln = int.from_bytes(data[k + 3:k + 5], "big")
                val = data[k + 5:k + 5 + ln].decode("utf-8", "replace").strip()
                if (rec, ds) in IPTC and val:
                    label, kind = IPTC[(rec, ds)]
                    out.append(item(source, label, val, kind, "IPTC press/editorial field."))
                k += 5 + ln
        i = j + 4 + size + (size % 2)
    return out


# --- JPEG -----------------------------------------------------------------------

def jpeg_segments(data):
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    i, n, segs = 2, len(data), []
    while i < n:
        if data[i] != 0xFF:
            raise ValueError("corrupt JPEG marker stream")
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker, start = data[i], i - 1
        i += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if marker == 0xD9:
            break
        if i + 2 > n:
            raise ValueError("truncated JPEG")
        length = int.from_bytes(data[i:i + 2], "big")
        if length < 2 or i + length > n:
            raise ValueError("bad JPEG segment length")
        segs.append({"marker": marker, "start": start, "end": i + length, "payload": data[i + 2:i + length]})
        i += length
        if marker == 0xDA:
            break
    return segs


def _jpeg_block(seg):
    m, p = seg["marker"], seg["payload"]
    if m == 0xE1 and p.startswith(b"Exif\0\0"):
        return "exif"
    if m == 0xE1 and p.startswith((b"http://ns.adobe.com/xap/1.0/\0", b"http://ns.adobe.com/xmp/extension/\0")):
        return "xmp"
    if m == 0xED and p.startswith(b"Photoshop 3.0\0"):
        return "iptc"
    if m == 0xFE:
        return "comment"
    if m == 0xEB and p[:2] == b"JP" and b"c2pa" in p:
        return "c2pa"
    return None


def inspect_jpeg(data):
    ins = new_inspection("JPEG")
    segs = jpeg_segments(data)
    ins["checked"] = ["JPEG segments (EXIF, XMP, IPTC, comments, C2PA marker)"]
    ins["not_checked"] = ["data after the first image scan; vendor MakerNote contents; C2PA signature validity"]
    for s in segs:
        blk = _jpeg_block(s)
        if not blk:
            continue
        ins["blocks"][blk] = ins["blocks"].get(blk, 0) + 1
        p = s["payload"]
        try:
            if blk == "exif":
                its, _, _ = parse_exif(p[6:])
                ins["items"] += its
            elif blk == "xmp":
                ins["items"] += xmp_items(p.split(b"\0", 1)[1].decode("utf-8", "replace"))
            elif blk == "iptc":
                ins["items"] += iptc_items(p)
            elif blk == "comment":
                ins["items"].append(item("COM", "Comment", p.decode("utf-8", "replace").strip()[:300], "description",
                                         "Free-text comment embedded by some program."))
        except ValueError as exc:
            ins["notes"].append(f"{blk.upper()} block present but could not be fully read ({exc}).")
    ins["provenance"]["c2pa"] = "c2pa" in ins["blocks"]
    return ins


def strip_jpeg(data, only, remove_c2pa=False):
    """Remove whole metadata blocks listed in `only`. ICC/JFIF/Adobe colour data is kept.
    C2PA (JUMBF in APP11) is removed only when remove_c2pa is True: every APP11
    segment is dropped, because a credential spans several of them."""
    segs = jpeg_segments(data)
    out, pos, removed = [data[:2]], 2, []
    for s in segs:
        blk = _jpeg_block(s)
        if remove_c2pa and "c2pa" in only and s["marker"] == 0xEB and s["payload"][:2] == b"JP":
            blk = "c2pa"
        out.append(data[pos:s["start"]])
        pos = s["start"]
        if blk == "c2pa" and remove_c2pa and "c2pa" in only:
            removed.append("c2pa (content credentials)")
            pos = s["end"]
        elif blk in only and blk != "c2pa":
            removed.append(blk)
            if blk == "exif":
                try:
                    _, orientation, _ = parse_exif(s["payload"][6:])
                except ValueError:
                    orientation = None
                if orientation and orientation != 1:
                    keep = minimal_exif_orientation(orientation)
                    out.append(b"\xff\xe1" + struct.pack(">H", len(keep) + 2) + keep)
                    removed.append("exif (orientation tag kept so the image still displays upright)")
            pos = s["end"]
    out.append(data[pos:])
    return b"".join(out), removed


# --- PNG ------------------------------------------------------------------------

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_BLOCKS = {b"tEXt": "text", b"zTXt": "text", b"iTXt": "text", b"eXIf": "exif", b"tIME": "time"}


def png_chunks(data):
    if data[:8] != PNG_SIG:
        raise ValueError("not a PNG file")
    i, chunks = 8, []
    while i + 12 <= len(data):
        ln = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8]
        if i + 12 + ln > len(data):
            raise ValueError("truncated PNG chunk")
        chunks.append({"type": typ, "start": i, "end": i + 12 + ln, "data": data[i + 8:i + 8 + ln]})
        i += 12 + ln
        if typ == b"IEND":
            break
    return chunks


def _png_text(c):
    typ, d = c["type"], c["data"]
    key, _, rest = d.partition(b"\0")
    key = key.decode("latin-1")
    if typ == b"tEXt":
        return key, rest.decode("latin-1")
    if typ == b"zTXt":
        z = zlib.decompressobj()
        return key, z.decompress(rest[1:], 1 << 20).decode("utf-8", "replace")
    flag, _method = rest[0], rest[1]
    rest = rest[2:]
    _lang, _, rest = rest.partition(b"\0")
    _tkey, _, txt = rest.partition(b"\0")
    if flag:
        txt = zlib.decompressobj().decompress(txt, 1 << 20)
    return key, txt.decode("utf-8", "replace")


TEXT_KEYS = {"author": "identity", "copyright": "identity", "creation time": "time", "software": "software",
             "description": "description", "comment": "description", "title": "description",
             "source": "device", "disclaimer": "description", "warning": "description"}


def inspect_png(data):
    ins = new_inspection("PNG")
    ins["checked"] = ["PNG chunks (text, XMP, EXIF, timestamp, C2PA caBX)"]
    ins["not_checked"] = ["C2PA signature validity"]
    for c in png_chunks(data):
        t = c["type"]
        if t in PNG_BLOCKS:
            ins["blocks"][PNG_BLOCKS[t]] = ins["blocks"].get(PNG_BLOCKS[t], 0) + 1
        try:
            if t in (b"tEXt", b"zTXt", b"iTXt"):
                key, val = _png_text(c)
                if key == "XML:com.adobe.xmp":
                    ins["items"] += xmp_items(val)
                elif val.strip():
                    ins["items"].append(item("PNG text", key, val.strip()[:300],
                                             TEXT_KEYS.get(key.lower(), "other"), "Text chunk stored in the image."))
            elif t == b"eXIf":
                ins["items"] += parse_exif(c["data"])[0]
            elif t == b"tIME":
                y, mo, d, h, mi, s = struct.unpack(">HBBBBB", c["data"][:7])
                ins["items"].append(item("PNG tIME", "LastModified", f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}",
                                         "time", "When the image was last modified."))
        except (ValueError, zlib.error, struct.error) as exc:
            ins["notes"].append(f"{t.decode('latin-1')} chunk present but could not be read ({exc}).")
    ins["provenance"]["c2pa"] = any(c["type"] == b"caBX" for c in png_chunks(data))
    return ins


def strip_png(data, only, remove_c2pa=False):
    out, removed = [PNG_SIG], []
    for c in png_chunks(data):
        blk = PNG_BLOCKS.get(c["type"])
        if blk is None and remove_c2pa and c["type"] == b"caBX":
            blk = "c2pa"
        if blk in only:
            removed.append(blk)
        else:
            out.append(data[c["start"]:c["end"]])
    chunks = png_chunks(data)
    tail_start = chunks[-1]["end"] if chunks else len(PNG_SIG)  # a PNG cut right after its signature has no chunk
    out.append(data[tail_start:])
    return b"".join(out), removed


# --- WebP / generic ----------------------------------------------------------------

def inspect_webp(data):
    ins = new_inspection("WebP")
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP file")
    ins["checked"] = ["RIFF chunk list (EXIF, XMP, ICC, C2PA chunk presence)"]
    ins["not_checked"] = ["C2PA signature validity"]
    ins["notes"].append("Stripping WebP metadata is not supported by this tool.")
    i = 12
    while i + 8 <= len(data):
        cc, ln = data[i:i + 4], int.from_bytes(data[i + 4:i + 8], "little")
        body = data[i + 8:i + 8 + ln]
        if cc == b"EXIF":
            ins["blocks"]["exif"] = 1
            try:
                ins["items"] += parse_exif(body[6:] if body.startswith(b"Exif\0\0") else body)[0]
            except ValueError as exc:
                ins["notes"].append(f"EXIF chunk present but could not be read ({exc}).")
        elif cc == b"XMP ":
            ins["blocks"]["xmp"] = 1
            ins["items"] += xmp_items(body.decode("utf-8", "replace"))
        elif cc == b"C2PA":
            ins["provenance"]["c2pa"] = True
        i += 8 + ln + (ln % 2)
    if ins["provenance"]["c2pa"] is None:
        ins["provenance"]["c2pa"] = False
    return ins


def inspect_unknown(data, label):
    ins = new_inspection(label)
    ins["not_checked"] = ["this format has no parser here: metadata fields were NOT read"]
    marks = [(b"c2pa", "C2PA marker"), (b"<x:xmpmeta", "XMP packet"), (b"Exif\0\0", "EXIF header")]
    found = [name for pat, name in marks if pat in data[: 8 * 1024 * 1024]]
    ins["checked"] = ["byte search for C2PA / XMP / EXIF markers only (heuristic)"]
    if found:
        ins["notes"].append("Heuristic markers found: " + ", ".join(found) + ". Their contents were not read.")
    ins["provenance"]["c2pa"] = "possible (heuristic)" if b"c2pa" in data else None
    ins["notes"].append("Absence of markers here does not prove the file has no metadata.")
    return ins


# --- OOXML (docx / xlsx / pptx) -------------------------------------------------------

CORE_PEOPLE = ("creator", "lastModifiedBy")
CORE_DESCRIPTIVE = ("title", "subject", "keywords", "description", "category")
APP_ORG = ("Company", "Manager")
OOXML_FIELD_INFO = {
    "creator": ("identity", "Name of the person who created the document."),
    "lastModifiedBy": ("identity", "Name of the last person who saved it."),
    "Company": ("identity", "Organisation name registered in the Office installation."),
    "Manager": ("identity", "Manager name entered in document properties."),
    "title": ("description", "Document title property."), "subject": ("description", "Subject property."),
    "keywords": ("description", "Keywords property."), "description": ("description", "Comments property."),
    "category": ("description", "Category property."),
    "created": ("time", "Creation date."), "modified": ("time", "Last modification date."),
    "Application": ("software", "Program and version that created it."),
    "TotalTime": ("other", "Total editing time in minutes."),
    "revision": ("other", "Number of saves."),
}


def _open_zip(data):
    zf = zipfile.ZipFile(io.BytesIO(data))
    if sum(i.file_size for i in zf.infolist()) > MAX_ZIP_TOTAL or any(i.file_size > MAX_PART * 4 for i in zf.infolist()):
        raise ValueError("archive expands to an unreasonable size; refusing to process it")
    return zf


def _part(zf, name):
    try:
        with zf.open(name) as f:
            raw = f.read(MAX_PART + 1)
    except KeyError:
        return None
    if len(raw) > MAX_PART:
        raise ValueError(f"{name} is too large")
    return raw.decode("utf-8", "replace")


def _field(xml, local):
    m = re.search(rf"<(?:[\w.-]+:)?{local}\b[^>]*>(.*?)</(?:[\w.-]+:)?{local}>", xml, re.DOTALL)
    return html.unescape(m.group(1)).strip() if m else ""


def inspect_ooxml(data, label):
    ins = new_inspection(label)
    zf = _open_zip(data)
    names = zf.namelist()
    ins["checked"] = ["docProps/core.xml, docProps/app.xml, docProps/custom.xml, tracked-change and comment authors, "
                      "signature parts, thumbnail"]
    ins["not_checked"] = ["metadata of images embedded inside the document (inspect them separately)",
                          "signature validity", "hidden text, rsid session ids"]
    core, app, custom = (_part(zf, f"docProps/{n}.xml") for n in ("core", "app", "custom"))
    for xml, fields in ((core, ("creator", "lastModifiedBy", "title", "subject", "keywords", "description",
                                "category", "created", "modified", "revision")),
                        (app, ("Application", "Company", "Manager", "TotalTime"))):
        for fld in fields if xml else ():
            v = _field(xml, fld)
            if v:
                kind, why = OOXML_FIELD_INFO[fld]
                ins["items"].append(item("docProps", fld, v[:300], kind, why))
    if core:
        ins["blocks"]["people"] = int(bool(_field(core, "creator") or _field(core, "lastModifiedBy")))
        ins["blocks"]["descriptive"] = int(any(_field(core, f) for f in CORE_DESCRIPTIVE))
    if app:
        ins["blocks"]["organization"] = int(bool(_field(app, "Company") or _field(app, "Manager")))
    if custom and re.search(r"<(?:[\w.-]+:)?property\b", custom):
        ins["notes"].append("docProps/custom.xml holds custom properties; they are listed here but not removed by this tool.")
        for m in re.finditer(r'<(?:[\w.-]+:)?property\b[^>]*\bname="([^"]*)"', custom):
            ins["items"].append(item("custom.xml", html.unescape(m.group(1)), "(custom property)", "other",
                                     "A property added by a person or template."))
    authors = set()
    for n in names:
        if re.fullmatch(r"(word|xl|ppt)/(document|comments|commentAuthors|people)[\w/]*\.xml", n):
            x = _part(zf, n) or ""
            pat = r'\bname="([^"]+)"' if n.endswith(("commentAuthors.xml", "people.xml")) else r'\bw(?:15)?:author="([^"]+)"'
            authors |= {html.unescape(a) for a in re.findall(pat, x)}
    if authors:
        ins["items"].append(item("document body", "Reviewer/author names", "; ".join(sorted(authors))[:300], "identity",
                                 "Names attached to tracked changes and comments; this tool reports them but does not rewrite them."))
    if any(n.startswith("docProps/thumbnail") for n in names):
        ins["items"].append(item("docProps", "Thumbnail", "present", "other", "A preview image of the first page."))
    media = [n for n in names if "/media/" in n]
    if media:
        ins["notes"].append(f"{len(media)} embedded media file(s) were not inspected individually.")
    sig = [n for n in names if n.startswith("_xmlsignatures/")]
    if sig:
        ins["provenance"]["signatures"].append("OOXML digital signature part(s): " + ", ".join(sig))
    ins["provenance"]["c2pa"] = False if not any(b"c2pa" in n.encode() for n in names) else "possible"
    return ins


def _clear_fields(xml, fields):
    n = 0
    for fld in fields:
        xml, k = re.subn(rf"(<((?:[\w.-]+:)?{fld})\b[^>]*>)(.*?)(</\2>)",
                         lambda m: m.group(1) + m.group(4) if m.group(3) else m.group(0), xml, flags=re.DOTALL)
        n += k
    return xml, n


def rewrite_zip(zin, replacements, mimetype_first=False):
    """Copy a zip entry by entry (same order, timestamps, compression), swapping the bytes in `replacements`.

    With `mimetype_first`, the `mimetype` entry goes first and is stored without compression (EPUB rule)."""
    out = io.BytesIO()
    infos = list(zin.infolist())
    if mimetype_first:
        infos.sort(key=lambda i: i.filename != "mimetype")  # stable: the other entries keep their order
    with zipfile.ZipFile(out, "w") as zout:
        for info in infos:
            ni = zipfile.ZipInfo(info.filename, info.date_time)
            ni.compress_type, ni.external_attr, ni.create_system = info.compress_type, info.external_attr, info.create_system
            if mimetype_first and info.filename == "mimetype":
                ni.compress_type = zipfile.ZIP_STORED
            zout.writestr(ni, replacements[info.filename] if info.filename in replacements else zin.read(info))
    return out.getvalue()


def strip_ooxml(data, only):
    zin = _open_zip(data)
    plan = {"docProps/core.xml": [], "docProps/app.xml": []}
    if "people" in only:
        plan["docProps/core.xml"] += CORE_PEOPLE
    if "descriptive" in only:
        plan["docProps/core.xml"] += CORE_DESCRIPTIVE
    if "organization" in only:
        plan["docProps/app.xml"] += APP_ORG
    repl, removed = {}, []
    for name, fields in plan.items():
        xml = _part(zin, name) if fields else None
        if xml:
            new, _ = _clear_fields(xml, fields)
            if new != xml:
                repl[name] = new.encode("utf-8")
                removed.append(name)
    return rewrite_zip(zin, repl), removed


# --- PDF -----------------------------------------------------------------------------------

def _pdf_string(raw):
    raw = raw.strip()
    if raw.startswith(b"<"):
        try:
            b = bytes.fromhex(re.sub(rb"\s", b"", raw[1:-1]).decode())
        except ValueError:
            return ""
    else:
        b = re.sub(rb"\\(.)", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t"}.get(m.group(1), m.group(1)), raw[1:-1])
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "replace")
    return b.decode("latin-1")


PDF_INFO = {"Title": "description", "Author": "identity", "Subject": "description", "Keywords": "description",
            "Creator": "software", "Producer": "software", "CreationDate": "time", "ModDate": "time"}

PDF_NOT_CHECKED = ("page content, embedded images, fonts and objects inside compressed object streams "
                   "are not changed or checked")
PDF_STRIP_NOTE = ("Removal works for the Info dictionary and for an XMP packet that is stored uncompressed. "
                  "Objects inside compressed object streams are not changed.")
_XMP_EMPTY = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"></x:xmpmeta>'
_XPACKET = re.compile(rb"(<\?xpacket begin[^>]*\?>)(.*?)(<\?xpacket end[^>]*\?>)", re.DOTALL)


class StripRefused(ValueError):
    """The tool refuses to change this file (exit code 2 in the command line)."""


def _pdf_literal_end(data, i):
    """Return the index after the literal string that starts at data[i] == '('. Tracks nesting and escapes."""
    depth, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == 0x5C:  # backslash: skip the escaped byte
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unterminated string in a PDF object")


def _pdf_string_spans(data, start):
    """List the strings of the object whose body starts at `start`: (key, begin, end) up to endobj or stream."""
    out, i, n, key = [], start, len(data), None
    while i < n:
        if data.startswith(b"endobj", i) or data.startswith(b"stream", i):
            break
        c = data[i]
        if c == 0x2F:  # name
            m = re.compile(rb"/([^\s/<>\[\]()%]*)").match(data, i)
            key, i = m.group(1).decode("latin-1"), m.end()
        elif c == 0x28:
            e = _pdf_literal_end(data, i)
            out.append((key, i, e))
            i = e
        elif c == 0x3C and data[i + 1:i + 2] == b"<":
            i += 2
        elif c == 0x3C:
            e = data.find(b">", i)
            if e < 0:
                raise ValueError("unterminated hexadecimal string in a PDF object")
            out.append((key, i, e + 1))
            i = e + 1
        elif c == 0x25:  # comment
            e = re.compile(rb"[\r\n]").search(data, i)
            i = e.start() if e else n
        else:
            i += 1
    return out


def _pdf_info_copies(data):
    """Return (refs, copies): every /Info reference, and the body start of every copy of each referenced object."""
    refs = sorted(set(re.findall(rb"/Info\s+(\d+)\s+(\d+)\s+R", data)))
    copies = []
    for num, gen in refs:
        for m in re.finditer(rb"(?<![\d])" + num + rb"\s+" + gen + rb"\s+obj\b\s*(?=<<)", data):
            copies.append(m.end())
    return refs, copies


def _pdf_is_empty(tok):
    return not tok[1:-1].strip() if tok[:1] == b"<" else tok == b"()"


def _pdf_xmp_packets(data):
    """Return (begin_end, inner_start, inner_end) of each uncompressed XMP packet that sits in a
    /Type /Metadata stream. A packet inside an image or another stream is not touched."""
    out = []
    for m in _XPACKET.finditer(data):
        head = data[data.rfind(b"obj", 0, m.start(1)):m.start(1)]
        if re.search(rb"/Type\s*/Metadata\b", head) and not re.search(rb"/Subtype\s*/Image\b", head):
            out.append((m.end(1), m.start(2), m.end(2)))
    return out


def _pdf_xmp_has_content(inner):
    t = inner.strip()
    return bool(t) and re.sub(rb"\s+", b"", t) != re.sub(rb"\s+", b"", _XMP_EMPTY)


def inspect_pdf(data):
    ins = new_inspection("PDF")
    if not data.startswith(b"%PDF-"):
        raise ValueError("not a PDF file")
    ins["checked"] = ["Info dictionary (when stored uncompressed), XMP packet, signature fields, encryption flag, markers"]
    ins["not_checked"] = [PDF_NOT_CHECKED, "signature validity"]
    refs, copies = _pdf_info_copies(data)
    last = None
    filled = 0
    for start in copies:
        spans = _pdf_string_spans(data, start)
        if any(not _pdf_is_empty(data[b:e]) for _k, b, e in spans):
            filled += 1
        last = spans
    if refs and not copies:
        ins["notes"].append("The Info dictionary is stored in a compressed object stream and was not decoded.")
        ins["strip_refusal"] = ("the Info dictionary is stored in a compressed object stream and no uncompressed "
                                "copy exists, so it cannot be changed here")
    if last is not None:
        for key, b, e in last:
            if key in PDF_INFO:
                v = _pdf_string(data[b:e])
                if v.strip():
                    ins["items"].append(item("PDF Info", key, v.strip()[:300], PDF_INFO[key],
                                             "Document information dictionary entry."))
        if filled:
            ins["blocks"]["info"] = filled
        if len(copies) > 1:
            ins["notes"].append(f"The Info object has {len(copies)} copies in the file (revisions); "
                                f"{filled} still hold text. Strip blanks every copy.")
    packets = _pdf_xmp_packets(data)
    live = [p for p in packets if _pdf_xmp_has_content(data[p[1]:p[2]])]
    if live:
        ins["blocks"]["xmp"] = len(live)
        for p in live:
            ins["items"] += xmp_items(data[p[1]:p[2]].decode("utf-8", "replace"))
    if re.search(rb"/ByteRange\s*\[", data) or re.search(rb"/Type\s*/Sig\b", data):
        ins["provenance"]["signatures"].append("PDF digital signature field(s)")
    if re.search(rb"/Encrypt\b", data):
        ins["notes"].append("The PDF appears to be encrypted; text and some metadata may be unreadable here.")
        ins["strip_refusal"] = "the PDF is encrypted; changing it would corrupt it"
    if data.count(b"%%EOF") > 1:
        ins["notes"].append("The PDF has several revisions (incremental updates): earlier versions of text or metadata may "
                            "still be present inside the file.")
    if b"/EmbeddedFile" in data:
        ins["notes"].append("The PDF contains embedded file attachments.")
    ins["provenance"]["c2pa"] = "possible (heuristic)" if b"c2pa" in data else None
    ins["notes"].append(PDF_STRIP_NOTE)
    return ins


def strip_pdf(data, only):
    """Blank the Info strings and the uncompressed XMP packets in place. The file length never changes."""
    if re.search(rb"/Encrypt\b", data):
        raise StripRefused("the PDF is encrypted; changing it would corrupt it")
    out = bytearray(data)
    removed = []
    if "info" in only:
        refs, copies = _pdf_info_copies(data)
        if not copies:
            raise StripRefused("the Info dictionary is stored in a compressed object stream and no uncompressed "
                               "copy exists, so it cannot be changed here")
        count = 0
        for start in copies:
            changed = False
            for _k, b, e in _pdf_string_spans(data, start):
                new = (b"<>" if data[b:b + 1] == b"<" else b"()")
                if data[b:e] != new.ljust(e - b, b" "):
                    out[b:e] = new.ljust(e - b, b" ")
                    changed = True
            count += changed
        removed.append(f"info ({count} of {len(copies)} object copies blanked)")
    if "xmp" in only:
        count = 0
        for _be, a, z in _pdf_xmp_packets(data):
            inner = data[a:z]
            if not _pdf_xmp_has_content(inner):
                continue
            fill = _XMP_EMPTY if len(_XMP_EMPTY) <= len(inner) else b""
            out[a:z] = fill.ljust(len(inner), b" ")
            count += 1
        removed.append(f"xmp ({count} packet(s) blanked)")
    new = bytes(out)
    if len(new) != len(data):
        raise ValueError("internal check failed: the output length differs from the input length")
    if "info" in only:
        _r, copies = _pdf_info_copies(new)
        for start in copies:
            for _k, b, e in _pdf_string_spans(new, start):
                if not _pdf_is_empty(new[b:e].rstrip()):
                    raise ValueError("internal check failed: an Info string is still not empty")
    if "xmp" in only:
        for _be, a, z in _pdf_xmp_packets(new):
            if _pdf_xmp_has_content(new[a:z]):
                raise ValueError("internal check failed: XMP text is still present")
    return new, removed


# --- HTML --------------------------------------------------------------------------------------

HTML_META_KINDS = {"author": "identity", "generator": "software", "copyright": "identity", "description": "description",
                   "keywords": "description", "article:author": "identity", "og:site_name": "description"}

# Parts of an HTML file in which a <meta> text is not a live tag: comments, scripts and styles.
_HTML_PROTECTED = re.compile(r"<!--.*?-->|<script\b.*?</script\s*>|<style\b.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_HTML_META_TAG = re.compile(r"""<meta\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.IGNORECASE)
_HTML_ATTR = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_OG_PERSON = re.compile(r"^og:(?:site_name|(?:[\w.-]+:)*(?:author|actor|director|writer|creator|first_name|last_name|username))$")
HTML_STRIP_NOTE = ("Only whole <meta> tags of the chosen blocks are removed. Other markup, scripts, styles, comments, "
                   "the file encoding and the line endings stay as they are.")


def _html_block(key):
    if key in ("author", "article:author", "copyright"):
        return "meta-identity"
    if key == "generator":
        return "meta-software"
    if _OG_PERSON.match(key):
        return "meta-social"
    return None


def _html_meta_tags(data):
    """Return (start, end, attrs, key, block) for every live <meta> tag. `data` is bytes; offsets are byte offsets."""
    text = data.decode("latin-1")  # one character per byte, so the offsets are byte offsets
    protected = [(m.start(), m.end()) for m in _HTML_PROTECTED.finditer(text)]
    out, k = [], 0
    for m in _HTML_META_TAG.finditer(text):
        while k < len(protected) and protected[k][1] <= m.start():
            k += 1
        if k < len(protected) and protected[k][0] <= m.start() < protected[k][1]:
            continue
        attrs = {}
        for name, a, b, c in _HTML_ATTR.findall(m.group(0)):
            raw = (a or b or c).encode("latin-1").decode("utf-8", "replace")
            attrs.setdefault(name.lower(), html.unescape(raw))
        key = (attrs.get("name") or attrs.get("property") or "").strip().lower()
        out.append((m.start(), m.end(), attrs, key, _html_block(key)))
    return out


def inspect_html(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    ins = new_inspection("HTML")
    ins["checked"] = ["<meta> tags, <link rel=author>, HTML comments"]
    ins["not_checked"] = ["scripts, embedded images, and anything loaded from other URLs"]
    counts = {}
    for _s, _e, attrs, key, block in _html_meta_tags(data):
        if key in HTML_META_KINDS and attrs.get("content"):
            ins["items"].append(item("HTML meta", key, attrs["content"][:300], HTML_META_KINDS[key],
                                     "Information the page declares about itself."))
        if block:
            counts[block] = counts.get(block, 0) + 1
    ins["blocks"].update(counts)
    text = data.decode("utf-8", "replace")
    for rel in re.findall(r'<link\b[^>]*\brel="author"[^>]*>', text, re.IGNORECASE):
        ins["items"].append(item("HTML link", "author", rel[:200], "identity", "Link to the author."))
    comments = re.findall(r"<!--(.*?)-->", text, re.DOTALL)
    if comments:
        ins["notes"].append(f"{len(comments)} HTML comment(s) present; they are invisible on the page but readable in the source.")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        ins["strip_refusal"] = "the file is encoded as UTF-16, which this tool does not rewrite"
    ins["plan_notes"] = [HTML_STRIP_NOTE]
    return ins


def strip_html(data, only):
    """Delete whole <meta> tags of the chosen blocks. Every other byte stays as it is."""
    blocks = {"meta-identity", "meta-software", "meta-social"} & set(only)
    tags = _html_meta_tags(data)
    spans = [(s, e) for s, e, _a, _k, b in tags if b in blocks]
    out, pos = bytearray(), 0
    for s, e in spans:
        out += data[pos:s]
        pos = e
    out += data[pos:]
    new = bytes(out)
    if len(new) != len(data) - sum(e - s for s, e in spans):
        raise ValueError("internal check failed: the output length is wrong")
    if any(b in blocks for _s, _e, _a, _k, b in _html_meta_tags(new)):
        raise ValueError("internal check failed: a chosen <meta> tag is still present")
    rest = bytearray(data)
    for s, e in reversed(spans):
        del rest[s:e]
    if bytes(rest) != new:
        raise ValueError("internal check failed: bytes outside the removed tags changed")
    return new, [f"{b} ({sum(1 for t in tags if t[4] == b)} tag(s))" for b in sorted(blocks)]


# --- EPUB -----------------------------------------------------------------------------------------

EPUB_MIME = b"application/epub+zip"
EPUB_BLOCKS = {"creator": "creator", "contributor": "creator", "publisher": "publisher", "rights": "rights", "date": "dates"}
_EPUB_TOOL_META = re.compile(r"^(calibre:.*|generator|[\w.-]+:generator|sigil[ _]version)$")
EPUB_KEPT = "dc:title, dc:language and dc:identifier"
EPUB_NOT_CHECKED = ("content documents (XHTML), images and fonts inside the book, the NCX file (it can hold docAuthor), "
                    "the navigation document, and OPF elements outside <metadata>")
EPUB_STRIP_NOTE = (f"Kept: {EPUB_KEPT}, because a reader needs them. Every other part of the ZIP file is copied without "
                   "change. An EPUB 3 checker can warn about a missing dcterms:modified after the dates block is removed.")


def _epub_open(data):
    zf = _open_zip(data)
    seen = set()
    for info in zf.infolist():
        n = info.filename
        if (n.startswith(("/", "\\")) or "\\" in n or re.match(r"^[A-Za-z]:", n)
                or ".." in n.split("/") or "\x00" in n):
            raise ValueError(f"the EPUB contains an unsafe path ({n!r}); refusing to process it")
        if n in seen:
            raise ValueError(f"the EPUB contains the entry {n!r} twice; refusing to process it")
        seen.add(n)
        if info.flag_bits & 0x1:
            raise ValueError("the EPUB contains an encrypted ZIP entry; it cannot be read here")
    return zf


def _xml_children(xml, start, end):
    """Yield (s, e, qname, attr_text, inner) for the elements that sit directly in xml[start:end].
    Comments, processing instructions and CDATA are skipped."""
    tok = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<([\w.:-]+)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.DOTALL)
    pos = start
    while True:
        m = tok.search(xml, pos, end)
        if not m:
            return
        if m.group(1) is None:
            pos = m.end()
            continue
        name, attrs = m.group(1), m.group(2)
        if attrs.rstrip().endswith("/"):
            yield m.start(), m.end(), name, attrs, ""
            pos = m.end()
            continue
        close = re.compile(r"</" + re.escape(name) + r"\s*>").search(xml, m.end(), end)
        if not close:
            raise ValueError(f"the OPF element <{name}> is not closed")
        yield m.start(), close.end(), name, attrs, xml[m.end():close.start()]
        pos = close.end()


def _attrs(attr_text):
    return {n.lower(): html.unescape(a or b or c) for n, a, b, c in _HTML_ATTR.findall(attr_text)}


def _epub_opf_paths(zf):
    xml = _part(zf, "META-INF/container.xml")
    if xml is None:
        raise ValueError("not a valid EPUB: META-INF/container.xml is missing")
    paths = []
    for tag in re.findall(r"<rootfile\b[^>]*>", xml):
        a = _attrs(tag)
        p = a.get("full-path", "")
        if p and (a.get("media-type", "application/oebps-package+xml") == "application/oebps-package+xml"):
            paths.append(p)
    if not paths:
        raise ValueError("not a valid EPUB: container.xml names no OPF file")
    for p in paths:
        if p not in zf.namelist():
            raise ValueError(f"not a valid EPUB: container.xml names {p}, which is not in the file")
    return paths


def _epub_scan(opf):
    """Return a list of dicts for the children of <metadata>: span, local name, text, block and key."""
    m = re.search(r"<((?:[\w.-]+:)?metadata)\b[^>]*>(.*?)</\1\s*>", opf, re.DOTALL)
    if not m:
        raise ValueError("not a valid EPUB: the OPF file has no metadata element")
    found, by_id = [], {}
    for s, e, name, attr_text, inner in _xml_children(opf, m.start(2), m.end(2)):
        local = name.rsplit(":", 1)[-1].lower()
        a = _attrs(attr_text)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        rec = {"start": s, "end": e, "local": local, "attrs": a, "text": text, "block": None, "key": name}
        if local in EPUB_BLOCKS:
            rec["block"] = EPUB_BLOCKS[local]
        elif local == "meta":
            label = (a.get("property") or a.get("name") or "").strip()
            rec["key"] = "meta " + label if label else "meta"
            rec["text"] = a.get("content", text).strip()
            if label.lower() == "dcterms:modified":
                rec["block"] = "dates"
            elif _EPUB_TOOL_META.match(label.lower()):
                rec["block"] = "software"
        if rec["block"] and a.get("id"):
            by_id[a["id"]] = rec["block"]
        found.append(rec)
    for rec in found:  # refinements (file-as, role, ...) of a creator or a date name the same person
        if rec["local"] == "meta" and rec["block"] is None:
            target = rec["attrs"].get("refines", "").lstrip("#")
            if target in by_id and by_id[target] in ("creator", "publisher", "rights", "dates"):
                rec["block"] = by_id[target]
    return found


_EPUB_INFO = {
    "creator": ("identity", "Name of an author or creator."),
    "contributor": ("identity", "Name of a contributor; some tools write their own name here."),
    "publisher": ("identity", "Name of the publisher."),
    "rights": ("description", "Rights or copyright statement."),
    "source": ("description", "Source of the book; it can name a file or a person."),
    "date": ("time", "A date of the book."),
}


def inspect_epub(data):
    ins = new_inspection("EPUB")
    zf = _epub_open(data)
    if (_part(zf, "mimetype") or "").strip().encode() != EPUB_MIME:
        raise ValueError("not a valid EPUB: the mimetype entry is missing or wrong")
    ins["checked"] = ["META-INF/container.xml, the OPF metadata (dc:creator, dc:contributor, dc:publisher, dc:rights, "
                      "dc:source, dc:date, dcterms:modified, tool meta values), signature parts"]
    ins["not_checked"] = [EPUB_NOT_CHECKED]
    counts = {}
    for path in _epub_opf_paths(zf):
        for rec in _epub_scan(_epub_text(zf, path)):
            if rec["block"]:
                counts[rec["block"]] = counts.get(rec["block"], 0) + 1
            if rec["local"] in _EPUB_INFO:
                kind, why = _EPUB_INFO[rec["local"]]
            elif rec["block"] == "dates":
                kind, why = "time", "Time of the last change of the book."
            elif rec["block"] == "software":
                kind, why = "software", "Value written by a tool that made or changed the book."
            else:
                continue
            if rec["text"]:
                ins["items"].append(item("EPUB " + path, rec["key"], rec["text"][:300], kind, why))
    ins["blocks"].update(counts)
    names = zf.namelist()
    sig = [n for n in names if n in ("META-INF/signatures.xml", "META-INF/rights.xml")]
    if sig:
        ins["provenance"]["signatures"].append("EPUB signature or rights part(s): " + ", ".join(sig))
    ins["provenance"]["c2pa"] = "possible (heuristic)" if any(b"c2pa" in n.lower().encode() for n in names) else None
    ins["plan_notes"] = [EPUB_STRIP_NOTE]
    return ins


def _epub_text(zf, name):
    raw = zf.read(name)
    if len(raw) > MAX_PART:
        raise ValueError(f"{name} is too large")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} is not valid UTF-8; this tool does not rewrite it") from exc


def _epub_kept(zf, path):
    return sorted(r["key"] + "|" + r["text"] for r in _epub_scan(_epub_text(zf, path))
                  if r["local"] in ("title", "language", "identifier"))


def strip_epub(data, only):
    zin = _epub_open(data)
    repl, removed = {}, []
    for path in _epub_opf_paths(zin):
        opf = _epub_text(zin, path)
        recs = [r for r in _epub_scan(opf) if r["block"] in only]
        if not recs:
            continue
        out, pos = [], 0
        for r in recs:
            out.append(opf[pos:r["start"]])
            pos = r["end"]
        out.append(opf[pos:])
        repl[path] = "".join(out).encode("utf-8")
        for b in sorted({r["block"] for r in recs}):
            removed.append(f"{b} ({sum(1 for r in recs if r['block'] == b)} element(s) in {path})")
    new = rewrite_zip(zin, repl, mimetype_first=True)
    # Verify the new file before anything is written.
    zout = _epub_open(new)
    infos = zout.infolist()
    if not infos or infos[0].filename != "mimetype" or infos[0].compress_type != zipfile.ZIP_STORED:
        raise ValueError("internal check failed: mimetype is not the first stored entry")
    if sorted(zout.namelist()) != sorted(zin.namelist()):
        raise ValueError("internal check failed: the list of parts changed")
    for n in zin.namelist():
        if n not in repl and zin.read(n) != zout.read(n):
            raise ValueError(f"internal check failed: the part {n} changed")
    for path in _epub_opf_paths(zout):
        left = [r for r in _epub_scan(_epub_text(zout, path)) if r["block"] in only]
        if left:
            raise ValueError("internal check failed: a chosen element is still present")
        if _epub_kept(zin, path) != _epub_kept(zout, path):
            raise ValueError("internal check failed: title, language or identifier changed")
    return new, removed


# --- MP3 (ID3) -------------------------------------------------------------------------------------

MP3_NOT_CHECKED = ("APEv2 and Lyrics3 tags, an ID3v2 tag at the end of the file, the extended ID3v1 tag, "
                   "and anything inside the audio frames")
MP3_STRIP_NOTE = ("The whole ID3v2 tag and the whole ID3v1 tag are removed. The audio frames stay byte-identical. "
                  "The tool does not edit or re-encode audio.")
_ID3_FRAMES = {
    "TPE1": ("Artist", "identity"), "TPE2": ("Album artist", "identity"), "TALB": ("Album", "description"),
    "TIT2": ("Title", "description"), "TCOM": ("Composer", "identity"), "TENC": ("Encoded by", "identity"),
    "TSSE": ("Encoding software", "software"),
    "TP1": ("Artist", "identity"), "TP2": ("Album artist", "identity"), "TAL": ("Album", "description"),
    "TT2": ("Title", "description"), "TCM": ("Composer", "identity"), "TEN": ("Encoded by", "identity"),
    "TSS": ("Encoding software", "software"),
}
_ID3_EXPLAIN = {"identity": "A name stored in the tag.", "description": "A description of the recording.",
                "software": "Program that wrote the tag or encoded the audio.", "other": "Other tag data."}


def _syncsafe(b):
    if any(x & 0x80 for x in b):
        raise ValueError("damaged ID3v2 tag: a size field is not synchsafe")
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3v2_at(data, pos):
    """Parse the ID3v2 header at data[pos]. Return None if there is none, else a dict."""
    if data[pos:pos + 3] != b"ID3":
        return None
    h = data[pos:pos + 10]
    if len(h) < 10 or h[3] not in (2, 3, 4) or h[4] == 0xFF:
        raise ValueError("damaged or unsupported ID3v2 header")
    flags, size = h[5], _syncsafe(h[6:10])
    footer = bool(flags & 0x10) and h[3] == 4
    total = 10 + size + (10 if footer else 0)
    if pos + total > len(data):
        raise ValueError("damaged ID3v2 tag: it is longer than the file")
    if footer and data[pos + 10 + size:pos + 13 + size] != b"3DI":
        raise ValueError("damaged ID3v2 tag: the footer flag is set but the footer is missing")
    return {"version": h[3], "flags": flags, "size": size, "footer": footer, "total": total}


def _id3_text(enc, raw):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(enc, "latin-1")
    try:
        s = raw.decode(codec, "replace")
    except (LookupError, ValueError):
        s = raw.decode("latin-1", "replace")
    return [p.strip("﻿") for p in s.split("\x00") if p.strip("﻿")]


def _id3_frames(data, pos, hdr, notes):
    """Return a list of (frame_id, payload) of the ID3v2 tag at `pos`."""
    ver, flags, size = hdr["version"], hdr["flags"], hdr["size"]
    body = data[pos + 10:pos + 10 + size]
    if flags & 0x80 and ver in (2, 3):
        body = body.replace(b"\xff\x00", b"\xff")  # undo the unsynchronisation of the whole tag
    i = 0
    if flags & 0x40:
        if ver == 2:
            raise ValueError("a compressed ID3v2.2 tag is not supported")
        if len(body) >= 4:
            i = (4 + int.from_bytes(body[:4], "big")) if ver == 3 else _syncsafe(body[:4])
    idlen, hlen = (3, 6) if ver == 2 else (4, 10)
    frames, skipped = [], 0
    while i + hlen <= len(body):
        fid = body[i:i + idlen]
        if not re.fullmatch(rb"[A-Z0-9]+", fid):
            break  # padding
        if ver == 2:
            fsize, fl = int.from_bytes(body[i + 3:i + 6], "big"), b"\0\0"
        elif ver == 3:
            fsize, fl = int.from_bytes(body[i + 4:i + 8], "big"), body[i + 8:i + 10]
        else:
            fsize, fl = _syncsafe(body[i + 4:i + 8]), body[i + 8:i + 10]
        if i + hlen + fsize > len(body):
            raise ValueError("damaged ID3v2 tag: a frame is longer than the tag")
        payload = body[i + hlen:i + hlen + fsize]
        i += hlen + fsize
        if ver == 3 and fl[1] & 0xC0 or ver == 4 and fl[1] & 0x0C:
            skipped += 1  # compressed or encrypted: the content cannot be read
            continue
        if ver == 3 and fl[1] & 0x20 or ver == 4 and fl[1] & 0x40:
            payload = payload[1:]  # grouping byte
        if ver == 4:
            if fl[1] & 0x01:
                payload = payload[4:]  # data length indicator
            if fl[1] & 0x02:
                payload = payload.replace(b"\xff\x00", b"\xff")
        frames.append((fid.decode("ascii"), payload))
    if skipped:
        notes.append(f"{skipped} ID3v2 frame(s) are compressed or encrypted and were not read.")
    return frames


def _id3_items(frames, source):
    items, other, owners, c2pa = [], 0, [], False
    for fid, p in frames:
        if fid in _ID3_FRAMES and p:
            label, kind = _ID3_FRAMES[fid]
            v = "; ".join(_id3_text(p[0], p[1:]))
            if v:
                items.append(item(source, f"{fid} {label}", v[:300], kind, _ID3_EXPLAIN[kind]))
        elif fid in ("COMM", "COM") and len(p) > 4:
            v = "; ".join(_id3_text(p[0], p[4:]))
            if v:
                items.append(item(source, f"{fid} Comment", v[:300], "description", "A free-text comment."))
        elif fid in ("TXXX", "TXX") and len(p) > 1:
            parts = _id3_text(p[0], p[1:])
            if parts:
                items.append(item(source, f"{fid} {parts[0]}"[:60], "; ".join(parts[1:])[:300], "other", "A custom text field."))
        elif fid in ("APIC", "PIC"):
            items.append(item(source, fid + " Picture", f"present ({len(p)} bytes)", "other",
                              "An embedded picture, often the cover; it can show a person or a place."))
        else:
            other += 1
            if fid in ("GEOB", "PRIV") and b"c2pa" in p[:300].lower():
                c2pa = True
            if fid in ("GEOB", "PRIV"):
                owners.append(fid)
    return items, other, owners, c2pa


def _id3v1(data, start):
    if len(data) - start >= 128 and data[-128:-125] == b"TAG":
        return data[-128:]
    return None


def inspect_mp3(data):
    ins = new_inspection("MP3")
    ins["checked"] = ["ID3v2 header and frames (TPE1, TPE2, TALB, TIT2, TCOM, COMM, TXXX, APIC, TENC, TSSE), ID3v1 tag"]
    ins["not_checked"] = [MP3_NOT_CHECKED]
    pos, tags, c2pa = 0, 0, False
    while True:
        hdr = _id3v2_at(data, pos)
        if hdr is None:
            break
        tags += 1
        frames = _id3_frames(data, pos, hdr, ins["notes"])
        items, other, owners, has_c2pa = _id3_items(frames, "ID3v2")
        ins["items"] += items
        if other:
            ins["notes"].append(f"{other} other ID3v2 frame(s) were counted but not read"
                                + (f" ({', '.join(sorted(set(owners)))} may hold software data)" if owners else "") + ".")
        c2pa = c2pa or has_c2pa
        pos += hdr["total"]
    if tags:
        ins["blocks"]["id3v2"] = tags
    v1 = _id3v1(data, pos)
    if v1:
        ins["blocks"]["id3v1"] = 1
        f = lambda b: b.split(b"\0")[0].decode("latin-1").strip()  # noqa: E731
        for key, raw, kind in (("title", v1[3:33], "description"), ("artist", v1[33:63], "identity"),
                               ("album", v1[63:93], "description"), ("year", v1[93:97], "time"),
                               ("comment", v1[97:127], "description")):
            if f(raw):
                ins["items"].append(item("ID3v1", key, f(raw), kind, _ID3_EXPLAIN.get(kind, "A field of the old ID3v1 tag.")))
    if c2pa:
        ins["provenance"]["c2pa"] = True
        ins["strip_refusal"] = ("C2PA data sits inside the ID3v2 tag; this tool removes C2PA data only from JPEG "
                                "and PNG files")
    else:
        ins["provenance"]["c2pa"] = "possible (heuristic)" if b"c2pa" in data[:pos] + data[-128:] else None
    ins["notes"].append("The audio frames are not read or changed.")
    ins["plan_notes"] = [MP3_STRIP_NOTE]
    return ins


def strip_mp3(data, only):
    start = 0
    while True:
        hdr = _id3v2_at(data, start)
        if hdr is None:
            break
        start += hdr["total"]
    end = len(data) - 128 if _id3v1(data, start) else len(data)
    head = b"" if "id3v2" in only else data[:start]
    tail = b"" if "id3v1" in only else data[end:]
    new = head + data[start:end] + tail
    removed = []
    if "id3v2" in only and start:
        removed.append(f"id3v2 ({start} bytes)")
    if "id3v1" in only and end != len(data):
        removed.append("id3v1 (128 bytes)")
    if new[len(head):len(new) - len(tail)] != data[start:end]:
        raise ValueError("internal check failed: the audio frames changed")
    if "id3v2" in only and _id3v2_at(new, 0) is not None:
        raise ValueError("internal check failed: an ID3v2 tag is still present")
    if "id3v1" in only and _id3v1(new, 0):
        raise ValueError("internal check failed: the ID3v1 tag is still present")
    return new, removed


# --- MP4 / M4A / MOV ----------------------------------------------------------------------------------

MP4_FORMAT = "MP4/M4A/MOV"
MP4_NOT_CHECKED = ("metadata fields in other places were NOT read (for example udta inside tracks and the content of "
                   "uuid atoms other than XMP); audio and video data")
MP4_STRIP_NOTE = ("The udta atom becomes a free atom and its bytes are set to zero. Sizes and offsets stay the same. "
                  "The tool reports the fields in moov/meta (for example iPhone make, model and location) and the uuid "
                  "atoms, but it does not remove them.")
_MDTA_KINDS = {"com.apple.quicktime.location.iso6709": "location", "com.apple.quicktime.make": "device",
               "com.apple.quicktime.model": "device", "com.apple.quicktime.software": "software",
               "com.apple.quicktime.creationdate": "time", "com.apple.quicktime.author": "identity",
               "com.apple.quicktime.artist": "identity", "com.apple.quicktime.displayname": "description"}
C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
XMP_UUID = bytes.fromhex("be7acfcb97a942e89c71999491e3afac")
_MP4_TEXT_KEYS = {
    b"\xa9nam": ("title", "description"), b"\xa9ART": ("artist", "identity"), b"\xa9alb": ("album", "description"),
    b"\xa9too": ("software", "software"), b"\xa9day": ("date", "time"), b"\xa9cmt": ("comment", "description"),
    b"\xa9xyz": ("location", "location"), b"\xa9wrt": ("composer", "identity"), b"aART": ("album artist", "identity"),
    b"cprt": ("copyright", "identity"), b"\xa9gen": ("genre", "description"),
}


def _mp4_atoms(data, start, end, top=False):
    """List (type, atom_start, header_len, atom_end) of the atoms between start and end."""
    out, pos = [], start
    while pos + 8 <= end:
        size = int.from_bytes(data[pos:pos + 4], "big")
        typ, hlen = data[pos + 4:pos + 8], 8
        if size == 1:
            if pos + 16 > end:
                raise ValueError("damaged MP4 file: an atom header is cut short")
            size, hlen = int.from_bytes(data[pos + 8:pos + 16], "big"), 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            raise ValueError("damaged MP4 file: an atom has a size that is too small")
        if pos + size > end:
            if top and typ == b"mdat":
                size = end - pos  # an incomplete download: keep what is there
            else:
                raise ValueError(f"damaged MP4 file: the atom {typ.decode('latin-1')!r} is longer than its parent")
        out.append((typ, pos, hlen, pos + size))
        pos += size
    return out


def _mp4_udtas(data):
    """Return the atoms of the moov atoms and the (start, header_len, end) of each moov/udta atom."""
    top = _mp4_atoms(data, 0, len(data), top=True)
    moovs = [a for a in top if a[0] == b"moov"]
    udtas = []
    for _t, s, h, e in moovs:
        udtas += [(us, uh, ue) for t, us, uh, ue in _mp4_atoms(data, s + h, e) if t == b"udta"]
    return top, moovs, udtas


def _mp4_value(data, a):
    """Read the text of an ilst item atom, or None if it has no text."""
    _t, s, h, e = a
    for t, ds, dh, de in _mp4_atoms(data, s + h, e):
        if t == b"data" and de - ds >= dh + 8:
            flags = int.from_bytes(data[ds + dh + 1:ds + dh + 4], "big")
            payload = data[ds + dh + 8:de]
            if flags == 1:
                return payload.decode("utf-8", "replace").strip("\x00 ")
            return ("<image, %d bytes>" if flags in (13, 14) else "<binary, %d bytes>") % len(payload)
    return None


def _mp4_udta_items(data, us, uh, ue, ins):
    for t, s, h, e in _mp4_atoms(data, us + uh, ue):
        if t in _MP4_TEXT_KEYS and t[:1] == b"\xa9" and e - s >= h + 4:
            _label, kind = _MP4_TEXT_KEYS[t]
            v = data[s + h + 4:e].decode("utf-8", "replace").strip("\x00 ")
            if v:
                ins["items"].append(item("MP4 udta", t.decode("latin-1"), v[:300], kind,
                                         "Location in the video or audio file." if kind == "location"
                                         else "Text stored by the recording or editing program."))
        elif t == b"meta":
            skip = 0 if data[s + h + 4:s + h + 8] == b"hdlr" else 4
            sub = _mp4_atoms(data, s + h + skip, e)
            if any(x[0] == b"keys" for x in sub):  # numeric item types: the names come from the keys atom
                _mp4_mdta_items(data, (t, s, h, e), ins, "MP4 ilst")
                continue
            for it, istart, ih, ie in sub:
                if it != b"ilst":
                    continue
                for a in _mp4_atoms(data, istart + ih, ie)[:60]:
                    v = _mp4_value(data, a)
                    kind = _MP4_TEXT_KEYS.get(a[0], (None, "other"))[1]
                    if v:
                        ins["items"].append(item("MP4 ilst", a[0].decode("latin-1"), v[:300], kind,
                                                 "Location in the video or audio file." if kind == "location"
                                                 else "Tag written by the recording or editing program."))


def _mp4_mdta_items(data, a, ins, source="MP4 moov/meta"):
    """Report the keys/ilst fields of a moov/meta atom (QuickTime style, as written by iPhones). Read only."""
    _t, s, h, e = a
    skip = 0 if data[s + h + 4:s + h + 8] == b"hdlr" else 4
    kids = _mp4_atoms(data, s + h + skip, e)
    names = []
    for t, ks, kh, ke in kids:
        if t == b"keys" and ke - ks >= kh + 8:
            pos = ks + kh + 8
            for _i in range(int.from_bytes(data[ks + kh + 4:ks + kh + 8], "big")):
                if pos + 8 > ke:
                    break
                size = int.from_bytes(data[pos:pos + 4], "big")
                if size < 8:
                    break
                names.append(data[pos + 8:pos + size].decode("utf-8", "replace"))
                pos += size
    for t, ls, lh, le in kids:
        if t != b"ilst":
            continue
        for a2 in _mp4_atoms(data, ls + lh, le)[:60]:
            idx = int.from_bytes(a2[0], "big")
            if not 1 <= idx <= len(names):
                continue
            v = _mp4_value(data, a2)
            if v:
                name = names[idx - 1]
                kind = _MDTA_KINDS.get(name.lower(), "other")
                ins["items"].append(item(source, name, v[:300], kind,
                                         "Location in the video file." if kind == "location"
                                         else "Field written by the camera or editing program. This tool does not remove it."))


def inspect_mp4(data):
    ins = new_inspection(MP4_FORMAT)
    ins["checked"] = ["atoms: moov/udta, moov/udta/meta/ilst (©nam, ©ART, ©alb, ©too, ©day, ©cmt, ©xyz), moov/meta keys, uuid atoms"]
    ins["not_checked"] = [MP4_NOT_CHECKED]
    top, moovs, udtas = _mp4_udtas(data)
    brand = data[8:12].decode("latin-1") if len(data) >= 12 and data[4:8] == b"ftyp" else ""
    if brand:
        ins["notes"].append(f"File type brand: {brand.strip()}.")
    c2pa_in_udta = False
    filled = 0
    for us, uh, ue in udtas:
        if ue - us > uh:
            filled += 1
        try:
            _mp4_udta_items(data, us, uh, ue, ins)
        except ValueError:
            ins["notes"].append("A udta atom holds data that could not be parsed; the strip still covers it.")
        kids = []
        try:
            kids = _mp4_atoms(data, us + uh, ue)
        except ValueError:
            pass
        c2pa_in_udta = c2pa_in_udta or any(t == b"uuid" and data[s + h:s + h + 16] == C2PA_UUID for t, s, h, e in kids)
    uuids = [a for a in top if a[0] == b"uuid"]
    for _t, s, h, e in moovs:
        kids = _mp4_atoms(data, s + h, e)
        uuids += [a for a in kids if a[0] == b"uuid"]
        for a in kids:
            if a[0] == b"meta":
                try:
                    _mp4_mdta_items(data, a, ins)
                except ValueError:
                    ins["notes"].append("A moov/meta atom holds data that could not be parsed.")
    c2pa = c2pa_in_udta
    for _t, s, h, e in uuids:
        uid = data[s + h:s + h + 16]
        if uid == C2PA_UUID:
            c2pa = True
        elif uid == XMP_UUID:
            xml = data[s + h + 16:min(e, s + h + 16 + 1024 * 1024)].decode("utf-8", "replace")
            ins["items"] += xmp_items(xml, "MP4 XMP uuid atom")
            ins["notes"].append("An XMP packet is stored in a uuid atom. This tool reports it but does not remove it.")
        else:
            ins["items"].append(item("MP4 uuid atom", uid.hex(), f"{e - s} bytes; content not read", "other",
                                     "Vendor-specific data. This tool reports it but does not remove it."))
    if filled:
        ins["blocks"]["udta"] = filled
    if c2pa:
        ins["provenance"]["c2pa"] = True
        ins["notes"].append("C2PA data was found in a uuid atom. It is never validated here.")
    else:
        ins["provenance"]["c2pa"] = "possible (heuristic)" if b"c2pa" in data else None
    if c2pa_in_udta:
        ins["strip_refusal"] = ("C2PA data sits inside the udta atom; this tool removes C2PA data only from JPEG "
                                "and PNG files")
    ins["notes"].append("Absence of fields here does not prove the file has no other metadata.")
    ins["plan_notes"] = [MP4_STRIP_NOTE]
    return ins


def strip_mp4(data, only, ins=None):
    if "udta" not in only:
        raise ValueError("no removable block chosen")
    _top, _moovs, udtas = _mp4_udtas(data)
    out = bytearray(data)
    spans = []
    for us, uh, ue in udtas:
        if ue - us > uh:
            out[us + 4:us + 8] = b"free"
            out[us + uh:ue] = b"\x00" * (ue - us - uh)
            spans.append((us + 4, ue))
    new = bytes(out)
    if len(new) != len(data):
        raise ValueError("internal check failed: the output length differs from the input length")
    pos = 0
    for s, e in spans:  # outside the changed atoms every byte must be equal
        if data[pos:s] != new[pos:s]:
            raise ValueError("internal check failed: bytes outside udta changed")
        pos = e
    if data[pos:] != new[pos:]:
        raise ValueError("internal check failed: bytes outside udta changed")
    if _mp4_atoms(new, 0, len(new), top=True) != _mp4_atoms(data, 0, len(data), top=True):
        raise ValueError("internal check failed: the atom layout changed")
    if any(ue - us > uh for us, uh, ue in _mp4_udtas(new)[2]):
        raise ValueError("internal check failed: a udta atom is still present")
    fields = [f"udta/{i['key']}" for i in (ins or {}).get("items", []) if i["source"] in ("MP4 udta", "MP4 ilst")]
    return new, [f"udta atom changed to free ({len(spans)} atom(s) zeroed)"] + fields


# --- dispatch ------------------------------------------------------------------------------------

def _looks_like_video_mp4(data):
    """A file with an ftyp atom and a top-level moov atom. A HEIC or AVIF photo has no moov atom."""
    if data[4:8] != b"ftyp":
        return False
    try:
        return any(a[0] == b"moov" for a in _mp4_atoms(data, 0, len(data), top=True))
    except ValueError:
        return False


# Everything a damaged or hostile file can raise from the parsers below. Callers only catch ValueError,
# so these are turned into ValueError at the two entry points (detect_and_inspect and strip).
PARSE_ERRORS = (zipfile.BadZipFile, struct.error, zlib.error, NotImplementedError, IndexError, KeyError,
                OverflowError, RuntimeError, EOFError)


def detect_and_inspect(path, data):
    low = path.lower()
    try:
        if data[:2] == b"\xff\xd8":
            return inspect_jpeg(data)
        if data[:8] == PNG_SIG:
            return inspect_png(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return inspect_webp(data)
        if data[:5] == b"%PDF-":
            return inspect_pdf(data)
        if data[:4] == b"PK\x03\x04" and low.endswith((".docx", ".xlsx", ".pptx")):
            return inspect_ooxml(data, "OOXML (" + low.rsplit(".", 1)[1] + ")")
        if data[:4] == b"PK\x03\x04" and (low.endswith(".epub") or (data[30:38] == b"mimetype" and EPUB_MIME in data[38:80])):
            return inspect_epub(data)
        if low.endswith(".mp3"):
            return inspect_mp3(data)
        if low.endswith((".mp4", ".m4a", ".m4v", ".mov")) or _looks_like_video_mp4(data):
            return inspect_mp4(data)
        if low.endswith((".html", ".htm")):
            return inspect_html(data)
        if low.endswith((".txt", ".md")):
            ins = new_inspection("plain text")
            ins["checked"] = ["plain text has no embedded metadata fields"]
            ins["not_checked"] = ["file-system metadata (owner, timestamps, extended attributes)"]
            return ins
    except (ValueError, *PARSE_ERRORS) as exc:
        raise ValueError(f"could not parse as {low.rsplit('.', 1)[-1]}: {exc}") from exc
    return inspect_unknown(data, "unsupported format")


def strip_supported(ins):
    return ins["format"] in ("JPEG", "PNG", "PDF", "HTML", "EPUB", "MP3", MP4_FORMAT) or ins["format"].startswith("OOXML")


def strip(path, data, ins, only, remove_c2pa=False):
    try:
        return _strip(data, ins, only, remove_c2pa)
    except PARSE_ERRORS as exc:
        raise ValueError(f"could not rewrite this {ins['format']} file: {exc}. Nothing was written") from exc


def _strip(data, ins, only, remove_c2pa):
    if ins["format"] == "JPEG":
        return strip_jpeg(data, only, remove_c2pa)
    if ins["format"] == "PNG":
        return strip_png(data, only, remove_c2pa)
    if ins["format"].startswith("OOXML"):
        return strip_ooxml(data, only)
    if ins["format"] == "PDF":
        return strip_pdf(data, only)
    if ins["format"] == "HTML":
        return strip_html(data, only)
    if ins["format"] == "EPUB":
        return strip_epub(data, only)
    if ins["format"] == "MP3":
        return strip_mp3(data, only)
    if ins["format"] == MP4_FORMAT:
        return strip_mp4(data, only, ins)
    raise ValueError(f"stripping {ins['format']} is not supported")


def format_inspection(ins, path=""):
    lines = [f"Format: {ins['format']}" + (f"   File: {path}" if path else ""),
             "Checked: " + "; ".join(ins["checked"]) if ins["checked"] else "Checked: nothing"]
    if ins["not_checked"]:
        lines.append("NOT checked: " + "; ".join(ins["not_checked"]))
    if ins["items"]:
        lines.append("\nMetadata found:")
        for it in ins["items"]:
            flag = " [personal]" if it["personal"] else ""
            lines.append(f"- {it['source']} / {it['key']}: {it['value']}{flag}\n    {it['explanation']}")
    else:
        lines.append("\nNo metadata fields were found in the regions that were checked.")
    prov = ins["provenance"]
    if prov["c2pa"] is True:
        lines.append("\nPROVENANCE: C2PA content credentials are present. Their signature was NOT validated here. "
                     "Removing other metadata would invalidate them.")
    elif prov["c2pa"]:
        lines.append(f"\nPROVENANCE: possible C2PA data ({prov['c2pa']}); not parsed.")
    for s in prov["signatures"]:
        lines.append(f"SIGNATURE: {s}. Editing the file would invalidate it. Validity was NOT checked.")
    for note in ins["notes"]:
        lines.append(f"Note: {note}")
    removable = [b for b in ins["blocks"] if b != "c2pa" and ins["blocks"][b]]
    if removable and strip_supported(ins):
        lines.append("Removable blocks: " + ", ".join(sorted(removable)))
    return "\n".join(lines)
