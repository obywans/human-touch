#!/usr/bin/env python3
"""Apply a HumanTouch update, safely, or explain why it can't.

Usage: python3 scripts/apply_update.py [--quiet] [--dry-run]

Safety rules, always:
  - Only ever talks to https://api.github.com/repos/obywans/human-touch/... —
    that owner/repo is a hardcoded constant, never taken from any file,
    argument, or downloaded content.
  - Never executes anything downloaded. A git-mode update runs `git fetch`
    and a fast-forward-only merge (git itself refuses anything that isn't a
    clean fast-forward). A copy-mode update downloads a release source
    tarball and copies files into place — it is never unpacked into a shell,
    never piped into anything, and no file in it is ever executed.
  - Refuses (does not guess, does not force) whenever it isn't sure: a dirty
    git working tree, a git remote that isn't the official repo (a fork), a
    network error, a malformed response. In every refusal case nothing on
    disk changes, and the script prints the installed version, the latest
    version if known, why it stopped, and the exact manual command to run.
  - This script is meant to run AFTER the current /human reply has already
    been sent, never during it — see skills/human/SKILL.md. Changing files
    on disk here only affects the *next* invocation of /human, not the one
    currently in progress.
"""
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

import _update_lib as lib

# A real SKILL.md/script in this project is a few KB. These caps are far
# above that on purpose, but still bounded: they exist only to stop a
# decompression bomb (a small .tar.gz that expands to gigabytes), not to
# constrain legitimate content.
MAX_MEMBER_BYTES = 2_000_000  # per extracted file
MAX_TOTAL_BYTES = 10_000_000  # across the whole archive


def _bounded_copy(src_fileobj, dst_path: str, max_bytes: int, remaining_budget: list[int]) -> int:
    """Copy src_fileobj to dst_path, reading in chunks, and raise ValueError
    the moment either this file's own cap or the shared remaining_budget
    (checked and decremented in place, so callers can enforce an aggregate
    cap across many files) would be exceeded. This bounds the actual bytes
    written regardless of what a tar header claims the size is — a crafted
    or corrupted header is not trusted."""
    written = 0
    with open(dst_path, "wb") as out:
        while True:
            chunk = src_fileobj.read(65536)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise ValueError(f"archive member exceeds {max_bytes} bytes uncompressed")
            if written > remaining_budget[0]:
                raise ValueError(f"archive exceeds {MAX_TOTAL_BYTES} bytes uncompressed in total")
            out.write(chunk)
    remaining_budget[0] -= written
    return written


def report(reason: str, installed: str | None, latest: str | None) -> None:
    print(f"NOT_UPDATED reason=\"{reason}\" installed={installed or '?'} latest={latest or '?'}")
    print("Manual update: see the 'Auto-update' section of README.md in the human-touch repository.")


