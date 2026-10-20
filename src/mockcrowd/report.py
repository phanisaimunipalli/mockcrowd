"""Turn votes into a verdict: probabilities, control lift, objection themes, confidence."""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from .brains import Brain, Task
from .personas import Persona
from .sim import Question
from .util import seed_from

# ---------------------------------------------------------------- statistics


def proportion(values: list[bool], seed: int = 0, z: float = 1.96) -> dict[str, float]:
    """Share of True with a Wilson 95% interval, which stays honest at 0% and 100%
    (a bootstrap collapses to 0 to 0 when nobody says yes)."""
    n = len(values)
    if n == 0:
        return {"p": 0.0, "low": 0.0, "high": 0.0, "n": 0}
    p = sum(values) / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"p": round(p, 3), "low": round(max(0.0, center - half), 3),
            "high": round(min(1.0, center + half), 3), "n": n}


def distribution(values: list[str], options: list[str]) -> dict[str, float]:
    n = max(1, len(values))
    counts = Counter(values)
    return {o: round(counts.get(o, 0) / n, 3) for o in options}


def score_index(values: list[str], options: list[str]) -> float:
    """Mean position on an ordered scale, 0 (lowest option) to 1 (highest)."""
    if not values or len(options) < 2:
        return 0.0
    pos = {o: i / (len(options) - 1) for i, o in enumerate(options)}
    return round(sum(pos.get(v, 0) for v in values) / len(values), 3)


def summarize(answers: dict[str, dict[str, Any]], arm: str, questions: list[Question], seed: int = 0) -> dict[str, Any]:
    rows = [a[arm] for a in answers.values() if arm in a]
    out: dict[str, Any] = {"n": len(rows)}
    for q in questions:
        vals = [r.get(q.key) for r in rows]
        if q.kind == "yesno":
            out[q.key] = proportion([bool(v) for v in vals], seed=seed_from(seed, arm, q.key))
        elif q.kind == "score":
            out[q.key] = {"index": score_index(vals, q.options), "distribution": distribution(vals, q.options)}
        elif q.kind == "choice":
            out[q.key] = {"distribution": distribution([v for v in vals if v], q.options)}
    return out


def by_segment(answers: dict[str, dict[str, Any]], personas: list[Persona], arm: str, key: str) -> dict[str, dict[str, Any]]:
    seg = {p.id: p.segment for p in personas}
    groups: dict[str, list[bool]] = {}
    for pid, a in answers.items():
        if arm in a and pid in seg:
            groups.setdefault(seg[pid], []).append(bool(a[arm].get(key)))
    return {s: {"p": round(sum(v) / len(v), 3), "n": len(v)} for s, v in sorted(groups.items())}


# ---------------------------------------------------------------- objections


def objection_themes(brain: Brain, idea: str, answers: dict[str, dict[str, Any]], arm: str = "idea") -> list[dict[str, Any]]:
    items = [(pid, a[arm].get("objection", "")) for pid, a in answers.items() if arm in a and a[arm].get("objection")]
    if not items:
        return []
    listing = "\n".join(f"[{pid}] {text}" for pid, text in items[:500])
    prompt = f"""Group these objections to a product idea into at most 6 themes, biggest first.

IDEA: {idea}
OBJECTIONS:
{listing}

Return JSON: {{"themes": [{{"theme": "short name", "count": number of objections in it,
  "quote": "one representative objection, verbatim", "ids": ["up to 5 ids"]}}]}}"""

    def mock() -> dict[str, Any]:
        counts = Counter(text for _, text in items)
        return {"themes": [{"theme": t, "count": c, "quote": t, "ids": [pid for pid, x in items if x == t][:5]}
                           for t, c in counts.most_common(6)]}

    reply = brain.run(Task("themes", prompt, mock, validate=lambda v: isinstance(v, dict) and "themes" in v))
    themes = [t for t in reply["themes"] if isinstance(t, dict)]
    total = len(items)
    for t in themes:
        try:
            t["share"] = round(int(t.get("count", 0)) / total, 3)
        except (TypeError, ValueError):
            t["share"] = 0.0
    return themes


# ---------------------------------------------------------------- confidence


def confidence(
    personas: list[Persona],
    voices_used: int,
    communities: int,
    pay: dict[str, float],
    backtest_accuracy: float | None,
) -> dict[str, Any]:
    """0 to 100: how much the crowd resembles real people, and how stable the number is."""
    n = max(1, len(personas))
    parts = {
        "grounding": sum(p.grounded for p in personas) / n,
        "evidence": min(1.0, voices_used / 150),
        "source_breadth": min(1.0, communities / 4),
        "precision": max(0.0, 1 - (pay["high"] - pay["low"]) / 0.3),
    }
    weights = {"grounding": 0.3, "evidence": 0.3, "source_breadth": 0.2, "precision": 0.2}
    if backtest_accuracy is not None:
        parts["backtest"] = backtest_accuracy
        weights = {k: v * 0.8 for k, v in weights.items()} | {"backtest": 0.2}
    score = round(100 * sum(parts[k] * weights[k] for k in weights))
    reasons = []
    if parts["grounding"] < 0.8:
        reasons.append(f"only {parts['grounding']:.0%} of personas are built from real posts")
    if voices_used < 150:
        reasons.append(f"{voices_used} real voices collected; 150 or more gives a solid base")
    if communities < 4:
        reasons.append(f"voices come from {communities} {'community' if communities == 1 else 'communities'}; "
                       "4 or more reduces echo chambers")
    if parts["precision"] < 0.6:
        reasons.append("the would-pay estimate has a wide interval; add agents")
    if backtest_accuracy is None:
        reasons.append("no backtest on record yet; run `mockcrowd eval --suite backtest`")
    label = "high" if score >= 75 else "medium" if score >= 50 else "low"
    return {"score": score, "label": label, "parts": {k: round(v, 3) for k, v in parts.items()}, "reasons": reasons}


