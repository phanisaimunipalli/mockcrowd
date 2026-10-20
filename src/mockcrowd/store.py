"""Runs, outcomes and eval history live under ~/.mockcrowd (override with MOCKCROWD_HOME)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .util import home, slugify


def runs_dir() -> Path:
    path = home() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_run_id(idea: str) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(idea, 24)}"


def save_run(run: dict[str, Any], markdown: str, out_dir: Path | None = None) -> Path:
    path = out_dir or runs_dir() / run["id"]
    path.mkdir(parents=True, exist_ok=True)
    (path / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    (path / "report.md").write_text(markdown, encoding="utf-8")
    return path


def load_run(run_id: str) -> dict[str, Any]:
    path = Path(run_id)
    if path.is_dir():
        path = path / "run.json"
    elif not path.is_file():
        path = runs_dir() / run_id / "run.json"
    if not path.is_file():
        raise FileNotFoundError(f"no run named {run_id!r} in {runs_dir()}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs() -> list[dict[str, Any]]:
    out = []
    for p in sorted(runs_dir().glob("*/run.json"), reverse=True):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"id": run["id"], "idea": run["idea"], "verdict": run["report"]["verdict"]})
    return out


def append_jsonl(name: str, row: dict[str, Any]) -> Path:
    path = home() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def read_jsonl(name: str) -> list[dict[str, Any]]:
    path = home() / name
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
