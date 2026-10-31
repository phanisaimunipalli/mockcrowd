import pytest

from mockcrowd.personas import allocate
from mockcrowd.report import proportion, score_index
from mockcrowd.sim import Question, parse_question
from mockcrowd.util import extract_json, strip_html


def test_extract_json_plain_fenced_and_embedded():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('Here you go: {"ok": true} hope that helps') == {"ok": True}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_allocate_sums_exactly_and_is_proportional():
    counts = allocate(500, {"a": 0.5, "b": 0.3, "c": 0.2})
    assert sum(counts.values()) == 500
    assert counts == {"a": 250, "b": 150, "c": 100}
    assert sum(allocate(7, {"x": 1, "y": 1, "z": 1}).values()) == 7
    assert allocate(5, {"x": 0}) == {}


def test_proportion_interval_contains_estimate():
    out = proportion([True] * 30 + [False] * 70, seed=1)
    assert out["p"] == 0.3
    assert out["low"] <= 0.3 <= out["high"]
    assert proportion([])["n"] == 0
    zero = proportion([False] * 20)
    assert zero["p"] == 0 and zero["low"] == 0 and zero["high"] > 0.1


def test_score_index():
    opts = ["none", "low", "medium", "high"]
    assert score_index(["none", "high"], opts) == 0.5
    assert score_index(["high"] * 3, opts) == 1.0


def test_question_parsing_and_normalizing():
    q = parse_question("choice:first:Which first?:scan|alerts")
    assert q.kind == "choice" and q.options == ["scan", "alerts"]
    assert q.normalize("SCAN") == "scan"
    assert Question("x", "yesno", "?").normalize("Yes") is True
    assert Question("x", "yesno", "?").normalize("no") is False
    with pytest.raises(ValueError):
        parse_question("choice:first:Which first?")
    with pytest.raises(ValueError):
        parse_question("bogus:k:t")


def test_strip_html():
    assert strip_html("<p>Hi &amp; <i>bye</i>") == "Hi & bye"


def test_votes_land_on_comments_written_in_the_same_step():
    from mockcrowd.brains.mock import MockBrain
    from mockcrowd.personas import Persona
    from mockcrowd.sim import Thread, step_thread

    class Scripted(MockBrain):
        def run(self, task):
            return {"actions": [
                {"id": "p1", "action": "comment", "target": None, "text": "Spreadsheet works fine."},
                {"id": "p2", "action": "upvote", "target": "p1", "text": ""},
                {"id": "p3", "action": "reply", "target": "p1", "text": "Agreed."},
            ]}

    people = {f"p{i}": Persona(id=f"p{i}", handle=f"u{i}", segment="s", bio="b", stance="neutral") for i in (1, 2, 3)}
    thread = Thread("t01", "r/x", "title", "idea", list(people))
    step_thread(Scripted(), thread, people, rnd=1)
    first, reply = thread.comments
    assert first.score == 1 and reply.parent == first.id
