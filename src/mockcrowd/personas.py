"""Persona design: question -> audience plan -> real voices -> labeled mix -> grounded personas."""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .brains import Brain, Task
from .sources import Voice, appstore, bluesky, dedupe, hn, reddit
from .util import chunks, log, parallel_map, seed_from

STANCES = ["positive", "neutral", "skeptical", "negative"]
PAIN = ["none", "low", "medium", "high"]


@dataclass
class Persona:
    id: str
    handle: str
    segment: str
    bio: str
    occupation: str = ""
    age_range: str = ""
    needs: list[str] = field(default_factory=list)
    frustrations: list[str] = field(default_factory=list)
    current_tools: list[str] = field(default_factory=list)
    budget_sensitivity: str = "medium"
    tech_savvy: str = "medium"
    writing_style: str = ""
    stance: str = "neutral"
    source_ids: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return bool(self.source_ids)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def card(self) -> str:
        """Compact description used inside simulation prompts."""
        return (
            f"{self.id} u/{self.handle} [{self.segment}; {self.occupation}, {self.age_range}; "
            f"budget sensitivity {self.budget_sensitivity}; stance {self.stance}] {self.bio} "
            f"Needs: {'; '.join(self.needs[:3])}. Frustrations: {'; '.join(self.frustrations[:3])}. "
            f"Uses: {', '.join(self.current_tools[:3]) or 'nothing special'}. Writes: {self.writing_style}"
        )


# ---------------------------------------------------------------- audience plan


def plan_audience(brain: Brain, idea: str, audience: str | None = None) -> dict[str, Any]:
    prompt = f"""Plan where the real target users of this product idea talk online.

IDEA: {idea}
AUDIENCE HINT: {audience or "(none, infer it)"}

Return JSON:
{{"audience": "one sentence on who would use or buy this",
  "segments": [{{"name": "short name", "description": "who they are"}}],
  "subreddits": ["r/name"],
  "search_queries": ["2 to 5 word queries real users would write about this problem"],
  "hn_queries": ["queries for Hacker News comments"],
  "appstore_terms": ["names or terms of the closest existing apps"]}}

Use 3 to 6 segments, including people who would NOT buy (for example happy with the status quo).
Use 3 to 6 real, active subreddits, 4 to 8 search queries, 2 to 3 hn_queries, 2 to 3 appstore_terms."""

    def mock() -> dict[str, Any]:
        words = [w for w in idea.lower().split() if len(w) > 3][:3] or ["product"]
        return {
            "audience": audience or f"people interested in {' '.join(words)}",
            "segments": [
                {"name": "enthusiasts", "description": "deeply engaged hobbyists"},
                {"name": "casuals", "description": "occasional users"},
                {"name": "status quo", "description": "happy with what they use today"},
            ],
            "subreddits": [f"r/{words[0]}"],
            "search_queries": [" ".join(words)],
            "hn_queries": [" ".join(words)],
            "appstore_terms": [words[0]],
        }

    return brain.run(Task("plan", prompt, mock, validate=lambda v: isinstance(v, dict) and v.get("segments")))


# ---------------------------------------------------------------- collection


def collect_voices(
    plan: dict[str, Any],
    sources: list[str],
    per_query: int = 8,
    errors: list[str] | None = None,
) -> list[Voice]:
    """Gather real posts. Each source failing is recorded, never fatal."""
    errors = errors if errors is not None else []
    jobs: list[tuple[str, Any]] = []
    queries = plan.get("search_queries", [])[:6]
    if "reddit" in sources:
        for sub in plan.get("subreddits", [])[:6]:
            for q in queries[:2]:
                jobs.append((f"reddit {sub} '{q}'", lambda s=sub, q=q: reddit.search(q, s, posts=per_query)))
        for q in queries[2:5]:
            jobs.append((f"reddit '{q}'", lambda q=q: reddit.search(q, None, posts=per_query)))
    if "hn" in sources:
        for q in plan.get("hn_queries", [])[:3]:
            jobs.append((f"hn '{q}'", lambda q=q: hn.search(q)))
    if "bluesky" in sources:
        for q in queries[:4]:
            jobs.append((f"bluesky '{q}'", lambda q=q: bluesky.search(q)))
    if "appstore" in sources:
        for term in plan.get("appstore_terms", [])[:3]:
            jobs.append((f"appstore '{term}'", lambda t=term: appstore.search(t)))

    def run(job: tuple[str, Any]) -> list[Voice]:
        label, fn = job
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            return []

    results = parallel_map(run, jobs, workers=4, label="collecting voices")
    voices = dedupe([v for batch in results for v in batch])
    log(f"  collected {len(voices)} unique voices ({len(errors)} source errors)")
    return voices


