from mockcrowd import store
from mockcrowd.cli import main


def test_validate_report_outcome_flow(voices_file, capsys, tmp_path):
    code = main(["-q", "validate", "A vinyl catalog app", "--brain", "mock", "--agents", "40", "--rounds", "1",
                 "--no-live", "--voices", str(voices_file)])
    assert code == 0
    assert "mockcrowd verdict" in capsys.readouterr().out
    run_id = store.list_runs()[0]["id"]

    assert main(["-q", "report", run_id, "--json"]) == 0
    assert '"verdict"' in capsys.readouterr().out

    assert main(["-q", "outcome", run_id, "--demand", "low", "--note", "12 signups from 3,000 visits"]) == 0
    outcomes = store.read_jsonl("outcomes.jsonl")
    assert outcomes[0]["demand"] == "low" and outcomes[0]["run_id"] == run_id


def test_user_outcomes_join_the_backtest(voices_file):
    from mockcrowd.evals import runner

    main(["-q", "validate", "A vinyl catalog app", "--brain", "mock", "--agents", "20", "--rounds", "1",
          "--no-live", "--voices", str(voices_file)])
    main(["-q", "outcome", store.list_runs()[0]["id"], "--demand", "high"])
    assert len(runner.user_cases()) == 1


def test_brains_and_install_skill(capsys, tmp_path):
    assert main(["brains"]) == 0
    assert "mock" in capsys.readouterr().out
    assert main(["install-skill", "--dir", str(tmp_path / "skills")]) == 0
    assert (tmp_path / "skills" / "mockcrowd" / "SKILL.md").read_text().startswith("---")


def test_bad_question_is_a_clean_error(capsys):
    assert main(["-q", "validate", "x", "--brain", "mock", "--no-live", "--question", "nope"]) == 2
    assert "bad --question" in capsys.readouterr().err
