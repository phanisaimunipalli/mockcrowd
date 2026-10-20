"""The simulation: blind vote, Reddit-style discussion, final vote.

The discussion layer follows the design of CAMEL-AI's OASIS (Apache-2.0): agents see a
ranked feed and pick one action per step from a fixed action space (comment, reply,
upvote, downvote, do nothing). mockcrowd reimplements that design in a few hundred lines
so that one LLM call can step a whole thread, which keeps 500 agents inside minutes.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from .brains import Brain, Task
from .personas import Persona
from .util import chunks, parallel_map, seed_from

# ---------------------------------------------------------------- typed questions


@dataclass
class Question:
    key: str
    kind: str  # yesno | score | choice | text
    text: str
    options: list[str] = field(default_factory=list)

    def spec(self) -> str:
        if self.kind == "yesno":
            return f'"{self.key}": true or false  // {self.text}'
        if self.kind in ("score", "choice"):
            return f'"{self.key}": one of {json.dumps(self.options)}  // {self.text}'
        return f'"{self.key}": "one short sentence"  // {self.text}'

    def normalize(self, value: Any) -> Any:
        if self.kind == "yesno":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "yes", "y", "1")
        if self.kind in ("score", "choice"):
            text = str(value).strip().lower()
            for opt in self.options:
                if opt.lower() == text:
                    return opt
            return self.options[0] if self.kind == "score" else None
        return str(value or "").strip()[:300]


def default_questions(price: str | None = None) -> list[Question]:
    pay_text = f"Would you pay {price} for it?" if price else "Would you pay any money for it?"
    return [
        Question("interest", "score", "How interested are you, honestly?", ["none", "low", "medium", "high"]),
        Question("try_free", "yesno", "Would you actually install or sign up if it were free?"),
        Question("would_pay", "yesno", pay_text),
        Question("objection", "text", "Your single biggest reason NOT to use it."),
    ]


def parse_question(spec: str) -> Question:
    """kind:key:question text[:opt1|opt2|...], for example
    choice:first_feature:Which would you use first?:scan|wishlist|alerts"""
    parts = spec.split(":", 3)
    if len(parts) < 3 or parts[0] not in ("yesno", "score", "choice", "text"):
        raise ValueError(f"bad --question {spec!r}; use kind:key:text[:opt1|opt2]")
    options = parts[3].split("|") if len(parts) == 4 else []
    if parts[0] in ("score", "choice") and len(options) < 2:
        raise ValueError(f"--question {spec!r} needs at least two options")
    return Question(parts[1], parts[0], parts[2], options)


# ---------------------------------------------------------------- control pitch


def placebo_pitch(brain: Brain, idea: str) -> str:
    """A same-category pitch with no differentiator. Real demand should beat it clearly."""
    prompt = f"""Write a bland control pitch for a demand experiment.

REAL IDEA: {idea}

Write a pitch for a generic product in the same category, aimed at the same people, with no new
feature, no clear advantage over what already exists, and a slightly higher price. Same length and
tone as the real idea. Do not mention the real idea.
Return JSON: {{"pitch": "..."}}"""

    def mock() -> dict[str, str]:
        return {"pitch": "A basic app in the same category with standard features and a monthly subscription."}

    return brain.run(Task("placebo", prompt, mock, validate=lambda v: isinstance(v, dict) and v.get("pitch")))["pitch"]


# ---------------------------------------------------------------- votes


_PAY_BASE = {"positive": 0.55, "neutral": 0.22, "skeptical": 0.08, "negative": 0.02}


def _mock_answers(questions: list[Question], persona: Persona, strength: float, salt: str) -> dict[str, Any]:
    rng = random.Random(seed_from(salt, persona.id))
    base = _PAY_BASE.get(persona.stance, 0.2) * strength
    out: dict[str, Any] = {}
    for q in questions:
        if q.kind == "yesno":
            p = min(0.95, base * (2.2 if q.key == "try_free" else 1.0))
            out[q.key] = rng.random() < p
        elif q.kind in ("score", "choice"):
            idx = min(len(q.options) - 1, int(rng.random() * len(q.options) * (0.4 + base)))
            out[q.key] = q.options[idx] if q.kind == "score" else rng.choice(q.options)
        else:
            out[q.key] = rng.choice(["too expensive", "I already use a spreadsheet", "privacy worries",
                                     "not a real problem for me", "would forget to use it"])
    return out


def _vote_task(
    personas: list[Persona],
    pitches: dict[str, str],
    questions: list[Question],
    context: str,
    mock_strength: dict[str, float],
    salt: str,
) -> Task:
    pitch_text = "\n".join(f"PITCH {k}: {v}" for k, v in pitches.items())
    people = "\n".join(p.card() for p in personas)
    spec = ",\n    ".join(q.spec() for q in questions)
    keys = list(pitches)
    prompt = f"""Each person below reacts privately to the product pitch(es). Answer as each person
