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

## Auto-update

Once installed, `/human` keeps itself current without you having to remember `git pull` or check the releases page.

**How it works:** a Claude Code skill is a file read at the moment you type `/human` — there is no background process for it between invocations. So the check happens as part of using `/human` itself: the first thing `/human` does is run `scripts/check_update.py`, which compares your installed version (`skills/human/VERSION`) against [the latest GitHub release](https://github.com/obywans/human-touch/releases/latest). To avoid hitting GitHub on every single use, it caches the result in `~/.cache/human-touch/update-state.json` and only checks again after about 20 hours.

If a newer version exists, the rewrite is delivered exactly as normal, and only afterward — never before, never in the middle — does `/human` add one line telling you the current and latest version, and separately run `scripts/apply_update.py` to try to update for next time. Running the update strictly after the reply is the point: it only ever changes what the *next* `/human` call reads, never the one that just answered you.

**What "update" means here:** only the files in `skills/human/` (mainly `SKILL.md` and `VERSION`) are replaced with the new release's versions. Nothing downloaded is ever executed as code — a copy-mode update downloads a release source archive from GitHub and copies specific files out of it; a git-mode update runs a fast-forward-only `git pull`-equivalent, which git itself refuses if your copy has local changes or has diverged.

**Safety, in order:**
- Every request goes to the fixed, hardcoded `github.com/obywans/human-touch` API endpoint — never a URL from a file, argument, or anything downloaded.
- If you installed via `git clone`/`ln -s`, it checks `git remote get-url origin` actually points at the official repo before touching anything. A fork is left alone, with instructions to update it yourself.
- If you installed via a plain copy (`cp -R`), it still works: version detection and the update itself use the files on disk, not git.
- Any uncommitted local edits to a git install stop the update — it will not overwrite your changes.
- Any problem at all (offline, GitHub down, a malformed response, a permission error, a fork, local edits) leaves every file exactly as it was and is reported as "could not update, here's why, and here's the manual command" — never a silent failure, never a partial write. `/human` itself is unaffected either way; the rewrite above still happened.
- `python3 scripts/apply_update.py --dry-run` shows what would happen without changing anything.

To turn off the automatic apply step and only ever get the one-line notice, delete or don't run `scripts/apply_update.py` yourself — the check in step 0 never applies anything on its own.

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

To have the assistant apply the same rules automatically, in every reply of a session or a project, see [`docs/always-on.md`](docs/always-on.md). That is a block of instructions you add yourself to the project's instructions file; it is not a different mode of the skill.

## What the skill changes

- **Punctuation:** replaces em dashes and stacked punctuation where a comma, period, colon, or parenthesis reads better. It keeps dashes that are part of the author's style or that mark ranges.
- **Filler and openers:** removes phrases such as "In today's world", "It's important to note", and "Let's dive in".
- **Sequencing and transitions:** removes "Firstly / Secondly / Finally" and stacks of "Moreover / Furthermore / Additionally", unless the logic needs one.
- **Conclusions:** replaces a restatement of the introduction with a concrete point, or removes it.
- **Structure:** removes headings, bullets, and bold from short text where a paragraph works better.
- **Vocabulary:** replaces inflated words ("crucial", "pivotal", "robust", "seamless", "leverage", "delve") with plainer ones, and removes repeated adjectives and adverbs.
- **Rhythm:** varies sentence and paragraph length in line with the content.
- **Register:** adapts to context instead of using one style for everything. A WhatsApp message, an email, a business proposal, technical documentation, a social post, personal writing and a long-form article each get different treatment; see the context table in `skills/human/SKILL.md`.
- **Voice:** keeps the author's person, sentence habits and any phrase that is clearly theirs, instead of replacing it with one generic "human" voice.

It keeps the source language and regional spelling. It translates only when you ask for a translation, for example `/human translate to Romanian: <text>`.

Supported with specific notes: English, Spanish, French and Romanian. Other languages get the general rules only.

See [`examples/before-after.md`](examples/before-after.md) for five before/after outputs, and [`examples/evaluation.md`](examples/evaluation.md) for nine more that cover chat, social, technical, business and personal writing across four languages, each with what should change and what must not.

## What it does NOT guarantee

- It does not guarantee that the output is free of AI-generated traces, and it does not guarantee any result from any AI-detection system.
- It does not check facts. It keeps the facts that are in the input, and it does not verify them.
- It does not add evidence. If a claim is vague, the rewrite stays vague, and the `Notes:` line tells you so.
- It does not replace your judgment about the text. Read the rewrite before you send it.

## Limitations

- Output depends on the underlying model and changes from run to run. The recorded examples show one run.
- Tested on English, Spanish, French and Romanian. Other languages may work, but they are not covered by the tests. The French and Romanian notes have not been reviewed by a native speaker.
- It cannot learn your personal voice from a few sentences. Each rewrite follows the register of the text you give it.
- It can remove a hedge or a qualifier that you meant. Check the rewrite where precision matters, such as legal, medical, or financial text.
- It does not know your audience unless the text tells it.
- It can make a text's rhythm more uniform, not less, in some runs. `tests/style_report.py` on the recorded 1.1.0 outputs shows a few cases where sentence-length variety went down after rewriting, which is the opposite of the "allow short, medium and long sentences" rule. This is a known limitation, not something the checker catches.
- The "always on" instructions in `docs/always-on.md` are guidance the assistant follows, not a guarantee. Check important texts before you send them, the same as with `/human` itself.

## Tests

The tests check the behavior that matters: keeping the facts and the language, and removing the patterns. They do not measure how natural the text sounds, because that needs a human reader.

```bash
python3 tests/check_outputs.py tests/recorded   # rewritten outputs: expect 16/16 pass
python3 tests/check_outputs.py tests/inputs     # original texts: expect failures where patterns exist
python3 tests/style_report.py                   # coarse report on sentence rhythm and voice convergence
python3 tests/test_update.py                    # auto-update logic: expect all tests to pass, no network used
```

- `tests/inputs/` holds sixteen representative texts: the ten from before, plus technical documentation, a social post, a WhatsApp message, a business proposal, a personal message, and a second technical text, across English, Spanish, French and Romanian.
- `tests/recorded/` holds the outputs of `/human` on those inputs, one run per case with the current skill.
- `tests/expectations.json` lists, for each case, every claim of the source as a group of accepted forms (a claim survives if any form is present), the facts that must survive word for word, and the phrases that must not appear.
- `tests/check_outputs.py` checks each output against those expectations. It ignores the `Notes:` line.
- `tests/style_report.py` reports sentence-length patterns per case, and whether the sixteen outputs are, on average, more similar to each other than the sixteen inputs were. That is the closest thing here to checking "does everything end up sounding like the same person", and it is a coarse proxy, not a validated measure.
- `tests/test_update.py` tests the auto-update system (see "Auto-update" above) against: the installed version equal to or behind the latest, GitHub being unreachable, GitHub returning something unusable, a failed update leaving files untouched, a git install from an official remote vs. a fork, a plain copy install, a symlinked install, and recovery after a failed attempt. Every network call is mocked, so it runs offline and never touches the real GitHub API.

The checker verifies the claims and facts it was told to look for. It does not read the whole text on its own, so a dropped claim is caught only if it is listed. It does not judge quality, and a passing result does not mean a text is good. Read the output yourself.

## Repository layout

```text
skills/human/SKILL.md             the skill (the only file the assistant needs to follow /human)
skills/human/VERSION              the installed version number, read by the update scripts
skills/human/scripts/             check_update.py, apply_update.py, and their shared _update_lib.py
docs/always-on.md                 instructions block to apply the same rules every reply, in a session or project
examples/before-after.md          before and after outputs
examples/evaluation.md            nine cases with what should and must not change
tests/                            inputs, recorded outputs, expectations, checker, style report, update tests
README.md, CHANGELOG.md, LICENSE, .gitignore
```

## Dedication

Con cariño para Maia, de parte de Leonardo.

## License

MIT. See [LICENSE](LICENSE).
