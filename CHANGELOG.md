# Changelog

Every correction is recorded here, starting with 1.0.1. Each version is tagged in git and published as a GitHub release.

## 3.3.2 (2026-11-26)

### Changed
- The rules follow the Wikipedia page "Signs of AI writing" at revision 1387897756 (2026-11-25T22:43:03Z). The text is a short paraphrase. The page text is not copied.
- Vocabulary. The skill file `skills/human/SKILL.md` lists more words and phrases that the page names as signs: "bolstered", "boasts", "deeply rooted", "diverse array", "enduring", "exemplifies", "garner", "indelible mark", "interplay", "meticulously", "nestled", "profound", "renowned", "showcasing", "serves as a", "evolving landscape", "key turning point", "valuable insights", "despite these challenges", "deep dive" and "focal point". The skill judges these by density. One use is normal. The skill keeps a word that is a precise term in its field.

### Notes
- Only `skills/human/SKILL.md` has a word list. The portable prompts have no word list, so they do not change.
- No rule was removed. The sign "sentences of 8 to 20 words" is still not adopted. See 3.3.0.

## 3.3.1 (2026-11-22)

### Changed
- The portable prompts now follow the rules of 3.3.0. 3.3.0 changed only the skill file `skills/human/SKILL.md`. The files `adapters/shared/CORE-PROMPT.md`, `adapters/gemini/GEM.md`, `adapters/local-qwen/SYSTEM-PROMPT.md` and `adapters/chatgpt/CUSTOM-INSTRUCTIONS.md` did not change. Hosts without the skill folder had the old rules.
- The new text says: keep the variety of punctuation, do not strip every dash, cut empty corrective disclaimers, keep a caveat that has a reason, and keep short sentences in technical text.
- `docs/always-on.md` has one new line with the same rule on punctuation and caveats.
- `README.md`: the table "Routes" now lists every host group. The groups are the skill folder (Claude Code, Codex, Gemini CLI), the MCP server (Claude Desktop, Cursor, LM Studio, Open WebUI), the two packages, and the text-only hosts (ChatGPT, Gemini app, Gems, Custom GPTs, local models). Each row says how that group gets an update. Text-only hosts have no update check. The user pastes the new text again.

### Notes
- HumanTouch is not only for Anthropic products. The rules and the update notice work in every host in the table.
- The suite has 255 tests. All pass.

## 3.3.0 (2026-11-22)

### Changed
- The rules follow the Wikipedia page "Signs of AI writing" at revision 1387041075 (22 November 2026). The text is a short paraphrase. The page text is not copied.
- Dashes. The skill no longer replaces every em dash. The page now says that newer models avoid em dashes, and that text with only commas and periods is itself a sign. The skill replaces a formulaic em dash and keeps the punctuation the author used. Self-check 5 follows the same rule.
- Vocabulary. The list has new words from the newest model generation: "emphasizing", "highlighting", "enhance", "multifaceted", "prioritize", "dependable", "universally", "quietly" and "steady". The skill judges these words by density. One use is normal. The skill also states that a synonym of an overused word is not overused by that fact.
- The example for "crucial" now gives "important" or "essential". The word "key" is on the page list of overused words, so the skill no longer suggests it.
- New rule "Corrective disclaimers". It covers empty warnings such as "should be treated as X rather than Y", "does not establish" and "should not be confused with". The skill keeps a caveat that the source states with a reason. It keeps the qualifiers that legal, medical, financial or scientific text needs.
- Rule "Uniform rhythm". The skill now keeps short sentences in technical, procedural and plain-language text.

### Not adopted
- The page lists strict sentences of 8 to 20 words as a sign of the newest models. The skill does not act on this sign. Many users write short procedure sentences on purpose, for example under ASD-STE100. A rule against short sentences would damage that text.

### Tests
- The suite has 255 tests. All pass. No test changed.

## 3.2.1 (2026-11-18)

### Removed
- The Claude Code plugin route of 3.2.0. A plugin gives the command `/human-touch:human`. The only route for Claude Code is now the skill folder, with the command `/human`.

