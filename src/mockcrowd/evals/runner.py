"""`mockcrowd eval`: run the suite, append to history, and gate regressions."""

from __future__ import annotations

import json
import time
from importlib import resources
from typing import Any

from .. import __version__, store
from ..brains import Brain
from ..pipeline import DEFAULT_SOURCES, Config, validate
from ..util import log
from . import metrics as M

SUITES = ("quick", "full", "backtest")
TOLERANCE = 0.05
QUICK_IDEA = "An app that scans your vinyl records with the phone camera to catalog your collection and track prices."


def builtin_cases() -> list[dict[str, Any]]:
    text = resources.files("mockcrowd.data").joinpath("backtest_cases.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def user_cases() -> list[dict[str, Any]]:
    """Outcomes users recorded with `mockcrowd outcome`: the strongest signal there is."""
    return [
        {"id": f"user:{o['run_id']}", "demand": o["demand"], "pitch": o["idea"], "audience": o.get("audience"),
         "outcome": o.get("note", ""), "source": o.get("evidence", "")}
        for o in store.read_jsonl("outcomes.jsonl")
    ]


def auc(scores: list[tuple[float, str]]) -> float | None:
    hits = [s for s, d in scores if d == "high"]
    flops = [s for s, d in scores if d == "low"]
    if not hits or not flops:
        return None
    wins = sum((h > f) + 0.5 * (h == f) for h in hits for f in flops)
    return round(wins / (len(hits) * len(flops)), 3)


def backtest(brain: Brain, agents: int = 40, threshold: float = 0.10, live_sources: bool = False, limit: int | None = None) -> dict[str, Any]:
    cases = (builtin_cases() + user_cases())[:limit]
    rows = []
    for i, case in enumerate(cases, 1):
        log(f"backtest {i}/{len(cases)}: {case['id']} (truth: {case['demand']})")
        cfg = Config(agents=agents, rounds=1, audience=case.get("audience"), seed=i,
                     sources=list(DEFAULT_SOURCES) if live_sources else [])
        run = validate(case["pitch"], brain, cfg, save=False)
        score = run["report"]["demand_score"]
        rows.append({"id": case["id"], "truth": case["demand"], "score": score,
                     "predicted": "high" if score >= threshold else "low"})
    graded = [r for r in rows if r["truth"] in ("high", "low")]
    accuracy = round(sum(r["predicted"] == r["truth"] for r in graded) / len(graded), 3) if graded else None
    return {"cases": rows, "accuracy": accuracy, "auc": auc([(r["score"], r["truth"]) for r in rows]),
            "leakage": M.leakage(brain, cases), "threshold": threshold}


def run_suite(brain: Brain, suite: str = "quick", agents: int | None = None, idea: str | None = None) -> dict[str, Any]:
    if suite not in SUITES:
        raise ValueError(f"suite must be one of {SUITES}")
    started = time.time()
    result: dict[str, Any] = {"suite": suite, "version": __version__, "brain": brain.describe(),
                              "date": time.strftime("%Y-%m-%d %H:%M:%S"), "metrics": {}}
    if suite in ("quick", "full"):
        cfg = Config(agents=agents or (60 if suite == "quick" else 200), rounds=1 if suite == "quick" else 2)
        run = validate(idea or QUICK_IDEA, brain, cfg, save=False)
        result["metrics"].update(M.run_metrics(run))
        if suite == "full":
            result["metrics"]["stability"] = M.stability(brain, run)
            real = M.realism(brain, run)
            if real is not None:
                result["metrics"]["realism"] = real
    if suite in ("full", "backtest"):
        bt = backtest(brain, agents=agents or 40)
        result["backtest"] = bt
        if bt["accuracy"] is not None:
            result["metrics"]["backtest_accuracy"] = bt["accuracy"]
        if bt["auc"] is not None:
            result["metrics"]["backtest_auc"] = bt["auc"]
        result["metrics"]["leakage"] = bt["leakage"]
    result["seconds"] = round(time.time() - started, 1)
    return result


def gate(result: dict[str, Any], history: list[dict[str, Any]]) -> list[str]:
    """Regressions against the best previous result for the same suite and brain."""
    prior = [h for h in history if h["suite"] == result["suite"] and h["brain"] == result["brain"]]
    failures = []
    for key, value in result["metrics"].items():
        past = [h["metrics"][key] for h in prior if key in h.get("metrics", {})]
        if not past:
            continue
        if key in M.LOWER_IS_BETTER:
            best = min(past)
            if value > best + TOLERANCE:
                failures.append(f"{key} rose to {value} (best {best})")
        else:
            best = max(past)
            if value < best - TOLERANCE:
                failures.append(f"{key} fell to {value} (best {best})")
    return failures


def record(result: dict[str, Any]) -> None:
    store.append_jsonl("evals/history.jsonl", {k: v for k, v in result.items() if k != "backtest"}
                       | {"backtest_cases": result.get("backtest", {}).get("cases")})


def history() -> list[dict[str, Any]]:
    return store.read_jsonl("evals/history.jsonl")
