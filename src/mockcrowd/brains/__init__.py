"""Brain selection. `auto` picks the first agent CLI the user already has installed."""

from __future__ import annotations

import os

from .base import Brain, BrainError, Task
from .cli import CLI_BRAINS, installed
from .http import Ollama, OpenAICompatible, ollama_running
from .mock import MockBrain

BRAIN_NAMES = ["auto", "claude", "codex", "code-puppy", "openai", "ollama", "mock"]

__all__ = ["Brain", "BrainError", "Task", "get_brain", "available_brains", "BRAIN_NAMES"]


def available_brains() -> dict[str, bool]:
    status = {name: installed(name) for name in CLI_BRAINS}
    status["openai"] = bool(os.environ.get("MOCKCROWD_API_BASE"))
    status["ollama"] = ollama_running()
    status["mock"] = True
    return status


def get_brain(name: str = "auto", model: str | None = None) -> Brain:
    name = os.environ.get("MOCKCROWD_BRAIN", name) if name == "auto" else name
    if name == "auto":
        status = available_brains()
        for candidate in ("claude", "codex", "code-puppy", "openai", "ollama"):
            if status[candidate]:
                name = candidate
                break
        else:
            raise BrainError(
                "no brain found. Install Claude Code, Codex or Code Puppy, start Ollama, "
                "or set MOCKCROWD_API_BASE and MOCKCROWD_MODEL."
            )
    if name in CLI_BRAINS:
        if not installed(name):
            raise BrainError(f"{name} is not installed or not on PATH")
        return CLI_BRAINS[name](model=model)
    if name == "openai":
        return OpenAICompatible(model=model)
    if name == "ollama":
        return Ollama(model=model)
    if name == "mock":
        return MockBrain()
    raise BrainError(f"unknown brain {name!r}; choose one of {', '.join(BRAIN_NAMES)}")