would in real life: from their needs, budget and stance, not from the founder's hopes.
Saying no is normal. Paying is a big step most people never take.
{context}
{pitch_text}

PEOPLE:
{people}

Return JSON: {{"answers": [{{"id": "person id", {", ".join(f'"{k}": {{answers}}' for k in keys)}}}]}}
where each {{answers}} object is:
    {{{spec}}}
Answer for every person, in the same order."""

    def mock() -> dict[str, Any]:
        return {"answers": [
            {"id": p.id, **{k: _mock_answers(questions, p, mock_strength.get(k, 1.0), f"{salt}{k}") for k in keys}}
            for p in personas
        ]}

    return Task("vote", prompt, mock, validate=lambda v: isinstance(v, dict) and isinstance(v.get("answers"), list))


def _collect_votes(reply: dict[str, Any], personas: list[Persona], keys: list[str], questions: list[Question]) -> dict[str, dict[str, Any]]:
    by_id = {str(a.get("id")): a for a in reply.get("answers", []) if isinstance(a, dict)}
    out = {}
    for p in personas:
        row = by_id.get(p.id)
        if not row:
            continue
        out[p.id] = {}
        for k in keys:
            ans = row.get(k) or {}
            out[p.id][k] = {q.key: q.normalize(ans.get(q.key)) for q in questions}
    return out


def blind_vote(
    brain: Brain,
    personas: list[Persona],
    idea: str,
    placebo: str | None,
    questions: list[Question],
    batch_size: int = 25,
    workers: int = 8,
    seed: int = 0,
) -> dict[str, dict[str, Any]]:
    """Round 0. Each persona answers alone, before seeing anyone else.
    The real idea and the control are shown side by side in random order, as A and B."""

    def run(job: tuple[int, list[Persona]]) -> dict[str, dict[str, Any]]:
        bi, batch = job
        if placebo is None:
            mapping = {"A": "idea"}
            pitches = {"A": idea}
        else:
            flip = random.Random(seed_from(seed, "flip", bi)).random() < 0.5
            mapping = {"A": "control", "B": "idea"} if flip else {"A": "idea", "B": "control"}
            pitches = {k: (placebo if v == "control" else idea) for k, v in mapping.items()}
        strength = {k: (0.45 if v == "control" else 1.0) for k, v in mapping.items()}
        task = _vote_task(batch, pitches, questions, "", strength, f"blind{seed}")
        votes = _collect_votes(brain.run(task), batch, list(pitches), questions)
        return {pid: {mapping[k]: ans for k, ans in row.items()} for pid, row in votes.items()}

    results = parallel_map(run, list(enumerate(chunks(personas, batch_size))), workers=workers, label="blind vote")
    merged: dict[str, dict[str, Any]] = {}
    for r in results:
        merged.update(r)
    return merged


# ---------------------------------------------------------------- discussion platform


@dataclass
class Comment:
    id: str
    author: str
    handle: str
    text: str
    parent: str | None
    round: int
    up: int = 0
    down: int = 0

    @property
    def score(self) -> int:
        return self.up - self.down


@dataclass
class Thread:
    id: str
    community: str
    title: str
    body: str
    members: list[str]
    comments: list[Comment] = field(default_factory=list)

    def hot(self, now: int) -> list[Comment]:
        """OASIS-style hot ranking: net votes, decayed by age in rounds."""
        return sorted(self.comments, key=lambda c: (c.score + 1) / (1 + now - c.round) ** 0.8, reverse=True)

    def render(self, now: int, limit: int = 30) -> str:
        if not self.comments:
            return "(no comments yet)"
        lines = []
        for c in self.hot(now)[:limit]:
            reply = f" (reply to {c.parent})" if c.parent else ""
            lines.append(f"[{c.id}] u/{c.handle} ({c.score:+d}){reply}: {c.text}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {**{k: v for k, v in asdict(self).items() if k != "comments"},
                "comments": [asdict(c) for c in self.comments]}


ACTIONS = ("comment", "reply", "upvote", "downvote", "nothing")


def make_threads(personas: list[Persona], idea: str, community: str, size: int = 20, seed: int = 0) -> list[Thread]:
    """Split the crowd into Reddit threads, mixing segments in every thread."""
    by_segment: dict[str, list[Persona]] = {}
    for p in personas:
        by_segment.setdefault(p.segment, []).append(p)
    rng = random.Random(seed_from(seed, "threads"))
    for group in by_segment.values():
        rng.shuffle(group)
    order = [p for row in zip_longest_all(list(by_segment.values())) for p in row]
    n_threads = max(1, round(len(order) / size))
    members: list[list[str]] = [[] for _ in range(n_threads)]
    for i, p in enumerate(order):
        members[i % n_threads].append(p.id)
    title = "Would you use this? Looking for honest feedback before I build it"
    return [Thread(f"t{i + 1:02d}", community, title, idea, m) for i, m in enumerate(members)]


def zip_longest_all(groups: list[list[Persona]]) -> list[list[Persona]]:
    longest = max((len(g) for g in groups), default=0)
    return [[g[i] for g in groups if i < len(g)] for i in range(longest)]


def step_thread(brain: Brain, thread: Thread, personas: dict[str, Persona], rnd: int, seed: int = 0) -> None:
    members = [personas[m] for m in thread.members]
    random.Random(seed_from(seed, thread.id, rnd)).shuffle(members)
    people = "\n".join(p.card() for p in members)
    prompt = f"""Simulate one step of a Reddit thread in {thread.community}. Each person sees the feed
