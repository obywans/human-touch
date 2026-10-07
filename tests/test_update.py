#!/usr/bin/env python3
"""Tests for HumanTouch's auto-update system.

Usage: python3 tests/test_update.py

Stdlib unittest only. Every network call is mocked, so these tests never
make a real HTTP request and work offline. They check the eight scenarios
the feature needs to handle:
  1. installed version == latest
  2. installed version < latest
  3. GitHub unavailable
  4. invalid response from GitHub
  5. an error during the update itself
  6. a symlink install
  7. a copy install
  8. recovery after a failed update
"""
import io
import json
import os
import tarfile
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "skills", "human", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import _update_lib as lib  # noqa: E402
import apply_update  # noqa: E402
import check_update  # noqa: E402


def fake_release(tag, tarball_url=None):
    return {
        "tag": tag,
        "name": tag,
        "html_url": f"https://github.com/obywans/human-touch/releases/tag/{tag}",
        "tarball_url": tarball_url,
    }


class TempDirsMixin:
    def make_skill_dir(self, version="1.0.0"):
        d = tempfile.mkdtemp(prefix="ht-test-skill-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
        with open(os.path.join(d, "VERSION"), "w", encoding="utf-8") as f:
            f.write(version + "\n")
        return d

    def make_cache_dir(self):
        d = tempfile.mkdtemp(prefix="ht-test-cache-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d


class TestVersionCompare(unittest.TestCase):
    def test_equal_versions_not_newer(self):
        self.assertFalse(lib.is_newer("v1.2.0", "1.2.0"))

    def test_newer_version_detected(self):
        self.assertTrue(lib.is_newer("v1.3.0", "1.2.0"))

    def test_older_version_not_newer(self):
        self.assertFalse(lib.is_newer("v1.0.0", "1.2.0"))


class TestCheckUpdate(TempDirsMixin, unittest.TestCase):
    def run_check(self, skill_dir, cache_dir, fetch_side_effect, quiet=False):
        script_path = os.path.join(skill_dir, "scripts", "check_update.py")
        with mock.patch.object(lib, "fetch_latest_release", side_effect=fetch_side_effect), \
             mock.patch.object(check_update, "__file__", script_path), \
             mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": cache_dir}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = check_update.main(["--quiet"] if quiet else [])
        return rc, buf.getvalue()

    # Scenario 1: installed version == latest
    def test_current_equals_latest(self):
        skill_dir = self.make_skill_dir("1.2.0")
        rc, out = self.run_check(skill_dir, self.make_cache_dir(), lambda **_: fake_release("v1.2.0"))
        self.assertEqual(rc, 0)
        self.assertIn("UP_TO_DATE", out)
        self.assertNotIn("UPDATE_AVAILABLE", out)

    # Scenario 2: installed version < latest
    def test_current_less_than_latest(self):
        skill_dir = self.make_skill_dir("1.0.0")
        rc, out = self.run_check(skill_dir, self.make_cache_dir(), lambda **_: fake_release("v1.2.0"))
        self.assertEqual(rc, 0)
        self.assertIn("UPDATE_AVAILABLE", out)
        self.assertIn("latest=v1.2.0", out)

    # Scenario 3: GitHub unavailable
    def test_github_unavailable_is_silent_and_safe(self):
        skill_dir = self.make_skill_dir("1.0.0")
        cache_dir = self.make_cache_dir()

        def boom(**_):
            raise OSError("Network is unreachable")

        rc, out = self.run_check(skill_dir, cache_dir, boom, quiet=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")  # never surfaces an error line or traceback
        with open(os.path.join(cache_dir, "update-state.json"), encoding="utf-8") as f:
            state = json.load(f)
        self.assertTrue(state["last_result"].startswith("error:"))

    # Scenario 4: invalid response from GitHub
    def test_invalid_github_response_is_handled_like_an_error(self):
        skill_dir = self.make_skill_dir("1.0.0")

        def bad(**_):
            raise ValueError("release response has no usable tag_name")

        rc, out = self.run_check(skill_dir, self.make_cache_dir(), bad, quiet=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_throttling_skips_network_within_window(self):
        skill_dir = self.make_skill_dir("1.0.0")
        cache_dir = self.make_cache_dir()
        with open(os.path.join(cache_dir, "update-state.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "last_checked_epoch": time.time(),
                    "last_known_latest": "v1.2.0",
                    "last_known_url": "https://example.invalid",
                    "last_result": "ok",
                },
                f,
            )

        def must_not_be_called(**_):
            raise AssertionError("fetch_latest_release must not run inside the throttle window")

        rc, out = self.run_check(skill_dir, cache_dir, must_not_be_called)
        self.assertEqual(rc, 0)
        self.assertIn("UPDATE_AVAILABLE", out)
        self.assertIn("v1.2.0", out)

    def test_missing_version_file_is_silent(self):
        skill_dir = tempfile.mkdtemp(prefix="ht-test-skill-noversion-")
        self.addCleanup(shutil.rmtree, skill_dir, ignore_errors=True)
        os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

        def must_not_be_called(**_):
            raise AssertionError("should never reach the network with no VERSION file")

        rc, out = self.run_check(skill_dir, self.make_cache_dir(), must_not_be_called)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


class TestApplyUpdate(TempDirsMixin, unittest.TestCase):
    def run_apply(self, skill_dir, cache_dir, fetch_side_effect, args=None, mode_override=None):
        args = args or []
        script_path = os.path.join(skill_dir, "scripts", "apply_update.py")
        patches = [
            mock.patch.object(lib, "fetch_latest_release", side_effect=fetch_side_effect),
            mock.patch.object(apply_update, "__file__", script_path),
            mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": cache_dir}),
        ]
        if mode_override is not None:
            patches.append(mock.patch.object(lib, "detect_install_mode", return_value=mode_override))
        with patches[0], patches[1], patches[2]:
            if mode_override is not None:
                with patches[3]:
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = apply_update.main(args)
            else:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = apply_update.main(args)
        return rc, buf.getvalue()

    # Scenario 1 again, for apply_update specifically
    def test_already_current_is_a_noop(self):
        skill_dir = self.make_skill_dir("1.2.0")
        rc, out = self.run_apply(skill_dir, self.make_cache_dir(), lambda **_: fake_release("v1.2.0"))
        self.assertEqual(rc, 0)
        self.assertIn("ALREADY_CURRENT", out)

    # Scenario 3 again, for apply_update: must report clearly and change nothing
    def test_github_unavailable_reports_and_changes_nothing(self):
        skill_dir = self.make_skill_dir("1.0.0")
        version_path = os.path.join(skill_dir, "VERSION")
        before = open(version_path, encoding="utf-8").read()

        def boom(**_):
            raise OSError("timed out")

        rc, out = self.run_apply(skill_dir, self.make_cache_dir(), boom)
        self.assertEqual(rc, 1)
        self.assertIn("NOT_UPDATED", out)
        self.assertIn("installed=1.0.0", out)
        self.assertEqual(before, open(version_path, encoding="utf-8").read())

    def test_fork_remote_refuses_to_auto_update(self):
        skill_dir = self.make_skill_dir("1.0.0")
        rc, out = self.run_apply(
            skill_dir, self.make_cache_dir(), lambda **_: fake_release("v1.2.0"),
            mode_override="git-other",
        )
        self.assertEqual(rc, 1)
        self.assertIn("NOT_UPDATED", out)
        self.assertIn("fork", out)

    # Scenario 5: an error during the update itself
    def test_copy_mode_failure_leaves_files_untouched(self):
        skill_dir = self.make_skill_dir("1.0.0")
        version_path = os.path.join(skill_dir, "VERSION")
        before = open(version_path, encoding="utf-8").read()
        with mock.patch.object(apply_update, "update_via_copy", side_effect=ValueError("boom")):
            rc, out = self.run_apply(
                skill_dir, self.make_cache_dir(),
                lambda **_: fake_release("v1.2.0", tarball_url="https://example.invalid/t.tar.gz"),
                mode_override="copy",
            )
        self.assertEqual(rc, 1)
        self.assertIn("NOT_UPDATED", out)
        self.assertEqual(before, open(version_path, encoding="utf-8").read())

    def _make_fake_release_tarball(self, skill_md_bytes: bytes, version_bytes: bytes | None = None) -> bytes:
        """Builds a real .tar.gz with the same layout GitHub's release
        tarballs use: one top-level '<owner>-<repo>-<sha>/' directory
        containing skills/human/SKILL.md (and, optionally, VERSION)."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="obywans-human-touch-abc123/skills/human/SKILL.md")
            info.size = len(skill_md_bytes)
            tf.addfile(info, io.BytesIO(skill_md_bytes))
            if version_bytes is not None:
                vinfo = tarfile.TarInfo(name="obywans-human-touch-abc123/skills/human/VERSION")
                vinfo.size = len(version_bytes)
                tf.addfile(vinfo, io.BytesIO(version_bytes))
        return buf.getvalue()

    def _fake_urlopen_returning(self, body: bytes, host: str = "codeload.github.com"):
        class _FakeResponse(io.BytesIO):
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def geturl(self_inner):
                return f"https://{host}/tarball/release"

        return mock.patch.object(apply_update.urllib.request, "urlopen", return_value=_FakeResponse(body))

    # A real security finding, fixed and tested: a release archive member
    # that declares a huge decompressed size must be rejected, and must not
    # touch any real file on disk (defense against a decompression bomb).
    def test_copy_mode_rejects_oversized_archive_member(self):
        skill_dir = self.make_skill_dir("1.0.0")
        version_path = os.path.join(skill_dir, "VERSION")
        before = open(version_path, encoding="utf-8").read()

        oversized = b"A" * (apply_update.MAX_MEMBER_BYTES + 1)
        tarball_bytes = self._make_fake_release_tarball(oversized)

        with self._fake_urlopen_returning(tarball_bytes):
            rc, out = self.run_apply(
                skill_dir, self.make_cache_dir(),
                lambda **_: fake_release("v1.2.0", tarball_url="https://codeload.github.com/t.tar.gz"),
                mode_override="copy",
            )
        self.assertEqual(rc, 1)
        self.assertIn("NOT_UPDATED", out)
        self.assertEqual(before, open(version_path, encoding="utf-8").read())

    def test_copy_mode_accepts_a_normal_sized_release(self):
        """Sanity check in the other direction: a real, small SKILL.md must
        still update successfully, so the size cap isn't just rejecting
        everything."""
        skill_dir = self.make_skill_dir("1.0.0")
        normal = b"---\nname: human\n---\n# HumanTouch\nSome normal-sized content.\n"
        tarball_bytes = self._make_fake_release_tarball(normal, version_bytes=b"1.2.0\n")

        with self._fake_urlopen_returning(tarball_bytes):
            rc, out = self.run_apply(
                skill_dir, self.make_cache_dir(),
                lambda **_: fake_release("v1.2.0", tarball_url="https://codeload.github.com/t.tar.gz"),
                mode_override="copy",
            )
        self.assertEqual(rc, 0)
        with open(os.path.join(skill_dir, "SKILL.md"), "rb") as f:
            self.assertEqual(f.read(), normal)

    # Scenario 8: recovery after a failed update
    def test_recovery_after_failed_update(self):
        skill_dir = self.make_skill_dir("1.0.0")
        cache_dir = self.make_cache_dir()

        def boom(**_):
            raise OSError("down")

        rc1, _ = self.run_apply(skill_dir, cache_dir, boom)
        self.assertEqual(rc1, 1)

        # GitHub is back: a plain check must work normally afterwards, and
        # VERSION must still be exactly what it was before the failed apply.
        with open(os.path.join(skill_dir, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "1.0.0")

        with mock.patch.object(lib, "fetch_latest_release", side_effect=lambda **_: fake_release("v1.2.0")), \
             mock.patch.object(check_update, "__file__", os.path.join(skill_dir, "scripts", "check_update.py")), \
             mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": cache_dir}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc2 = check_update.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("UPDATE_AVAILABLE", buf.getvalue())


class TestInstallModeDetection(TempDirsMixin, unittest.TestCase):
    def run_git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    # Scenario 7: a copy install
    def test_copy_install_has_no_git(self):
        skill_dir = self.make_skill_dir("1.0.0")
        self.assertEqual(lib.detect_install_mode(skill_dir), "copy")

    def test_git_official_remote_detected(self):
        real_dir = tempfile.mkdtemp(prefix="ht-test-gitrepo-")
        self.addCleanup(shutil.rmtree, real_dir, ignore_errors=True)
        self.run_git(real_dir, "init", "-q")
        self.run_git(real_dir, "remote", "add", "origin", "https://github.com/obywans/human-touch.git")
        skill_dir = os.path.join(real_dir, "skills", "human")
        os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)
        with open(os.path.join(skill_dir, "VERSION"), "w", encoding="utf-8") as f:
            f.write("1.0.0\n")
        self.assertEqual(lib.detect_install_mode(skill_dir), "git-official")

    def test_git_fork_remote_detected_as_other(self):
        real_dir = tempfile.mkdtemp(prefix="ht-test-gitfork-")
        self.addCleanup(shutil.rmtree, real_dir, ignore_errors=True)
        self.run_git(real_dir, "init", "-q")
        self.run_git(real_dir, "remote", "add", "origin", "https://github.com/someoneelse/human-touch.git")
        self.assertEqual(lib.detect_install_mode(real_dir), "git-other")

    # Scenario 6: a symlink install
    def test_symlinked_install_resolves_to_the_same_git_repo(self):
        """Simulates `ln -s .../human-touch/skills/human ~/.claude/skills/human`:
        the path the user actually invokes is a symlink into a git clone."""
        real_dir = tempfile.mkdtemp(prefix="ht-test-gitreal-")
        self.addCleanup(shutil.rmtree, real_dir, ignore_errors=True)
        self.run_git(real_dir, "init", "-q")
        self.run_git(real_dir, "remote", "add", "origin", "https://github.com/obywans/human-touch.git")
        real_skill_dir = os.path.join(real_dir, "skills", "human")
        os.makedirs(os.path.join(real_skill_dir, "scripts"), exist_ok=True)
        with open(os.path.join(real_skill_dir, "VERSION"), "w", encoding="utf-8") as f:
            f.write("1.0.0\n")

        fake_claude_dir = tempfile.mkdtemp(prefix="ht-test-claudeskills-")
        self.addCleanup(shutil.rmtree, fake_claude_dir, ignore_errors=True)
        symlink_path = os.path.join(fake_claude_dir, "human")
        os.symlink(real_skill_dir, symlink_path)

        self.assertEqual(lib.read_installed_version(symlink_path), "1.0.0")
        self.assertEqual(lib.detect_install_mode(symlink_path), "git-official")


if __name__ == "__main__":
    unittest.main()