# ---------------------------------------------------------------- verdict


def verdict(pay_final: float, lift: float | None) -> str:
    """Thresholds are starting points; `mockcrowd eval --suite backtest` reports how well they separate
    known hits from known flops."""
    if lift is not None and lift < 0.05:
        return "No real demand signal: the idea does not beat a bland control"
    if pay_final >= 0.30 and (lift is None or lift >= 0.15):
        return "Strong demand signal"
    if pay_final >= 0.15:
        return "Some demand: worth a cheap real-world test (landing page, waitlist)"
    return "Weak demand: most of the crowd would not pay"


def demand_score(summary_final: dict[str, Any], summary_control: dict[str, Any] | None) -> float:
    """Single number used by backtests: final would-pay share, minus the control's."""
    pay = summary_final["would_pay"]["p"]
    if summary_control:
        return round(pay - summary_control["would_pay"]["p"], 3)
    return pay


# ---------------------------------------------------------------- markdown


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_markdown(run: dict[str, Any]) -> str:
    r = run["report"]
    blind, final, control = r["blind"], r["final"], r.get("control")
    pay_b, pay_f = blind["would_pay"], final["would_pay"]
    conf = r["confidence"]
    lines = [
        f"# mockcrowd verdict: {r['verdict']}",
        "",
        f"**Idea:** {run['idea']}",
        "",
        f"**Crowd:** {len(run['personas'])} personas from {r['voices_used']} real voices across "
        f"{r['communities']} {'community' if r['communities'] == 1 else 'communities'}. "
        f"Brain: {run['brain']}. Run id: `{run['id']}`",
        "",
        "## Headline",
        "",
        "| Measure | Blind (alone) | After discussion |",
        "|---|---|---|",
        f"| Would pay | {_pct(pay_b['p'])} ({_pct(pay_b['low'])} to {_pct(pay_b['high'])}) | "
        f"{_pct(pay_f['p'])} ({_pct(pay_f['low'])} to {_pct(pay_f['high'])}) |",
        f"| Would try free | {_pct(blind['try_free']['p'])} | {_pct(final['try_free']['p'])} |",
        f"| Interest index (0 to 1) | {blind['interest']['index']} | {final['interest']['index']} |",
    ]
    if control:
        lines += [
            "",
            f"**Control check:** a bland same-category pitch got {_pct(control['would_pay']['p'])} would pay. "
            f"Lift of the real idea: **{r['lift']:+.0%}**. "
            + ("A lift under 5 points means the crowd is just being agreeable." if r["lift"] < 0.05 else ""),
        ]
    lines += ["", f"## Confidence: {conf['score']}/100 ({conf['label']})", ""]
    lines += [f"- {k}: {v:.0%}" for k, v in conf["parts"].items()]
    lines += [f"- caveat: {x}" for x in conf["reasons"]]
    lines += ["", "## Who would pay, by segment", "", "| Segment | Would pay | n |", "|---|---|---|"]
    lines += [f"| {s} | {_pct(v['p'])} | {v['n']} |" for s, v in r["segments"].items()]
    if r["themes"]:
        lines += ["", "## Top objections", "", "| Theme | Share | Example |", "|---|---|---|"]
        lines += [f"| {t.get('theme')} | {_pct(t.get('share', 0))} | {str(t.get('quote', '')).replace('|', '/')} |" for t in r["themes"]]
    if r.get("custom"):
        lines += ["", "## Your questions", ""]
        for key, val in r["custom"].items():
            lines.append(f"- **{key}**: {json.dumps(val)}")
    if r.get("top_comments"):
        lines += ["", "## Loudest comments in the discussion", ""]
        lines += [f"- ({c['score']:+d}) u/{c['handle']}: {c['text']}" for c in r["top_comments"]]
    lines += [
        "",
        "## How to read this",
        "",
        "- This is a simulation. It estimates direction and objections, not revenue.",
        "- The strongest proof is real behavior. After you test or launch, record what happened:",
        f"  `mockcrowd outcome {run['id']} --demand high|medium|low --note \"what happened\"`",
        "  Every recorded outcome becomes a backtest case that makes future verdicts more trustworthy.",
    ]
    if r.get("source_errors"):
        lines += ["", "## Source errors", ""] + [f"- {e}" for e in r["source_errors"][:10]]
    return "\n".join(lines) + "\n"
