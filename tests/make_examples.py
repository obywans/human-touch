#!/usr/bin/env python3
"""Build examples/before-after.md from tests/inputs/ and tests/recorded/.

Usage:
  python3 tests/make_examples.py           # rewrite examples/before-after.md
  python3 tests/make_examples.py --check   # exit 1 if the page does not match the recordings

The page shows the first five cases. Their before and after texts are read from
the input and recorded files, so the page cannot drift from the recordings.
Only the titles and the "What changed" lines below are written by hand: re-read
them whenever one of these recordings changes.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
PAGE = ROOT.parent / "examples" / "before-after.md"

INTRO = (
    "These are real outputs of `/human`, recorded on the inputs in `tests/inputs/`. "
    "The raw outputs are in `tests/recorded/`. `tests/make_examples.py` builds this page from them, "
    "and `python3 tests/make_examples.py --check` fails if the two differ. "
    "Model output varies between runs, so treat these as examples, not fixed results."
)

EXAMPLES = [
    ("01-generic-ai-en", "Generic English text",
     "The opener, \"It's important to note\", \"Firstly / Secondly / Finally\", \"In conclusion\", "
     "\"crucial\", \"foster\" and \"cornerstone\" are gone. The reason the source gives "
     "(\"because consistency matters\") is kept, and nothing was added."),
    ("02-professional-es", "Professional Spanish email",
     "\"En el mundo empresarial actual\", \"Cabe destacar que\", \"Además\" and \"En definitiva\" are gone, "
     "and the dashes around the team description became commas. The date, the budget and the team size "
     "are unchanged, and so is the usted address."),
    ("03-casual-en", "Casual English message",
     "Nothing. The message was already natural casual chat, and the chat register keeps the author's "
     "casing and punctuation."),
    ("04-already-natural-en", "Text that is already natural",
     "Nothing. \"No change needed\" is a valid result for a text that already reads naturally."),
    ("05-long-form-en", "Long-form English essay",
     "\"Moreover\", \"This is a significant development that\", \"Furthermore, it is important to recognize "
     "that\", \"Ultimately\" and \"In conclusion\" are gone, and \"underscore\" became \"show\". Every figure is "
     "unchanged, the rest keeps the author's wording, and every claim survives, including the broader shifts "
     "in how work is organized and the need for policy design."),
]


def quote(text: str) -> str:
    blocks = []
    for para in text.strip("\n").split("\n\n"):
        lines = para.split("\n")
        if lines[0].startswith("Notes:"):
            blocks.append("> *" + " ".join(lines) + "*")
        else:
            blocks.append("\n".join("> " + line for line in lines))
    return "\n>\n".join(blocks)


def build() -> str:
    out = ["# Before and after", "", INTRO, ""]
    for number, (case, title, changed) in enumerate(EXAMPLES, 1):
        before = (ROOT / "inputs" / f"{case}.txt").read_text(encoding="utf-8")
        after = (ROOT / "recorded" / f"{case}.txt").read_text(encoding="utf-8")
        out += [f"## {number}. {title}", "", "**Before**", "", quote(before), "",
                "**After**", "", quote(after), "", "What changed: " + changed, ""]
    return "\n".join(out)


def main() -> int:
    page = build()
    args = sys.argv[1:]
    if args == ["--check"]:
        current = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
        if current != page:
            print("FAIL examples/before-after.md does not match tests/recorded/. Run: python3 tests/make_examples.py")
            return 1
        print("PASS examples/before-after.md matches tests/recorded/")
        return 0
    if args:
        print(__doc__)
        return 2
    PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {PAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
