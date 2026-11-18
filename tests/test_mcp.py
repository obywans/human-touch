"""MCP server: scripted stdio JSON-RPC sessions against mcp/human_touch_mcp.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "mcp", "human_touch_mcp.py")


def session(messages, cwd=None):
    payload = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)
    p = subprocess.run([sys.executable, "-I", SERVER], input=payload, capture_output=True,
                       text=True, encoding="utf-8", timeout=30, cwd=cwd)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    return [json.loads(l) for l in lines], p


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
NOTIF = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def call(i, name, args):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}


class McpTests(unittest.TestCase):
    def test_handshake_and_tool_list(self):
        out, p = session([INIT, NOTIF, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                          {"jsonrpc": "2.0", "id": 3, "method": "ping"}])
        self.assertEqual(p.stderr, "")
        self.assertEqual(len(out), 3)  # the notification gets no reply
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "human-touch")
        names = [t["name"] for t in out[1]["result"]["tools"]]
        self.assertEqual(names, ["human_audit", "human_clean", "human_metadata_inspect"])
        for t in out[1]["result"]["tools"]:
            self.assertTrue(t["annotations"]["readOnlyHint"])
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_no_consent_gated_tool_and_no_human_prompt(self):
        out, _ = session([INIT, {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
                          {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}])
        self.assertEqual(out[1]["result"]["prompts"], [])
        joined = json.dumps(out[2])
        for bad in ("strip", "remove_provenance", "confirm", "fix_homoglyphs"):
            self.assertNotIn(bad, joined)

    def test_audit_text(self):
        out, _ = session([INIT, call(2, "human_audit", {"text": "pаss a︀b"})])
        r = out[1]["result"]
        self.assertFalse(r["isError"])
        self.assertIn("homoglyph", r["content"][0]["text"])
        self.assertIn("NOT checked", r["content"][0]["text"])

    def test_audit_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "n.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("a​b")
            out, _ = session([INIT, call(2, "human_audit", {"path": f})])
            self.assertIn("ZERO WIDTH SPACE", out[1]["result"]["content"][0]["text"])
            self.assertEqual(os.listdir(d), ["n.txt"])

    def test_clean_returns_copy_only(self):
        out, _ = session([INIT, call(2, "human_clean", {"text": "a​b ︀ \U0001F44D️"})])
        body = json.loads(out[1]["result"]["content"][0]["text"])
        self.assertEqual(body["cleaned_text"], "ab  \U0001F44D️")
        self.assertTrue(body["changed"])

    def test_metadata_inspect_and_errors(self):
        out, _ = session([INIT, call(2, "human_metadata_inspect", {"path": "/nonexistent/x.jpg"}),
                          call(3, "human_audit", {"text": 5}), call(4, "nope", {})])
        self.assertTrue(out[1]["result"]["isError"])
        self.assertTrue(out[2]["result"]["isError"])
        self.assertEqual(out[3]["error"]["code"], -32602)

    def test_bad_input_does_not_kill_server(self):
        payload_out, p = session([INIT])
        proc = subprocess.run([sys.executable, "-I", SERVER], input="not json\n[]\n" + json.dumps(
            {"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n", capture_output=True, text=True, timeout=30)
        lines = [json.loads(l) for l in proc.stdout.splitlines()]
        self.assertEqual(lines[0]["error"]["code"], -32700)
        self.assertEqual(lines[1]["error"]["code"], -32600)
        self.assertEqual(lines[2]["result"], {})

    def test_modern_protocol_2026_07_28_without_handshake(self):
        meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
        out, _ = session([
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": meta}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": meta}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"_meta": meta, "name": "human_audit", "arguments": {"text": "a\u200bb"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list",
             "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}}},
        ])
        self.assertEqual(out[0]["result"]["resultType"], "complete")
        self.assertIn("2026-07-28", out[0]["result"]["supportedVersions"])
        self.assertEqual(out[0]["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "human-touch")
        self.assertEqual(out[1]["result"]["resultType"], "complete")
        self.assertIn("ZERO WIDTH SPACE", out[2]["result"]["content"][0]["text"])
        self.assertEqual(out[3]["error"]["code"], -32022)
        self.assertEqual(out[3]["error"]["data"]["supported"], ["2026-07-28"])

    def test_legacy_2025_11_25_handshake(self):
        init = {**INIT, "params": {**INIT["params"], "protocolVersion": "2025-11-25"}}
        out, _ = session([init])
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-11-25")
        self.assertNotIn("resultType", out[0]["result"])

    def test_rules_resource(self):
        out, _ = session([INIT, {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
                          {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "humantouch://rules"}}])
        self.assertEqual(out[1]["result"]["resources"][0]["uri"], "humantouch://rules")
        self.assertIn("HumanTouch", out[2]["result"]["contents"][0]["text"])


if __name__ == "__main__":
    unittest.main()
