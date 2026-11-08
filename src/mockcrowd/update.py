"""Once a day, tell the user when a newer mockcrowd is on PyPI. It only prints a line; it never installs."""

from __future__ import annotations

import json
import os
import sys
import time

from . import __version__
from .util import home, http_json

PYPI_URL = "https://pypi.org/pypi/mockcrowd/json"
DAY = 24 * 3600


def _parse(version: str) -> tuple[int, ...] | None:
    parts = version.split(".")
    return tuple(int(p) for p in parts) if all(p.isdigit() for p in parts) else None  # skip pre-releases


def latest_version(now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    cache = home() / "update.json"
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if now - saved["checked"] < DAY:
            return saved["latest"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        latest = http_json(PYPI_URL, timeout=2, retries=0)["info"]["version"]
    except Exception:  # offline or PyPI down: stay silent, try again tomorrow
        latest = None
    cache.write_text(json.dumps({"checked": now, "latest": latest}), encoding="utf-8")
    return latest


def notice(now: float | None = None) -> str | None:
    if os.environ.get("MOCKCROWD_NO_UPDATE_CHECK") or not sys.stderr.isatty():
        return None
    latest = latest_version(now)
    new, current = _parse(latest or ""), _parse(__version__)
    if new and current and new > current:
        return f"mockcrowd {latest} is available (you have {__version__}). Upgrade: pip install -U mockcrowd"
    return None
