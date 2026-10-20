"""Voices from local files: JSONL, CSV or plain text.

This is also how any other platform (X, Threads, Instagram, surveys, support tickets,
interview notes) gets in: export or paste the posts into a file.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from . import Voice, clean_text


def load(path: str | Path, source: str = "file") -> list[Voice]:
    path = Path(path)
    stem = path.stem
    voices: list[Voice] = []
    if path.suffix == ".jsonl":
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, str):
                row = {"text": row}
            voices.append(_from_row(row, f"{stem}:{i}", source))
    elif path.suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        for i, row in enumerate(rows):
            voices.append(_from_row(row if isinstance(row, dict) else {"text": row}, f"{stem}:{i}", source))
    elif path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            for i, row in enumerate(csv.DictReader(fh)):
                voices.append(_from_row(row, f"{stem}:{i}", source))
    else:
        blocks = [b for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
        voices = [Voice(id=f"{stem}:{i}", source=source, text=clean_text(b), community=stem) for i, b in enumerate(blocks)]
    return voices


def _from_row(row: dict, default_id: str, source: str) -> Voice:
    text = row.get("text") or row.get("body") or row.get("content") or ""
    return Voice(
        id=str(row.get("id") or default_id),
        source=str(row.get("source") or source),
        text=clean_text(str(text)),
        community=str(row.get("community") or row.get("subreddit") or ""),
        author=str(row.get("author") or ""),
        url=str(row.get("url") or ""),
        score=int(float(row.get("score") or 0)),
    )


def save(voices: list[Voice], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        for v in voices:
            fh.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")
