#!/usr/bin/env python3
"""HumanTouch Text Cleaner: find and remove invisible/anomalous Unicode.

Usage:
  python3 scripts/text_clean.py scan  PATH|-            report only, changes nothing
  python3 scripts/text_clean.py clean PATH|- [options]  write a cleaned COPY

Options for clean:
  --output PATH    where to write the copy (default: NAME.clean.EXT next to the
                   input; never overwrites an existing file or the input)
  --protect-code   leave fenced code blocks and `inline code` untouched
  --bidi MODE      auto (default: keep direction marks in right-to-left text),
                   strip, or keep
  --keep-nbsp      keep every non-breaking space
  --json           machine-readable report

With "-" the text is read from stdin; clean then prints the cleaned text on
stdout and the report on stderr. Fully local: no network, no dependencies.
Exit codes: 0 ok, 1 usage/input error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _clean_lib as lib  # noqa: E402


def report_dict(result, scan_only):
    return {
        "mode": "scan" if scan_only else "clean",
        "changes": sum(1 for f in result.findings if f.action in ("removed", "replaced")),
        "findings": [
            {"codepoint": f"U+{f.cp:04X}", "name": f.name, "category": f.category,
             "action": f.action, "line": f.line, "col": f.col, "reason": f.reason}
            for f in result.findings
        ],
        "warnings": result.warnings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HumanTouch Text Cleaner")
    ap.add_argument("action", choices=["scan", "clean"])
    ap.add_argument("path")
    ap.add_argument("--output")
    ap.add_argument("--protect-code", action="store_true")
    ap.add_argument("--bidi", choices=["auto", "strip", "keep"], default="auto")
    ap.add_argument("--keep-nbsp", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    lib.setup_stdio()
    scan_only = args.action == "scan"

    try:
        raw = sys.stdin.buffer.read() if args.path == "-" else lib.read_input_bytes(args.path)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print("error: input is not valid UTF-8; convert it first (nothing was guessed or changed)", file=sys.stderr)
            return 1
        spans = lib.code_spans(text) if args.protect_code else []
        result = lib.clean_text(text, protected=spans, bidi=args.bidi,
                                keep_nbsp=args.keep_nbsp, scan_only=scan_only)
        report = json.dumps(report_dict(result, scan_only), indent=2, ensure_ascii=False) \
            if args.json else lib.format_report(result, scan_only=scan_only)

        if scan_only:
            print(report)
        elif args.path == "-":
            sys.stdout.write(result.text)
            print(report, file=sys.stderr)
        else:
            out = lib.pick_output_path(args.path, ".clean", args.output)
            lib.write_new_file(out, result.text.encode("utf-8"))
            print(report)
            print(f"Cleaned copy written to: {out}\nOriginal left untouched: {args.path}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
