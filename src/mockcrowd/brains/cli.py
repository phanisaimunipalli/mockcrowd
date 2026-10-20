"""Brains that drive coding-agent CLIs the user already has, so runs use their subscription."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from .base import SYSTEM_PROMPT, Brain, BrainError


def _run(cmd: list[str], stdin: str | None, timeout: float) -> str:
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "MOCKCROWD_CHILD": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise BrainError(f"{cmd[0]} timed out after {timeout:.0f}s") from exc
    if proc.returncode != 0:
        raise BrainError(f"{cmd[0]} exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc.stdout


class ClaudeCLI(Brain):
    """Claude Code in print mode: `claude -p` with tools and MCP servers switched off."""

    name = "claude"
    binary = "claude"

    def complete(self, prompt: str) -> str:
        cmd = [
            self.binary, "-p",
            "--output-format", "json",
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--system-prompt", SYSTEM_PROMPT,
        ]
        if self.model:
            cmd += ["--model", self.model]
        out = _run(cmd, prompt, self.timeout)
        try:
            envelope = json.loads(out)
        except json.JSONDecodeError:
            return out
        self.add_cost(float(envelope.get("total_cost_usd") or 0))
        if envelope.get("is_error"):
            raise BrainError(f"claude error: {str(envelope.get('result'))[:300]}")
        return str(envelope.get("result", ""))


class CodexCLI(Brain):
    """OpenAI Codex CLI: `codex exec`, reading the final message from -o FILE."""

    name = "codex"
    binary = "codex"

    def complete(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out_file = os.path.join(tmp, "last.txt")
            cmd = [self.binary, "exec", "--skip-git-repo-check", "--ephemeral", "-o", out_file]
            if self.model:
                cmd += ["-c", f'model="{self.model}"']
            cmd.append("-")
            _run(cmd, f"{SYSTEM_PROMPT}\n\n{prompt}", self.timeout)
            try:
                with open(out_file, encoding="utf-8") as fh:
                    return fh.read()
            except FileNotFoundError as exc:
                raise BrainError("codex produced no final message") from exc


class CodePuppyCLI(Brain):
    """Code Puppy single-prompt mode: `code-puppy -p PROMPT`."""

    name = "code-puppy"
    binary = "code-puppy"

    def complete(self, prompt: str) -> str:
        return _run([self.binary, "-p", f"{SYSTEM_PROMPT}\n\n{prompt}"], None, self.timeout)


CLI_BRAINS: dict[str, type[Brain]] = {
    "claude": ClaudeCLI,
    "codex": CodexCLI,
    "code-puppy": CodePuppyCLI,
}


def installed(name: str) -> bool:
    cls = CLI_BRAINS[name]
    return shutil.which(cls.binary) is not None  # type: ignore[attr-defined]
