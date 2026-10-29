#!/usr/bin/env python3
"""HumanTouch File Cleaner: clean invisible Unicode in a file and write a new copy.

Usage:
  python3 scripts/file_clean.py FILE [--scan] [--output PATH] [--bidi MODE]
                                [--keep-nbsp] [--protect-code] [--break-provenance]

Supported (what is actually done):
  .txt .md   text cleaned; Markdown code is protected automatically
  .html .htm text nodes cleaned; tags, attributes, comments, <script>, <style>,
             <pre>, <code>, <textarea> are left byte-for-byte unchanged
  .docx      text inside <w:t>/<w:delText> of body, headers, footers, notes and
             comments cleaned; every other part of the package is copied as-is
  .pdf       text is EXTRACTED with pdftotext (if installed), cleaned, and saved
             as a new .txt. The PDF is never rewritten and its layout is not
             preserved.
  images     no text layer is read (no OCR). Use metadata_inspect.py instead.

The original is never modified or overwritten; the result is NAME.clean.EXT
(or --output). --scan reports what would change and writes nothing. A .docx
with a digital signature is refused unless --break-provenance is given,
because any edit invalidates the signature.

Fully local: no network. Exit codes: 0 ok, 1 error, 2 unsupported/refused.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _clean_lib as lib  # noqa: E402
import _meta_lib as meta  # noqa: E402

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".heic", ".bmp")
HTML_PROTECT_RE = re.compile(
    r"<!--.*?-->|<(script|style|pre|code|textarea)\b.*?</\1\s*>|<[^>]*>", re.DOTALL | re.IGNORECASE)
DOCX_TEXT_RE = re.compile(r"(<w:(?:t|delText)\b[^>]*>)(.*?)(</w:(?:t|delText)>)", re.DOTALL)
DOCX_PARTS_RE = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml")


def _opts(args):
    return {"bidi": args.bidi, "keep_nbsp": args.keep_nbsp, "scan_only": args.scan}


def clean_txt(raw, args, is_md):
    text = raw.decode("utf-8")
    spans = lib.code_spans(text) if (args.protect_code or is_md) else []
    r = lib.clean_text(text, protected=spans, **_opts(args))
    return r.text.encode("utf-8"), [("text", r)]


def clean_html(raw, args):
    text = raw.decode("utf-8")
    spans = [m.span() for m in HTML_PROTECT_RE.finditer(text)]
    r = lib.clean_text(text, protected=spans, decode_entities=True, **_opts(args))
    notes = ["Named entities such as &nbsp; are left as written."]
    return r.text.encode("utf-8"), [("html", r)], notes


def _fix_preserve(xml):
    def fix(m):
        open_tag, text = m.group(1), m.group(2)
        if (text != text.strip()) and "xml:space" not in open_tag:
            open_tag = open_tag[:-1] + ' xml:space="preserve">'
        return open_tag + text + m.group(3)
    return DOCX_TEXT_RE.sub(fix, xml)


def clean_docx(raw, args):
    zin = meta._open_zip(raw)
    sigs = [n for n in zin.namelist() if n.startswith("_xmlsignatures/")]
    if sigs and not args.break_provenance:
        raise PermissionError("this .docx has a digital signature; editing it would invalidate the signature. "
                              "Re-run with --break-provenance only if you accept that")
    repl, results = {}, []
    for name in zin.namelist():
        if not DOCX_PARTS_RE.fullmatch(name):
            continue
        xml = meta._part(zin, name)
        ranges = [m.span(2) for m in DOCX_TEXT_RE.finditer(xml)]
        spans = lib.complement(ranges, len(xml))
        r = lib.clean_text(xml, protected=spans, decode_entities=True, **_opts(args))
        results.append((name, r))
        if r.changed:
            repl[name] = _fix_preserve(r.text).encode("utf-8")
    notes = ["Only the text runs of the document body, headers, footers, notes and comments were examined.",
             "Document properties are not touched; use metadata_inspect.py for those."]
    if sigs:
        notes.append("PROVENANCE WARNING: the signature part was left in place but will no longer validate.")
    return (meta.rewrite_zip(zin, repl) if not args.scan else raw), results, notes


def extract_pdf(path):
    exe = shutil.which("pdftotext")
    if not exe:
        raise PermissionError("pdftotext (poppler) is not installed, so no text can be extracted from the PDF. "
                              "Nothing was written. (Install it yourself, e.g. `brew install poppler`, if you want this.)")
    proc = subprocess.run([exe, "-enc", "UTF-8", "-layout", os.path.abspath(path), "-"],
                          capture_output=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise ValueError("pdftotext could not read the PDF: " + proc.stderr.decode("utf-8", "replace").strip()[:200])
    if len(proc.stdout) > lib.MAX_INPUT_BYTES:
        raise ValueError("extracted text is too large")
    return proc.stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HumanTouch File Cleaner")
    ap.add_argument("path")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--output")
    ap.add_argument("--bidi", choices=["auto", "strip", "keep"], default="auto")
    ap.add_argument("--keep-nbsp", action="store_true")
    ap.add_argument("--protect-code", action="store_true")
    ap.add_argument("--break-provenance", action="store_true")
    args = ap.parse_args(argv)
    lib.setup_stdio()
    low = args.path.lower()

    try:
        if low.endswith(IMAGE_EXTS):
            print("Images have no text layer here: no OCR is performed, so there is no text to clean.\n"
                  "Use `metadata_inspect.py inspect` to see what the image reveals. Nothing was written.", file=sys.stderr)
            return 2
        raw = lib.read_input_bytes(args.path)
        notes, new_ext = [], None
        if low.endswith((".txt", ".md")):
            data, results = clean_txt(raw, args, low.endswith(".md"))
        elif low.endswith((".html", ".htm")):
            data, results, notes = clean_html(raw, args)
        elif low.endswith(".docx"):
            data, results, notes = clean_docx(raw, args)
        elif low.endswith(".pdf"):
            text = extract_pdf(args.path).decode("utf-8", "replace")
            r = lib.clean_text(text, **_opts(args))
            data, results, new_ext = r.text.encode("utf-8"), [("pdf text", r)], ".txt"
            notes = ["PDF: text was extracted; layout, fonts, images and the PDF itself are NOT preserved or modified.",
                     "Scanned PDFs without a text layer yield no text (no OCR)."]
        else:
            print(f"Unsupported file type: {os.path.splitext(args.path)[1] or '(none)'}. "
                  "Supported: .txt .md .html .htm .docx .pdf (text extraction). Nothing was written.", file=sys.stderr)
            return 2
    except UnicodeDecodeError:
        print("error: file is not valid UTF-8; convert it first (nothing was guessed or changed)", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f"error: {exc}. Nothing was written.", file=sys.stderr)
        return 1

    for label, r in results:
        if len(results) > 1 and not r.findings:
            continue
        print(f"[{label}]" if len(results) > 1 else "", end="\n" if len(results) > 1 else "")
        print(lib.format_report(r, scan_only=args.scan, limit_locations=not label.startswith("word/")))
    for n in notes:
        print(f"Note: {n}")

    if args.scan:
        print("SCAN ONLY: nothing was written.")
        return 0
    try:
        out = lib.pick_output_path(args.path, ".clean", args.output, new_ext)
        lib.write_new_file(out, data)
    except OSError as exc:
        print(f"error: {exc}. Nothing was written.", file=sys.stderr)
        return 1
    print(f"Cleaned copy written to: {out}\nOriginal left untouched: {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
