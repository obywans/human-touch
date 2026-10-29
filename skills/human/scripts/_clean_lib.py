"""Shared helpers for HumanTouch's technical cleaning scripts.

Stdlib only, fully local: nothing here touches the network. The cleaner only
ever removes or replaces characters from the explicit tables below. Every
visible character is left alone, and a self-check after each run proves it
(see verify_preserved). Characters that are legitimate in context (ZWJ in
emoji, ZWNJ in Persian, direction marks in right-to-left text, the
non-breaking space of French typography) are kept and reported as kept.
"""
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field

# --- character tables ------------------------------------------------------

ZERO_WIDTH = {
    0x200B: "zero-width",  # ZERO WIDTH SPACE
    0x2060: "zero-width",  # WORD JOINER
    0xFEFF: "zero-width",  # ZERO WIDTH NO-BREAK SPACE / BOM
    0x180E: "zero-width",  # MONGOLIAN VOWEL SEPARATOR
    0x2061: "zero-width",  # invisible math operators
    0x2062: "zero-width",
    0x2063: "zero-width",
    0x2064: "zero-width",
    0x00AD: "soft-hyphen",
    0x3164: "blank-filler",  # HANGUL FILLER, renders as blank
    0xFFA0: "blank-filler",  # HALFWIDTH HANGUL FILLER
    0xFFF9: "annotation",  # interlinear annotation anchors
    0xFFFA: "annotation",
    0xFFFB: "annotation",
    0xFFFC: "annotation",  # OBJECT REPLACEMENT CHARACTER
}
JOINERS = {0x200C: "joiner", 0x200D: "joiner"}
BIDI_MARKS = {0x200E: "bidi", 0x200F: "bidi", 0x061C: "bidi"}
BIDI_CONTROLS = {cp: "bidi" for cp in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
BIDI_OVERRIDES = {0x202D, 0x202E}  # also a known source-code spoofing vector
SPACES = {0x00A0: " ", 0x1680: " ", 0x202F: " ", 0x205F: " ", 0x3000: " "}
SPACES.update({cp: " " for cp in range(0x2000, 0x200B)})
LINE_SEPARATORS = {0x2028: "\n", 0x2029: "\n", 0x0085: "\n"}
KEEP_CONTROLS = {0x09, 0x0A, 0x0D, 0x0C}

CATEGORY_LABELS = {
    "zero-width": "zero-width / invisible characters",
    "soft-hyphen": "soft hyphens",
    "blank-filler": "blank filler characters",
    "annotation": "annotation / object placeholders",
    "joiner": "zero-width joiners",
    "bidi": "direction marks and controls",
    "space": "unusual spaces",
    "line-separator": "unusual line separators",
    "tag": "Unicode tag characters",
    "control": "control characters",
    "replacement": "replacement characters (possible encoding damage)",
}

JOINER_SCRIPT_PREFIXES = (
    "ARABIC", "SYRIAC", "NKO", "ADLAM", "DEVANAGARI", "BENGALI", "GURMUKHI",
    "GUJARATI", "ORIYA", "TAMIL", "TELUGU", "KANNADA", "MALAYALAM", "SINHALA",
    "MYANMAR", "KHMER", "TIBETAN", "THAANA", "MONGOLIAN",
)
FRENCH_PUNCT_AFTER_NBSP = set(":;!?»%")

# Entities that decode to a character the cleaner always removes.
ENTITY_RE = re.compile(
    r"&(?:#[xX]([0-9a-fA-F]{1,6})|#([0-9]{1,7})|ZeroWidthSpace|NoBreak|shy);"
)
_NAMED_ENTITIES = {"ZeroWidthSpace": 0x200B, "NoBreak": 0x2060, "shy": 0x00AD}


def _always_removed(cp: int) -> bool:
    return cp in ZERO_WIDTH or 0xE0000 <= cp <= 0xE007F


# --- result types -----------------------------------------------------------

@dataclass
class Finding:
    cp: int
    category: str
    action: str  # removed | replaced | kept | skipped
    line: int
    col: int
    reason: str = ""

    @property
    def name(self) -> str:
        try:
            return unicodedata.name(chr(self.cp))
        except ValueError:
            return "(unnamed)"


@dataclass
class CleanResult:
    text: str
    findings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(f.action in ("removed", "replaced") for f in self.findings)


# --- protected regions ------------------------------------------------------

_FENCE_RE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[`~]*[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def code_spans(text: str) -> list:
    """(start, end) spans of fenced code blocks and inline code spans."""
    spans = [m.span() for m in _FENCE_RE.finditer(text)]
    for m in _INLINE_CODE_RE.finditer(text):
        s, e = m.span()
        if not any(a <= s < b for a, b in spans):
            spans.append((s, e))
    return sorted(spans)


def complement(spans: list, length: int) -> list:
    out, pos = [], 0
    for s, e in sorted(spans):
        if s > pos:
            out.append((pos, s))
        pos = max(pos, e)
    if pos < length:
        out.append((pos, length))
    return out


# --- core cleaner -----------------------------------------------------------

def _is_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(c) in ("R", "AL") for c in text)


def _is_pictographic(cp: int) -> bool:
    return (
        0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF or cp in (0xFE0F, 0x2764, 0x00A9, 0x00AE)
    )


def _needs_joiner(text: str, i: int, cp: int) -> str:
    """Reason to keep a ZWJ/ZWNJ at text[i], or '' if it is stray."""
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if cp == 0x200D and prev and _is_pictographic(ord(prev)):
        return "emoji sequence"
    for ch in (prev, nxt):
        if ch:
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            if name.startswith(JOINER_SCRIPT_PREFIXES):
                return "required by the neighbouring script"
    return ""


def _tag_run_is_emoji_flag(text: str, i: int) -> bool:
    j = i
    while j > 0 and 0xE0000 <= ord(text[j - 1]) <= 0xE007F:
        j -= 1
    return j > 0 and ord(text[j - 1]) == 0x1F3F4


def _neighbour(text: str, i: int, step: int) -> str:
    """Nearest character in direction `step` that is not itself an invisible one."""
    j = i + step
    while 0 <= j < len(text) and (ord(text[j]) in ZERO_WIDTH or ord(text[j]) in JOINERS):
        j += step
    return text[j] if 0 <= j < len(text) else ""


def _nbsp_is_intentional(text: str, i: int) -> bool:
    prev, nxt = _neighbour(text, i, -1), _neighbour(text, i, 1)
    if nxt in FRENCH_PUNCT_AFTER_NBSP or prev == "\u00ab":
        return True
    return prev.isdigit() and nxt.isdigit()


def clean_text(text: str, *, protected=(), bidi: str = "auto", keep_nbsp: bool = False,
               scan_only: bool = False, decode_entities: bool = False) -> CleanResult:
    """Remove/replace anomalous invisible characters.

    protected: (start, end) spans that are never modified (still scanned, so
        hidden characters inside e.g. code are reported as 'skipped').
    bidi: 'auto' keeps direction controls in right-to-left text and removes
        them elsewhere; 'strip' removes all; 'keep' keeps all.
    scan_only: report without producing changes.
    decode_entities: also drop numeric/named HTML-XML entities that stand for
        an always-removed character (e.g. &#8203;).
    """
    if bidi not in ("auto", "strip", "keep"):
        raise ValueError("bidi must be auto, strip or keep")
    protected = sorted(protected)
    rtl = _is_rtl(text)
    out, findings = [], []
    line, col, pi = 1, 1, 0

    def in_protected(i):
        nonlocal pi
        while pi < len(protected) and protected[pi][1] <= i:
            pi += 1
        return pi < len(protected) and protected[pi][0] <= i

    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        cp = ord(ch)
        prot = in_protected(i)
        action, repl, cat, reason = "keep", ch, None, ""

        if decode_entities and ch == "&" and not prot:
            m = ENTITY_RE.match(text, i)
            if m:
                ecp = _NAMED_ENTITIES.get(m.group(0)[1:-1])
                if ecp is None:
                    ecp = int(m.group(1), 16) if m.group(1) else int(m.group(2))
                if _always_removed(ecp):
                    findings.append(Finding(ecp, "tag" if ecp >= 0xE0000 else ZERO_WIDTH.get(ecp, "zero-width"),
                                            "removed", line, col, "as an entity"))
                    if not scan_only:
                        col += m.end() - i
                        i = m.end()
                        continue

        if cp in ZERO_WIDTH:
            cat = ZERO_WIDTH[cp]
            action, repl = "removed", ""
            if cp == 0xFEFF and i == 0:
                reason = "byte-order mark at start"
        elif 0xE0000 <= cp <= 0xE007F:
            cat = "tag"
            if _tag_run_is_emoji_flag(text, i):
                action, reason = "kept", "part of an emoji flag"
            else:
                action, repl = "removed", ""
                reason = "hidden text channel"
        elif cp in JOINERS:
            cat = "joiner"
            why = _needs_joiner(text, i, cp)
            if why:
                action, reason = "kept", why
            else:
                action, repl = "removed", ""
        elif cp in BIDI_MARKS or cp in BIDI_CONTROLS:
            cat = "bidi"
            if cp in BIDI_OVERRIDES:
                reason = "direction override can disguise text"
            if bidi == "keep" or (bidi == "auto" and rtl):
                action, reason = "kept", "right-to-left text" if bidi == "auto" else "kept on request"
            else:
                action, repl = "removed", ""
        elif cp in SPACES:
            cat = "space"
            if cp in (0x00A0, 0x202F) and (keep_nbsp or _nbsp_is_intentional(text, i)):
                action, reason = "kept", "typographic non-breaking space"
            else:
                action, repl = "replaced", SPACES[cp]
        elif cp in LINE_SEPARATORS:
            cat = "line-separator"
            action, repl = "replaced", LINE_SEPARATORS[cp]
        elif cp == 0xFFFD:
            cat, action = "replacement", "kept"
            reason = "not removed: the original character is already lost"
        elif (cp < 0x20 and cp not in KEEP_CONTROLS) or cp == 0x7F or 0x80 <= cp <= 0x9F:
            cat = "control"
            action, repl = "removed", ""

        if cat is not None:
            if prot:
                action, repl, reason = "skipped", ch, "inside a protected region such as code or markup"
            elif scan_only and action in ("removed", "replaced"):
                pass  # reported with its real planned action
            findings.append(Finding(cp, cat, action, line, col, reason))
            if prot or scan_only:
                repl = ch
        out.append(repl)
        if ch == "\n":
            line, col = line + 1, 1
        else:
            col += 1
        i += 1

    result = CleanResult("".join(out), findings)
    if any(f.cp in BIDI_OVERRIDES for f in findings):
        result.warnings.append("Bidirectional override characters (U+202D/U+202E) were found; "
                               "they can make text or code display differently from how it reads.")
    if any(f.cp == 0xFFFD for f in findings):
        result.warnings.append("U+FFFD replacement characters indicate text already damaged by an "
                               "encoding error; the lost characters cannot be recovered.")
    if any(f.category == "tag" and f.action == "removed" for f in findings):
        result.warnings.append("Unicode tag characters were present; they are invisible and can carry "
                               "hidden text.")
    if scan_only:
        if result.text != text:
            raise ValueError("internal check failed: scan_only must not change text")
    else:
        verify_preserved(text, result.text, protected, decode_entities)
    return result


def _visible_view(s: str) -> str:
    out = []
    for ch in s:
        cp = ord(ch)
        if cp in ZERO_WIDTH or cp in JOINERS or cp in BIDI_MARKS or cp in BIDI_CONTROLS \
                or 0xE0000 <= cp <= 0xE007F:
            continue
        if cp in SPACES:
            out.append(" ")
        elif cp in LINE_SEPARATORS:
            out.append("\n")
        elif (cp < 0x20 and cp not in KEEP_CONTROLS) or cp == 0x7F or 0x80 <= cp <= 0x9F:
            continue
        else:
            out.append(ch)
    return "".join(out)


def verify_preserved(original: str, cleaned: str, protected=(), decode_entities: bool = False) -> None:
    """Prove that only table characters changed: the visible content is identical."""
    # Entities removed on request change the literal text, so the view is
    # compared after dropping them from the original too.
    if decode_entities:
        drop = lambda m: "" if _entity_removable(m) else m.group(0)  # noqa: E731
        original, cleaned = ENTITY_RE.sub(drop, original), ENTITY_RE.sub(drop, cleaned)
    if _visible_view(original) != _visible_view(cleaned):
        raise ValueError("internal check failed: visible content would change; nothing was written")
    for s, e in protected:
        if decode_entities:
            continue  # offsets shift once entities are dropped; the view check above still holds
        if original[s:e] not in cleaned:
            raise ValueError("internal check failed: a protected region would change")


def _entity_removable(m) -> bool:
    ecp = _NAMED_ENTITIES.get(m.group(0)[1:-1])
    if ecp is None:
        ecp = int(m.group(1), 16) if m.group(1) else int(m.group(2))
    return _always_removed(ecp)


# --- reporting --------------------------------------------------------------

def summarize(findings: list) -> list:
    """Group findings into (category, cp, name, action, reason) -> count rows."""
    rows = {}
    for f in findings:
        rows.setdefault((f.category, f.cp, f.name, f.action, f.reason), []).append(f)
    return [(k, len(v), v[0].line, v[0].col) for k, v in sorted(rows.items())]


def format_report(result: CleanResult, *, scan_only: bool = False, limit_locations: bool = True) -> str:
    if not result.findings:
        return "No anomalous invisible characters were found (checked against the tables in _clean_lib.py)."
    verb = {"removed": "would remove" if scan_only else "removed",
            "replaced": "would replace with plain text" if scan_only else "replaced with plain text",
            "kept": "kept", "skipped": "found, left unchanged"}
    lines = []
    for (cat, cp, name, action, reason), count, line, col in summarize(result.findings):
        extra = f" ({reason})" if reason else ""
        loc = f", first at line {line}, col {col}" if limit_locations else ""
        lines.append(f"- U+{cp:04X} {name} x{count}: {verb[action]}{extra}{loc}")
    changed = sum(1 for f in result.findings if f.action in ("removed", "replaced"))
    head = f"{changed} change(s) {'planned' if scan_only else 'made'}; " \
           f"{len(result.findings) - changed} other character(s) kept or left unchanged."
    out = [head, *lines]
    out += [f"WARNING: {w}" for w in result.warnings]
    return "\n".join(out)


def setup_stdio() -> None:
    """Make console output UTF-8 so names and metadata in any language print on every platform
    (Windows consoles often default to a legacy code page). Never raises."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


# --- safe output paths ------------------------------------------------------

MAX_INPUT_BYTES = 100 * 1024 * 1024


def read_input_bytes(path: str, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"not a file: {path}")
    if os.path.getsize(path) > max_bytes:
        raise ValueError(f"{path} is larger than {max_bytes // (1024 * 1024)} MB; refusing to load it")
    with open(path, "rb") as f:
        return f.read()


def pick_output_path(input_path: str, suffix: str, explicit: str | None = None, new_ext: str | None = None) -> str:
    """A new path that never equals the input and never exists yet."""
    if explicit:
        out = explicit
        if os.path.exists(out):
            raise FileExistsError(f"{out} already exists; choose another --output (originals and existing files are never overwritten)")
    else:
        base, ext = os.path.splitext(input_path)
        ext = new_ext if new_ext is not None else ext
        out, k = f"{base}{suffix}{ext}", 2
        while os.path.exists(out):
            out, k = f"{base}{suffix}-{k}{ext}", k + 1
    if os.path.exists(input_path) and os.path.exists(out) and os.path.samefile(input_path, out):
        raise FileExistsError("output would overwrite the input")
    return out


def write_new_file(path: str, data: bytes) -> None:
    """Create-only write (O_EXCL): refuses to replace anything that exists."""
    with open(path, "xb") as f:
        f.write(data)
