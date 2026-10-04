# Changelog

Every correction is recorded here, starting with 1.0.1. Each version is tagged in git and published as a GitHub release.

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