### Changed
- The text for an old plugin install tells the user to move to the skill folder.
- Tests: the suite has 255 tests. Five manifest tests of 3.2.0 became four tests in `tests/test_v320.py`. One new test checks that `.claude-plugin/` does not exist.

## 3.2.0 (2026-11-18)

### Added
- The Claude Code plugin route is back. The folder `.claude-plugin/` holds `plugin.json` and `marketplace.json`. Both point to `skills/`, so one copy of the skill serves both routes. The plugin command is `/human-touch:human`. The skill-folder command stays `/human`.
- Update of a plugin install. `check_update.py` prints `PLUGIN_INSTALL installed=X latest=Y url=...` when a newer release exists. After the work, the skill asks for consent. If the owner agrees, it runs `claude plugin marketplace update human-touch` and then `claude plugin update human-touch@human-touch`. The owner restarts Claude Code or runs `/reload-plugins`. If a command fails, the skill shows both commands and does not retry.
- Notice for a package install. When the skill folder cannot be written (for example the `human-skill.zip` in claude.ai) and a newer release exists, `check_update.py` prints `PACKAGE_INSTALL`. The skill gives the version, the release link and the upload steps. It does not claim that it updated itself.
- New MCP tool `human_update_check`. It is read-only. It makes one HTTPS request to the GitHub releases API when the owner asks. It returns the installed version, the latest version, the release link and the words "Reinstall the extension by hand: Claude Desktop does not update this file". It is the only tool that uses the network. A failed request returns one short line and no error trace.
- 18 new tests in `tests/test_v320.py` (256 in total).

### Changed
- `apply_update.py` refuses to write in `plugins/cache` and in `plugins/marketplaces`. The message now names the two plugin commands.
- `README.md`: the section "Move from the plugin route" is now "Choose a route". It shows the commands and the update method of each route. The false sentence "There is no plugin and no marketplace" is removed.
- The MCP server has four tools. Two existing tests changed for this reason: `test_media_strip.McpAndExitTests.test_mcp_inspects_the_new_formats_and_stays_read_only` and `test_mcp.McpTests.test_handshake_and_tool_list` now expect `human_update_check` in the tool list.
- `ACTUALIZAR.md` is rewritten with one block for each notice line.

### Not added
- No update without consent. No new dependency. No network use other than the update check and `human_update_check`.

## 3.1.0 (2026-11-18)

### Added
- Metadata inspection and removal, with consent, for four more formats: EPUB, HTML, MP3 and MP4/M4A/MOV. Each report keeps its "NOT checked" line.
- EPUB: the tool reads `META-INF/container.xml` and the OPF file. It removes the blocks `creator` (creator and contributor), `publisher`, `rights`, `software` (generator and `calibre:*` values) and `dates`. It keeps `dc:title`, `dc:language` and `dc:identifier`.
- EPUB: the tool writes a new ZIP file. `mimetype` is the first entry and is stored without compression. The other parts stay byte-identical. The tool refuses an unsafe path, an encrypted entry and an oversize part.
- HTML: the tool removes whole `<meta>` tags of the blocks `meta-identity`, `meta-software` and `meta-social`. All other bytes stay the same. The tool checks the result after the write.
- MP3: the tool reads ID3v2 (versions 2.2, 2.3 and 2.4, with unsynchronisation, extended header and footer) and ID3v1. It removes the blocks `id3v2` and `id3v1`. The audio frames stay byte-identical.
- MP4, M4A and MOV: the tool walks the atoms. It reports `udta`, `ilst`, `moov/meta` and `uuid` atoms. It changes the `udta` atom to `free` and sets its bytes to zero. Sizes and `stco` values stay the same.
- The tool detects C2PA data in an MP4 `uuid` atom and in an ID3v2 frame. It does not validate it. The file needs `--break-provenance`. The tool removes C2PA data only from JPEG and PNG files.
- The plan of a removal shows format notes, for example which fields the tool keeps.
- 42 new tests on files built in memory (238 in total). The 3.0.0 entry said 195 tests; the real number was 196.

