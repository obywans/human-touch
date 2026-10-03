# HumanTouch

`/human` is a skill that rewrites text so it reads like natural, human-written prose. It removes filler openers, template-like transitions, repeated vocabulary, and uniform sentence rhythm, and keeps the meaning, facts, language, and tone of the original.

**What it is for:** better writing. Clearer, more specific, more varied text in the register you need.

**What it is not:** a tool for AI-detection evasion. HumanTouch does not target any detector, does not promise any score, and does not claim its output will pass one. The goal is text that a reader finds natural.

## Installation

HumanTouch is a single skill file. Install it as a personal skill, which makes the command `/human` available in every project:

```bash
mkdir -p ~/.claude/skills
ln -s ~/Desktop/human-touch/skills/human ~/.claude/skills/human
```

Use `ln -s` so that a `git pull` in the repository updates the skill. If you prefer a copy, use `cp -R skills/human ~/.claude/skills/` instead.

Start a new session after installing, so the skill is picked up.

The skill is installed as a standalone skill rather than as a plugin on purpose. Plugin skills are namespaced, so a plugin would be invoked as `/human-touch:human`, not `/human`.

## Usage

Type `/human` followed by the text:

```text
/human hey! so i finally finished the report, it was kind of a nightmare but i think it turned out pretty good.
```

You can also pass a path to a text file. The assistant reads the file and shows the rewrite in the reply. It does not overwrite the file:

```text
/human notes/draft-email.txt
```

With no text, `/human` asks for the text.

Ask for an explanation of the changes by adding it to the request, for example `/human please list what you changed: <text>`.

The skill only runs when you type `/human`. The assistant does not invoke it on its own.

## What the skill changes

- **Punctuation:** replaces em dashes and stacked punctuation where a comma, period, colon, or parenthesis reads better. It keeps dashes that are part of the author's style or that mark ranges.
- **Filler and openers:** removes phrases such as "In today's world", "It's important to note", and "Let's dive in".
- **Sequencing and transitions:** removes "Firstly / Secondly / Finally" and stacks of "Moreover / Furthermore / Additionally", unless the logic needs one.
- **Conclusions:** replaces a restatement of the introduction with a concrete point, or removes it.
- **Structure:** removes headings, bullets, and bold from short text where a paragraph works better.
- **Vocabulary:** replaces inflated words ("crucial", "pivotal", "robust", "seamless", "leverage", "delve") with plainer ones, and removes repeated adjectives and adverbs.
- **Rhythm:** varies sentence and paragraph length in line with the content.
- **Register:** keeps the tone the text already has. A casual message stays casual, a formal email stays formal, and an already-natural text gets small edits.

It keeps the source language and regional spelling, and does not translate unless asked.

See [`examples/before-after.md`](examples/before-after.md) for real before and after outputs in English and Spanish.

## What it does NOT guarantee

- It does not guarantee that the output is free of AI-generated traces, and it does not guarantee any result from any AI-detection system.
- It does not check facts. It keeps the facts that are in the input, and it does not verify them.
- It does not add evidence. If a claim is vague, the rewrite stays vague, and the `Notes:` line tells you so.
- It does not replace your judgment about the text. Read the rewrite before you send it.

## Limitations

- Output depends on the underlying model and changes from run to run. The recorded examples show one run.
- Tested on English and Spanish only. Other languages may work, but they are not covered by the tests.
- It cannot learn your personal voice from a few sentences. Each rewrite follows the register of the text you give it.
- It can remove a hedge or a qualifier that you meant. Check the rewrite where precision matters, such as legal, medical, or financial text.
- It does not know your audience unless the text tells it.

## Tests

The tests check the behavior that matters: keeping the facts and the language, and removing the patterns. They do not measure how natural the text sounds, because that needs a human reader.

```bash
python3 tests/check_outputs.py tests/recorded   # rewritten outputs: expect 5/5 pass
python3 tests/check_outputs.py tests/inputs     # original texts: expect failures where patterns exist
```

- `tests/inputs/` holds five representative texts: a generic AI-style English paragraph, a formal Spanish email, a casual English message, a text that is already natural, and a long-form English essay.
- `tests/recorded/` holds the outputs of `/human` on those inputs.
- `tests/expectations.json` lists the facts that must survive each rewrite (names, figures, dates, terms), and the phrases that must not appear.
- `tests/check_outputs.py` checks each output against those expectations. It ignores the `Notes:` line.

The checker is a phrase and fact check. It does not judge quality, and a passing result does not mean a text is good. Read the output yourself.

## Repository layout

```text
skills/human/SKILL.md     the skill (the only file the assistant needs)
examples/before-after.md  before and after outputs
tests/                    inputs, recorded outputs, expectations, checker
README.md, LICENSE, .gitignore
```

## License

MIT. See [LICENSE](LICENSE).
