"""Real-world voices that personas are grounded in."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Voice:
    id: str
    source: str  # reddit, hn, appstore, file, ...
    text: str
    community: str = ""  # r/vinyl, Hacker News, an app name
    author: str = ""
    url: str = ""
    score: int = 0
    labels: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Voice":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


MIN_CHARS = 40
MAX_CHARS = 1200


def clean_text(text: str) -> str:
    text = " ".join((text or "").split())
    return text[:MAX_CHARS]


def dedupe(voices: list[Voice]) -> list[Voice]:
    seen: set[str] = set()
    out = []
    for v in voices:
        key = v.text[:120].lower()
        if len(v.text) < MIN_CHARS or key in seen or v.text in ("[deleted]", "[removed]"):
            continue
        seen.add(key)
        out.append(v)
    return out
