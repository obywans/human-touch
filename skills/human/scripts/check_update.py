#!/usr/bin/env python3
"""Throttled, fail-safe update check for HumanTouch.

Usage: python3 scripts/check_update.py [--quiet]

Prints at most two lines:
  UPDATE_AVAILABLE installed=X.Y.Z latest=A.B.C url=<release url>
  WIKIPEDIA_CHANGED url=<page url>
or, without --quiet, also:
  UP_TO_DATE installed=X.Y.Z

On ANY problem (no VERSION file, offline, GitHub down, malformed response,
rate limit, anything) each check prints nothing of its own and exits 0. It
never raises, and it never blocks for more than a few seconds. This script
only ever reads state and talks to the network; it does not change any
installed file, and the Wikipedia check never reads the page's content or
touches SKILL.md — it only reports that the page changed. See
apply_update.py for the code-version update, and README.md's "Auto-update"
section for what a human does with a Wikipedia-changed notice. /human must
work identically whether this script succeeds, fails, or is missing
entirely.
"""
import sys
import time

import _update_lib as lib


def _check_github_release(installed: str, state: dict, quiet: bool) -> list[str]:
    if not lib.should_check(state):
        cached_latest = state.get("last_known_latest")
        if cached_latest and lib.is_newer(cached_latest, installed):
            url = state.get("last_known_url") or ""
            return [f"UPDATE_AVAILABLE installed={installed} latest={cached_latest} url={url}"]
        return [] if quiet else [f"UP_TO_DATE installed={installed}"]

    try:
        release = lib.fetch_latest_release()
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        state["last_checked_epoch"] = time.time()
        state["last_result"] = f"error: {lib.describe_fetch_error(exc)}"
        return []  # offline / GitHub down / bad response: say nothing, move on

    state["last_checked_epoch"] = time.time()
    state["last_known_latest"] = release["tag"]
    state["last_known_url"] = release["html_url"]
    state["last_result"] = "ok"

    if lib.is_newer(release["tag"], installed):
        return [
            f"UPDATE_AVAILABLE installed={installed} latest={release['tag']} "
            f"url={release['html_url']}"
        ]
    return [] if quiet else [f"UP_TO_DATE installed={installed}"]


def _check_wikipedia_page(state: dict) -> list[str]:
    """Notice-only: reports when the source Wikipedia page's revision id
    changes since the last check. Never fetches the page's content, never
    changes SKILL.md. A human decides whether anything needs updating."""
    if not lib.should_check(state, key="wiki_last_checked_epoch"):
        return []

    try:
        revision = lib.fetch_wikipedia_revision()
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        state["wiki_last_checked_epoch"] = time.time()
        state["wiki_last_result"] = f"error: {exc}"
        return []  # offline / Wikipedia down / bad response: say nothing

    previous_revid = state.get("wiki_last_known_revid")
    state["wiki_last_checked_epoch"] = time.time()
    state["wiki_last_known_revid"] = revision["revid"]
    state["wiki_last_result"] = "ok"

    if previous_revid is not None and revision["revid"] != previous_revid:
        url = f"https://en.wikipedia.org/wiki/{lib.WIKI_PAGE_TITLE.replace(' ', '_')}"
        return [f"WIKIPEDIA_CHANGED url={url}"]
    return []


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    skill_dir = lib.skill_dir_from_script(__file__)

    installed = lib.read_installed_version(skill_dir)
    if not installed:
        return 0  # no VERSION file: nothing to compare against, say nothing

    state = lib.load_state()
    lines = []
    lines += _check_github_release(installed, state, quiet)
    lines += _check_wikipedia_page(state)
    lib.save_state(state)

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