### Changed
- The inspection of HTML counts the `<meta>` tags per block. It ignores a `<meta>` text inside a comment, a script or a style.
- A removal on an HTML file no longer returns exit code 2. The test that used HTML as an unsupported format now uses a TXT file.
- After the write, the tool reads the new file back and compares it with the verified data.
- A HEIC or AVIF photo (an `ftyp` atom without a `moov` atom) is not treated as a video. The tool reports it as an unknown format.
- The version number goes from 3.0.0 to 3.1.0 because `strip` accepts four new formats.

### Limits
- The tool reports the `moov/meta` fields of an MP4 file (iPhone make, model, location) and `uuid` atoms. It does not remove them.
- The tool does not check APEv2 tags or an ID3v2 tag at the end of an MP3 file.
- The tool does not check the NCX file or the content documents of an EPUB file.

## 3.0.0 (2026-11-18)

### Added
- Metadata removal for PDF files (Info dictionary and uncompressed XMP packet), with consent. The tool overwrites the bytes in place. The file length and the `startxref` values do not change.
- The tool blanks every copy of the Info object in all revisions of the file. It reports how many copies it blanked.
- The tool refuses an encrypted PDF and a PDF whose Info dictionary is in a compressed object stream. It writes nothing and returns exit code 2.
- Tests on real structures for PDF, JPEG, PNG and DOCX (28 new tests, 195 in total).

### Changed
- The inspection of a PDF no longer says that removal is not supported. It lists the limits.
- The inspection of a PDF reads strings with nested parentheses and escapes. Before, it stopped at the first closing parenthesis.
- The report of a PDF lists what the tool does not change or check: page content, embedded images, fonts and objects in compressed object streams.
- The inspection reads every XMP packet that is stored uncompressed in a metadata stream. A packet inside an image stream is not read or changed.
- The inspection reports the number of copies of the Info object. The `blocks` count includes only copies and packets that still hold text.
- The README line "This package is version" shows 3.0.0. Before, it showed 2.6.0.
- The version number goes from 2.6.1 to 3.0.0 because `strip` accepts a new format.

## 2.6.1 (2026-11-18)

### Changed
- The update check contacts GitHub at most once in an hour. Before, it waited 20 hours. A new release now reaches users within an hour.

## 2.6.0 (2026-11-18)

### Added
- MCP server `mcp/human_touch_mcp.py` for desktop apps. It uses only the Python standard library. It has three read-only tools: `human_audit`, `human_clean` and `human_metadata_inspect`. It gives the writing rules as a resource.
- The MCP server supports revision 2026-07-28 (no handshake) and the older revisions. It has no tool that needs consent. It has no prompt named `human`.
- Installers: `install.sh` for macOS and Linux, `install.ps1` for Windows. They link one clone into `~/.claude/skills/human` and `~/.agents/skills/human`. They never overwrite existing files.
- The option `--gemini-command` adds a Gemini CLI command, so Gemini CLI gets `/human`.
- `tools/build_packages.py` builds `human-skill.zip` for claude.ai and `human-touch.mcpb` for Claude Desktop.
- Continuous integration on Ubuntu, macOS and Windows with Python 3.9, 3.10, 3.12 and 3.13.

### Changed
- The plugin route is removed. Claude Code adds a prefix to plugin skills, so the command was `/human-touch:human`. The command is now `/human`. A copy that was installed as a plugin tells the user to move to the skill install.
- The update check runs first in each `/human` call again. It contacts GitHub at most once in 20 hours. The skill asks for consent before it updates.
- The scripts run on Python 3.9. A Codex test showed that macOS `python3` is often 3.9, and the scripts failed there before.
- The adapters for ChatGPT, Gemini and local models say that Clean and Audit need the skill or the MCP server.
- The README has one Install section. It shows which hosts the maintainer tested.

## 2.5.1 (2026-11-18)

### Changed
- README: the recommended Claude Code install is now the skill route, whose command is `/human`. A plugin's skill is always prefixed by Claude Code (`/human-touch:human`), which the README now says.
- Lower cost per use, no feature removed. `SKILL.md` went from about 30 KB to about 20 KB: the Clean, Metadata, Audit and Plain details moved to `scripts/MODOS_TECNICOS.md`, and the update-check details to `scripts/ACTUALIZAR.md`. Both are read only when needed. Measured with `claude plugin details`: about 10.1k to about 5k tokens per invocation, and about 230 to about 85 always-on tokens.
- Plugin installs no longer run the update check on each call (the plugin manager updates them).
- Shorter skill description.

