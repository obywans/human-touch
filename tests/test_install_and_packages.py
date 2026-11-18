"""Installer (sh, in a fake HOME), skill ZIP, and the .mcpb bundle actually running."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_packages as bp  # noqa: E402


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp()
        bp.main(["--out", cls.out])
        cls.version = bp.version()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_skill_zip_root_is_the_human_folder(self):
        with zipfile.ZipFile(os.path.join(self.out, "human-skill.zip")) as z:
            names = z.namelist()
        self.assertIn("human/SKILL.md", names)
        self.assertTrue(all(n.startswith("human/") for n in names))
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
        self.assertIn("human/scripts/watermark_audit.py", names)

    def test_mcpb_manifest_required_fields(self):
        with zipfile.ZipFile(os.path.join(self.out, "human-touch.mcpb")) as z:
            m = json.loads(z.read("manifest.json"))
        for k in ("manifest_version", "name", "version", "description", "author", "server"):
            self.assertIn(k, m)
        self.assertEqual(m["version"], self.version)
        self.assertEqual(m["server"]["type"], "python")
        self.assertIn("win32", m["server"]["mcp_config"]["platform_overrides"])

    def test_mcpb_server_runs_from_the_extracted_bundle(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with zipfile.ZipFile(os.path.join(self.out, "human-touch.mcpb")) as z:
            z.extractall(d)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "human_audit", "arguments": {"text": "a​b"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "humantouch://rules"}}]
        p = subprocess.run([sys.executable, "-I", os.path.join(d, "mcp", "human_touch_mcp.py")],
                           input="".join(json.dumps(m) + "\n" for m in msgs), capture_output=True,
                           text=True, encoding="utf-8", timeout=30, cwd=d)
        out = [json.loads(l) for l in p.stdout.splitlines()]
        self.assertEqual(out[0]["result"]["serverInfo"]["version"], self.version)
        self.assertIn("ZERO WIDTH SPACE", out[1]["result"]["content"][0]["text"])
        self.assertIn("HumanTouch", out[2]["result"]["contents"][0]["text"])


@unittest.skipIf(os.name == "nt", "install.sh is for macOS and Linux; install.ps1 is tested in CI on Windows")
class InstallShTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.src = tempfile.mkdtemp()  # a local git repo standing in for GitHub
        self.addCleanup(shutil.rmtree, self.src, True)
        shutil.copytree(ROOT, os.path.join(self.src, "r"), ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
        r = os.path.join(self.src, "r")
        for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", r, *c], check=True, capture_output=True)
        self.env = {**os.environ, "HOME": self.home, "HUMAN_TOUCH_REPO": r}

    def run_sh(self, *args):
        return subprocess.run(["sh", os.path.join(ROOT, "install.sh"), *args], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def test_default_installs_claude_and_agents_and_is_idempotent(self):
        r = self.run_sh()
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in (".claude/skills/human", ".agents/skills/human"):
            p = os.path.join(self.home, rel)
            self.assertTrue(os.path.islink(p), rel)
            self.assertTrue(os.path.isfile(os.path.join(p, "SKILL.md")))
        r2 = self.run_sh()
        self.assertEqual(r2.returncode, 0)
        self.assertIn("already installed", r2.stdout)

    def test_never_overwrites_an_existing_skill(self):
        mine = os.path.join(self.home, ".claude", "skills", "human")
        os.makedirs(mine)
        open(os.path.join(mine, "SKILL.md"), "w").write("mine")
        r = self.run_sh("--claude")
        self.assertIn("SKIPPED", r.stderr)
        self.assertEqual(open(os.path.join(mine, "SKILL.md")).read(), "mine")
        self.assertFalse(os.path.islink(mine))

    def test_gemini_command_file(self):
        self.run_sh("--gemini-command")
        f = os.path.join(self.home, ".gemini", "commands", "human.toml")
        text = open(f, encoding="utf-8").read()
        self.assertIn("prompt =", text)
        self.assertIn("{{args}}", text)

    def test_unknown_option_fails(self):
        self.assertEqual(self.run_sh("--nope").returncode, 2)


if __name__ == "__main__":
    unittest.main()