# ---------------------------------------------------------------- labeling


def label_voices(brain: Brain, idea: str, plan: dict[str, Any], voices: list[Voice], workers: int = 8) -> list[Voice]:
    """Tag each voice with segment, relevance, pain and stance. Drops irrelevant ones."""
    segments = [s["name"] for s in plan["segments"]]

    def label_batch(batch: list[Voice]) -> list[dict[str, Any]]:
        listing = "\n".join(f"[{v.id}] ({v.community}) {v.text[:500]}" for v in batch)
        prompt = f"""Label real online posts for a demand study of this idea.

IDEA: {idea}
SEGMENTS: {json.dumps(segments)}

POSTS:
{listing}

For EVERY post return one item:
{{"labels": [{{"id": "post id", "segment": "one of SEGMENTS", "relevance": 0-3,
  "pain": "none|low|medium|high", "stance": "positive|neutral|skeptical|negative",
  "pays_for_tools": "yes|no|unknown"}}]}}
relevance 0 means the author is not part of this audience at all.
stance is the author's attitude toward solutions like this idea, judged only from what they wrote."""

        def mock() -> dict[str, Any]:
            out = []
            for v in batch:
                rng = random.Random(seed_from("label", v.id))
                out.append({
                    "id": v.id, "segment": rng.choice(segments), "relevance": rng.choice([0, 1, 2, 2, 3, 3]),
                    "pain": rng.choice(PAIN), "stance": rng.choices(STANCES, [2, 3, 3, 2])[0],
                    "pays_for_tools": rng.choice(["yes", "no", "unknown"]),
                })
            return {"labels": out}

        reply = brain.run(Task("label", prompt, mock, validate=lambda v: isinstance(v, dict) and "labels" in v))
        return reply["labels"]

    results = parallel_map(label_batch, chunks(voices, 40), workers=workers, label="labeling voices")
    by_id = {str(item.get("id")): item for batch in results for item in batch if isinstance(item, dict)}
    kept = []
    for v in voices:
        lab = by_id.get(v.id)
        if not lab:
            continue
        try:
            relevance = int(lab.get("relevance", 0))
        except (TypeError, ValueError):
            relevance = 0
        if relevance <= 0:
            continue
        seg = lab.get("segment") if lab.get("segment") in segments else segments[0]
        v.labels = {
            "segment": seg, "relevance": relevance,
            "pain": lab.get("pain") if lab.get("pain") in PAIN else "low",
            "stance": lab.get("stance") if lab.get("stance") in STANCES else "neutral",
            "pays_for_tools": lab.get("pays_for_tools", "unknown"),
        }
        kept.append(v)
    log(f"  {len(kept)} of {len(voices)} voices are relevant to the audience")
    return kept


# ---------------------------------------------------------------- quotas


