import asyncio

import pytest

pytest.importorskip("mcp")

from mockcrowd import mcp_server as M  # noqa: E402


def test_tools_are_listed():
    names = {t.name for t in asyncio.run(M.server.list_tools())}
    assert names == {"validate_idea", "design_personas", "get_report", "list_runs", "record_outcome", "list_brains"}


def test_validate_report_and_outcome_round_trip():
    out = asyncio.run(M.validate_idea("A vinyl scanner app", price="$3.99/month", agents=10, sources=[], brain="mock"))
    assert out["verdict"] and 0 <= out["would_pay"]["after_discussion"] <= 1
    assert "mockcrowd verdict" in M.get_report(out["run_id"])
    assert any(r["id"] == out["run_id"] for r in M.list_runs())
    assert "recorded" in M.record_outcome(out["run_id"], "low", note="no signups")


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        M.get_report("../../etc/passwd")
    with pytest.raises(ValueError):
        asyncio.run(M.validate_idea("idea", agents=5000, brain="mock"))
    with pytest.raises(ValueError):
        asyncio.run(M.validate_idea("idea", sources=["twitter"], brain="mock"))


def test_design_personas_tool():
    out = asyncio.run(M.design_personas("people who forget subscriptions", agents=20, sources=[], brain="mock", pins={"tech savvy": "high"}))
    assert len(out["personas"]) == 20 and "tech_savvy" in out["dims"] and out["pins"] == {"tech_savvy": 0.85}
    assert all(p["traits"]["tech_savvy"] == 0.85 for p in out["personas"])
    with pytest.raises(ValueError):
        asyncio.run(M.design_personas("x", agents=2, brain="mock"))
    with pytest.raises(ValueError):
        asyncio.run(M.design_personas("x", agents=20, sources=[], brain="mock", pins={"nope": "low"}))
