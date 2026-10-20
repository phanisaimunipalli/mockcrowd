"""validate(): the whole run, from idea to verdict."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__, personas as P, report as R, sim as S, store
from .brains import Brain
from .sources import Voice, dedupe, files
from .util import log

ALL_SOURCES = ["reddit", "hn", "bluesky", "appstore"]
# Apple's public review feed returned no entries when tested (2026-10-19), so appstore is opt-in.
DEFAULT_SOURCES = ["reddit", "hn", "bluesky"]


@dataclass
class Config:
    agents: int = 500
    rounds: int = 2
    thread_size: int = 20
    batch_size: int = 25
    workers: int = 8
    seed: int = 0
    price: str | None = None
    audience: str | None = None
    community: str | None = None
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    voice_files: list[str] = field(default_factory=list)
    questions: list[S.Question] = field(default_factory=list)
    control: bool = True
    max_voices: int = 600


def latest_backtest_accuracy() -> float | None:
    rows = [r for r in store.read_jsonl("evals/history.jsonl") if "backtest_accuracy" in r.get("metrics", {})]
    return rows[-1]["metrics"]["backtest_accuracy"] if rows else None


def validate(idea: str, brain: Brain, cfg: Config, out_dir: Path | None = None, save: bool = True) -> dict[str, Any]:
    started = time.time()
    run_id = store.new_run_id(idea)
    log(f"mockcrowd {__version__} | run {run_id} | brain {brain.describe()} | {cfg.agents} agents")

    log("1/6 planning the audience")
    plan = P.plan_audience(brain, idea, cfg.audience)

    log("2/6 collecting real voices")
    errors: list[str] = []
    voices: list[Voice] = []
    for path in cfg.voice_files:
        voices += files.load(path)
    if cfg.sources:
        voices += P.collect_voices(plan, cfg.sources, errors=errors)
    voices = dedupe(voices)[: cfg.max_voices]
    if voices:
        voices = P.label_voices(brain, idea, plan, voices, workers=cfg.workers)
    if not voices:
        log("  warning: no real voices; personas will be ungrounded and confidence will be low")

    log("3/6 designing personas")
    crowd = P.design_personas(brain, idea, plan, voices, cfg.agents, cfg.batch_size, cfg.workers, cfg.seed)
    by_id = {p.id: p for p in crowd}

    questions = S.default_questions(cfg.price) + cfg.questions
    log("4/6 blind vote (each persona alone, real idea vs a bland control)")
    placebo = S.placebo_pitch(brain, idea) if cfg.control else None
    blind = S.blind_vote(brain, crowd, idea, placebo, questions, cfg.batch_size, cfg.workers, cfg.seed)

    log("5/6 discussion")
    community = cfg.community or (plan.get("subreddits") or ["r/startups"])[0]
    threads = S.make_threads(crowd, idea, community, cfg.thread_size, cfg.seed)
    S.discuss(brain, threads, by_id, cfg.rounds, cfg.workers, cfg.seed)
    final = S.final_vote(brain, threads, by_id, idea, questions, cfg.rounds, cfg.workers, cfg.seed)

    log("6/6 writing the report")
    s_blind = R.summarize(blind, "idea", questions, cfg.seed)
    s_final = R.summarize(final, "idea", questions, cfg.seed)
    s_control = R.summarize(blind, "control", questions, cfg.seed) if placebo else None
    lift = round(s_blind["would_pay"]["p"] - s_control["would_pay"]["p"], 3) if s_control else None
    communities = len({v.community for v in voices if v.community})
    all_comments = [c for t in threads for c in t.comments]
    top = sorted(all_comments, key=lambda c: c.score, reverse=True)[:8]
    custom_keys = [q.key for q in cfg.questions]
    rep = {
        "verdict": R.verdict(s_final["would_pay"]["p"], lift),
        "demand_score": R.demand_score(s_final, s_control),
        "blind": s_blind,
        "final": s_final,
        "control": s_control,
        "lift": lift,
        "shift": round(s_final["would_pay"]["p"] - s_blind["would_pay"]["p"], 3),
        "segments": R.by_segment(final, crowd, "idea", "would_pay"),
        "themes": R.objection_themes(brain, idea, final),
        "confidence": R.confidence(crowd, len(voices), communities, s_final["would_pay"], latest_backtest_accuracy()),
        "voices_used": len(voices),
        "communities": communities,
        "custom": {k: s_final.get(k) for k in custom_keys if k in s_final},
        "top_comments": [{"handle": c.handle, "score": c.score, "text": c.text} for c in top],
        "source_errors": errors,
        "seconds": round(time.time() - started, 1),
        "llm_calls": brain.calls,
        "llm_cost_usd": round(brain.cost_usd, 4) if brain.cost_usd else None,
    }
    run = {
        "id": run_id,
        "version": __version__,
        "idea": idea,
        "brain": brain.describe(),
        "config": {k: v for k, v in cfg.__dict__.items() if k != "questions"} | {"questions": [q.__dict__ for q in questions]},
        "plan": plan,
        "placebo": placebo,
        "voices": [v.to_dict() for v in voices],
        "personas": [p.to_dict() for p in crowd],
        "answers": {"blind": blind, "final": final},
        "threads": [t.to_dict() for t in threads],
        "report": rep,
    }
    if save:
        path = store.save_run(run, R.render_markdown(run), out_dir)
        run["path"] = str(path)
        cost = (f", ${brain.cost_usd:.2f} at list price (on a subscription plan this uses your usage "
                f"limits, it is not billed)") if brain.cost_usd else ""
        log(f"done in {rep['seconds']}s with {brain.calls} LLM calls{cost}. Report: {path / 'report.md'}")
    return run