def allocate(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Largest-remainder split of `total` across keys in proportion to weights."""
    keys = [k for k, w in weights.items() if w > 0]
    if not keys:
        return {}
    wsum = sum(weights[k] for k in keys)
    raw = {k: total * weights[k] / wsum for k in keys}
    counts = {k: int(raw[k]) for k in keys}
    for k in sorted(keys, key=lambda k: raw[k] - counts[k], reverse=True)[: total - sum(counts.values())]:
        counts[k] += 1
    return counts


def population_mix(voices: list[Voice], plan: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Segment share and stance share per segment, measured on the real voices."""
    segments = [s["name"] for s in plan["segments"]]
    if not voices:
        even = 1 / len(segments)
        return {s: {"share": even, **{st: 1 / len(STANCES) for st in STANCES}} for s in segments}
    seg_counts = Counter(v.labels["segment"] for v in voices)
    mix = {}
    for s in segments:
        group = [v for v in voices if v.labels["segment"] == s]
        stance_counts = Counter(v.labels["stance"] for v in group)
        n = max(1, len(group))
        mix[s] = {"share": seg_counts.get(s, 0) / len(voices), **{st: stance_counts.get(st, 0) / n for st in STANCES}}
    return mix


# ---------------------------------------------------------------- design


def design_personas(
    brain: Brain,
    idea: str,
    plan: dict[str, Any],
    voices: list[Voice],
    n_agents: int,
    batch_size: int = 25,
    workers: int = 8,
    seed: int = 0,
) -> list[Persona]:
    mix = population_mix(voices, plan)
    seg_counts = allocate(n_agents, {s: m["share"] for s, m in mix.items()})
    seg_desc = {s["name"]: s.get("description", "") for s in plan["segments"]}
    jobs = []
    for seg, count in seg_counts.items():
        stance_counts = allocate(count, {st: mix[seg][st] for st in STANCES}) or allocate(count, {st: 1 for st in STANCES})
        stance_list = [st for st, c in stance_counts.items() for _ in range(c)]
        random.Random(seed_from(seed, seg)).shuffle(stance_list)
        pool = [v for v in voices if v.labels.get("segment") == seg] or voices
        for bi, stances in enumerate(chunks(stance_list, batch_size)):
            rng = random.Random(seed_from(seed, seg, bi))
            sample = rng.sample(pool, min(len(pool), 30)) if pool else []
            jobs.append((seg, seg_desc.get(seg, ""), stances, sample, bi))

    def design(job: tuple[str, str, list[str], list[Voice], int]) -> list[dict[str, Any]]:
        seg, desc, stances, sample, bi = job
        evidence = "\n".join(f"[{v.id}] ({v.community}) {v.text[:400]}" for v in sample) or "(no real posts available)"
        stance_need = ", ".join(f"{c} {st}" for st, c in Counter(stances).items())
        prompt = f"""Design {len(stances)} distinct, realistic people from the segment "{seg}" ({desc}).
They will later react to this product idea, but design them WITHOUT reference to the idea's merits.

IDEA CONTEXT: {idea}

REAL POSTS FROM THIS SEGMENT (the only evidence you may build on):
{evidence}

Rules:
- Every person must be built from one to three of the real posts above; cite their ids in source_ids.
- Copy needs, frustrations, tools, vocabulary and writing style from the posts. Do not invent enthusiasm.
- Exactly this stance mix toward products like this: {stance_need}.
- Vary age, job, budget, and how much they care. Most people are busy and only mildly interested.

Return JSON: {{"personas": [{{"handle": "reddit-style username", "occupation": "", "age_range": "e.g. 25-34",
  "bio": "two sentences", "needs": [""], "frustrations": [""], "current_tools": [""],
  "budget_sensitivity": "low|medium|high", "tech_savvy": "low|medium|high",
  "writing_style": "how they write online", "stance": "positive|neutral|skeptical|negative",
  "source_ids": ["ids of the posts this person is built from"]}}]}}"""

        def mock() -> dict[str, Any]:
            out = []
            for i, st in enumerate(stances):
                rng = random.Random(seed_from(seed, seg, bi, i))
                src = [v.id for v in rng.sample(sample, min(2, len(sample)))] if sample else []
                out.append({
                    "handle": f"{seg.replace(' ', '_')}_{bi}_{i}_{rng.randint(10, 99)}",
                    "occupation": rng.choice(["teacher", "engineer", "nurse", "student", "designer", "retail manager"]),
                    "age_range": rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"]),
                    "bio": f"A {st} member of {seg} who {rng.choice(['collects', 'tinkers', 'browses', 'rarely engages'])}.",
                    "needs": [rng.choice(["save time", "save money", "keep track", "share with friends"])],
                    "frustrations": [rng.choice(["clunky apps", "subscriptions", "lost data", "too many tools"])],
                    "current_tools": [rng.choice(["spreadsheet", "notes app", "nothing", "a competitor app"])],
                    "budget_sensitivity": rng.choice(["low", "medium", "high"]),
                    "tech_savvy": rng.choice(["low", "medium", "high"]),
                    "writing_style": rng.choice(["terse", "chatty", "sarcastic", "detailed"]),
                    "stance": st, "source_ids": src,
                })
            return {"personas": out}

        reply = brain.run(Task("design", prompt, mock, validate=lambda v: isinstance(v, dict) and "personas" in v))
        valid_ids = {v.id for v in sample}
        rows = []
        for i, p in enumerate(reply["personas"][: len(stances)]):
            if not isinstance(p, dict):
                continue
            p["segment"] = seg
            p["stance"] = p.get("stance") if p.get("stance") in STANCES else stances[min(i, len(stances) - 1)]
            p["source_ids"] = [s for s in p.get("source_ids", []) if s in valid_ids]
            rows.append(p)
        return rows

    results = parallel_map(design, jobs, workers=workers, label="designing personas")
    personas = []
    for row in (r for batch in results for r in batch):
        row["id"] = f"p{len(personas) + 1:03d}"
        row.setdefault("handle", row["id"])
        row.setdefault("bio", "")
        for key in ("needs", "frustrations", "current_tools", "source_ids"):
            if not isinstance(row.get(key), list):
                row[key] = [str(row[key])] if row.get(key) else []
        personas.append(Persona.from_dict(row))
    log(f"  designed {len(personas)} personas, {sum(p.grounded for p in personas)} grounded in real posts")
    return personas
