#!/usr/bin/env python3
"""Build the two uploadable packages into dist/ (standard library only).

  dist/human-skill.zip    the skill, for claude.ai (Customize > Skills > Upload a skill).
                          The ZIP root is the folder `human/`, as that upload requires.
  dist/human-touch.mcpb   the MCP server as a Claude Desktop extension bundle.

Usage: python3 tools/build_packages.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "human")


def version():
    with open(os.path.join(SKILL, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def files_under(base, skip_dirs=("__pycache__",)):
    for dirpath, dirnames, names in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for n in sorted(names):
            if n.endswith((".pyc", ".update-tmp", ".DS_Store")):
                continue
            full = os.path.join(dirpath, n)
            yield full, os.path.relpath(full, base).replace(os.sep, "/")


def add(zf, src, arc):
    info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if arc.endswith((".py", ".sh")) else 0o644) << 16
    with open(src, "rb") as f:
        zf.writestr(info, f.read())


def manifest():
    return {
        "manifest_version": "0.3",
        "name": "human-touch",
        "display_name": "HumanTouch",
        "version": version(),
        "description": "Read-only tools to audit text and files for hidden watermark carriers, "
                       "return a cleaned copy of text, and inspect file metadata. Only the update check uses the network.",
        "author": {"name": "obywans", "url": "https://github.com/obywans"},
        "repository": {"type": "git", "url": "https://github.com/obywans/human-touch"},
        "license": "MIT",
        "server": {
            "type": "python",
            "entry_point": "mcp/human_touch_mcp.py",
            "mcp_config": {
                "command": "python3",
                "args": ["${__dirname}/mcp/human_touch_mcp.py"],
                "platform_overrides": {"win32": {"command": "python"}},
            },
        },
        "tools": [
            {"name": "human_audit", "description": "Audit text or a file for hidden watermark carriers (read-only)."},
            {"name": "human_clean", "description": "Return a cleaned copy of text without invisible Unicode (read-only)."},
            {"name": "human_metadata_inspect", "description": "List what a file reveals: EXIF, XMP, Office, PDF, HTML, EPUB, MP3, MP4/M4A (read-only)."},
            {"name": "human_update_check", "description": "Compare the installed version with the latest GitHub release. One HTTPS request, only when asked (read-only)."},
        ],
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"python": ">=3.10"}},
    }


def build_skill_zip(out):
    path = os.path.join(out, "human-skill.zip")
    with zipfile.ZipFile(path, "w") as zf:
        for src, rel in files_under(SKILL):
            add(zf, src, "human/" + rel)
    return path


def build_mcpb(out):
    path = os.path.join(out, "human-touch.mcpb")
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
        zf.writestr(info, json.dumps(manifest(), indent=2) + "\n")
        add(zf, os.path.join(ROOT, "mcp", "human_touch_mcp.py"), "mcp/human_touch_mcp.py")
        for src, rel in files_under(os.path.join(SKILL, "scripts")):
            if rel.endswith(".py"):
                add(zf, src, "skills/human/scripts/" + rel)
        add(zf, os.path.join(SKILL, "VERSION"), "skills/human/VERSION")
        add(zf, os.path.join(ROOT, "adapters", "shared", "CORE-PROMPT.md"), "adapters/shared/CORE-PROMPT.md")
        add(zf, os.path.join(ROOT, "LICENSE"), "LICENSE")
        add(zf, os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "THIRD_PARTY_NOTICES.md")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    for p in (build_skill_zip(args.out), build_mcpb(args.out)):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
