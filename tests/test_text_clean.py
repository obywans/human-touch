#!/usr/bin/env python3
"""Tests for the Text Cleaner (skills/human/scripts/_clean_lib.py, text_clean.py).

Usage: python3 tests/test_text_clean.py

Covers: each invisible-character category, the context rules that must NOT
remove legitimate characters (emoji ZWJ, Persian ZWNJ, RTL marks, French
typography), content preservation (the visible text is identical before and
after, including a randomized check), protected code, scan-only, and the
command-line behaviour (new file, no overwrite, bad input).
"""
import contextlib
import io
import os
import random
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "human", "scripts"))
import _clean_lib as lib  # noqa: E402
import text_clean  # noqa: E402


def run_cli(*argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    old_in = sys.stdin
    if stdin is not None:
        sys.stdin = io.TextIOWrapper(io.BytesIO(stdin))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = text_clean.main(list(argv))
    finally:
        sys.stdin = old_in
    return rc, out.getvalue(), err.getvalue()


class TestCategories(unittest.TestCase):
    def test_zero_width_removed_and_counted(self):
        r = lib.clean_text("a\u200bb\u2060c\ufeffd\u00ade\u180ef")
        self.assertEqual(r.text, "abcdef")
        self.assertEqual(sum(f.action == "removed" for f in r.findings), 5)

    def test_unusual_spaces_become_plain_space(self):
        r = lib.clean_text("a\u00a0b\u2003c\u202fd\u3000e")
        self.assertEqual(r.text, "a b c d e")

    def test_line_separators_replaced(self):
        self.assertEqual(lib.clean_text("a\u2028b\u2029c").text, "a\nb\nc")

    def test_controls_removed_but_tab_newline_cr_kept(self):
        self.assertEqual(lib.clean_text("a\x00b\x07c\x7fd\x85e").text, "abcd\ne")
        self.assertEqual(lib.clean_text("a\tb\r\nc").text, "a\tb\r\nc")

    def test_bom_at_start_removed_with_reason(self):
        r = lib.clean_text("\ufeffHola")
        self.assertEqual(r.text, "Hola")
        self.assertIn("byte-order mark", r.findings[0].reason)

    def test_tag_characters_removed_with_warning(self):
        hidden = "".join(chr(0xE0000 + ord(c)) for c in "secret")
        r = lib.clean_text("visible" + hidden)
        self.assertEqual(r.text, "visible")
        self.assertTrue(any("tag characters" in w for w in r.warnings))

    def test_emoji_flag_tag_sequence_kept(self):
        flag = "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + "\U000E007F"
        self.assertEqual(lib.clean_text(flag).text, flag)

    def test_replacement_character_reported_not_removed(self):
        r = lib.clean_text("caf�")
        self.assertEqual(r.text, "caf�")
        self.assertTrue(r.warnings)


class TestContextRules(unittest.TestCase):
    def test_emoji_zwj_sequence_kept(self):
        family = "\U0001F468\u200d\U0001F469\u200d\U0001F467"
        self.assertEqual(lib.clean_text(family).text, family)

    def test_persian_zwnj_kept_but_latin_zwnj_removed(self):
        persian = "می\u200cخواهم"
        self.assertEqual(lib.clean_text(persian).text, persian)
        self.assertEqual(lib.clean_text("ab\u200ccd").text, "abcd")

    def test_french_nbsp_kept(self):
        for s in ("Bonjour\u00a0!", "Quoi\u00a0?", "«\u00a0oui\u00a0»", "prix\u00a0: 5", "50\u202f%"):
            self.assertEqual(lib.clean_text(s).text, s, s)

    def test_digit_grouping_nbsp_kept(self):
        self.assertEqual(lib.clean_text("10\u00a0000 EUR").text, "10\u00a0000 EUR")

    def test_stray_nbsp_between_words_replaced_and_keep_flag(self):
        self.assertEqual(lib.clean_text("uno\u00a0dos").text, "uno dos")
        self.assertEqual(lib.clean_text("uno\u00a0dos", keep_nbsp=True).text, "uno\u00a0dos")

    def test_bidi_marks_removed_in_latin_kept_in_rtl(self):
        self.assertEqual(lib.clean_text("abc\u200edef\u202bx\u202c").text, "abcdefx")
        hebrew = "שלום\u200f world"
        self.assertEqual(lib.clean_text(hebrew).text, hebrew)
        self.assertEqual(lib.clean_text(hebrew, bidi="strip").text, "שלום world")
        self.assertEqual(lib.clean_text("a\u200eb", bidi="keep").text, "a\u200eb")

    def test_bidi_override_warns(self):
        r = lib.clean_text("access\u202egnp.exe")
        self.assertTrue(any("override" in w for w in r.warnings))

    def test_bad_bidi_mode_rejected(self):
        with self.assertRaises(ValueError):
            lib.clean_text("x", bidi="nope")


class TestContentPreservation(unittest.TestCase):
    SAMPLE = ("Reșița: 450 MVA, 10 000 € — «¿Cómo estás?» “quote”, naïve café, 日本語, "
              "emoji \U0001F600, https://example.com/a?b=c&d=e, `code`, 3.14%\n")

    def test_visible_text_untouched(self):
        noisy = self.SAMPLE.replace(" ", " \u200b", 3).replace("café", "ca\u00adfé")
        r = lib.clean_text(noisy)
        self.assertEqual(r.text.replace("\u00a0", " "), self.SAMPLE.replace("\u00a0", " "))

    def test_diacritics_digits_urls_survive(self):
        r = lib.clean_text(self.SAMPLE)
        for must in ("Reșița", "450 MVA", "«¿Cómo estás?»", "https://example.com/a?b=c&d=e", "3.14%", "日本語"):
            self.assertIn(must, r.text)

    def test_randomized_only_table_characters_change(self):
        rnd = random.Random(7)
        # pure deletions only; replacements (spaces, separators) have their own tests
        noise = ["\u200b", "\u200d", "\u200c", "\u202e", "\u200e", "\u00ad", "\ufeff", "\x00", "\U000E0041"]
        visible = list("abc XYZ 123 áéí ñ ș ț ă î — « » ! ? : ; % € \U0001F600 日 א ع\n\t")
        for _ in range(300):
            chars = [rnd.choice(visible if rnd.random() < 0.7 else noise) for _ in range(rnd.randint(0, 40))]
            s = "".join(chars)
            r = lib.clean_text(s)  # raises if the internal preservation check fails
            keep = [c for c in s if c in visible]
            got = [c for c in r.text if c in visible]
            self.assertEqual(keep, got, repr(s))

    def test_clean_is_idempotent(self):
        once = lib.clean_text("a\u200b b\u00a0c \u202e x").text
        self.assertEqual(lib.clean_text(once).text, once)

    def test_empty_and_clean_input(self):
        self.assertEqual(lib.clean_text("").text, "")
        r = lib.clean_text("Texto limpio.")
        self.assertEqual((r.text, r.findings), ("Texto limpio.", []))
        self.assertIn("No anomalous", lib.format_report(r))


class TestProtectedRegions(unittest.TestCase):
    def test_code_blocks_and_inline_code_untouched_prose_cleaned(self):
        text = "Hola\u200b mundo\n```py\nx = 'a\u200bb'\n```\nusa `a\u00a0b` aqui\u200b\n"
        r = lib.clean_text(text, protected=lib.code_spans(text))
        self.assertIn("x = 'a\u200bb'", r.text)
        self.assertIn("`a\u00a0b`", r.text)
        self.assertNotIn("Hola\u200b", r.text)
        self.assertTrue(r.text.endswith("aqui\n"))
        skipped = [f for f in r.findings if f.action == "skipped"]
        self.assertEqual(len(skipped), 2)  # hidden characters in code are reported, not hidden

    def test_unclosed_fence_protects_to_end(self):
        text = "a\u200b\n```\ncode\u200b still code"
        r = lib.clean_text(text, protected=lib.code_spans(text))
        self.assertTrue(r.text.endswith("code\u200b still code"))

    def test_scan_only_changes_nothing(self):
        text = "a\u200bb\u00a0c"
        r = lib.clean_text(text, scan_only=True)
        self.assertEqual(r.text, text)
        self.assertEqual(len(r.findings), 2)
        self.assertIn("would remove", lib.format_report(r, scan_only=True))

    def test_entities_for_invisible_characters(self):
        r = lib.clean_text("a&#8203;b&#x200B;c&ZeroWidthSpace;d&amp;e&nbsp;f", decode_entities=True)
        self.assertEqual(r.text, "abcd&amp;e&nbsp;f")


class TestLanguages(unittest.TestCase):
    """Real text in many scripts: noise is removed, the language itself is never altered."""
    SAMPLES = {
        "es": "Año nuevo: ¿qué tal? Señor Núñez, 1.250,50 \u20ac",
        "fr": "L\u2019\u00e9t\u00e9 \u00e0 Gen\u00e8ve, \u00e7a va\u00a0? \u00ab\u00a0Oui\u00a0\u00bb",
        "ro": "Re\u0219i\u021ba, \u0103 \u00e2 \u00ee \u0219 \u021b",
        "de": "Stra\u00dfe, \u00fcber \u00d6l, \u00c4rger",
        "tr": "\u0130stanbul \u0131\u015f\u0131k \u011f",
        "ru": "\u041f\u0440\u0438\u0432\u0435\u0442, \u043c\u0438\u0440",
        "el": "\u0393\u03b5\u03b9\u03b1 \u03c3\u03bf\u03c5",
        "zh": "\u4f60\u597d\uff0c\u4e16\u754c",
        "ja": "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c\u30ab\u30bf\u30ab\u30ca",
        "ko": "\uc548\ub155\ud558\uc138\uc694",
        "th": "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35",
        "ar": "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
        "he": "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd",
    }

    def test_noise_removed_language_untouched(self):
        for lang, text in self.SAMPLES.items():
            noisy = "\u200b".join(text) if lang not in ("ar", "th") else text + "\u200b\u2060"
            r = lib.clean_text(noisy)
            self.assertNotIn("\u2060", r.text, lang)
            for ch in text:
                self.assertIn(ch, r.text, (lang, ch))
            if lang not in ("ar",):  # Arabic-script letters legitimately keep joiners; no ZWSP here either way
                self.assertNotIn("\u200b", r.text, lang)

    def test_clean_native_text_is_a_noop(self):
        for lang, text in self.SAMPLES.items():
            r = lib.clean_text(text)
            self.assertEqual(r.text, text, lang)

    def test_indic_joiners_are_required_and_kept(self):
        hindi = "\u0915\u094d\u200d\u0937"  # virama + ZWJ forms a half-form in Devanagari
        self.assertEqual(lib.clean_text(hindi).text, hindi)
        bengali = "\u09b0\u200d\u09cd\u09af"
        self.assertEqual(lib.clean_text(bengali).text, bengali)

    def test_arabic_script_marks_and_zwnj_kept(self):
        arabic = "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645 \u200f(1)"
        self.assertEqual(lib.clean_text(arabic).text, arabic)

    def test_mixed_rtl_and_latin_keeps_direction_marks(self):
        mixed = "Total: \u200f\u05e9\u05dc\u05d5\u05dd\u200e 42"
        self.assertEqual(lib.clean_text(mixed).text, mixed)

    def test_unicode_and_spaced_paths_work_on_the_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "informe final \u00f1\u00e1 \u65e5\u672c.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("hola\u200b")
            rc, out, _ = run_cli("clean", src)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "informe final \u00f1\u00e1 \u65e5\u672c.clean.txt")))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_clean_file_writes_new_copy_and_keeps_original(self):
        src = self.path("n.txt")
        original = "uno\u200b dos\r\ntres\u00a0cuatro\r\n".encode()
        with open(src, "wb") as f:
            f.write(original)
        rc, out, _ = run_cli("clean", src)
        self.assertEqual(rc, 0)
        with open(src, "rb") as f:
            self.assertEqual(f.read(), original)
        with open(self.path("n.clean.txt"), "rb") as f:
            self.assertEqual(f.read(), b"uno dos\r\ntres cuatro\r\n")
        self.assertIn("Original left untouched", out)

    def test_never_overwrites_existing_output(self):
        src = self.path("n.txt")
        with open(src, "w") as f:
            f.write("x\u200by")
        run_cli("clean", src)
        rc, _, _ = run_cli("clean", src)  # second run picks n.clean-2.txt
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self.path("n.clean-2.txt")))
        rc, _, err = run_cli("clean", src, "--output", self.path("n.clean.txt"))
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)

    def test_scan_writes_nothing(self):
        src = self.path("n.txt")
        with open(src, "w") as f:
            f.write("x\u200by")
        rc, out, _ = run_cli("scan", src)
        self.assertEqual(rc, 0)
        self.assertEqual(os.listdir(self.tmp.name), ["n.txt"])
        self.assertIn("would remove", out)

    def test_stdin_to_stdout(self):
        rc, out, err = run_cli("clean", "-", stdin="a\u200bb".encode())
        self.assertEqual((rc, out), (0, "ab"))
        self.assertIn("removed", err)

    def test_invalid_utf8_and_missing_file_fail_cleanly(self):
        bad = self.path("bad.txt")
        with open(bad, "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        rc, _, err = run_cli("clean", bad)
        self.assertEqual(rc, 1)
        self.assertIn("not valid UTF-8", err)
        rc, _, err = run_cli("scan", self.path("missing.txt"))
        self.assertEqual(rc, 1)
        self.assertIn("not a file", err)

    def test_json_report(self):
        rc, out, _ = run_cli("scan", "-", "--json", stdin="a\u200b".encode())
        self.assertEqual(rc, 0)
        self.assertIn('"U+200B"', out)


if __name__ == "__main__":
    unittest.main()
