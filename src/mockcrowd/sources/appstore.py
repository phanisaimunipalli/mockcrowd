"""App Store reviews of the closest existing apps, through Apple's public iTunes endpoints."""

from __future__ import annotations

from ..util import http_json, log
from . import Voice, clean_text


def search(term: str, apps: int = 3, country: str = "us") -> list[Voice]:
    found = http_json(
        "https://itunes.apple.com/search",
        params={"term": term, "entity": "software", "limit": apps, "country": country},
    )
    voices = []
    for app in found.get("results", [])[:apps]:
        app_id, app_name = app.get("trackId"), app.get("trackName", "")
        try:
            feed = http_json(
                f"https://itunes.apple.com/{country}/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"
            )
        except RuntimeError as exc:
            log(f"  appstore: skipped {app_name}: {exc}")
            continue
        entries = feed.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        for e in entries:
            body = e.get("content", {}).get("label")
            if not body:
                continue
            rating = e.get("im:rating", {}).get("label", "")
            title = e.get("title", {}).get("label", "")
            voices.append(Voice(
                id=f"appstore:{e.get('id', {}).get('label', '')}", source="appstore",
                text=clean_text(f"[{rating} stars] {title}. {body}"), community=app_name,
                author=e.get("author", {}).get("name", {}).get("label", ""),
                url=app.get("trackViewUrl", ""), score=int(rating or 0),
            ))
    return voices
