#!/usr/bin/env python3
"""Throttled, fail-safe update check for HumanTouch.

Usage: python3 scripts/check_update.py [--quiet]

Prints at most one line:
  UPDATE_AVAILABLE installed=X.Y.Z latest=A.B.C url=<release url>
or, without --quiet, also:
  UP_TO_DATE installed=X.Y.Z

On ANY problem (no VERSION file, offline, GitHub down, malformed response,
rate limit, anything) this prints nothing and exits 0. It never raises, and
it never blocks for more than a few seconds. This script only ever reads
state and talks to the network; it does not change any installed file —
see apply_update.py for that. /human must work identically whether this
script succeeds, fails, or is missing entirely.
"""
import sys
import time

import _update_lib as lib


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    skill_dir = lib.skill_dir_from_script(__file__)

    installed = lib.read_installed_version(skill_dir)
    if not installed:
        return 0  # no VERSION file: nothing to compare against, say nothing

    state = lib.load_state()

    if not lib.should_check(state):
        # Within the throttle window: reuse the last known answer, don't hit
        # the network again.
        cached_latest = state.get("last_known_latest")
        if cached_latest and lib.is_newer(cached_latest, installed):
            url = state.get("last_known_url") or ""
            print(f"UPDATE_AVAILABLE installed={installed} latest={cached_latest} url={url}")
        elif not quiet:
            print(f"UP_TO_DATE installed={installed}")
        return 0

    try:
        release = lib.fetch_latest_release()
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        state["last_checked_epoch"] = time.time()
        state["last_result"] = f"error: {exc}"
        lib.save_state(state)
        return 0  # offline / GitHub down / bad response: say nothing, move on

    state["last_checked_epoch"] = time.time()
    state["last_known_latest"] = release["tag"]
    state["last_known_url"] = release["html_url"]
    state["last_result"] = "ok"
    lib.save_state(state)

    if lib.is_newer(release["tag"], installed):
        print(
            f"UPDATE_AVAILABLE installed={installed} latest={release['tag']} "
            f"url={release['html_url']}"
        )
    elif not quiet:
        print(f"UP_TO_DATE installed={installed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