## 2.5.0 (2026-11-18)

### Added
- **C2PA removal, opt-in** (JPEG and PNG): `metadata_inspect.py strip <file> --remove-provenance --confirm` writes a new file without the content credentials (all JUMBF segments). Without the flag, credentials are still never removed. It needs a dry run and consent, says that removal does not prove that no provenance remains, and `SKILL.md` forbids it where disclosure is required.
- **Look-alike letter fix, opt-in**: `text_clean.py clean <file> --fix-homoglyphs` replaces Cyrillic and fullwidth look-alikes inside Latin words. Off by default; reported as "replaced".
- `tests/test_opt_in_removal.py`.

### Still not included
Detector scoring and the measure-before/after rewriting loop (it exists to move a detector's verdict), the file-write hook, and the Docker HTTP service (external dependencies; its functions that make sense here are native now). Rewrite mode keeps its rule of never promising a detector result.

## 2.4.0 (2026-11-18)

### Added
- **Audit mode** (`/human audit <text or file>`), report only: detects hidden watermark carriers that Clean did not cover (variation selectors, combining grapheme joiners, noncharacters, reserved and private-use code points, deprecated format controls, Khmer and Hangul fillers outside their script, look-alike letters inside Latin words) together with everything Clean already finds, and reports C2PA credentials and signatures by presence. Legitimate uses (emoji sequences, ideographic variation sequences, Mongolian, Khmer and Hangul text) are not flagged. It never states that a text has no watermark.
- Detection tables and context rules adapted from Watermarks Remover by Guillaume Meyer (MIT, https://github.com/guillaumemeyer/watermarks-remover). Credits in README.md, full licence in THIRD_PARTY_NOTICES.md and in the header of `scripts/_audit_lib.py`.
- Claude Code plugin manifest and marketplace (`.claude-plugin/`): `/plugin marketplace add obywans/human-touch`, `/plugin install human-touch@human-touch`.
- `tests/test_watermark_audit.py`.

### Changed
- **Clean** now also removes the stray carriers that Audit flags (variation selectors, combining joiners, noncharacters, reserved code points, deprecated format controls, fillers outside their script). Audit and Clean share one classifier, so they cannot disagree. Emoji sequences and CJK, Mongolian, Khmer and Hangul uses are kept. Look-alike letters and private-use characters are reported only, never changed.
- The built-in updater detects an installation inside Claude Code's plugin cache and never writes there; it prints the plugin update commands instead.
- README: install and update instructions for each install method; the stated package version (it said 2.2.0) now matches VERSION.

### Not included, on purpose
Watermarks Remover's removal of C2PA credentials, the replacement of look-alike letters, its statistical-watermark rewriting loop, its detector scoring, its HTTP service (Docker) and its file-write hook. They contradict this project's rule of not evading detectors or disguising provenance, and the service needs external dependencies.

## 2.3.0 (2026-11-05)

These changes come from failures that users reported for similar humanizer skills and tools (the GitHub issues listed under "Sources"), checked against this skill's own rules, examples and tests.

### Added
- **Plain mode** (`/human plain: <text>`), on request only, for readers who use machine translation or read the language as a second language: one idea per sentence, common literal words, no idioms or phrasal verbs, the same term for the same thing, acronyms spelled out once, explicit subjects, no long noun chains. It keeps the language, the register and every fact.
- Five test cases built so that the reported failures would fail the checker: `17-numbers-logic-en` (numbers with units, signs and qualifiers; "single most important", "only", "at least", "because", "although"), `18-warning-symbols-en` (❌ and ⚠️ kept), `19-quotes-es` (« » and ¿ ¡ kept, the quotation untouched), `20-honorific-ro` (an honorific kept as written with an ambiguous first name) and `21-plain-translation-en` (idioms replaced in Plain mode). Their recorded outputs, like the new recording of `05-long-form-en`, are single runs of the 2.3.0 skill made from the rules and the input alone. Output varies between runs.
- `tests/make_examples.py` builds `examples/before-after.md` from the recordings, and `python3 tests/make_examples.py --check` fails when the page and the recordings differ.

### Changed
- Claims now include their polarity, ranking and scope words and the logical links between them, and numbers stay bound to their unit, sign, qualifier and role, in order (step 2 and the self-check).
- No invented specifics: a new number, date, name, place, quote, anecdote or specific noun counts as an added claim.
- Triage before editing: few patterns means few edits, and "no change needed" is a valid result.
- Over-editing: no synonym swaps in sentences that already read well, no rarer or more formal synonyms, and no new fragments, dropped subjects or casualness.
- Symbols and emphasis that carry meaning (❌, ✅, ⚠️, warnings) are kept, or their meaning is put into words.
- Languages: each language keeps its punctuation and quotation marks, and quotations are never edited. A language without dedicated notes gets only the edits that can be judged with certainty in it, not the English word lists, and the `Notes:` line says so.
- Precise technical, legal and scientific terms and real hedges are kept.
- File input: the whole file is read every time and never rewritten from memory. A result requested as a file is a new file, and its code, front matter and link targets are checked afterwards.
- Output: prose is not hard-wrapped, intentional line breaks (greetings, sign-offs, addresses, lists, verse, chat) stay, and no blockquote or code fence is added.
- Self-check: four new items (numbers and logic words; paragraph coverage and length within about 15%; symbols, quotes, links, Markdown and code; no new habit).
- Gender and forms of address: the skill never changes or guesses the gender, honorific or pronouns of a named person. When the gender is not established, it keeps the text as written and flags it in the `Notes:` line.
- Portable adapters (`shared`, Gemini, local Qwen, ChatGPT Custom Instructions) and the block in `docs/always-on.md` carry the same new rules in short form.

### Fixed
- `examples/before-after.md` showed older runs that no longer matched `tests/recorded/`: one "after" text added a claim the source did not make ("consistency is what makes the updates believable"), and another changed a text that was already natural. The page is now generated from the recordings.
- `05-long-form-en`: the previous recording dropped two claims (the broader shifts in how work is organized, and the need for policy design), and the checker did not notice. The expectations now require both, and the case was re-recorded.

### Sources
- blader/humanizer issues #78, #93, #146, #172, #187, #212, #238, #306, #326: https://github.com/blader/humanizer/issues
- hardikpandya/stop-slop issues #15, #42, #56: https://github.com/hardikpandya/stop-slop/issues
- devswha/patina issues #870, #872, #882: https://github.com/devswha/patina/issues
- Nanako0129/sepia issue #286: https://github.com/Nanako0129/sepia/issues/286
- op7418/Humanizer-zh issues #11, #41: https://github.com/op7418/Humanizer-zh/issues
- epoko77-ai/im-not-ai issue #74: https://github.com/epoko77-ai/im-not-ai/issues/74

## 2.2.0 (2026-10-29)

### Added
- **Clean** operation (`scripts/text_clean.py`, `scripts/file_clean.py`): finds and removes invisible or anomalous Unicode (zero-width characters, soft hyphens, blank fillers, hidden tag characters, control characters, odd spaces and line separators, direction marks in left-to-right text) and reports every change. Keeps legitimate uses in context (emoji, Persian and Indic joiners, direction marks in right-to-left text, French non-breaking spaces) and reports them as kept. A built-in check proves the visible characters are unchanged. Works on pasted text and TXT, Markdown, HTML and DOCX files, and extracts and cleans PDF text through `pdftotext` when installed. Code regions are never modified.
- **Metadata** operation (`scripts/metadata_inspect.py`): inspects EXIF (including GPS and serial numbers), XMP, IPTC, PNG text chunks, Office document properties, PDF info and HTML meta; explains each field; states what was not checked. Removal works on whole blocks of JPEG, PNG and Office files, writes a new file, is a dry run unless `--confirm` is given, keeps pixels, colour profile and orientation, and re-inspects the result. C2PA credentials and digital signatures are detected (not validated), never removed, and a file carrying them is refused unless `--break-provenance` is added.
- SKILL.md: Clean and Metadata as separate modes, and a technical pre-clean for Rewrite and Code-safe rewrite whose changes are reported in the `Notes:` line.
- Portable adapters now say plainly that these operations need the skill form and must never be claimed.
- Tests: `test_text_clean.py` (37), `test_file_clean.py` (16), `test_metadata.py` (27), with in-memory fixtures. No new dependencies; Python standard library only; macOS, Linux and Windows.

### Not included
- No PDF metadata removal or PDF rewriting, no HTML or WebP metadata removal, no OCR for images, no rewriting of tracked-change author names. These are listed in the README table and refused or reported rather than approximated.

## 2.1.0 (18-10-2026)

### Added
- Restored the skill form's auto-updater (`scripts/check_update.py`, `apply_update.py`, `_update_lib.py`, removed in 2.0.0), unchanged from 1.3.1: anyone still on 1.3.1 or earlier finds and applies 2.1.0 the same way they always found releases, with no gap to bridge. The portable adapters (ChatGPT, Gemini, local Qwen) are unaffected — they are plain pasted text and cannot run scripts, so they get no updater and never will.
- Changed the update flow from silent auto-apply to explicit consent: on finding a newer version, `/human` now asks, in the language of the user's request, whether to update now, and only runs `apply_update.py` on an explicit yes. The previous behavior (1.2.0-1.3.1) applied the update automatically after the reply and only reported it after the fact.
- Restored `tests/test_update.py` (36 tests), unchanged from 1.3.1.

### Known gap
- Anyone who installed exactly 2.0.0 has no updater on disk at all (it shipped without one), so this version's check can never run for them automatically. They need to manually re-copy or re-symlink `skills/human` once to get the updater back; after that, normal updates resume.

## 2.0.0 (2026-10-18)

### Added
- A code-safe rewrite mode that preserves code blocks, inline code, commands, identifiers, URLs, and configuration values exactly while editing surrounding prose.
- A source-review mode that checks draft claims against sources the user provides, reports attribution gaps, and never invents references.
- Clear boundaries against detector evasion, plagiarism concealment, and claims that rewriting makes copied ideas original.
- Portable plugin manifest for ChatGPT/Codex, plus setup adapters for Claude Code, Gemini, ChatGPT Custom Instructions, and local Qwen.
- Removed the automatic updater and its scripts for the local-first edition; updating is manual and does not contact GitHub.

## 1.3.1 (2026-10-08)

### Fixed
- `disable-model-invocation: true` and the description's "Invoke only when the user types /human" meant Claude would only run the skill in response to the literal `/human` command, and refused to run it when a user asked for the same thing in their own words (e.g. "make this sound more human"). That is tighter than intended: a user who doesn't know the exact command shouldn't be told the skill can't help them. Removed `disable-model-invocation` and reworded the description so Claude can invoke the skill either from `/human` or from a plain-language request to make text sound more natural, less AI-sounding, or more human, in any language.

### Verified before publishing
- Grepped the rest of `SKILL.md` and `README.md` for the same restriction — none left.
- Full suite: `tests/check_outputs.py` (16/16), `tests/test_update.py` (36/36), `tests/test_check_outputs.py` (5/5), `tests/test_style_report.py` (2/2) — this change touches only the frontmatter/description, not the update or test code, and all were already passing before the change.

## 1.3.0 (2026-10-08)

### Added
- A Wikipedia change notice. HumanTouch's patterns were informed by Wikipedia's "Signs of AI writing" page, read once by hand, never kept in sync automatically. The existing update check (`check_update.py`), using the same cache file and the same ~20-hour throttle, now also compares that page's current revision id (not its content) against the last one seen. If it changed, `/human` adds one line after the rewrite: a notice with the page's URL. Nothing is read from the page, nothing in `SKILL.md` changes on its own — a person reviews the change, tests anything worth incorporating against the existing cases, and publishes it as a new version, the same as every other change to `SKILL.md` so far. See the "Auto-update" section of README.md.
- `_update_lib.fetch_wikipedia_revision()` and `describe_fetch_error`-style fail-safe handling: offline, Wikipedia down, or a malformed response just means no notice that time; `/human` is unaffected either way.
- `_update_lib.should_check()` now takes a `key` parameter, so the Wikipedia check and the GitHub release check run on independent clocks within the same state file, instead of resetting each other.

### Verified before publishing
- 36 tests in `tests/test_update.py` (up from 31), covering: first check records the revision with no notice, an unchanged revision stays silent, a changed revision prints the notice, Wikipedia being unreachable is silent and safe, and the Wikipedia check never affects the GitHub update notice.
- A real end-to-end run against the live Wikipedia and GitHub APIs: first run recorded the real current revision id with no notice; forcing past the throttle with the same id stayed silent; simulating an old cached id produced the correct notice with the correct URL.
- Full suite: `tests/check_outputs.py` (16/16), `tests/test_check_outputs.py` (5/5), `tests/test_style_report.py` (2/2).

## 1.2.4 (2026-10-08)

### Fixed
- `apply_update.py` labeled every failure to get a usable release — including GitHub responding fine but with something unexpected (a JSON array, `null`, or missing `tag_name`) — as "could not reach GitHub", which is misleading: GitHub was reached, the data just wasn't usable. `_update_lib.py` now has `describe_fetch_error()`, which classifies DNS failures, TLS errors, an HTTP error status, a timeout, and GitHub responding with unusable data as distinct, specific messages, matching the categories the connectivity diagnosis earlier in this project asked for but that hadn't actually been implemented yet. `fetch_latest_release()` also now explicitly checks the response is a JSON object before reading `tag_name` from it, instead of letting a non-dict response raise an unrelated `AttributeError`.
- Three tests in `tests/test_update.py` read a file with a bare `open(...).read()` instead of a context manager, which leaked unclosed file handles (visible as a `ResourceWarning` under `python3 -W error`). Replaced with a small `read_text()` helper.

### Verified before publishing
- This closes out the last 2 of the 12 raw findings from the review that produced 1.2.2 and 1.2.3 (10 were already fixed, 1 was a confirmed false alarm). All 12 are now accounted for: fixed, or correctly dismissed.
- New tests cover the error classifier directly (HTTP status, DNS, TLS, timeout, malformed JSON, unusable release data, an unclassified fallback) and confirm a malformed response is no longer reported as "could not reach GitHub". `python3 -W error tests/test_update.py` no longer reports a `ResourceWarning` from the three fixed tests (a `ResourceWarning` from constructing a test `HTTPError` object for the new error-classification test itself is a separate, cosmetic, test-only artifact, not the issue being fixed here).
- Full suite: `tests/check_outputs.py` (16/16), `tests/test_update.py` (31/31, up from 21), `tests/test_check_outputs.py` (5/5), `tests/test_style_report.py` (2/2), `tests/style_report.py` runs cleanly. A real `check_update.py` run against the live GitHub API still correctly reports `UP_TO_DATE`.

## 1.2.3 (2026-10-08)

### Fixed
- **Security:** `apply_update.py`'s copy-mode update called `os.replace()` directly on the destination path. On POSIX, replacing a path that is itself a symlink unlinks the symlink and puts the new file there — it never writes through to whatever the symlink pointed at. The README's own install method symlinks the whole `human` directory, not individual files inside it, so this never triggers for the documented install path (verified directly: a file reached through a symlinked parent directory is not itself a symlink). But if any individual file under `skills/human/` were ever symlinked some other way, the old code would silently destroy that symlink and leave the real target stale with no warning, contradicting its own "refuse whenever unsure" design. Reproduced with a real symlink before fixing. Now the whole copy-mode update is checked for any symlinked destination and refused outright, before anything is written, if one is found.
- `tests/style_report.py` treated a present-but-empty recorded output file as real data: it printed a fabricated "kept" casing label (comparing two empty strings) and folded an empty word-bigram set into the pairwise-similarity average as a spurious 0.0 — the opposite of how a genuinely missing file is correctly excluded. Now an empty file is reported as `(empty recorded output)` and excluded the same way a missing one is.
- Two new regression test files: `tests/test_check_outputs.py` (added in 1.2.2, listed here for completeness) and `tests/test_style_report.py`, plus a new case in `tests/test_update.py` for the symlink refusal.

### How this was found
A second bug-hunt-and-security review (a retry of the one that failed in 1.2.2's round) completed its search phase but its verification phase again hit a session usage limit partway through — 2 of 12 raw findings were independently verified and acted on in 1.2.2, the other 10 were not auto-verified. Of those 10, these 2 held up under hands-on re-verification (an empirical symlink test and a direct reproduction of the empty-file report), and are fixed here. The others were documentation/maintainability nits already addressed, already fixed, or not reviewed to the same depth this round.

### Verified before publishing
- All tests pass: `tests/check_outputs.py` (16/16), `tests/test_update.py` (21/21, up from 20), `tests/test_check_outputs.py` (5/5), `tests/test_style_report.py` (2/2, new), `tests/style_report.py` runs cleanly.
- The symlink-destination scenario was reproduced directly against `os.replace()` before fixing, and against the real (patched) code after fixing, confirming the symlink and its target are both left untouched when refused.

## 1.2.2 (2026-10-08)

### Fixed
- **Security:** `apply_update.py` called `tf.getmembers()` to list a release archive's files, which pre-loads every member by scanning the whole archive — for a non-seekable gzip stream, that means decompressing straight through a member's full declared content just to reach the next header. A member declaring gigabytes of size would be fully decompressed before the per-member size cap added in 1.2.1 ever got a chance to reject it: a second, distinct decompression-bomb gap (CPU/time, not disk) from the one already fixed. Reproduced with a real crafted archive: the old code took measurable time decompressing a 300 MB-declared member before rejecting it; switching to lazy iteration (`for member in tf:` instead of `tf.getmembers()`) rejects the same member in ~0ms, before any of its content is read.
- `tests/check_outputs.py` compared text with no Unicode normalization. NFC and NFD renderings of the same accented text are byte-for-byte different even though they look identical, which could make the checker miss a kept fact that was really there, and — more seriously — let a banned phrase through completely undetected when it happened to be in the other normal form. All comparisons now normalize to NFC first. New regression tests (`tests/test_check_outputs.py`) reproduce both directions and confirm the fix.
- README overstated that English has "specific notes" the way Spanish, French and Romanian do; it only uses the general rules. Reworded.
- `SKILL.md` never said that the text being rewritten is data, not instructions. Added: pasted text that reads like a command to the model is rewritten like any other sentence, never acted on.
- Two internal contradictions in `SKILL.md`'s context table clarified: "no hedging on facts" for technical documentation does not override keeping a hedge the source genuinely has; and a register row's own instruction (e.g. WhatsApp's "don't fix punctuation habits") now explicitly wins over a general pattern rule when the two conflict for that text.

### How this was found
A background security review of the 1.2.1 push caught the first issue above directly. The rest came from a dedicated bug-hunt-and-security review of the whole project, including three dimensions focused specifically on the update system (network input handling, subprocess argument safety — confirmed safe, no fix needed — and filesystem/symlink safety). Several of that review's findings could not be automatically double-checked because the verification agents hit a session usage limit; the ones acted on here were re-verified by hand, including an empirical, timed reproduction of the decompression-bomb gap, before fixing anything.

### Verified before publishing
- All existing tests pass: `tests/check_outputs.py` (16/16), `tests/test_update.py` (20/20), `tests/style_report.py` (runs cleanly), plus the 5 new `tests/test_check_outputs.py` tests.
- A real end-to-end update was performed against the actual published GitHub repository (no mocks): a symlinked install pinned at v1.2.0 correctly detected v1.2.1 was available, updated via a real git fast-forward, and the resulting installation's `VERSION` and `SKILL.md` were confirmed correct and usable afterward.

### Known limitation
- A full connectivity diagnosis this round also found that `git clone` to `github.com` can return HTTP 403 inside this project's own sandboxed review-agent environment specifically (not from a normal shell, not from DNS/proxy/TLS/permissions, and not from HumanTouch's own update code, which never runs a bare `git clone`). This affected how some of today's review agents worked, not anything a `/human` user would experience, since `check_update.py`/`apply_update.py` only ever use plain HTTPS requests or `git fetch`/`merge` against an existing remote.

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
