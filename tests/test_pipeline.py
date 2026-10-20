import json

from mockcrowd import store
from mockcrowd.brains import get_brain
from mockcrowd.evals import metrics as M
from mockcrowd.evals import runner
from mockcrowd.pipeline import Config, validate
from mockcrowd.report import render_markdown
from mockcrowd.sources import files

IDEA = "An app that scans your vinyl records to catalog your collection and track prices, $3.99/month."


def offline(agents=80, **kw):
    return Config(agents=agents, rounds=2, sources=[], **kw)


def test_end_to_end_offline(voices_file):
    brain = get_brain("mock")
    run = validate(IDEA, brain, offline(voice_files=[str(voices_file)], price="$3.99/month"))
    rep = run["report"]
    assert len(run["personas"]) == 80
    assert rep["voices_used"] > 0
    assert set(rep["blind"]) >= {"n", "interest", "try_free", "would_pay"}
    assert rep["control"] is not None and rep["lift"] is not None
    assert 0 <= rep["confidence"]["score"] <= 100
    assert sum(len(t["members"]) for t in run["threads"]) == 80
    assert any(t["comments"] for t in run["threads"])
    md = render_markdown(run)
    assert "mockcrowd verdict" in md and "Control check" in md
    saved = store.load_run(run["id"])
    assert saved["id"] == run["id"]


def test_personas_are_grounded_and_cite_real_posts(voices_file):
    run = validate(IDEA, get_brain("mock"), offline(voice_files=[str(voices_file)]))
    ids = {v["id"] for v in run["voices"]}
    assert all(set(p["source_ids"]) <= ids for p in run["personas"])
    m = M.run_metrics(run)
    assert m["grounding"] > 0.9
    assert m["citation_valid"] == 1.0
    assert m["mix_fidelity"] > 0.8
    assert 0 < m["diversity"] <= 1


def test_runs_are_deterministic_with_mock_brain(voices_file):
    a = validate(IDEA, get_brain("mock"), offline(voice_files=[str(voices_file)]), save=False)
    b = validate(IDEA, get_brain("mock"), offline(voice_files=[str(voices_file)]), save=False)
    assert a["report"]["final"] == b["report"]["final"]


def test_custom_question_is_reported(voices_file):
    from mockcrowd.sim import parse_question

    cfg = offline(voice_files=[str(voices_file)], questions=[parse_question("choice:first:Which first?:scan|alerts|wishlist")])
    run = validate(IDEA, get_brain("mock"), cfg, save=False)
    dist = run["report"]["custom"]["first"]["distribution"]
    assert set(dist) == {"scan", "alerts", "wishlist"}
    assert abs(sum(dist.values()) - 1) < 0.01


def test_no_voices_still_runs_with_low_confidence():
    run = validate(IDEA, get_brain("mock"), offline(agents=30), save=False)
    assert run["report"]["confidence"]["label"] == "low"
    assert run["report"]["voices_used"] == 0


def test_backtest_and_gate():
    result = runner.run_suite(get_brain("mock"), "backtest", agents=20)
    bt = result["backtest"]
    assert len(bt["cases"]) == len(runner.builtin_cases()) == 13
    assert 0 <= bt["accuracy"] <= 1
    assert bt["leakage"] == 0.0
    runner.record(result)
    worse = json.loads(json.dumps(result))
    worse["metrics"]["backtest_accuracy"] = result["metrics"]["backtest_accuracy"] - 0.2
    assert runner.gate(worse, runner.history())
    assert not runner.gate(result, runner.history())


def test_auc():
    assert runner.auc([(0.5, "high"), (0.1, "low")]) == 1.0
    assert runner.auc([(0.1, "high"), (0.5, "low")]) == 0.0
    assert runner.auc([(0.1, "high")]) is None


def test_voice_file_formats(tmp_path):
    (tmp_path / "a.csv").write_text("text,url\n" + "A long enough post about records and collecting them,x\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("first post about records here\n\nsecond post about records here", encoding="utf-8")
    assert files.load(tmp_path / "a.csv")[0].url == "x"
    assert len(files.load(tmp_path / "b.txt")) == 2
