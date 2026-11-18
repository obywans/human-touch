# Third-party notices

HumanTouch incorporates and adapts work from the following project. Its licence
and copyright notice are reproduced here in full, as the licence requires.

## Watermarks Remover

- **Original author:** Guillaume Meyer and contributors
- **Project:** Watermarks Remover
- **Repository:** https://github.com/guillaumemeyer/watermarks-remover
- **Licence:** MIT

**What HumanTouch took from it:** the Unicode detection tables (variation
selectors, combining grapheme joiners, noncharacters, reserved and private-use
code points, deprecated format controls, Khmer and Hangul fillers), the rules
for which of these are legitimate next to which scripts, and the look-alike
letter (homoglyph) table. They live in `skills/human/scripts/_audit_lib.py`,
which carries this notice in its header.

**What was changed:** detection only, as a read-only "Audit" mode of `/human`.
HumanTouch does not include Watermarks Remover's removal of C2PA content
credentials, its statistical-watermark rewriting, its detector scoring, its
HTTP service or its hooks. C2PA credentials and signatures are still preserved
by HumanTouch, as before.

**What is not the original author's work:** the Audit command line
(`watermark_audit.py`), the merge with HumanTouch's own cleaner, the report
format and the tests are HumanTouch code.

```text
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
```
