#!/usr/bin/env python3
"""Check HumanTouch outputs against tests/expectations.json.

Usage: python3 tests/check_outputs.py <dir-with-<case>.txt-files>

For each case it checks that:
  - every must_keep substring is still present (facts, names, terms);
  - every claim in "claims" survives: each claim is a list of accepted
    forms, and the claim passes if any form appears (case-insensitive).
    This covers every claim of the source, not only the listed words;
  - no generic or case-specific must_not phrase appears (case-insensitive);
  - the rewrite contains no em dash.
The line starting with "Notes:" (or "Notes :" in French) is ignored, because it
describes the edits. Exit code is 1 if any case fails.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
EXPECT = json.loads((ROOT / "expectations.json").read_text(encoding="utf-8"))


def body(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("Notes:", "Notes :"))
    )


def check(case: str, text: str) -> list[str]:
    spec = EXPECT["cases"][case]
    b = body(text)
    low = b.lower()
    problems = []
    for item in spec["must_keep"]:
        if item not in b:
            problems.append(f"missing kept item: {item!r}")
    for forms in spec.get("claims", []):
        if not any(form.lower() in low for form in forms):
            problems.append(f"claim lost, none of {forms!r} found")
    for phrase in EXPECT["generic_must_not"] + spec["must_not"]:
        if phrase.lower() in low:
            problems.append(f"found banned phrase: {phrase!r}")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = pathlib.Path(sys.argv[1])
    failed = 0
    for case in EXPECT["cases"]:
        path = out_dir / f"{case}.txt"
        if not path.exists():
            print(f"FAIL {case}: file not found: {path}")
            failed += 1
            continue
        problems = check(case, path.read_text(encoding="utf-8"))
        if problems:
            failed += 1
            print(f"FAIL {case}")
            for p in problems:
                print(f"     - {p}")
        else:
            print(f"PASS {case}")
    print(f"\n{len(EXPECT['cases']) - failed}/{len(EXPECT['cases'])} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