and takes exactly ONE action, the way they really would. Most real users scroll past
("nothing") or vote; few write. Comments are short, in each person's own voice, and honest:
agreement only when they truly mean it, pushback, jokes, questions, "just use a spreadsheet".
People can change their mind if a comment convinces them, in either direction.

POST by u/founder: "{thread.title}"
{thread.body}

FEED (hot first, [id] u/handle (score)):
{thread.render(rnd)}

PEOPLE:
{people}

Return JSON: {{"actions": [{{"id": "person id", "action": "comment|reply|upvote|downvote|nothing",
  "target": "comment id for reply/upvote/downvote, else null", "text": "comment text or empty"}}]}}
One action for every person."""

    def mock() -> dict[str, Any]:
        rng = random.Random(seed_from(seed, thread.id, rnd, "mock"))
        ids = [c.id for c in thread.comments]
        out = []
        for p in members:
            action = rng.choices(ACTIONS, [3, 2 if ids else 0, 3 if ids else 0, 1 if ids else 0, 4])[0]
            text = {"positive": "I'd try this honestly.", "neutral": "Not sure I need it.",
                    "skeptical": "What does this do that a spreadsheet can't?",
                    "negative": "Another subscription? Pass."}[p.stance]
            out.append({"id": p.id, "action": action, "target": rng.choice(ids) if ids else None, "text": text})
        return {"actions": out}

    reply = brain.run(Task("thread", prompt, mock, validate=lambda v: isinstance(v, dict) and isinstance(v.get("actions"), list)))
    existing = {c.id: c for c in thread.comments}
    member_ids = set(thread.members)
    counter = len(thread.comments)
    for act in reply["actions"]:
        if not isinstance(act, dict) or act.get("id") not in member_ids:
            continue
        kind, target, text = act.get("action"), act.get("target"), str(act.get("text") or "").strip()
        author = personas[act["id"]]
        if kind in ("comment", "reply") and text:
            counter += 1
            parent = target if kind == "reply" and target in existing else None
            thread.comments.append(Comment(f"{thread.id}c{counter}", author.id, author.handle, text[:600], parent, rnd))
        elif kind in ("upvote", "downvote") and target in existing and existing[target].author != author.id:
            if kind == "upvote":
                existing[target].up += 1
            else:
                existing[target].down += 1


def discuss(brain: Brain, threads: list[Thread], personas: dict[str, Persona], rounds: int, workers: int = 8, seed: int = 0) -> None:
    for rnd in range(1, rounds + 1):
        parallel_map(lambda t: step_thread(brain, t, personas, rnd, seed), threads, workers=workers,
                     label=f"discussion round {rnd}/{rounds}")


def final_vote(
    brain: Brain,
    threads: list[Thread],
    personas: dict[str, Persona],
    idea: str,
    questions: list[Question],
    rounds: int,
    workers: int = 8,
    seed: int = 0,
) -> dict[str, dict[str, Any]]:
    """After the discussion, each persona answers again, with their thread in mind."""

    def run(thread: Thread) -> dict[str, dict[str, Any]]:
        members = [personas[m] for m in thread.members]
        context = f"\nTHE THREAD THEY JUST READ (top comments):\n{thread.render(rounds + 1, limit=10)}\n"
        out: dict[str, dict[str, Any]] = {}
        for bi, batch in enumerate(chunks(members, 25)):
            task = _vote_task(batch, {"A": idea}, questions, context, {"A": 1.05}, f"final{seed}{thread.id}{bi}")
            for pid, row in _collect_votes(brain.run(task), batch, ["A"], questions).items():
                out[pid] = {"idea": row["A"]}
        return out

    merged: dict[str, dict[str, Any]] = {}
    for r in parallel_map(run, threads, workers=workers, label="final vote"):
        merged.update(r)
    return merged
