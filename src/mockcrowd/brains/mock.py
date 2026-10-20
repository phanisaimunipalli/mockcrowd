"""Offline brain for tests and dry runs. Every Task carries its own deterministic mock."""

from __future__ import annotations

from typing import Any

from .base import Brain, BrainError, Task


class MockBrain(Brain):
    name = "mock"

    def complete(self, prompt: str) -> str:
        raise BrainError("the mock brain only answers Tasks that define a mock")

    def run(self, task: Task) -> Any:
        self.calls += 1
        if task.mock is None:
            raise BrainError(f"task {task.name} has no mock answer")
        return task.mock()
