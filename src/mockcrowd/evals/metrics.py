"""Metrics computed from a finished run, plus the brain-judged ones."""

from __future__ import annotations

import itertools
import random
import re
from collections import Counter
from typing import Any

from ..brains import Brain, Task
from ..personas import STANCES, Persona
from ..sim import blind_vote, default_questions
from ..util import chunks, seed_from

LOWER_IS_BETTER = {"agreeableness", "persuasion_drift", "leakage"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']{3,}", text.lower()))


def run_metrics(run: dict[str, Any]) -> dict[str, float]:
    personas = [Persona.from_dict(p) for p in run["personas"]]
    voices = run["voices"]
    n = max(1, len(personas))
    voice_ids = {v["id"] for v in voices}
    cited = [s for p in personas for s in p.source_ids]
    metrics: dict[str, float] = {
        "grounding": round(sum(p.grounded for p in personas) / n, 3),
        "citation_valid": round(sum(s in voice_ids for s in cited) / len(cited), 3) if cited else 0.0,
        "mix_fidelity": mix_fidelity(voices, personas),
        "diversity": diversity(personas, seed=run["config"].get("seed", 0)),
    }
    rep = run["report"]
    if rep.get("control"):
        metrics["control_lift"] = rep["lift"]
        metrics["agreeableness"] = rep["control"]["would_pay"]["p"]
    metrics["persuasion_drift"] = round(abs(rep["shift"]), 3)
    return metrics


def mix_fidelity(voices: list[dict[str, Any]], personas: list[Persona]) -> float:
    real = Counter(v.get("labels", {}).get("stance") for v in voices if v.get("labels"))
    sim = Counter(p.stance for p in personas)
    if not real or not sim:
        return 0.0
    rt, st = sum(real.values()), sum(sim.values())
    tvd = 0.5 * sum(abs(real.get(s, 0) / rt - sim.get(s, 0) / st) for s in STANCES)
    return round(1 - tvd, 3)


def diversity(personas: list[Persona], seed: int = 0, pairs: int = 400) -> float:
    if len(personas) < 2:
        return 0.0
    rng = random.Random(seed_from(seed, "diversity"))
    all_pairs = list(itertools.combinations(range(len(personas)), 2))
    sample = rng.sample(all_pairs, min(pairs, len(all_pairs)))
    sims = []
    for i, j in sample:
        a = _words(f"{personas[i].bio} {personas[i].occupation} {' '.join(personas[i].needs)}")
        b = _words(f"{personas[j].bio} {personas[j].occupation} {' '.join(personas[j].needs)}")
        sims.append(len(a & b) / len(a | b) if a | b else 1.0)
    return round(1 - sum(sims) / len(sims), 3)


# ---------------------------------------------------------------- brain-judged


def realism(brain: Brain, run: dict[str, Any], pairs: int = 30) -> float | None:
    """A judge sees a real post and a simulated comment and must say which is real."""
    real = [v["text"] for v in run["voices"] if len(v["text"]) < 400]
    fake = [c["text"] for t in run["threads"] for c in t["comments"]]
    if not real or not fake:
        return None
    rng = random.Random(seed_from(run["id"], "realism"))
    items = []
    for i in range(min(pairs, len(real), len(fake))):
        real_first = rng.random() < 0.5
        r, f = rng.choice(real), rng.choice(fake)
        items.append({"id": f"q{i}", "a": r if real_first else f, "b": f if real_first else r, "real": "a" if real_first else "b"})
    correct = 0
    for batch in chunks(items, 15):
        listing = "\n".join(f"[{it['id']}] A: {it['a']}\n      B: {it['b']}" for it in batch)
        prompt = f"""Each pair has one real post written by a human on social media and one written by an AI
playing a persona. For each pair, say which one is the real human post.

{listing}

Return JSON: {{"picks": [{{"id": "q0", "real": "a or b"}}]}}"""

        def mock(batch=batch) -> dict[str, Any]:
            r = random.Random(seed_from("realism-mock", batch[0]["id"]))
            return {"picks": [{"id": it["id"], "real": r.choice("ab")} for it in batch]}

        reply = brain.run(Task("realism", prompt, mock, validate=lambda v: isinstance(v, dict) and "picks" in v))
        picks = {p.get("id"): str(p.get("real", "")).lower() for p in reply["picks"] if isinstance(p, dict)}
        correct += sum(picks.get(it["id"]) == it["real"] for it in batch)
    accuracy = correct / len(items)
    return round(1 - (max(accuracy, 0.5) - 0.5) * 2, 3)


def stability(brain: Brain, run: dict[str, Any], sample: int = 50) -> float:
    """Re-ask a sample of personas, with a new seed, and compare would-pay shares."""
    personas = [Persona.from_dict(p) for p in run["personas"]]
    rng = random.Random(seed_from(run["id"], "stability"))
    chosen = rng.sample(personas, min(sample, len(personas)))
    cfg = run["config"]
    questions = default_questions(cfg.get("price"))
    again = blind_vote(brain, chosen, run["idea"], None, questions, cfg.get("batch_size", 25), cfg.get("workers", 8),
                       seed=cfg.get("seed", 0) + 1)
    first = run["answers"]["blind"]
    ids = [p.id for p in chosen if p.id in again and p.id in first]
    if not ids:
        return 0.0
    p1 = sum(bool(first[i]["idea"]["would_pay"]) for i in ids) / len(ids)
    p2 = sum(bool(again[i]["idea"]["would_pay"]) for i in ids) / len(ids)
    return round(1 - abs(p1 - p2), 3)


def leakage(brain: Brain, cases: list[dict[str, Any]]) -> float:
    """Share of anonymized backtest pitches the brain recognizes. High leakage means the
    backtest partly measures memory of history, not simulation skill."""
    if not cases:
        return 0.0
    listing = "\n".join(f"[{c['id']}] {c['pitch']}" for c in cases)
    prompt = f"""For each product pitch, name the real product or company it describes, if you recognize it.
Use null if you do not.

{listing}

Return JSON: {{"guesses": [{{"id": "case id", "guess": "name or null"}}]}}"""

    def mock() -> dict[str, Any]:
        return {"guesses": [{"id": c["id"], "guess": None} for c in cases]}

    reply = brain.run(Task("leakage", prompt, mock, validate=lambda v: isinstance(v, dict) and "guesses" in v))
    guesses = {g.get("id"): str(g.get("guess") or "").lower() for g in reply["guesses"] if isinstance(g, dict)}
    hits = 0
    for c in cases:
        name = c.get("outcome", "").split(":")[0].lower().strip()
        guess = guesses.get(c["id"], "")
        if guess and guess not in ("none", "null") and name and (name.split()[0] in guess or guess in name):
            hits += 1
    return round(hits / len(cases), 3)
