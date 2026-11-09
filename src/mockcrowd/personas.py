"""Persona design: question -> audience plan -> real voices -> labeled mix -> grounded personas."""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from . import traits as T
from .brains import Brain, Task
from .sources import Voice, appstore, bluesky, dedupe, fenced, github, hn, reddit
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
    traits: dict[str, float] = field(default_factory=dict)  # 0 to 1, sampled from the measured trait model

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
        traits = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in self.traits.items())
        return (
            f"{self.id} u/{self.handle} [{self.segment}; {self.occupation}, {self.age_range}; "
            f"budget sensitivity {self.budget_sensitivity}; stance {self.stance}] {self.bio} "
            f"Needs: {'; '.join(self.needs[:3])}. Frustrations: {'; '.join(self.frustrations[:3])}. "
            f"Uses: {', '.join(self.current_tools[:3]) or 'nothing special'}. Writes: {self.writing_style}"
            + (f" Traits (0 to 1): {traits}." if traits else "")
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
  "github_queries": ["GitHub issue search queries, ONLY if the audience is software developers, else empty"],
  "appstore_terms": ["names or terms of the closest existing apps"],
  "trait_dims": [{{"name": "short snake_case name", "description": "what 0 and 1 mean"}}]}}

Use 3 to 6 segments, including people who would NOT buy (for example happy with the status quo).
Use 3 to 6 real, active subreddits, 4 to 8 search queries, 2 to 3 hn_queries, 2 to 3 appstore_terms,
and 0 to 2 github_queries (short keyword queries, for example "rerank model support").
trait_dims: 0 to 4 traits that matter for THIS audience and are not generic (generic ones such as budget
sensitivity, tech savvy and trust are already measured), for example "collection_size" for record collectors."""

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
            "github_queries": [],
            "appstore_terms": [words[0]],
            "trait_dims": [{"name": "engagement", "description": "0 is a bystander, 1 is a daily user"}],
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
    if "github" in sources:
        for q in plan.get("github_queries", [])[:2]:
            jobs.append((f"github '{q}'", lambda q=q: github.search(q)))
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


def mock_traits(rng: random.Random, keys: list[str]) -> dict[str, Any]:
    """Offline stand-in: traits that move together through one hidden factor, so structure can be recovered."""
    factor = rng.gauss(0, 1)
    return {k: {"score": round(min(1.0, max(0.0, 0.5 + (0.28 if i % 2 == 0 else -0.22) * factor + rng.gauss(0, 0.12))), 2),
                "basis": rng.choice(["stated", "inferred", "inferred"])} for i, k in enumerate(keys)}


def label_voices(brain: Brain, idea: str, plan: dict[str, Any], voices: list[Voice], workers: int = 8) -> list[Voice]:
    """Tag each voice with segment, relevance, pain and stance. Drops irrelevant ones."""
    segments = [s["name"] for s in plan["segments"]]
    defs = T.definitions(plan)
    trait_help = "\n".join(f"- {k}: {d}" for k, d in defs.items())

    def label_batch(batch: list[Voice]) -> list[dict[str, Any]]:
        listing = "\n".join(fenced(v, 500) for v in batch)
        prompt = f"""Label real online posts for a demand study of this idea.

IDEA: {idea}
SEGMENTS: {json.dumps(segments)}

POSTS:
{listing}

For EVERY post return one item:
{{"labels": [{{"id": "post id", "segment": "one of SEGMENTS", "relevance": 0-3,
  "pain": "none|low|medium|high", "stance": "positive|neutral|skeptical|negative",
  "pays_for_tools": "yes|no|unknown",
  "traits": {{"trait_name": {{"score": 0.0 to 1.0, "basis": "stated|inferred"}}}}}}]}}
relevance 0 means the author is not part of this audience at all.
stance is the author's attitude toward solutions like this idea, judged only from what they wrote.
traits: score the AUTHOR from 0 (low) to 1 (high) on EVERY trait below, for every post.
basis is "stated" when the post itself shows the trait, and "inferred" when you are estimating it from
the rest of what they wrote. Be honest about which: do not mark a guess as stated.
{trait_help}"""

        def mock() -> dict[str, Any]:
            out = []
            for v in batch:
                rng = random.Random(seed_from("label", v.id))
                out.append({
                    "id": v.id, "segment": rng.choice(segments), "relevance": rng.choice([0, 1, 2, 2, 3, 3]),
                    "pain": rng.choice(PAIN), "stance": rng.choices(STANCES, [2, 3, 3, 2])[0],
                    "pays_for_tools": rng.choice(["yes", "no", "unknown"]),
                    "traits": mock_traits(rng, list(defs)),
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
        scores, stated = T.clean(lab.get("traits"), list(defs))
        v.labels = {
            "segment": seg, "relevance": relevance,
            "pain": lab.get("pain") if lab.get("pain") in PAIN else "low",
            "stance": lab.get("stance") if lab.get("stance") in STANCES else "neutral",
            "pays_for_tools": lab.get("pays_for_tools", "unknown"),
            "traits": scores, "stated": stated,
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
    model: dict[str, Any] | None = None,
    pins: dict[str, float] | None = None,
) -> list[Persona]:
    """Each persona gets a trait profile sampled from the measured trait model and the real posts nearest to it."""
    model = model or T.measure(voices, plan)
    ds = model["dims"]
    mix = population_mix(voices, plan)
    seg_counts = allocate(n_agents, {s: m["share"] for s, m in mix.items()})
    seg_desc = {s["name"]: s.get("description", "") for s in plan["segments"]}
    defs = T.definitions(plan)
    jobs = []
    for seg, count in seg_counts.items():
        stance_counts = allocate(count, {st: mix[seg][st] for st in STANCES}) or allocate(count, {st: 1 for st in STANCES})
        stance_list = [st for st, c in stance_counts.items() for _ in range(c)]
        random.Random(seed_from(seed, seg)).shuffle(stance_list)
        group = [v for v in voices if v.labels.get("segment") == seg] or voices
        pool = [(v, T.vector(v.labels, ds)) for v in group]
        profiles = T.sample(model, seg, stance_list, random.Random(seed_from(seed, seg, "traits")), pins)
        slots = [{"stance": st, "traits": pr, "posts": T.closest(pool, pr, st, ds)} for st, pr in zip(stance_list, profiles)]
        for bi, batch in enumerate(chunks(slots, batch_size)):
            jobs.append((seg, seg_desc.get(seg, ""), batch, bi))

    def design(job: tuple[str, str, list[dict[str, Any]], int]) -> list[dict[str, Any]]:
        seg, desc, slots, bi = job
        shown: dict[str, Voice] = {}
        for slot in slots:
            for v in slot["posts"]:
                shown[v.id] = v
        evidence = "\n".join(fenced(v, 400) for v in shown.values()) or "(no real posts available)"
        spec = json.dumps([{"slot": i, "stance": sl["stance"], "traits": sl["traits"],
                            "posts": [v.id for v in sl["posts"]]} for i, sl in enumerate(slots)])
        trait_help = "\n".join(f"- {k}: {d}" for k, d in defs.items())
        prompt = f"""Write {len(slots)} distinct, realistic people from the segment "{seg}" ({desc}).
