"""Bluesky posts through the public AppView search (no key needed)."""

from __future__ import annotations

from ..util import http_json
from . import Voice, clean_text

API = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"


def search(query: str, limit: int = 40) -> list[Voice]:
    data = http_json(API, params={"q": query, "limit": limit, "sort": "top"})
    voices = []
    for post in data.get("posts", []):
        text = clean_text(post.get("record", {}).get("text", ""))
        handle = post.get("author", {}).get("handle", "")
        rkey = post.get("uri", "").rsplit("/", 1)[-1]
        voices.append(Voice(
            id=f"bsky:{rkey}", source="bluesky", text=text, community="Bluesky", author=handle,
            url=f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else "",
            score=int(post.get("likeCount") or 0),
        ))
    return voices
