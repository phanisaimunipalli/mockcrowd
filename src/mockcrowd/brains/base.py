"""The Brain interface: anything that turns a prompt into JSON."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..util import extract_json, log

SYSTEM_PROMPT = (
    "You are the simulation engine of mockcrowd, a tool that predicts how real people "
    "react to product ideas. You never act as an assistant to the founder and you never "
    "flatter ideas. Real people are busy, skeptical and mostly indifferent to new products: "
    "most say no, many never reply, and only a few would ever pay. Stay faithful to the "
    "evidence you are given. Reply with JSON only, no prose, no markdown fences."
)


class BrainError(RuntimeError):
    pass


@dataclass
class Task:
    """One unit of LLM work. `mock` gives a deterministic offline answer for tests."""

    name: str
    prompt: str
    mock: Callable[[], Any] | None = None
    validate: Callable[[Any], bool] | None = None


class Brain(ABC):
    name = "brain"

    def __init__(self, model: str | None = None, timeout: float = 600.0):
        self.model = model
        self.timeout = timeout
        self.calls = 0
        self.cost_usd = 0.0  # only brains that report cost (claude) add to this
        self._lock = threading.Lock()

    def add_cost(self, usd: float) -> None:
        with self._lock:
            self.cost_usd += usd

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return the raw text reply for a prompt."""

    def run(self, task: Task) -> Any:
        last: Exception | None = None
        prompt = task.prompt
        for attempt in range(3):
            self.calls += 1
            try:
                value = extract_json(self.complete(prompt))
                if task.validate and not task.validate(value):
                    raise ValueError("reply did not match the expected shape")
                return value
            except (ValueError, BrainError) as exc:
                last = exc
                log(f"  {self.name}: retrying {task.name} ({exc})")
                prompt = (
                    task.prompt
                    + "\n\nYour previous reply was invalid. Reply with ONLY the JSON described above."
                )
        raise BrainError(f"{self.name} failed on task {task.name}: {last}")

    def describe(self) -> str:
        return f"{self.name}" + (f" ({self.model})" if self.model else "")
