#!/usr/bin/env python3
"""HumanTouch Watermark Audit: report-only detection of hidden marks.

Usage:
  python3 scripts/watermark_audit.py PATH|-  [--json]

Text (TXT, Markdown, HTML, any UTF-8 text, or "-" for stdin) and the text of a
DOCX are scanned for hidden-character carriers and look-alike letters.
Images, PDF, DOCX and other files are also checked for provenance markers
(C2PA content credentials, digital signatures, XMP/EXIF) by presence only.

Never modifies anything and never writes a file. Fully local: no network.
Exit codes: 0 audit ran, 1 usage/input error.

Detection tables adapted from Watermarks Remover by Guillaume Meyer
(MIT), see _audit_lib.py.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _clean_lib as lib  # noqa: E402
import _meta_lib as meta  # noqa: E402
import _audit_lib as audit  # noqa: E402

DOCX_TEXT_RE = re.compile(r"<w:(?:t|delText)\b[^>]*>(.*?)</w:(?:t|delText)>", re.DOTALL)
DOCX_PARTS_RE = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml")
PROVENANCE_BINARY = (b"\xff\xd8", b"\x89PNG", b"RIFF", b"%PDF-", b"PK\x03\x04")


def docx_text(raw):
    zin = meta._open_zip(raw)
    parts = []
    for name in zin.namelist():
        if DOCX_PARTS_RE.fullmatch(name):
            xml = meta._part(zin, name)
            parts.append("".join(m.group(1) for m in DOCX_TEXT_RE.finditer(xml)))
    return "\n".join(parts)


def provenance_lines(path, raw):
    ins = meta.detect_and_inspect(path, raw)
    prov = ins.get("provenance", {})
    out = [f"Provenance markers ({ins.get('format')}):"]
    c2pa = prov.get("c2pa")
    out.append("  C2PA content credentials: " + ("PRESENT (presence only; validity is not checked)" if c2pa
                                                  else "not found" if c2pa is False else "could not be determined"))
    sigs = prov.get("signatures") or []
    out.append("  Digital signatures: " + (", ".join(map(str, sigs)) if sigs else "not found"))
    out.append("  Checked: " + "; ".join(ins.get("checked", [])))
    out.append("  NOT checked: " + "; ".join(ins.get("not_checked", [])))
    return out, ins


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HumanTouch Watermark Audit (report only)")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    lib.setup_stdio()
    try:
        raw = sys.stdin.buffer.read() if args.path == "-" else lib.read_input_bytes(args.path)
        text, prov, prov_ins = None, [], None
        if args.path != "-":
            if raw.startswith(PROVENANCE_BINARY) or args.path.lower().endswith((".html", ".htm")):
                prov, prov_ins = provenance_lines(args.path, raw)
            if raw[:4] == b"PK\x03\x04" and args.path.lower().endswith(".docx"):
                text = docx_text(raw)
        if text is None and not raw.startswith(PROVENANCE_BINARY):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("not UTF-8 text and not a format this audit reads")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = audit.audit_text(text) if text is not None else audit.AuditResult()
    if args.json:
        print(json.dumps({
            "label": args.path,
            "text_audited": text is not None,
            "findings": [{"codepoint": f"U+{f.cp:04X}", "name": f.name, "category": f.category,
                          "verdict": f.verdict, "line": f.line, "col": f.col, "reason": f.reason,
                          "source": f.source} for f in result.findings],
            "warnings": result.warnings,
            "provenance": prov_ins.get("provenance") if prov_ins else None,
            "checked": audit.CHECKED, "not_checked": audit.NOT_CHECKED[0],
        }, indent=2, ensure_ascii=False))
        return 0
    if text is not None:
        print(audit.format_report(result, args.path))
    else:
        print(f"Watermark audit: {args.path}\nNo text layer was read from this file type.")
    if prov:
        print()
        print("\n".join(prov))
    return 0


if __name__ == "__main__":
    sys.exit(main())