They will later react to this product idea, but write them WITHOUT reference to the idea's merits.

IDEA CONTEXT: {idea}

Each person is a SLOT with a FIXED profile. Traits run from 0 (low) to 1 (high):
{trait_help}
Write each person so they fit their profile and stance exactly. Never contradict a trait value.

SLOTS (stance, traits, and the real posts closest to that profile):
{spec}

REAL POSTS (the only evidence you may build on):
{evidence}

Rules:
- Build each person from one to three of THEIR slot's posts; cite those ids in source_ids.
- Copy needs, frustrations, tools, vocabulary and writing style from the posts. Do not invent enthusiasm.
- Vary age and job. Most people are busy and only mildly interested.

Return JSON: {{"personas": [{{"slot": 0, "handle": "reddit-style username", "occupation": "", "age_range": "e.g. 25-34",
  "bio": "two sentences", "needs": [""], "frustrations": [""], "current_tools": [""],
  "writing_style": "how they write online", "source_ids": ["ids from this slot's posts"]}}]}}"""

        def mock() -> dict[str, Any]:
            out = []
            for i, sl in enumerate(slots):
                rng = random.Random(seed_from(seed, seg, bi, i))
                src = [v.id for v in sl["posts"][:2]]
                out.append({
                    "slot": i,
                    "handle": f"{seg.replace(' ', '_')}_{bi}_{i}_{rng.randint(10, 99)}",
                    "occupation": rng.choice(["teacher", "engineer", "nurse", "student", "designer", "retail manager"]),
                    "age_range": rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"]),
                    "bio": f"A {sl['stance']} member of {seg} who {rng.choice(['collects', 'tinkers', 'browses', 'rarely engages'])}.",
                    "needs": [rng.choice(["save time", "save money", "keep track", "share with friends"])],
                    "frustrations": [rng.choice(["clunky apps", "subscriptions", "lost data", "too many tools"])],
                    "current_tools": [rng.choice(["spreadsheet", "notes app", "nothing", "a competitor app"])],
                    "writing_style": rng.choice(["terse", "chatty", "sarcastic", "detailed"]),
                    "source_ids": src,
                })
            return {"personas": out}

        reply = brain.run(Task("design", prompt, mock, validate=lambda v: isinstance(v, dict) and "personas" in v))
        rows = []
        for pos, row in enumerate(p for p in reply["personas"] if isinstance(p, dict)):
            try:
                idx = int(row.get("slot", pos))
            except (TypeError, ValueError):
                idx = pos
            if not 0 <= idx < len(slots) or any(r.get("_slot") == idx for r in rows):
                continue
            slot = slots[idx]
            allowed = {v.id for v in slot["posts"]}
            row.update(segment=seg, stance=slot["stance"], traits=slot["traits"], _slot=idx,
                       budget_sensitivity=T.label_level(slot["traits"].get("budget_sensitivity", 0.5)),
                       tech_savvy=T.label_level(slot["traits"].get("tech_savvy", 0.5)),
                       source_ids=[x for x in row.get("source_ids", []) if x in allowed])
            rows.append(row)
        return rows

    results = parallel_map(design, jobs, workers=workers, label="designing personas")
    personas = []
    for row in (r for batch in results for r in batch):
        row.pop("_slot", None)
        row.pop("slot", None)
        row["id"] = f"p{len(personas) + 1:03d}"
        row.setdefault("handle", row["id"])
        row.setdefault("bio", "")
        for key in ("needs", "frustrations", "current_tools", "source_ids"):
            if not isinstance(row.get(key), list):
                row[key] = [str(row[key])] if row.get(key) else []
        personas.append(Persona.from_dict(row))
    log(f"  designed {len(personas)} personas, {sum(p.grounded for p in personas)} grounded in real posts")
    return personas
