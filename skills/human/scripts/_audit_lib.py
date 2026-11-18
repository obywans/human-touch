"""Detection tables and rules for HumanTouch's watermark audit (read-only).

Stdlib only, fully local, never touches the network, never modifies anything.

ATTRIBUTION. The code-point tables, the context rules (which invisible
characters are legitimate next to which scripts) and the homoglyph table in
this file are adapted from "Watermarks Remover" by Guillaume Meyer and
contributors, https://github.com/guillaumemeyer/watermarks-remover
(file skills/clean-user-facing-text/scripts/text_unicode.py). Adaptation done
for HumanTouch: detection only (nothing here removes or rewrites anything),
rules re-expressed as a flat audit report, merged with HumanTouch's own
cleaner (_clean_lib.py) so both agree on what is a finding, and made
word-boundary aware for the homoglyph check. Everything else is original
HumanTouch code.

The original work is distributed under the following licence, reproduced in
full as it requires:

    MIT License

    Copyright (c) 2026 Guillaume Meyer and contributors

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import _clean_lib as lib

# --- tables (adapted from Watermarks Remover) --------------------------------

VS_BMP = range(0xFE00, 0xFE10)            # variation selectors 1-16
VS_SUPPLEMENT = range(0xE0100, 0xE01F0)   # variation selectors 17-256
MONGOLIAN_FVS = frozenset({0x180B, 0x180C, 0x180D, 0x180F})
KHMER_VOWELS = frozenset({0x17B4, 0x17B5})
HANGUL_FILLERS = frozenset({0x115F, 0x1160})  # 3164 / FFA0 are handled by _clean_lib
DEPRECATED_FORMAT = range(0x206A, 0x2070)  # inhibit/activate swapping, digit shapes...
CGJ = 0x034F

# Unassigned code points with Other_Default_Ignorable_Code_Point=Yes. Kept as
# explicit ranges, never a "category Cn" rule: unicodedata is pinned per Python
# build, so a Cn rule would flag characters assigned in newer Unicode versions.
RESERVED_IGNORABLE_CPS = frozenset({0x2065, 0xE0000})
RESERVED_IGNORABLE_RANGES = (range(0xFFF0, 0xFFF9), range(0xE0080, 0xE0100), range(0xE01F0, 0xE1000))

# Latin look-alikes (Cyrillic and fullwidth); only reported inside a word that
# also contains plain ASCII letters.
CYRILLIC_CONFUSABLES = {
    0x0410: "A", 0x0412: "B", 0x0415: "E", 0x041A: "K", 0x041C: "M", 0x041D: "H",
    0x041E: "O", 0x0420: "P", 0x0421: "C", 0x0422: "T", 0x0425: "X",
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0443: "y",
    0x0445: "x", 0x0456: "i",
}
FULLWIDTH_LATIN = frozenset(list(range(0xFF21, 0xFF3B)) + list(range(0xFF41, 0xFF5B)))

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)

CATEGORY_LABELS = {
    "variation-selector": "variation selectors outside emoji/CJK/Mongolian sequences",
    "combining-joiner": "combining grapheme joiners outside combining-mark sequences",
    "noncharacter": "Unicode noncharacters",
    "reserved-ignorable": "reserved invisible code points",
    "private-use": "private-use characters",
    "deprecated-format": "deprecated format controls",
    "script-filler": "Khmer/Hangul invisible fillers outside their script",
    "homoglyph": "look-alike letters mixed into Latin words",
}


@dataclass
class AuditFinding:
    cp: int
    category: str
    verdict: str   # "flagged" | "context-ok" | "review"
    line: int
    col: int
    reason: str = ""
    source: str = "audit"  # "cleaner" for findings from HumanTouch's own cleaner

    @property
    def name(self) -> str:
        try:
            return unicodedata.name(chr(self.cp))
        except ValueError:
            return "(unnamed)"


@dataclass
class AuditResult:
    findings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def flagged(self):
        return [f for f in self.findings if f.verdict in ("flagged", "review")]


def _is_cjk_ideograph(cp: int) -> bool:
    return (0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
            or 0x20000 <= cp <= 0x323AF)


def _is_noncharacter(cp: int) -> bool:
    return 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE


def _is_reserved_ignorable(cp: int) -> bool:
    return cp in RESERVED_IGNORABLE_CPS or any(cp in r for r in RESERVED_IGNORABLE_RANGES)


def _is_private_use(cp: int) -> bool:
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def _is_hangul(cp: int) -> bool:
    return 0x1100 <= cp <= 0x11FF or 0xA960 <= cp <= 0xA97F or 0xAC00 <= cp <= 0xD7FF or 0x3130 <= cp <= 0x318F


def _is_emoji_base(cp: int) -> bool:
    """Characters after which VS15/VS16 select text or emoji presentation."""
    return (0x1F000 <= cp <= 0x1FAFF or 0x2190 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF
            or cp in (0x203C, 0x2049, 0x2139, 0x2934, 0x2935, 0x00A9, 0x00AE, 0x2122,
                      0x3030, 0x303D, 0x3297, 0x3299) or lib._is_pictographic(cp))


def _is_keycap_base(cp: int) -> bool:
    return cp in (0x23, 0x2A) or 0x30 <= cp <= 0x39


def _position(text: str, index: int) -> tuple:
    line = text.count("\n", 0, index) + 1
    col = index - (text.rfind("\n", 0, index) + 1) + 1
    return line, col


def classify_hidden(text: str, i: int, cp: int):
    """(category, verdict, reason) for the categories beyond the basic cleaner
    tables, or None. Used by both Audit and Clean, so they always agree.
    verdict: "flagged" (stray, safe to remove), "context-ok" (legitimate here),
    "review" (report only, never removed)."""
    if cp < 0x34F and cp != 0x2065:
        return None
    prev = ord(text[i - 1]) if i > 0 else None
    nxt = ord(text[i + 1]) if i + 1 < len(text) else None

    if cp in VS_BMP:
        if cp in (0xFE0E, 0xFE0F) and prev is not None and (_is_emoji_base(prev) or _is_keycap_base(prev)):
            return "variation-selector", "context-ok", "emoji presentation selector"
        if prev is not None and _is_cjk_ideograph(prev):
            return "variation-selector", "context-ok", "ideographic variation sequence"
        return "variation-selector", "flagged", "variation selector with no base that uses it: a known carrier for hidden data"
    if cp in VS_SUPPLEMENT:
        if prev is not None and _is_cjk_ideograph(prev):
            return "variation-selector", "context-ok", "ideographic variation sequence"
        return "variation-selector", "flagged", "supplementary variation selector with no CJK base: a known carrier for hidden data"
    if cp in MONGOLIAN_FVS:
        if prev is not None and 0x1800 <= prev <= 0x18AF:
            return "variation-selector", "context-ok", "Mongolian free variation selector after a Mongolian letter"
        return "variation-selector", "flagged", "Mongolian selector outside Mongolian text"
    if cp == CGJ:
        if (prev is not None and unicodedata.category(chr(prev)).startswith("M")
                and nxt is not None and unicodedata.category(chr(nxt)).startswith("M")):
            return "combining-joiner", "context-ok", "between combining marks"
        return "combining-joiner", "flagged", "combining grapheme joiner outside a combining-mark sequence"
    if cp in KHMER_VOWELS:
        if prev is not None and 0x1780 <= prev <= 0x17FF:
            return "script-filler", "context-ok", "Khmer inherent vowel after a Khmer letter"
        return "script-filler", "flagged", "Khmer inherent vowel outside Khmer text"
    if cp in HANGUL_FILLERS:
        if (prev is not None and _is_hangul(prev)) or (nxt is not None and _is_hangul(nxt)):
            return "script-filler", "context-ok", "Hangul filler inside Hangul text"
        return "script-filler", "flagged", "Hangul filler outside Hangul text"
    if cp in DEPRECATED_FORMAT:
        return "deprecated-format", "flagged", "deprecated format control with no use in current text"
    if _is_noncharacter(cp):
        return "noncharacter", "flagged", "noncharacter: forbidden in interchange text"
    if _is_reserved_ignorable(cp):
        return "reserved-ignorable", "flagged", "reserved invisible code point: no legitimate use"
    if _is_private_use(cp):
        return "private-use", "review", "private-use character: icon fonts use these; elsewhere it has no portable meaning"
    return None


def _homoglyph_findings(text: str):
    for m in _WORD_RE.finditer(text):
        word = m.group()
        has_ascii = any(ch.isascii() and ch.isalpha() for ch in word)
        if not has_ascii:
            continue
        for off, ch in enumerate(word):
            cp = ord(ch)
            if cp in CYRILLIC_CONFUSABLES or cp in FULLWIDTH_LATIN:
                idx = m.start() + off
                line, col = _position(text, idx)
                look = CYRILLIC_CONFUSABLES.get(cp) or chr(cp - 0xFEE0)
                yield AuditFinding(cp, "homoglyph", "flagged", line, col,
                                   f"looks like Latin {look!r} inside the word {word!r}")


def _latin_for(cp: int):
    return CYRILLIC_CONFUSABLES.get(cp) or (chr(cp - 0xFEE0) if cp in FULLWIDTH_LATIN else None)


def fold_char(ch: str) -> str:
    return _latin_for(ord(ch)) or ch


def homoglyph_map(text: str) -> dict:
    """{index: Latin letter} for look-alikes inside words that also hold ASCII letters."""
    out = {}
    for m in _WORD_RE.finditer(text):
        word = m.group()
        if not any(c.isascii() and c.isalpha() for c in word):
            continue
        for off, ch in enumerate(word):
            latin = _latin_for(ord(ch))
            if latin:
                out[m.start() + off] = latin
    return out


def audit_text(text: str) -> AuditResult:
    """Scan only. Returns every finding with its verdict; never changes text."""
    result = AuditResult()

    base = lib.clean_text(text, scan_only=True)
    result.warnings.extend(base.warnings)
    for f in base.findings:
        if f.action == "kept":
            verdict = "review" if f.reason.startswith("review:") else "context-ok"
        elif f.category in ("space", "line-separator"):
            verdict = "review"  # common in pasted Word/Outlook text, so not a hard flag
        else:
            verdict = "flagged"
        result.findings.append(AuditFinding(f.cp, f.category, verdict, f.line, f.col,
                                            f.reason.replace("review: ", "", 1), source="cleaner"))

    result.findings.extend(_homoglyph_findings(text))
    result.findings.sort(key=lambda f: (f.line, f.col))
    return result


NOT_CHECKED = (
    "statistical watermarks in word choice (they need the provider's secret key, so no local tool can confirm or "
    "rule them out), pixel/audio/video watermarks, and any format the tool cannot read",
)

CHECKED = (
    "invisible and zero-width characters, direction controls, tag characters, unusual spaces and separators, "
    "control characters, variation selectors, combining joiners, noncharacters, reserved and private-use "
    "code points, deprecated format controls, Khmer/Hangul fillers, and look-alike letters inside Latin words"
)


def summarize(result: AuditResult) -> dict:
    out = {}
    for f in result.findings:
        key = (f.category, f.verdict)
        out[key] = out.get(key, 0) + 1
    return out


def format_report(result: AuditResult, label: str, max_lines: int = 40) -> str:
    lines = [f"Watermark audit: {label}", f"Checked: {CHECKED}.", f"NOT checked: {NOT_CHECKED[0]}.", ""]
    flagged = [f for f in result.findings if f.verdict != "context-ok"]
    ok = [f for f in result.findings if f.verdict == "context-ok"]
    if not flagged:
        lines.append("Nothing suspicious found in the categories checked. That is not proof that the text carries no watermark.")
    else:
        lines.append(f"{len(flagged)} suspicious or to-review finding(s):")
        for f in flagged[:max_lines]:
            tag = "REVIEW" if f.verdict == "review" else "FLAGGED"
            lines.append(f"  {tag} line {f.line}, col {f.col}: U+{f.cp:04X} {f.name} [{f.category}] {f.reason}".rstrip())
        if len(flagged) > max_lines:
            lines.append(f"  ... {len(flagged) - max_lines} more (use --json for the full list)")
    if ok:
        lines.append(f"{len(ok)} character(s) judged legitimate in context (emoji sequences, joining scripts, etc.), left out of the findings.")
    for w in result.warnings:
        lines.append(f"WARNING: {w}")
    lines.append("")
    lines.append("This audit only reports. Nothing was changed. Clean removes the flagged invisible characters; it never touches look-alike letters or private-use characters.")
    return "\n".join(lines)
