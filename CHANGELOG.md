# Changelog

Every correction is recorded here, starting with 1.0.1. Each version is tagged in git and published as a GitHub release.

## 1.2.1 (2026-10-07)

### Fixed
- **Security:** `apply_update.py`'s copy-mode path capped the size of the *compressed* download, but not the size written during decompression — a decompression bomb (a small archive that expands to a huge amount of data) could have exhausted disk space. Flagged by a background security review of the 1.2.0 push, confirmed real, and fixed: each archive member is now rejected if its declared size exceeds 2 MB, and the actual bytes written are independently capped per file and across the whole archive (10 MB total), regardless of what the archive's own header claims. Two new tests prove it: one oversized member is rejected with nothing written to any real file, and one normal-sized release still updates successfully.

## 1.2.0 (2026-10-07)

### Added
- An auto-update system. `/human` now checks, at most once per ~20 hours, whether a newer release is published at `https://github.com/obywans/human-touch/releases/latest`, and tells you about it in one line after the rewrite. See the new "Auto-update" section in README.md for exactly how it works and what it does and does not do.
- `skills/human/VERSION`: a single, local source of truth for the installed version, read by the update scripts without needing git (so it works whether the skill was installed by `ln -s`, `git clone`, or `cp -R`).
- `skills/human/scripts/check_update.py`, `apply_update.py`, `_update_lib.py`: the update check and the update itself, as stdlib-only Python with no third-party dependencies.
- `tests/test_update.py`: 18 tests covering the installed version equal to or behind the latest, GitHub unreachable, GitHub returning something unusable, a failed update leaving files untouched, an official git install vs. a fork, a copy install, a symlinked install, and recovery after a failed attempt. All mocked, no real network calls.

### Design decisions, and why
- **The update check runs as part of `/human` itself**, not as a background process — a Claude Code skill has no process between invocations, so there is nothing else that could run it. This is the real constraint, not a shortcut.
- **The actual file update is applied only after the rewrite has already been delivered**, never before or during. This is the direct answer to "what if the skill is updating itself while it's being used": changing files on disk after the reply only affects the *next* `/human` call, never the one in progress, so there is no race with the model's already-loaded instructions for the current turn.
- **Only a Markdown instructions file is ever replaced.** Nothing downloaded is executed as code. A git-mode update is a fast-forward-only pull, which git itself refuses on any local change or divergence. A copy-mode update downloads a release source archive and copies named files out of it; archive members are extracted one at a time, only if they are plain files, only inside the target directory — never through `tarfile.extractall()`, which a static security scan (Semgrep) correctly flagged as unsafe to trust on an untrusted archive even with manual path checks in front of it.
- **The source is never configurable.** `obywans`/`human-touch` and the GitHub API host are fixed constants in the code, never taken from a file, argument, or anything downloaded, and a git install's `origin` remote is checked against that same fixed pattern before any `git fetch`/`merge` runs.
- **Every failure mode reports clearly and changes nothing**: offline, GitHub down, a malformed response, a fork remote, a dirty working tree, a download or extraction error. `/human` itself is unaffected in every case.

### Known limitation
- A planned adversarial security review of this update mechanism (a separate multi-agent pass specifically trying to break it) did not run this round — the review agents hit a session usage limit before producing any result, and were not retried to avoid repeating the failure. The design above was reviewed by hand instead, including fixing one real finding from the session's own Semgrep scan (the `tarfile.extractall()` pattern). A dedicated adversarial review is still worth doing as a follow-up before relying on this for anything higher-stakes than a personal writing tool.

## 1.1.0 (2026-10-07)

### Audit findings (before any change)
- The claim check only verified the exact words listed per case, so a dropped claim could pass unnoticed unless one of its words happened to be listed.
- The skill used one register for every text. There was no guidance to treat a WhatsApp message, a technical explanation and a social post differently, which risked pulling different texts toward the same "clean, natural" voice.
- There was no rule to keep the author's own voice (person, habits, signature phrases) as something to preserve on purpose, only rules to remove patterns.
- No way to use the skill automatically in a session or project; `/human` is, and stays, manual only.

