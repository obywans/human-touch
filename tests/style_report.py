#!/usr/bin/env python3
"""Report whether /human makes different texts sound like the same author.

Usage: python3 tests/style_report.py

This does not grade quality and is not an AI detector. It reports
measurable style signals so a person can judge convergence directly:

  - sentence-length pattern (mean and spread) of each input vs its output;
  - whether casing, exclamations, questions, emoji and hashtags survive
    in contexts where they are the author's voice (chat, social);
  - the main signal: average pairwise similarity between all OUTPUTS,
    compared to the average pairwise similarity between all INPUTS.
    If outputs are much more similar to each other than the inputs were,
    that is homogenization: /human is flattening different voices into one.

Exit code is always 0. This is a report to read, not a pass/fail gate.
"""
import itertools
import pathlib
import re
import statistics as stats

ROOT = pathlib.Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
RECORDED = ROOT / "recorded"


def body(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("Notes:", "Notes :"))
        and not line.strip().startswith("---")
    ).strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


def words(text: str) -> list[str]:
    return re.findall(r"[^\s]+", text)


def word_shapes(text: str) -> set[str]:
    """Lowercased word bigrams, used only to measure how similar two texts
    are to EACH OTHER, not to judge either one."""
    ws = [w.lower().strip(".,!?;:\"'()») ") for w in words(text)]
    ws = [w for w in ws if w]
    return {f"{a} {b}" for a, b in zip(ws, ws[1:])}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


def sentence_stats(text: str) -> tuple[float, float]:
    lens = [len(words(s)) for s in sentences(text)]
    if not lens:
        return (0.0, 0.0)
    mean = stats.mean(lens)
    spread = stats.pstdev(lens) if len(lens) > 1 else 0.0
    return (mean, spread)


def main() -> int:
    cases = sorted(p.stem for p in INPUTS.glob("*.txt"))
    print(f"{'case':<24} {'in avg/spread':<16} {'out avg/spread':<16} {'casing':<10} {'!':<3} {'?':<3}")
    for case in cases:
        in_path = INPUTS / f"{case}.txt"
        out_path = RECORDED / f"{case}.txt"
        if not out_path.exists():
            print(f"{case:<24} (no recorded output)")
            continue
        src = in_path.read_text(encoding="utf-8")
        out = body(out_path.read_text(encoding="utf-8"))
        if not out:
            # An empty recorded file has no text to judge. Treat it the same
            # as a missing one: say so, and keep it out of out_sets below so
            # it doesn't drag the pairwise-similarity average down with a
            # spurious zero, and don't fabricate a "kept"/"changed" casing
            # label from comparing two empty strings.
            print(f"{case:<24} (empty recorded output)")
            continue
        in_mean, in_sd = sentence_stats(src)
        out_mean, out_sd = sentence_stats(out)
        lowercase_in = src.strip()[:1].islower() if src.strip() else False
        lowercase_out = out[:1].islower() if out else False
        casing = "kept" if lowercase_in == lowercase_out else "changed"
        bang = f"{out.count('!')}/{src.count('!')}"
        q = f"{out.count('?')}/{src.count('?')}"
        print(
            f"{case:<24} {in_mean:5.1f}/{in_sd:<9.1f} {out_mean:5.1f}/{out_sd:<9.1f} {casing:<10} {bang:<3} {q:<3}"
        )

    # Main signal: are the outputs converging on one voice?
    in_sets = {c: word_shapes(body((INPUTS / f"{c}.txt").read_text(encoding="utf-8"))) for c in cases}
    out_sets = {
        c: word_shapes(body((RECORDED / f"{c}.txt").read_text(encoding="utf-8")))
        for c in cases
        if (RECORDED / f"{c}.txt").exists() and body((RECORDED / f"{c}.txt").read_text(encoding="utf-8"))
    }
    in_pairs = [jaccard(in_sets[a], in_sets[b]) for a, b in itertools.combinations(cases, 2)]
    out_pairs = [
        jaccard(out_sets[a], out_sets[b])
        for a, b in itertools.combinations(out_sets.keys(), 2)
    ]
    in_avg = stats.mean(in_pairs) if in_pairs else 0.0
    out_avg = stats.mean(out_pairs) if out_pairs else 0.0
    print()
    print(f"Average pairwise similarity between INPUTS:  {in_avg:.4f}")
    print(f"Average pairwise similarity between OUTPUTS: {out_avg:.4f}")
    if out_avg > in_avg + 0.02:
        print("Signal: outputs are more similar to each other than the inputs were.")
        print("This would mean /human is pulling different texts toward one voice.")
    else:
        print("Signal: outputs are not more similar to each other than the inputs were.")
        print("No sign of /human flattening these texts into one voice, by this measure.")
    print()
    print("This measure uses word-bigram overlap. It is a coarse proxy for 'sounds like")
    print("the same author', not a validated stylometric test. Read the actual outputs")
    print("in tests/recorded/ to judge voice for yourself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
