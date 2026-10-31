"""Adapters against stand-ins that follow each tool's documented interface (no accounts needed)."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from mockcrowd.brains.base import Task
from mockcrowd.brains.cli import CodePuppyCLI, CodexCLI
from mockcrowd.brains.http import Ollama, OpenAICompatible

REPLY = {"ok": True}


def fake_cli(tmp_path, monkeypatch, name, body):
    """Put an executable called `name` on PATH that logs its argv and runs `body`."""
    script = tmp_path / name
    script.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        f"open({str(tmp_path / 'argv.json')!r}, 'w').write(json.dumps(sys.argv[1:]))\n{body}\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    return lambda: json.loads((tmp_path / "argv.json").read_text())


def task():
    return Task("t", "say ok", lambda: {"ok": False}, validate=lambda v: v.get("ok") is True)


def test_codex_runs_read_only_and_reads_the_last_message(tmp_path, monkeypatch):
    argv = fake_cli(tmp_path, monkeypatch, "codex",
                    "out = sys.argv[sys.argv.index('-o') + 1]\nsys.stdin.read()\n"
                    f"open(out, 'w').write({json.dumps(json.dumps(REPLY))})")
    assert CodexCLI(model="gpt-x").run(task()) == REPLY
    args = argv()
    assert args[:2] == ["exec", "--skip-git-repo-check"] and args[-1] == "-"
    assert args[args.index("-s") + 1] == "read-only" and args[args.index("-m") + 1] == "gpt-x"


def test_code_puppy_has_no_tools_and_passes_the_model(tmp_path, monkeypatch):
    argv = fake_cli(tmp_path, monkeypatch, "code-puppy",
                    f"print('Woof! thinking...')\nprint({json.dumps(json.dumps(REPLY))})")
    assert CodePuppyCLI(model="m1").run(task()) == REPLY
    args = argv()
    assert "--no-tools" in args and args[args.index("--model") + 1] == "m1" and "-p" in args


def serve(monkeypatch):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps({"choices": [{"message": {"content": json.dumps(REPLY)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def test_openai_compatible_and_ollama(monkeypatch):
    server, seen = serve(monkeypatch)
    base = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        assert OpenAICompatible(model="m", base_url=base, api_key="k").run(task()) == REPLY
        assert seen["path"] == "/v1/chat/completions" and seen["auth"] == "Bearer k"
        assert seen["body"]["model"] == "m" and seen["body"]["messages"][0]["role"] == "system"
        monkeypatch.setenv("OLLAMA_BASE_URL", base)
        assert Ollama(model="qwen").run(task()) == REPLY and seen["body"]["model"] == "qwen"
    finally:
        server.shutdown()