### Added
- A context table in the skill: WhatsApp or chat, email, business proposal, technical documentation, social post, personal writing, long-form article, already natural. Each gets different treatment instead of one generic style.
- A "Voice" rule: keep the author's person, sentence habits and signature phrases; do not replace them with a generic friendly voice; do not give different inputs the same rhythm or closing style.
- An "Over-editing" rule: change only what sounds generated, do not add transitions, headings or a "punchy short sentences" device of its own, do not use semicolons or dashes to look less generated.
- `docs/always-on.md`: an instructions block the user can add to a project's own instructions file (for Claude Code, `CLAUDE.md`) to apply the same rules in every reply, not only on `/human`. This is guidance a project can ask the assistant to follow; it is not a change to how `/human` itself is invoked, and the skill still only runs on `/human`.
- Six new test inputs: technical documentation and a business proposal (English), a social post (English), a WhatsApp message (Spanish), a personal message (Romanian), and a technical explanation (Spanish). Sixteen cases in total.
- `tests/expectations.json` now lists every claim of each source as a group of accepted forms; a claim survives if any form is present. This replaces checking only a few chosen words, which is the limit flagged after 1.0.2.
- `examples/evaluation.md`: nine cases with input, output, what should change and what must not, covering English, Spanish, French and Romanian across chat, social, technical, business and personal writing.
- `tests/style_report.py`: reports sentence-length patterns per case and whether the sixteen outputs are, on average, more similar to each other than the sixteen inputs were. It is a coarse, unvalidated proxy for voice convergence, not a quality score.

### Fixed
- The "keep every claim" rule made the skill preserve filler framing word for word (for example "that is a significant development"), instead of only the claim underneath it. The rule now says keeping a claim means keeping its content, not its exact wording.
- The instruction to list the source's claims before rewriting leaked into the actual reply as visible text ("Claims to preserve: ...") in one case. The skill now says explicitly that this list is working notes and must never appear in the output.

### Known limitations
- `tests/style_report.py` found that sentence-length variety went down after rewriting in a few cases, which is the opposite of the rhythm rule. Recorded as a limitation in the README; not fixed by chasing this single run further.
- The word-bigram similarity measure in `tests/style_report.py` is near zero for both inputs and outputs whenever cases are in different languages, which limits what it can show across languages. Read the actual outputs for a real judgment on voice.
- Outputs in this version are from one run per case. They can vary between runs.

## 1.0.2 (2026-10-04)

### Fixed
- The skill dropped claims from the source. In the Romanian generic test, the closing claim that effective communication is the foundation of high-performing teams was removed. The skill now lists the source's claims before rewriting and keeps every one of them, including claims that appear only in a conclusion. Removing a sentence is allowed only when all its claims survive elsewhere.
- Conflict between two rules: keeping the author's strength and replacing inflated words made the skill reintroduce "crucial" and "cornerstone". The vocabulary rule now gives examples of replacements of the same strength ("crucial" becomes "essential" or "key", "cornerstone" becomes "foundation").

### Changed
- Tests check the claims that were lost before: "high-performing" (English), "choices" (long-form English), "performantes" (French) and "performante" (Romanian).

### Known limitations
- The checker verifies the words listed in `tests/expectations.json`. It does not read the whole text, so a dropped claim is caught only if it has a listed word.
- Results are from one run per case, with the corrected skill. Outputs can change between runs.

## 1.0.1 (2026-10-04)

### Added
- Language notes for French and Romanian, next to the existing English and Spanish ones. For any other language the skill applies only the general rules.
- Translation on request: when the user explicitly asks for a translation (for example "Translate to Romanian"), the skill translates the rewritten text as natural prose and keeps every fact.
- Tests for French and Romanian: a generic AI-style text and a formal email in each language, plus an English to Romanian translation case. Ten cases in total, with recorded outputs in `tests/recorded/`.
- Dedication in the README.

### Fixed
- The skill weakened the author's judgments: "exemplary" became "good", in French and in Romanian. The skill now keeps the strength of the author's praise and claims. Found by the French email test and the translation test, and fixed before recording the final outputs.
- The checker did not recognize the French "Notes :" line, because it has a space before the colon. It now does.
- The checker now checks that the strength of the author's praise is kept, not only the facts.
- Product names were removed from the README, the `.gitignore` comment, the examples and the commit message.

### Known limitations
- The French and Romanian notes are a working list of common patterns in those languages. They have not been reviewed by a native speaker.
- The "Signs of AI writing" page exists in English only. No official French or Romanian version was found, so those notes are not a translation of that page. The English page was read through a summary tool, not copied word for word.
- Outputs of cases 01 to 07 and 09 come from the first run, before the praise rule was added. Cases 08 and 10 were re-run after the fix. All ten pass the current checker.
- The checker looks for phrases and facts. It does not measure how natural a text sounds, and it is not an AI detector.

### Not included
- A check that predicts whether a text passes third-party AI detectors. The project's purpose is writing quality, not detector evasion.

## 1.0.0 (2026-10-03)

### Added
- Initial skill `/human`, with English and Spanish notes.
- README, LICENSE (MIT), `.gitignore`.
- Five test inputs in English and Spanish, recorded outputs, expectations, and a checker that verifies kept facts and absence of banned phrases.
- Before and after examples.
