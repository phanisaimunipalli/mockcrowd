"""Reddit posts and top comments.

Uses app-only OAuth when REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are set (free,
non-commercial, about 100 queries per minute). Falls back to the public .json pages,
which Reddit may throttle or block.
"""

from __future__ import annotations

import base64
import os
import urllib.parse

from ..util import http_json, log
from . import Voice, clean_text

_token: str | None = None


def _auth() -> tuple[str, dict[str, str]]:
    global _token
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return "https://www.reddit.com", {}
    if _token is None:
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        data = http_json(
            "https://www.reddit.com/api/v1/access_token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        )
        _token = data["access_token"]
    return "https://oauth.reddit.com", {"Authorization": f"bearer {_token}"}


def _subreddit(name: str) -> str:
    return name.strip().removeprefix("r/").removeprefix("/r/").strip("/")


def search(
    query: str,
    subreddit: str | None = None,
    posts: int = 10,
    comments_per_post: int = 15,
) -> list[Voice]:
    base, headers = _auth()
    if subreddit:
        sub = _subreddit(subreddit)
        url = f"{base}/r/{sub}/search.json"
        params = {"q": query, "restrict_sr": 1, "sort": "relevance", "t": "all", "limit": posts}
    else:
        sub = ""
        url = f"{base}/search.json"
        params = {"q": query, "sort": "relevance", "t": "all", "limit": posts}
    listing = http_json(url, params=params, headers=headers)
    voices: list[Voice] = []
    for child in listing.get("data", {}).get("children", []):
        post = child.get("data", {})
        community = f"r/{post.get('subreddit', sub)}"
        permalink = f"https://www.reddit.com{post.get('permalink', '')}"
        body = clean_text(f"{post.get('title', '')}. {post.get('selftext', '')}")
        voices.append(Voice(
            id=f"reddit:{post.get('id')}", source="reddit", text=body, community=community,
            author=post.get("author", ""), url=permalink, score=int(post.get("score", 0)),
        ))
        if comments_per_post <= 0:
            continue
        try:
            thread = http_json(
                f"{base}/comments/{post.get('id')}.json",
                params={"limit": comments_per_post, "depth": 1, "sort": "top"},
                headers=headers,
            )
        except RuntimeError as exc:
            log(f"  reddit: skipped comments for {post.get('id')}: {exc}")
            continue
        if not isinstance(thread, list) or len(thread) < 2:
            continue
        for c in thread[1].get("data", {}).get("children", [])[:comments_per_post]:
            cd = c.get("data", {})
            if c.get("kind") != "t1" or not cd.get("body"):
                continue
            voices.append(Voice(
                id=f"reddit:{cd.get('id')}", source="reddit", text=clean_text(cd["body"]),
                community=community, author=cd.get("author", ""),
                url=f"https://www.reddit.com{cd.get('permalink', '')}", score=int(cd.get("score", 0)),
            ))
    return voices
