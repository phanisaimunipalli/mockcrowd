"""Command line interface: `mockcrowd validate "your idea"` and friends."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from importlib import resources
from pathlib import Path

from . import __version__, store
from .brains import BRAIN_NAMES, BrainError, available_brains, get_brain
from .pipeline import ALL_SOURCES, DEFAULT_SOURCES, Config, validate
from .report import render_markdown
from .sim import parse_question
from .util import set_quiet


def _brain_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--brain", default="auto", choices=BRAIN_NAMES,
                   help="which AI runs the crowd (default: first installed of claude, codex, code-puppy, openai, ollama)")
    p.add_argument("--model", help="model name passed to the brain, exactly as given")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mockcrowd", description="Validate product demand before you build.")
    parser.add_argument("--version", action="version", version=f"mockcrowd {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="no progress output")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="run a crowd on a product idea")
    v.add_argument("idea", help="the product idea, as you would pitch it")
    v.add_argument("--price", help='price to test, for example "$4.99/month"')
    v.add_argument("--audience", help="who it is for, if you already know")
    v.add_argument("--agents", type=int, default=500, help="crowd size (default 500)")
    v.add_argument("--rounds", type=int, default=2, help="discussion rounds (default 2)")
    v.add_argument("--source", action="append", dest="sources", choices=ALL_SOURCES,
                   help="live sources to search (repeatable; default all)")
    v.add_argument("--no-live", action="store_true", help="do not search the web; use only --voices files")
    v.add_argument("--voices", action="append", default=[], help="JSONL, CSV or text file of real posts (repeatable)")
    v.add_argument("--community", help='where the discussion is set, for example "r/vinyl"')
    v.add_argument("--question", action="append", default=[],
                   help='extra typed question, kind:key:text[:opt1|opt2], for example "choice:first:Which first?:scan|alerts"')
    v.add_argument("--no-control", action="store_true", help="skip the bland control pitch (not recommended)")
    v.add_argument("--workers", type=int, default=8, help="parallel LLM calls (default 8)")
    v.add_argument("--seed", type=int, default=0)
    v.add_argument("--out", help="directory for run.json and report.md (default ~/.mockcrowd/runs/<id>)")
    v.add_argument("--json", action="store_true", help="print the report as JSON instead of markdown")
    _brain_args(v)

    c = sub.add_parser("collect", help="only gather and save real voices for an idea")
    c.add_argument("idea")
    c.add_argument("-o", "--output", default="voices.jsonl")
    c.add_argument("--audience")
    c.add_argument("--source", action="append", dest="sources", choices=ALL_SOURCES)
    _brain_args(c)

    r = sub.add_parser("report", help="print the report of a past run")
    r.add_argument("run_id")
    r.add_argument("--json", action="store_true")

    sub.add_parser("runs", help="list past runs")

    o = sub.add_parser("outcome", help="record what really happened after a run (feeds the backtest)")
    o.add_argument("run_id")
    o.add_argument("--demand", required=True, choices=["high", "medium", "low"])
    o.add_argument("--note", default="", help="what happened, for example '40 signups from 2,000 visits'")
    o.add_argument("--evidence", default="", help="link to proof")

    e = sub.add_parser("eval", help="measure how real the crowd is and catch regressions")
    e.add_argument("--suite", default="quick", choices=["quick", "full", "backtest"])
    e.add_argument("--agents", type=int)
    e.add_argument("--gate", action="store_true", help="exit 1 if any metric regressed versus the best previous run")
    e.add_argument("--no-record", action="store_true", help="do not append to eval history")
    _brain_args(e)

    sub.add_parser("brains", help="show which brains are available")

    s = sub.add_parser("install-skill", help="install the agent skill so you can ask your coding agent")
    s.add_argument("--dir", help="skills directory (default ~/.claude/skills)")
    return parser


def cmd_validate(args: argparse.Namespace) -> int:
    brain = get_brain(args.brain, args.model)
    cfg = Config(
        agents=args.agents, rounds=args.rounds, workers=args.workers, seed=args.seed,
        price=args.price, audience=args.audience, community=args.community,
        sources=[] if args.no_live else (args.sources or list(DEFAULT_SOURCES)),
        voice_files=args.voices, questions=[parse_question(q) for q in args.question],
        control=not args.no_control,
    )
    run = validate(args.idea, brain, cfg, out_dir=Path(args.out) if args.out else None)
    print(json.dumps(run["report"], indent=2) if args.json else render_markdown(run))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from .personas import collect_voices, plan_audience
    from .sources import files

    brain = get_brain(args.brain, args.model)
    plan = plan_audience(brain, args.idea, args.audience)
    errors: list[str] = []
    voices = collect_voices(plan, args.sources or list(DEFAULT_SOURCES), errors=errors)
    files.save(voices, args.output)
    print(f"saved {len(voices)} voices to {args.output}")
    for err in errors:
        print(f"  source error: {err}", file=sys.stderr)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run = store.load_run(args.run_id)
    print(json.dumps(run["report"], indent=2) if args.json else render_markdown(run))
    return 0


def cmd_runs(_: argparse.Namespace) -> int:
    runs = store.list_runs()
    if not runs:
        print("no runs yet")
    for r in runs:
        print(f"{r['id']}  {r['verdict']}\n    {r['idea'][:100]}")
    return 0


def cmd_outcome(args: argparse.Namespace) -> int:
    run = store.load_run(args.run_id)
    row = {"run_id": run["id"], "idea": run["idea"], "audience": run["config"].get("audience"),
           "predicted": run["report"]["verdict"], "demand_score": run["report"]["demand_score"],
           "demand": args.demand, "note": args.note, "evidence": args.evidence,
           "date": time.strftime("%Y-%m-%d")}
    path = store.append_jsonl("outcomes.jsonl", row)
    print(f"recorded. It is now a backtest case ({path}). Run `mockcrowd eval --suite backtest` to re-score.")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from .evals import runner

    brain = get_brain(args.brain, args.model)
    result = runner.run_suite(brain, args.suite, args.agents)
    failures = runner.gate(result, runner.history()) if args.gate else []
    if not args.no_record:
        runner.record(result)
    print(json.dumps({k: v for k, v in result.items() if k != "backtest"}, indent=2))
    if result.get("backtest"):
        print("\nbacktest:")
        for row in result["backtest"]["cases"]:
            mark = "ok " if row["predicted"] == row["truth"] else "MISS"
            print(f"  {mark} {row['id']:<32} truth {row['truth']:<5} score {row['score']:+.3f}")
    if failures:
        print("\nREGRESSIONS:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


def cmd_brains(_: argparse.Namespace) -> int:
    for name, ok in available_brains().items():
        print(f"  {'yes' if ok else 'no ':<4} {name}")
    return 0


def cmd_install_skill(args: argparse.Namespace) -> int:
    target = Path(args.dir).expanduser() if args.dir else Path.home() / ".claude" / "skills"
    dest = target / "mockcrowd" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with resources.as_file(resources.files("mockcrowd.skill").joinpath("SKILL.md")) as src:
        shutil.copyfile(src, dest)
    print(f"installed {dest}")
    return 0


COMMANDS = {
    "validate": cmd_validate, "collect": cmd_collect, "report": cmd_report, "runs": cmd_runs,
    "outcome": cmd_outcome, "eval": cmd_eval, "brains": cmd_brains, "install-skill": cmd_install_skill,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    set_quiet(args.quiet)
    try:
        return COMMANDS[args.command](args)
    except (BrainError, FileNotFoundError, ValueError) as exc:
        print(f"mockcrowd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
