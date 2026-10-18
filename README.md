# HumanTouch

`/human` is a writing skill. It can improve prose, preserve technical code while editing surrounding text, or review citations against sources you provide. It keeps the meaning, facts, language, and tone of the original.

**What it is for:** better writing. Clearer, more specific, more varied text in the register you need.

**What it is not:** a tool for AI-detection evasion or disguising plagiarism. It does not target any detector, promise a score, verify sources it cannot access, or claim that paraphrased copied work is original.

## One workflow, several hosts

The writing rules and modes are bundled in `skills/human/SKILL.md`; provider-neutral instructions are in `adapters/shared/CORE-PROMPT.md`. The 2.0.0 package has no updater, network call, MCP server, or external service dependency. Its skill only gives instructions; the host model processes the text.

| Where you want to use it | Setup |
|---|---|
| ChatGPT and Codex | Use the portable `plugin.json` package in a supported local plugin marketplace. |
| Claude Code | Copy or symlink `skills/human` into Claude Code's skills folder. |
| Gemini | Create a Gem and paste the instructions from `adapters/gemini/GEM.md`. |
| Local Qwen / llama.cpp | Paste `adapters/local-qwen/SYSTEM-PROMPT.md` into the local chat's system prompt. It makes no network requests. |
| ChatGPT custom instructions | Use the compact text in `adapters/chatgpt/CUSTOM-INSTRUCTIONS.md` if you don't install the full skill as a plugin. |

The ChatGPT/Codex portable plugin format is documented by [OpenAI](https://developers.openai.com/plugins/build/plugins). ChatGPT Custom Instructions are an account setting, not local inference ([OpenAI instructions](https://help.openai.com/en/articles/8096356-chatgpt-custom-instructions)). Gemini Gems accept reusable instructions ([Google instructions](https://support.google.com/gemini/answer/15236405)). For local llama.cpp, the system message is passed by the client with each chat request ([llama.cpp server guide](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).

**Local means local only when you use a model running on your device.** The same prompt can be used in ChatGPT, Codex, or Gemini, but those services process your conversation according to their own cloud settings. This package does not make those services local.

This package is version `2.0.0`. Updates are manual; using it will not contact GitHub.

## Usage

Type `/human` followed by the text where slash skills are supported, or ask the assistant directly to improve, edit safely around code, or review sources:

```text
/human hey! so i finally finished the report, it was kind of a nightmare but i think it turned out pretty good.
```

You can also pass a path to a text file. The assistant reads the file and shows the rewrite in the reply. It does not overwrite the file:

```text
/human notes/draft-email.txt
```

With no text, `/human` asks for the text.

Ask for an explanation of the changes by adding it to the request, for example `/human please list what you changed: <text>`.

Choose a mode when useful:

- `/human code-safe rewrite: <text>` edits the prose while keeping code blocks, inline code, commands, identifiers, URLs, and configuration values unchanged.
- `/human source review: <draft and references>` checks claims against the references you provide and reports unsupported claims or citation gaps. It does not invent sources.

For copied material, HumanTouch can help you write an original explanation from your own understanding, retain quotations, and cite sources. It cannot make copied ideas original by rewording them.

On ChatGPT or Gemini, use the matching plugin/custom-instructions/Gem setup above. On local Qwen, keep the prompt in the system message. This does not automatically configure every app on your device.

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

Supported: English, Spanish, French and Romanian (Spanish, French and Romanian each have their own extra language-specific notes; English uses the general rules directly). Other languages get the general rules only.

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
python3 tests/test_check_outputs.py             # checker regression tests (Unicode normalization, clean failures)
python3 tests/test_style_report.py              # style_report.py regression test (empty vs. missing recorded file)
```

- `tests/inputs/` holds sixteen representative texts: the ten from before, plus technical documentation, a social post, a WhatsApp message, a business proposal, a personal message, and a second technical text, across English, Spanish, French and Romanian.
- `tests/recorded/` holds the outputs of `/human` on those inputs, one run per case with the current skill.
- `tests/expectations.json` lists, for each case, every claim of the source as a group of accepted forms (a claim survives if any form is present), the facts that must survive word for word, and the phrases that must not appear.
- `tests/check_outputs.py` checks each output against those expectations. It ignores the `Notes:` line.
- `tests/style_report.py` reports sentence-length patterns per case, and whether the sixteen outputs are, on average, more similar to each other than the sixteen inputs were. That is the closest thing here to checking "does everything end up sounding like the same person", and it is a coarse proxy, not a validated measure.
- `tests/test_check_outputs.py` and `tests/test_style_report.py` are regression tests for the test tooling itself, added after a review found real bugs in it (Unicode NFC/NFD handling in the checker; an empty recorded file being treated as real data in the style report).

The checker verifies the claims and facts it was told to look for. It does not read the whole text on its own, so a dropped claim is caught only if it is listed. It does not judge quality, and a passing result does not mean a text is good. Read the output yourself.

## Repository layout

```text
plugin.json                       portable ChatGPT/Codex plugin manifest
skills/human/SKILL.md             the slash-command skill
skills/human/VERSION              local package version
adapters/                         shared prompt, ChatGPT, Gemini, and local Qwen instructions
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
