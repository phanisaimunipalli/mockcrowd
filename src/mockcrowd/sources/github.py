"""GitHub issues and their top comments: where developers ask for features (no key needed).

Set GITHUB_TOKEN (or GH_TOKEN) to raise the search rate limit from 10 to 30 requests a minute.
"""

from __future__ import annotations

import os

from ..util import http_json, log
from . import Voice, clean_text

API = "https://api.github.com"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def search(query: str, issues: int = 8, threads: int = 3, comments: int = 10) -> list[Voice]:
    """Most-reacted issues for a query, plus top comments from the busiest few."""
    headers = _headers()
    found = http_json(f"{API}/search/issues", headers=headers,
                      params={"q": f"{query} is:issue", "sort": "reactions", "order": "desc", "per_page": issues})
    voices: list[Voice] = []
    items = [i for i in found.get("items", []) if isinstance(i, dict)]
    for item in items:
        repo = str(item.get("repository_url", "")).split("/repos/")[-1]
        voices.append(Voice(
            id=f"gh:{repo}#{item.get('number')}", source="github", community=repo,
            text=clean_text(f"{item.get('title', '')}. {item.get('body') or ''}"),
            author=(item.get("user") or {}).get("login", ""), url=item.get("html_url", ""),
            score=int((item.get("reactions") or {}).get("total_count") or 0),
        ))
    for item in sorted(items, key=lambda i: -int(i.get("comments") or 0))[:threads]:
        if not item.get("comments"):
            continue
        repo = str(item.get("repository_url", "")).split("/repos/")[-1]
        try:
            rows = http_json(item["comments_url"], headers=headers, params={"per_page": comments})
        except (RuntimeError, KeyError) as exc:
            log(f"  github: skipped comments for {repo}#{item.get('number')}: {exc}")
            continue
        for c in rows if isinstance(rows, list) else []:
            voices.append(Voice(
                id=f"gh:{repo}#c{c.get('id')}", source="github", community=repo, text=clean_text(c.get("body") or ""),
                author=(c.get("user") or {}).get("login", ""), url=c.get("html_url", ""),
                score=int((c.get("reactions") or {}).get("total_count") or 0),
            ))
    return voices
