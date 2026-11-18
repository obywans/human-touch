#!/usr/bin/env python3
"""HumanTouch Metadata Inspector: see what a file reveals, remove it only with consent.

Usage:
  python3 scripts/metadata_inspect.py inspect FILE [--json]
  python3 scripts/metadata_inspect.py strip FILE [--only BLOCKS] [--output PATH]
                                       [--confirm] [--break-provenance]

inspect   Read-only. Lists the metadata found (EXIF, XMP, IPTC, PNG text,
          Office document properties, PDF info, HTML meta, EPUB, MP3, MP4/M4A), explains each
          field, and states what was NOT checked.
strip     Writes a NEW file without the chosen metadata blocks; the original is
          never modified. Without --confirm it only prints the plan and writes
          nothing. Supported: JPEG, PNG, DOCX/XLSX/PPTX, PDF, HTML, EPUB, MP3, MP4/M4A/MOV.
          Blocks are removed whole (not tag by tag). JPEG: exif, xmp, iptc,
          comment. PNG: text, exif, time. Office: people, organization,
          descriptive. PDF: info, xmp (overwritten in place; the file length
          does not change). HTML: meta-identity, meta-software, meta-social.
          EPUB: creator, publisher, rights, software, dates. MP3: id3v2, id3v1.
          MP4/M4A/MOV: udta (changed to free; sizes stay). Default: every block the file has except C2PA.

C2PA content credentials and digital signatures are never removed by this
tool. If the file has them, strip refuses, because changing the file would
make them fail validation, unless --break-provenance is also given. Their
validity is never checked here, only their presence.

Fully local: no network, no dependencies. Exit codes: 0 ok, 1 error,
2 refused (provenance/signature, or unsupported format).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _clean_lib as lib  # noqa: E402
import _meta_lib as meta  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HumanTouch Metadata Inspector")
    ap.add_argument("action", choices=["inspect", "strip"])
    ap.add_argument("path")
    ap.add_argument("--only", help="comma-separated block names to remove")
    ap.add_argument("--output")
    ap.add_argument("--confirm", action="store_true", help="user consented: actually write the stripped copy")
    ap.add_argument("--break-provenance", action="store_true",
                    help="allow stripping a file that carries C2PA credentials or a digital signature")
    ap.add_argument("--remove-provenance", action="store_true",
                    help="also remove C2PA content credentials (JPEG/PNG only). Needs --confirm; "
                         "the caller must have the owner's reason and must keep any disclosure the context requires")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    lib.setup_stdio()

    try:
        data = lib.read_input_bytes(args.path)
        ins = meta.detect_and_inspect(args.path, data)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.action == "inspect":
        print(json.dumps(ins, indent=2, ensure_ascii=False) if args.json else meta.format_inspection(ins, args.path))
        return 0

    if not meta.strip_supported(ins):
        print(f"Cannot strip {ins['format']}: not supported by this tool (inspection above still applies).\n"
              "Nothing was written.", file=sys.stderr)
        return 2

    if ins.get("strip_refusal"):
        print(f"REFUSED: {ins['strip_refusal']}. Nothing was written.", file=sys.stderr)
        return 2

    prov = ins["provenance"]
    has_prov = prov["c2pa"] is True or bool(prov["signatures"])
    available = {b for b, n in ins["blocks"].items() if n and b != "c2pa"}
    if args.remove_provenance and prov["c2pa"] is True and ins["format"] in ("JPEG", "PNG"):
        available.add("c2pa")
    chosen = {b.strip() for b in args.only.split(",")} if args.only else set(available)
    unknown = chosen - available
    if unknown:
        print(f"error: not present in this file or not removable: {', '.join(sorted(unknown))}. "
              f"Removable here: {', '.join(sorted(available)) or 'none'}", file=sys.stderr)
        return 1
    if not chosen:
        print("Nothing to remove: no removable metadata blocks were found. Nothing was written.")
        return 0

    sigs_only = bool(prov["signatures"]) and not args.break_provenance
    c2pa_handled = args.remove_provenance and "c2pa" in chosen
    if has_prov and not args.break_provenance and not (c2pa_handled and not sigs_only):
        print("REFUSED: this file carries "
              + ("C2PA content credentials" if prov["c2pa"] is True else "a digital signature")
              + ". Removing any metadata changes the file and would make that provenance fail validation.\n"
              "C2PA data itself is never removed by this tool. If you have a legitimate reason and accept that,\n"
              "run again with --break-provenance (and --confirm). Nothing was written.", file=sys.stderr)
        return 2

    print("Plan: remove block(s) " + ", ".join(sorted(chosen)) + f" from {args.path}")
    print("These blocks are removed whole; authorship or copyright notices stored in them go too."
          " The original file is not modified.")
    for note in ins.get("plan_notes", []):
        print(note)
    if c2pa_handled:
        print("PROVENANCE: the C2PA content credentials will be REMOVED from the new file. This is not proof "
              "that no provenance signal remains: invisible pixel watermarks and server-side records can survive.")
    elif has_prov:
        print("PROVENANCE WARNING: the credentials/signature stay in the file but will no longer validate.")
    if not args.confirm:
        print("DRY RUN: nothing was written. Re-run with --confirm after the user has agreed.")
        return 0

    try:
        new_data, removed = meta.strip(args.path, data, ins, chosen, args.remove_provenance)
        ext = os.path.splitext(args.path)[1]
        out = lib.pick_output_path(args.path, ".nometa", args.output, ext)
        after = meta.detect_and_inspect(out, new_data)  # verify before anything is written
        lib.write_new_file(out, new_data)
        with open(out, "rb") as fh:  # read the new file back: it must equal what was verified
            if fh.read() != new_data:
                raise ValueError("the file on disk differs from the verified data; delete " + out)
    except meta.StripRefused as exc:
        print(f"REFUSED: {exc}. Nothing was written.", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}. Nothing was written.", file=sys.stderr)
        return 1

    print(f"Written: {out}\nOriginal left untouched: {args.path}")
    print("Removed: " + (", ".join(removed) if removed else "nothing (blocks already empty)"))
    left = [i for i in after["items"] if i["personal"]]
    print("Re-inspection of the new file: " + (
        f"{len(left)} personal field(s) still found: " + "; ".join(f"{i['key']}" for i in left)
        if left else "no personal fields found in the regions checked."))
    print("Not checked in the new file: " + "; ".join(after["not_checked"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
