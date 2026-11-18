#!/usr/bin/env python3
"""HumanTouch MCP server (stdio). Read-only tools for hosts that have no slash commands.

Standard library only, fully local: no network, no uploads, nothing is written.
It reuses the scripts in skills/human/scripts/ (one implementation, not a fork).

Tools (all read-only):
  human_audit             report hidden watermark carriers and provenance markers
  human_clean             return a cleaned COPY of pasted text (invisible Unicode removed)
  human_metadata_inspect  list what a file reveals (EXIF, XMP, IPTC, Office, PDF, HTML)

Deliberately NOT exposed: stripping metadata, removing C2PA credentials, replacing look-alike
letters in files. Those need the user's consent and stay in the skill and the command line,
where a person confirms them.

There is no MCP prompt named "human": registering one would create a second command name in
hosts that turn prompts into slash commands. The rewriting rules are offered as a resource.

Run:  python3 mcp/human_touch_mcp.py   (speaks newline-delimited JSON-RPC on stdin/stdout)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.environ.get("HUMAN_TOUCH_SCRIPTS") or os.path.join(os.path.dirname(HERE), "skills", "human", "scripts")
sys.path.insert(0, SCRIPTS)

import _audit_lib as audit  # noqa: E402
import _clean_lib as clean  # noqa: E402
import _meta_lib as meta  # noqa: E402
import watermark_audit as wm  # noqa: E402

def _version():
    try:
        with open(os.path.join(SCRIPTS, "..", "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0"
    except OSError:
        return "0"


SERVER = {"name": "human-touch", "version": _version()}
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MODERN = "2026-07-28"
SUPPORTED = LEGACY
PROTO_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS = {"tools": {"listChanged": False}, "resources": {"listChanged": False}}
INSTRUCTIONS = ("Read-only HumanTouch tools: audit text/files for hidden watermark carriers, return a cleaned "
                "copy of text, inspect file metadata. To rewrite prose, read the resource humantouch://rules "
                "and apply it.")
MAX_TEXT = 2_000_000
RULES_PATHS = (
    os.path.join(os.path.dirname(HERE), "adapters", "shared", "CORE-PROMPT.md"),
    os.path.join(HERE, "CORE-PROMPT.md"),
)

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {
        "name": "human_audit",
        "title": "Audit text or a file for hidden watermark carriers",
        "description": (
            "Read-only. Reports invisible and look-alike characters (zero-width, variation selectors, "
            "tag characters, homoglyphs, ...) in pasted text or in a file (text, Markdown, HTML, DOCX), and "
            "C2PA/signature markers in images, PDF and Office files, by presence only. Never changes anything. "
            "It cannot detect statistical watermarks in word choice and never proves a text has no watermark."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to audit (use this or path)."},
                "path": {"type": "string", "description": "Absolute path of a local file to audit."},
            },
        },
        "annotations": {**READ_ONLY, "title": "Audit for hidden watermark carriers"},
    },
    {
        "name": "human_clean",
        "title": "Return a cleaned copy of text",
        "description": (
            "Read-only. Returns a cleaned COPY of the pasted text without invisible or anomalous Unicode "
            "(zero-width characters, stray variation selectors, odd spaces, direction controls in left-to-right "
            "text, tag characters, control characters). Wording is never changed. Legitimate uses (emoji "
            "sequences, joining scripts, French spacing) are kept. Nothing is written to disk."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to clean."},
                "protect_code": {"type": "boolean", "description": "Leave fenced and inline code untouched."},
            },
            "required": ["text"],
        },
        "annotations": {**READ_ONLY, "title": "Clean invisible Unicode (copy)"},
    },
    {
        "name": "human_metadata_inspect",
        "title": "Inspect what a file reveals",
        "description": (
            "Read-only. Lists the metadata a local file carries (EXIF/GPS, XMP, IPTC, PNG text, Office "
            "properties, PDF info, HTML meta) and whether C2PA credentials or signatures are present "
            "(presence only, validity not checked). It always states what was NOT checked. Removal is not "
            "available here."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute path of a local file."}},
            "required": ["path"],
        },
        "annotations": {**READ_ONLY, "title": "Inspect file metadata"},
    },
]


def _text_arg(args, key):
    v = args.get(key)
    if not isinstance(v, str):
        raise ValueError(f"'{key}' must be a string")
    if len(v) > MAX_TEXT:
        raise ValueError(f"'{key}' is larger than {MAX_TEXT} characters")
    return v


def tool_audit(args):
    if args.get("path"):
        if not isinstance(args["path"], str):
            raise ValueError("'path' must be a string")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = wm.main([args["path"]])
        if rc != 0:
            raise ValueError(buf.getvalue().strip() or "audit failed")
        return buf.getvalue().strip()
    text = _text_arg(args, "text")
    return audit.format_report(audit.audit_text(text), "pasted text")


def tool_clean(args):
    text = _text_arg(args, "text")
    spans = clean.code_spans(text) if args.get("protect_code") else []
    result = clean.clean_text(text, protected=spans)
    report = clean.format_report(result, scan_only=False)
    return json.dumps({"cleaned_text": result.text, "changed": result.changed, "report": report},
                      ensure_ascii=False, indent=2)


def tool_meta(args):
    path = args.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("'path' must be a non-empty string")
    data = clean.read_input_bytes(path)
    return meta.format_inspection(meta.detect_and_inspect(path, data), path)


HANDLERS = {"human_audit": tool_audit, "human_clean": tool_clean, "human_metadata_inspect": tool_meta}


def rules_text():
    for p in RULES_PATHS:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return None


def reply(msg_id, result=None, error=None, modern=False):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        if modern and isinstance(result, dict):
            result = {"resultType": "complete", **result}
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg):
    method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if msg_id is None:  # notification: no reply
        return
    meta_in = params.get("_meta") if isinstance(params, dict) else None
    version = meta_in.get(PROTO_KEY) if isinstance(meta_in, dict) else None
    modern = version is not None
    if modern and version != MODERN:
        reply(msg_id, error={"code": -32022, "message": "unsupported protocol version",
                             "data": {"supported": [MODERN], "requested": version}})
        return

    def ok(result):
        reply(msg_id, result, modern=modern)

    if method == "server/discover":
        ok({"supportedVersions": [MODERN, *LEGACY], "capabilities": CAPS,
            "_meta": {"io.modelcontextprotocol/serverInfo": SERVER}, "instructions": INSTRUCTIONS})
    elif method == "initialize":
        want = params.get("protocolVersion")
        ok({"protocolVersion": want if want in SUPPORTED else SUPPORTED[0], "capabilities": CAPS,
            "serverInfo": SERVER, "instructions": INSTRUCTIONS})
    elif method == "ping":
        ok({})
    elif method == "tools/list":
        ok({"tools": TOOLS})
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            reply(msg_id, error={"code": -32602, "message": f"unknown tool: {name}"})
            return
        try:
            ok({"content": [{"type": "text", "text": fn(args)}], "isError": False})
        except (OSError, ValueError, PermissionError) as exc:
            ok({"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True})
    elif method == "resources/list":
        res = []
        if rules_text() is not None:
            res.append({"uri": "humantouch://rules", "name": "HumanTouch writing rules",
                        "description": "The host-neutral rewriting rules. Apply them to rewrite prose.",
                        "mimeType": "text/markdown"})
        ok({"resources": res})
    elif method == "resources/read":
        if params.get("uri") == "humantouch://rules" and rules_text() is not None:
            ok({"contents": [{"uri": "humantouch://rules", "mimeType": "text/markdown", "text": rules_text()}]})
        else:
            reply(msg_id, error={"code": -32002, "message": "resource not found"})
    elif method == "prompts/list":
        ok({"prompts": []})
    else:
        reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main():
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply(None, error={"code": -32700, "message": "parse error"})
            continue
        if not isinstance(msg, dict):
            reply(None, error={"code": -32600, "message": "invalid request"})
            continue
        try:
            handle(msg)
        except Exception as exc:  # noqa: BLE001 - a server must not die on one bad request
            if msg.get("id") is not None:
                reply(msg["id"], error={"code": -32603, "message": f"internal error: {exc}"})


if __name__ == "__main__":
    main()
