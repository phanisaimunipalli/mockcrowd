"""Hacker News comments through the free Algolia search API (no key needed)."""

from __future__ import annotations

from ..util import http_json, strip_html
from . import Voice, clean_text

API = "https://hn.algolia.com/api/v1/search"


def search(query: str, limit: int = 40) -> list[Voice]:
    data = http_json(API, params={"query": query, "tags": "comment", "hitsPerPage": limit})
    voices = []
    for hit in data.get("hits", []):
        text = clean_text(strip_html(hit.get("comment_text") or ""))
        if not text:
            continue
        voices.append(Voice(
            id=f"hn:{hit.get('objectID')}", source="hn", text=text, community="Hacker News",
            author=hit.get("author") or "", score=int(hit.get("points") or 0),
            url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
        ))
    return voices
