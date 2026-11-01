"""Real-world voices that personas are grounded in."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..util import strip_control


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
    text = " ".join(strip_control(text or "").split())
    return text[:MAX_CHARS]


def fenced(voice: Voice, limit: int) -> str:
    """One post for a prompt, fenced so a stranger's text cannot pose as our instructions."""
    text = re.sub(r"(?i)</post", r"<\\/post", voice.text[:limit])
    return f"[{voice.id}] ({voice.community}) <post>{text}</post>"


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