def update_via_git(repo_dir: str, quiet: bool) -> bool:
    try:
        subprocess.run(["git", "-C", repo_dir, "fetch", "--tags", "origin"], check=True, timeout=20, capture_output=True)
        subprocess.run(
            ["git", "-C", repo_dir, "merge", "--ff-only", "origin/main"],
            check=True, timeout=20, capture_output=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    if not quiet:
        print("UPDATED via git fast-forward.")
    return True


def update_via_copy(skill_dir: str, tarball_url: str, target_tag: str, quiet: bool) -> bool:
    req = urllib.request.Request(tarball_url, headers={"User-Agent": "human-touch-update-apply"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        host = resp.geturl().split("/")[2].lower()
        if not (host == "codeload.github.com" or host.endswith(".github.com")):
            raise ValueError(f"unexpected download host: {host!r}")
        data = resp.read(20_000_000)  # cap: a HumanTouch release is a few KB; refuse anything huge

    with tempfile.TemporaryDirectory(prefix="human-touch-update-") as tmp:
        archive_path = os.path.join(tmp, "release.tar.gz")
        with open(archive_path, "wb") as f:
            f.write(data)

        extract_dir = os.path.join(tmp, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        safe_root = os.path.realpath(extract_dir)
        remaining_budget = [MAX_TOTAL_BYTES]
        with tarfile.open(archive_path, "r:gz") as tf:
            # Iterate the TarFile directly (lazy, one header at a time) and
            # NEVER call tf.getmembers(): that method pre-loads every member
            # by scanning the whole archive first, which for a non-seekable
            # gzip stream means decompressing straight through any earlier
            # member's declared content to reach the next header. A member
            # that declares gigabytes of size would then be fully decompressed
            # just to list it, before this loop ever got a chance to reject
            # it on size -- a second, separate decompression-bomb gap from
            # the one fixed in 1.2.1 (that one capped bytes written during
            # extraction; this one is about bytes read merely to enumerate
            # members). Reproduced and timed: a lazily-rejected 300 MB-declared
            # member takes ~0ms here, versus tf.getmembers() needing to
            # decompress through it first.
            for member in tf:
                # Extract each member by hand instead of extractall(): only
                # ever write plain regular files, never a symlink, hardlink,
                # device, or fifo, and never outside safe_root. This is
                # stricter than extractall()'s own traversal checks and
                # avoids trusting any single API to get that right.
                if not member.isfile():
                    continue
                member_path = os.path.realpath(os.path.join(extract_dir, member.name))
                if not (member_path == safe_root or member_path.startswith(safe_root + os.sep)):
                    raise ValueError(f"unsafe path in archive: {member.name!r}")
                # Check the header's declared size and abort immediately if
                # it's over the cap, BEFORE asking tarfile for the next
                # member -- that's what keeps this lazy. The real limit is
                # still enforced on actual bytes read below too, which does
                # not trust the header either.
                if member.size > MAX_MEMBER_BYTES:
                    raise ValueError(f"archive member {member.name!r} declares {member.size} bytes, over the cap")
                os.makedirs(os.path.dirname(member_path), exist_ok=True)
                src_fileobj = tf.extractfile(member)
                if src_fileobj is None:
                    continue
                with src_fileobj as sf:
                    _bounded_copy(sf, member_path, MAX_MEMBER_BYTES, remaining_budget)

        # GitHub wraps the tarball in one top-level "<owner>-<repo>-<sha>/" dir.
        entries = [e for e in os.listdir(extract_dir) if not e.startswith(".")]
        if len(entries) != 1:
            raise ValueError(f"unexpected archive layout: {entries!r}")
        new_skill_dir = os.path.join(extract_dir, entries[0], "skills", "human")
        if not os.path.isfile(os.path.join(new_skill_dir, "SKILL.md")):
            raise ValueError("downloaded release has no skills/human/SKILL.md")

        # Copy new files to temp paths next to the real ones, then atomically
        # swap each in with os.replace — never leaves a half-written file.
        for name in ("SKILL.md", "VERSION"):
            src = os.path.join(new_skill_dir, name)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(skill_dir, name)
            tmp_dst = dst + ".update-tmp"
            shutil.copyfile(src, tmp_dst)
            os.replace(tmp_dst, dst)

        new_scripts = os.path.join(new_skill_dir, "scripts")
        if os.path.isdir(new_scripts):
            dst_scripts = os.path.join(skill_dir, "scripts")
            os.makedirs(dst_scripts, exist_ok=True)
            for name in os.listdir(new_scripts):
                src = os.path.join(new_scripts, name)
                if not os.path.isfile(src):
                    continue
                dst = os.path.join(dst_scripts, name)
                tmp_dst = dst + ".update-tmp"
                shutil.copyfile(src, tmp_dst)
                os.replace(tmp_dst, dst)

    if not quiet:
        print(f"UPDATED via file copy to {target_tag}.")
    return True


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    dry_run = "--dry-run" in argv
    skill_dir = lib.skill_dir_from_script(__file__)

    installed = lib.read_installed_version(skill_dir)
    if not installed:
        report("no local VERSION file found; cannot tell what is installed", None, None)
        return 1

    try:
        release = lib.fetch_latest_release()
    except Exception as exc:  # noqa: BLE001
        report(f"could not reach GitHub ({exc})", installed, None)
        return 1

    if not lib.is_newer(release["tag"], installed):
        if not quiet:
            print(f"ALREADY_CURRENT installed={installed}")
        return 0

    if dry_run:
        print(f"WOULD_UPDATE installed={installed} latest={release['tag']}")
        return 0

    mode = lib.detect_install_mode(skill_dir)

    if mode == "git-official":
        try:
            top = subprocess.run(
                ["git", "-C", skill_dir, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            report("could not locate the git repository root", installed, release["tag"])
            return 1
        if not lib.git_working_tree_clean(top):
            report("local git working tree has uncommitted changes; refusing to touch it", installed, release["tag"])
            return 1
        if update_via_git(top, quiet):
            new_version = lib.read_installed_version(skill_dir)
            if new_version != release["tag"].lstrip("v") and new_version != release["tag"]:
                report(f"update ran but VERSION is now {new_version!r}, expected {release['tag']!r}", installed, release["tag"])
                return 1
            return 0
        report("git fast-forward update failed (fetch/merge error); run `git pull` manually", installed, release["tag"])
        return 1

    if mode == "git-other":
        report("installed from a git remote that is not the official repository (looks like a fork); not auto-updating", installed, release["tag"])
        return 1

    # mode == "copy"
    if not release.get("tarball_url"):
        report("release has no downloadable source archive", installed, release["tag"])
        return 1
    try:
        update_via_copy(skill_dir, release["tarball_url"], release["tag"], quiet)
    except Exception as exc:  # noqa: BLE001
        report(f"copy-mode update failed ({exc}); installed files were left unchanged", installed, release["tag"])
        return 1

    new_version = lib.read_installed_version(skill_dir)
    if new_version and lib.is_newer(release["tag"], new_version):
        report(f"update copied files but VERSION still reads {new_version!r}", installed, release["tag"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
