from mockcrowd.brains.mock import MockBrain
from mockcrowd.pipeline import Config, validate
from mockcrowd.report import render_markdown
from mockcrowd.sources import github


def test_free_mode_judges_use_not_payment(voices_file):
    run = validate("An async API for an agent library", MockBrain(),
                   Config(agents=20, rounds=1, free=True, sources=[], voice_files=[str(voices_file)]), save=False)
    rep = run["report"]
    keys = {q["key"] for q in run["config"]["questions"]}
    assert "would_use" in keys and "would_pay" not in keys
    assert rep["mode"] == "free" and "interest" in rep["verdict"].lower()
    text = render_markdown(run)
    assert "Would use" in text and "Would pay" not in text


def test_free_and_price_together_is_an_error():
    import pytest

    with pytest.raises(ValueError):
        validate("x", MockBrain(), Config(agents=10, free=True, price="$5", sources=[]), save=False)


def test_github_issues_and_comments_become_voices(monkeypatch):
    issue = {"number": 7, "title": "Support rerankers", "body": "Please add reranking models, my RAG needs it",
             "repository_url": "https://api.github.com/repos/acme/llm", "html_url": "https://github.com/acme/llm/issues/7",
             "user": {"login": "dev1"}, "reactions": {"total_count": 42}, "comments": 2,
             "comments_url": "https://api.github.com/repos/acme/llm/issues/7/comments"}
    comment = {"id": 99, "body": "Same here, I run a separate reranker server just for this", "user": {"login": "dev2"},
               "html_url": "https://github.com/acme/llm/issues/7#issuecomment-99", "reactions": {"total_count": 5}}
    calls = []

    def fake(url, params=None, headers=None, **_):
        calls.append((url, headers))
        return {"items": [issue]} if "search" in url else [comment]

    monkeypatch.setattr(github, "http_json", fake)
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    voices = github.search("rerank")
    assert [v.id for v in voices] == ["gh:acme/llm#7", "gh:acme/llm#c99"]
    assert voices[0].score == 42 and voices[0].community == "acme/llm"
    assert all(h["Authorization"] == "Bearer t0ken" for _, h in calls)
    assert all(u.startswith("https://api.github.com/") for u, _ in calls)


def test_exclude_drops_matching_real_posts(voices_file):
    run = validate("idea", MockBrain(), Config(agents=10, rounds=1, sources=[], voice_files=[str(voices_file)],
                                               exclude=[":0", ":1"]), save=False)
    assert all(not v["id"].endswith((":0", ":1")) for v in run["voices"])
