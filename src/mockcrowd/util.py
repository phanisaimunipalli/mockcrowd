"""Small shared helpers: JSON extraction, parallel map, HTTP, logging."""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

USER_AGENT = "mockcrowd/0.4 (+https://github.com/phanisaimunipalli/mockcrowd)"
_quiet = False
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def ssl_context() -> ssl.SSLContext:
    """Use certifi's CA bundle: python.org builds on macOS ship without root certificates."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class SameOriginAuthRedirect(urllib.request.HTTPRedirectHandler):
    """urllib keeps Authorization across redirects; drop it when the origin changes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        before, after = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new and (before.scheme, before.netloc) != (after.scheme, after.netloc):
            new.remove_header("Authorization")
        return new


def urlopen(req: urllib.request.Request | str, timeout: float):
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context()), SameOriginAuthRedirect())
    return opener.open(req, timeout=timeout)


def set_quiet(value: bool) -> None:
    global _quiet
    _quiet = value


def log(msg: str) -> None:
    if not _quiet:
        print(msg, file=sys.stderr, flush=True)


def home() -> Path:
    custom = os.environ.get("MOCKCROWD_HOME")
    path = Path(custom or Path.home() / ".mockcrowd")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)  # runs hold unannounced ideas
    if not custom:
        path.chmod(0o700)
    return path


def seed_from(*parts: Any) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:12], 16)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "run"


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object or array out of an LLM reply."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for block in _FENCE.findall(text):
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                value, _ = decoder.raw_decode(text[i:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON found in reply: {text[:200]!r}")


def parallel_map(
    fn: Callable[[T], R],
    items: Iterable[T],
    workers: int = 8,
    label: str = "",
) -> list[R]:
    """Run fn over items with a thread pool, keeping input order."""
    items = list(items)
    if not items:
        return []
    results: list[Any] = [None] * len(items)
    done = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, item): i for i, item in enumerate(items)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            if label:
                log(f"  {label}: {done}/{len(items)} ({time.time() - start:.0f}s)")
    return results


def chunks(items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def http_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network errors, HTTP errors, bad JSON
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}: {last}")


def strip_control(text: str) -> str:
    """Remove control characters, so scraped or generated text cannot drive the terminal."""
    return _CONTROL.sub("", text)


def strip_html(text: str) -> str:
    text = re.sub(r"<p>", "\n", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    for a, b in (("&#x27;", "'"), ("&quot;", '"'), ("&amp;", "&"), ("&gt;", ">"), ("&lt;", "<"), ("&#x2F;", "/")):
        text = text.replace(a, b)
    return text.strip()
