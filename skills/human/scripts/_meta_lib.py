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


def strip_jpeg(data, only):
    """Remove whole metadata blocks listed in `only`. ICC/JFIF/Adobe colour data is kept."""
    segs = jpeg_segments(data)
    out, pos, removed = [data[:2]], 2, []
    for s in segs:
        blk = _jpeg_block(s)
        out.append(data[pos:s["start"]])
        pos = s["start"]
        if blk in only and blk != "c2pa":
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


def strip_png(data, only):
    out, removed = [PNG_SIG], []
    for c in png_chunks(data):
        blk = PNG_BLOCKS.get(c["type"])
        if blk in only:
            removed.append(blk)
        else:
            out.append(data[c["start"]:c["end"]])
    tail_start = png_chunks(data)[-1]["end"]
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


def rewrite_zip(zin, replacements):
    """Copy a zip entry by entry (same order, timestamps, compression), swapping the bytes in `replacements`."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            ni = zipfile.ZipInfo(info.filename, info.date_time)
            ni.compress_type, ni.external_attr, ni.create_system = info.compress_type, info.external_attr, info.create_system
            zout.writestr(ni, replacements[info.filename] if info.filename in replacements else zin.read(info.filename))
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


def inspect_pdf(data):
    ins = new_inspection("PDF")
    if not data.startswith(b"%PDF-"):
        raise ValueError("not a PDF file")
    ins["checked"] = ["Info dictionary (when stored uncompressed), XMP packet, signature fields, encryption flag, markers"]
    ins["not_checked"] = ["objects stored inside compressed object streams", "signature validity", "page content and embedded images"]
    refs = re.findall(rb"/Info\s+(\d+)\s+(\d+)\s+R", data)
    info_body = None
    if refs:
        num, gen = refs[-1]
        ms = list(re.finditer(rb"(?<![\d])" + num + rb"\s+" + gen + rb"\s+obj(.*?)endobj", data, re.DOTALL))
        info_body = ms[-1].group(1) if ms else None
        if info_body is None:
            ins["notes"].append("The Info dictionary is stored in a compressed object stream and was not decoded.")
    for key, kind in PDF_INFO.items():
        if info_body is None:
            break
        m = re.search(rb"/" + key.encode() + rb"\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", info_body)
        if m:
            v = _pdf_string(m.group(1))
            if v.strip():
                ins["items"].append(item("PDF Info", key, v.strip()[:300], kind, "Document information dictionary entry."))
    if info_body is not None:
        ins["blocks"]["info"] = 1
    xm = re.search(rb"<\?xpacket begin.*?<\?xpacket end[^>]*\?>", data, re.DOTALL)
    if xm:
        ins["blocks"]["xmp"] = 1
        ins["items"] += xmp_items(xm.group(0).decode("utf-8", "replace"))
    if re.search(rb"/ByteRange\s*\[", data) or re.search(rb"/Type\s*/Sig\b", data):
        ins["provenance"]["signatures"].append("PDF digital signature field(s)")
    if re.search(rb"/Encrypt\b", data):
        ins["notes"].append("The PDF appears to be encrypted; text and some metadata may be unreadable here.")
    if data.count(b"%%EOF") > 1:
        ins["notes"].append("The PDF has several revisions (incremental updates): earlier versions of text or metadata may "
                            "still be present inside the file.")
    if b"/EmbeddedFile" in data:
        ins["notes"].append("The PDF contains embedded file attachments.")
    ins["provenance"]["c2pa"] = "possible (heuristic)" if b"c2pa" in data else None
    ins["notes"].append("Stripping PDF metadata is not supported by this tool; use a dedicated PDF sanitiser "
                        "(for example qpdf or Acrobat's Sanitize Document) after reviewing the list above.")
    return ins


# --- HTML --------------------------------------------------------------------------------------

HTML_META_KINDS = {"author": "identity", "generator": "software", "copyright": "identity", "description": "description",
                   "keywords": "description", "article:author": "identity", "og:site_name": "description"}


def inspect_html(text):
    ins = new_inspection("HTML")
    ins["checked"] = ["<meta> tags, <link rel=author>, HTML comments"]
    ins["not_checked"] = ["scripts, embedded images, and anything loaded from other URLs"]
    for tag in re.findall(r"<meta\b[^>]*>", text, re.IGNORECASE):
        attrs = {k.lower(): html.unescape(v) for k, _q, v in re.findall(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2', tag)}
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        if key in HTML_META_KINDS and attrs.get("content"):
            ins["items"].append(item("HTML meta", key, attrs["content"][:300], HTML_META_KINDS[key],
                                     "Information the page declares about itself."))
    for rel in re.findall(r'<link\b[^>]*\brel="author"[^>]*>', text, re.IGNORECASE):
        ins["items"].append(item("HTML link", "author", rel[:200], "identity", "Link to the author."))
    comments = re.findall(r"<!--(.*?)-->", text, re.DOTALL)
    if comments:
        ins["notes"].append(f"{len(comments)} HTML comment(s) present; they are invisible on the page but readable in the source.")
    ins["notes"].append("Stripping HTML metadata is not supported by this tool.")
    return ins


# --- dispatch ------------------------------------------------------------------------------------

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
        if low.endswith((".html", ".htm")):
            return inspect_html(data.decode("utf-8", "replace"))
        if low.endswith((".txt", ".md")):
            ins = new_inspection("plain text")
            ins["checked"] = ["plain text has no embedded metadata fields"]
            ins["not_checked"] = ["file-system metadata (owner, timestamps, extended attributes)"]
            return ins
    except (ValueError, zipfile.BadZipFile, struct.error) as exc:
        raise ValueError(f"could not parse as {low.rsplit('.', 1)[-1]}: {exc}") from exc
    return inspect_unknown(data, "unsupported format")


def strip_supported(ins):
    return ins["format"] in ("JPEG", "PNG") or ins["format"].startswith("OOXML")


def strip(path, data, ins, only):
    if ins["format"] == "JPEG":
        return strip_jpeg(data, only)
    if ins["format"] == "PNG":
        return strip_png(data, only)
    if ins["format"].startswith("OOXML"):
        return strip_ooxml(data, only)
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
