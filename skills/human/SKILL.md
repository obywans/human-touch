---
name: human
description: Rewrites text so it reads like natural, human-written prose. Keeps the meaning, facts, language, terminology and the author's tone, and removes formulaic, repetitive or template-sounding patterns. Invoke only when the user types /human. It improves writing quality and does not target or guarantee any AI-detector result.
argument-hint: "[text, or path to a text file]"
disable-model-invocation: true
---

# HumanTouch

Rewrite the text in $ARGUMENTS so it reads as natural, human-written prose.

The goal is writing quality: clearer, more varied, more specific to its context, and free of template-like habits. It is not a tool for evading AI detectors. Never say or imply that the output will pass a detector.

## 1. Read the input

- If $ARGUMENTS is empty, ask the user for the text and stop.
- If $ARGUMENTS is the path to an existing text file, read it. Show the rewrite in the reply. Do not overwrite the file unless the user asks.
- Otherwise treat $ARGUMENTS as the text itself.

Replies that are not the rewrite (questions, requests for text, the Notes line) use the language of the user's request. The rewrite itself keeps the language of the source text.

## 2. Establish what must be preserved

Before rewriting, note internally:

- **Language and variant.** Keep the source language. Keep its regional spelling (es-ES vs es-MX, en-US vs en-GB). Do not translate unless asked.
- **Register.** Casual chat, professional email, report, academic, marketing, or narrative.
- **Facts and specifics.** Every number, date, name, place, quote, URL, code, identifier, version, price, and legal or technical term.
- **Required terminology.** Terms the author uses on purpose, even if they look repetitive.
- **Every claim.** Each point the text makes. Do not add claims, and do not drop any.

## 3. Remove the artificial patterns

Fix these where they occur. Not every instance is a problem. Fix the ones that make the text sound generated.

- **Dashes and punctuation.** Replace em dashes and stacked punctuation with commas, periods, colons, or parentheses where that reads better. Keep dashes that are the author's habit or that mark ranges, lists, or numbers.
- **Filler openers.** "In today's world", "It's important to note that", "In the realm of", "Let's dive in", "Certainly!", "Great question". Start with the content.
- **Formulaic sequencing.** "Firstly / Secondly / Finally", and stacks of "Moreover / Furthermore / Additionally / In addition". Use transitions only when the logic needs one.
- **Conclusions that repeat the introduction.** Cut them, or replace them with a concrete point, next step, or open question taken from the text.
- **Unnecessary structure.** Headings, bullets, and bold in short text where a paragraph would do. Keep structure the content needs.
- **Reflexive triads and contrasts.** "Not just X, but Y", "It's not about X, it's about Y", and lists of three where two or four items fit the content.
- **Vague claims.** "Many experts agree", "significant benefits", "a wide range of". If the source gives no specifics, keep the claim as vague as the source is. Do not invent specifics. Mention the gap in the Notes line.
- **Excess hedging.** Stacks such as "may potentially be able to". Keep the hedges that reflect real uncertainty.
- **Inflated vocabulary.** "crucial", "pivotal", "vital", "robust", "seamless", "comprehensive", "leverage", "delve", "tapestry", "landscape", "foster", "underscore", "showcase", "testament", "groundbreaking", "vibrant", "embark". Use plainer words, or repeat a precise word rather than rotating synonyms.
- **Repeated adjectives and adverbs.** Keep one good word and drop the rest.
- **Uniform rhythm.** Sentences of the same length and paragraphs of the same size. Vary them naturally, following the content.
- **Over-explanation.** Explanations of things the reader already knows, and recaps of what was just said.
- **Marketing polish.** Empty superlatives and brochure phrasing in text that should sound direct.

## 4. Adapt to the register

| Register | Target |
|---|---|
| Casual message | Conversational, short, direct. Contractions and plain words are fine. |
| Professional email or text | Clear, courteous, specific. No filler, no slang, no emojis unless the original has them. |
| Long-form | Paragraphs of varied length, a clear through-line, few headings, examples only from the source. |
| Already natural | Minimal edits. Say so in the Notes line. Do not rewrite for the sake of rewriting. |

Never make a formal text informal. Never make an informal text stiff.

## 5. Hard rules

- Do not change facts, figures, names, dates, quotes, code, URLs, or required terms.
- Do not add claims, examples, citations, or sources that are not in the input.
- Do not add typos, grammar errors, or fake imperfections on purpose.
- Do not add slang, emojis, or jokes the author did not write.
- Do not change the language.
- Do not state or imply any detector score or guarantee.

## 6. Self-check before answering

Confirm all of these. If one fails, fix it:

1. Every fact, number, name, date, and term from the input is present and unchanged.
2. Every claim is present. None were added.
3. The language and regional spelling match the input.
4. The tone matches the register in step 4.
5. The rewrite contains no em-dash habit, filler opener, or canned transition that the input did not need.
6. There are no new grammar or spelling errors.

## 7. Output format

Return only the rewritten text, unless the user asked for an explanation.

If the user asked what changed, add a short bulleted list of changes after the text.

If something needs attention (a vague claim, a missing fact, an ambiguous sentence), add one line at the end starting with `Notes:`. Keep it to one or two sentences.
