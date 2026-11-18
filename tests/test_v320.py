"""Tests for version 3.2.0: plugin route, package notice, human_update_check, version consistency."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skills", "human", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import _update_lib as lib  # noqa: E402
import apply_update  # noqa: E402
import check_update  # noqa: E402
from test_mcp import INIT, call, session  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def fake_release(tag):
    return {"tag": tag, "name": tag, "html_url": "https://example.invalid/r/" + tag, "tarball_url": None}


def make_skill(base, version):
    d = os.path.join(base, "skills", "human")
    os.makedirs(os.path.join(d, "scripts"))
    with open(os.path.join(d, "VERSION"), "w", encoding="utf-8") as f:
        f.write(version + "\n")
    return d


def run_check(skill_dir, cache_dir, release, quiet=True):
    script = os.path.join(skill_dir, "scripts", "check_update.py")
    buf = io.StringIO()
    with mock.patch.object(lib, "fetch_latest_release", side_effect=lambda **_: release), \
         mock.patch.object(lib, "fetch_wikipedia_revision", side_effect=OSError("off")), \
         mock.patch.object(check_update, "__file__", script), \
         mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": cache_dir}), \
         contextlib.redirect_stdout(buf):
        rc = check_update.main(["--quiet"] if quiet else [])
    return rc, buf.getvalue()


def snapshot(d):
    out = {}
    for dp, _, names in os.walk(d):
        for n in names:
            p = os.path.join(dp, n)
            with open(p, "rb") as f:
                out[p] = f.read()
    return out


class PluginRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ht-v320-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache = os.path.join(self.tmp, "state")
        os.makedirs(self.cache)

    def plugin_skill(self, where="cache", version="3.1.0"):
        base = os.path.join(self.tmp, "home", "plugins", where, "human-touch", "human-touch", version)
        return make_skill(base, version)

    def test_plugin_cache_prints_both_versions_and_writes_nothing(self):
        skill = self.plugin_skill()
        before = snapshot(skill)
        rc, out = run_check(skill, self.cache, fake_release("v3.2.0"))
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("PLUGIN_INSTALL installed=3.1.0 latest=v3.2.0 url="), out)
        self.assertNotIn("UPDATE_AVAILABLE", out)
        self.assertEqual(snapshot(skill), before)

    def test_plugin_cache_up_to_date_prints_nothing(self):
        skill = self.plugin_skill(version="3.2.0")
        rc, out = run_check(skill, self.cache, fake_release("v3.2.0"))
        self.assertEqual((rc, out), (0, ""))

    def test_plugin_cache_offline_prints_nothing(self):
        skill = self.plugin_skill()
        script = os.path.join(skill, "scripts", "check_update.py")
        buf = io.StringIO()
        with mock.patch.object(lib, "fetch_latest_release", side_effect=OSError("off")), \
             mock.patch.object(lib, "fetch_wikipedia_revision", side_effect=OSError("off")), \
             mock.patch.object(check_update, "__file__", script), \
             mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": self.cache}), \
             contextlib.redirect_stdout(buf):
            self.assertEqual(check_update.main(["--quiet"]), 0)
        self.assertEqual(buf.getvalue(), "")

    def test_apply_update_refuses_plugin_cache_and_marketplaces(self):
        for where in ("cache", "marketplaces"):
            with self.subTest(where=where):
                skill = self.plugin_skill(where)
                self.assertEqual(lib.detect_install_mode(skill), "plugin")
                before = snapshot(skill)
                script = os.path.join(skill, "scripts", "apply_update.py")
                buf = io.StringIO()
                with mock.patch.object(lib, "fetch_latest_release", side_effect=lambda **_: fake_release("v3.2.0")), \
                     mock.patch.object(apply_update, "__file__", script), \
                     mock.patch.dict(os.environ, {"HUMAN_TOUCH_CACHE_DIR": self.cache}), \
                     contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    rc = apply_update.main(["--quiet"])
                self.assertNotEqual(rc, 0)
                self.assertIn("claude plugin update human-touch@human-touch", buf.getvalue())
                self.assertEqual(snapshot(skill), before)

    def test_package_install_prints_notice_when_not_writable(self):
        base = os.path.join(self.tmp, "pkg")
        skill = make_skill(base, "3.1.0")
        with mock.patch.object(lib, "skill_dir_writable", return_value=False):
            rc, out = run_check(skill, self.cache, fake_release("v3.2.0"))
        self.assertTrue(out.startswith("PACKAGE_INSTALL installed=3.1.0 latest=v3.2.0 url="), out)

    def test_package_install_up_to_date_prints_nothing(self):
        skill = make_skill(os.path.join(self.tmp, "pkg"), "3.2.0")
        with mock.patch.object(lib, "skill_dir_writable", return_value=False):
            rc, out = run_check(skill, self.cache, fake_release("v3.2.0"))
        self.assertEqual(out, "")

    def test_writable_folder_keeps_update_available(self):
        skill = make_skill(os.path.join(self.tmp, "plain"), "3.1.0")
        rc, out = run_check(skill, self.cache, fake_release("v3.2.0"))
        self.assertTrue(out.startswith("UPDATE_AVAILABLE installed=3.1.0 latest=v3.2.0"), out)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.version = read("skills", "human", "VERSION").strip()
        self.plugin = json.loads(read(".claude-plugin", "plugin.json"))
        self.market = json.loads(read(".claude-plugin", "marketplace.json"))

    def test_plugin_manifest_keys_and_skills_folder(self):
        for key in ("name", "version", "description", "skills"):
            self.assertIn(key, self.plugin)
        self.assertEqual(self.plugin["name"], "human-touch")
        self.assertEqual(self.plugin["skills"], "./skills/")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", "human", "SKILL.md")))

    def test_marketplace_manifest_keys(self):
        self.assertEqual(self.market["name"], "human-touch")
        self.assertIn("owner", self.market)
        plugins = self.market["plugins"]
        self.assertEqual(plugins[0]["name"], "human-touch")
        self.assertEqual(plugins[0]["source"], "./")

    def test_version_is_the_same_everywhere(self):
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(self.plugin["version"], self.version)
        self.assertEqual(json.loads(read("plugin.json"))["version"], self.version)
        for entry in self.market["plugins"]:
            if "version" in entry:
                self.assertEqual(entry["version"], self.version)
        self.assertIn("version `%s`" % self.version, read("README.md"))
        self.assertIn("## %s (" % self.version, read("CHANGELOG.md"))

    def test_readme_has_no_false_plugin_statement(self):
        self.assertNotIn("There is no plugin and no marketplace", read("README.md"))
        self.assertIn("claude plugin update human-touch@human-touch", read("README.md"))

    def test_update_instructions_name_both_commands_and_consent(self):
        text = read("skills", "human", "scripts", "ACTUALIZAR.md")
        self.assertIn("claude plugin marketplace update human-touch", text)
        self.assertIn("claude plugin update human-touch@human-touch", text)
        self.assertIn("/reload-plugins", text)
        self.assertIn("PACKAGE_INSTALL", text)
        self.assertIn("PACKAGE_INSTALL", read("skills", "human", "SKILL.md"))


class UpdateCheckToolTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env)))

    def run_tool(self, url):
        os.environ["HUMAN_TOUCH_RELEASE_URL"] = url
        out, p = session([INIT, call(2, "human_update_check", {})])
        return out[1]["result"], p

    def test_tool_listed_read_only(self):
        out, _ = session([INIT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        tool = [t for t in out[1]["result"]["tools"] if t["name"] == "human_update_check"][0]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_offline_error_has_no_trace(self):
        res, p = self.run_tool("http://127.0.0.1:9/none")
        self.assertFalse(res["isError"])
        data = json.loads(res["content"][0]["text"])
        self.assertIsNone(data["latest"])
        self.assertIn("check failed", data["status"])
        self.assertIn("Reinstall the extension by hand: Claude Desktop does not update this file", data["note"])
        self.assertNotIn("Traceback", p.stderr + res["content"][0]["text"])

    def test_reads_a_local_release_file(self):
        d = tempfile.mkdtemp(prefix="ht-v320-rel-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "latest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"tag_name": "v9.9.9", "html_url": "https://example.invalid/r"}, f)
        res, _ = self.run_tool("file://" + path.replace(os.sep, "/") if os.sep == "/" else "file:///" + path.replace(os.sep, "/"))
        data = json.loads(res["content"][0]["text"])
        self.assertEqual(data["latest"], "9.9.9")
        self.assertEqual(data["installed"], read("skills", "human", "VERSION").strip())
        self.assertEqual(data["release_url"], "https://example.invalid/r")

    def test_bad_json_is_handled(self):
        d = tempfile.mkdtemp(prefix="ht-v320-rel-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json")
        res, p = self.run_tool("file://" + path if os.sep == "/" else "file:///" + path.replace(os.sep, "/"))
        self.assertIn("check failed", json.loads(res["content"][0]["text"])["status"])

    def test_only_this_tool_uses_the_network_in_source(self):
        src = read("mcp", "human_touch_mcp.py")
        self.assertEqual(src.count("urlopen("), 1)
        self.assertIn("def tool_update_check", src)
        self.assertEqual(src.split("def tool_update_check")[0].count("urllib"), 1)  # import line only

    def test_package_manifest_lists_four_tools(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import build_packages
        names = [t["name"] for t in build_packages.manifest()["tools"]]
        self.assertEqual(names, ["human_audit", "human_clean", "human_metadata_inspect", "human_update_check"])


if __name__ == "__main__":
    unittest.main()
