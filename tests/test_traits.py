import random

from mockcrowd import traits as T
from mockcrowd.brains import get_brain
from mockcrowd.cli import main
from mockcrowd import store
from mockcrowd.pipeline import Config, validate
from mockcrowd.report import render_markdown
from mockcrowd.sources import Voice

PLAN = {"segments": [{"name": "a"}, {"name": "b"}], "trait_dims": [{"name": "Collection Size", "description": "0 small, 1 huge"}]}


def voices(n=60, link=0.9, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        z = rng.gauss(0, 1)
        traits = {k: min(1, max(0, 0.5 + 0.25 * z * (1 if j % 2 == 0 else -link) + rng.gauss(0, 0.05)))
                  for j, k in enumerate(T.definitions(PLAN))}
        out.append(Voice(id=f"v{i}", source="file", text="x" * 50,
                         labels={"segment": "a" if i % 2 else "b", "stance": rng.choice(T.STANCE_ORDER), "traits": traits}))
    return out


def test_dims_are_core_then_audience_then_stance():
    ds = T.dims(PLAN)
    assert ds[:6] == list(T.CORE) and ds[6] == "collection_size" and ds[-1] == "stance"
    assert T.audience_dims({"trait_dims": [{"name": "tech savvy"}, {"name": "x"}] * 5}) == [{"key": "x", "description": ""}]


def test_clean_clips_and_drops_junk():
    raw = {"tech_savvy": {"score": 4, "basis": "stated"}, "vendor_trust": "x", "nope": 1, "pain_urgency": -2,
           "budget_sensitivity": {"score": 0.3, "basis": "inferred"}}
    assert T.clean(raw, list(T.CORE)) == ({"tech_savvy": 1.0, "pain_urgency": 0.0, "budget_sensitivity": 0.3}, ["tech_savvy"])


def test_measure_finds_the_links_and_sampling_keeps_them():
    model = T.measure(voices(), PLAN)
    assert model["structured"] and T.structure(model) > 0.4
    rng = random.Random(0)
    stances = [rng.choice(T.STANCE_ORDER) for _ in range(300)]
    ds = model["dims"]
    rows = [[T.STANCE_CODE[s] if d == "stance" else t[d] for d in ds] for s, t in zip(stances, T.sample(model, "a", stances, rng))]
    sampled = T.corr_matrix(rows, len(ds))
    target = model["segments"]["a"]["corr"]
    assert T._error(sampled, target) < 0.15


def test_too_few_posts_means_no_invented_structure():
    model = T.measure(voices(n=5), PLAN)
    assert not model["structured"] and T.structure(model) == 0.0
    out = T.sample(model, "a", ["neutral"] * 30, random.Random(0))
    rows = [[t[d] for d in model["dims"] if d != "stance"] for t in out]
    assert abs(T.pearson([r[0] for r in rows], [r[1] for r in rows])) < 0.5


def test_stance_stays_exact_and_traits_follow_it():
    v = voices(n=200)
    for x in v:  # make negative people budget sensitive
        x.labels["traits"]["budget_sensitivity"] = 0.9 if x.labels["stance"] == "negative" else 0.2
    model = T.measure(v, PLAN)
    got = T.sample(model, "a", ["negative"] * 100 + ["positive"] * 100, random.Random(3))
    neg = sum(t["budget_sensitivity"] for t in got[:100]) / 100
    pos = sum(t["budget_sensitivity"] for t in got[100:]) / 100
    assert neg > pos + 0.3


def test_closest_returns_nearest_posts():
    ds = T.dims(PLAN)
    pool = [(x, T.vector(x.labels, ds)) for x in voices()]
    target = {d: 0.9 for d in ds if d != "stance"}
    near = T.closest(pool, target, "neutral", ds, k=3)
    far = T.closest(pool[::-1], {d: 0.1 for d in target}, "neutral", ds, k=3)
    assert len(near) == 3 and {v.id for v in near} != {v.id for v in far}


def test_run_carries_traits_and_exports(voices_file, capsys, tmp_path):
    run = validate("A vinyl catalog app", get_brain("mock"), Config(agents=60, rounds=1, sources=[], voice_files=[str(voices_file)]))
    p = run["personas"][0]
    assert p["traits"] and p["stance"] and run["trait_model"]["structured"]
    assert 0 < run["report"]["traits"]["stated_share"] < 1
    assert run["report"]["traits"]["trait_error"] < run["report"]["traits"]["trait_error_independent"]
    assert "How the crowd's traits connect" in render_markdown(store.load_run(run["id"]))
    assert main(["personas", run["id"], "-o", str(tmp_path / "p.json")]) == 0
    assert (tmp_path / "p.json").stat().st_mode & 0o777 == 0o600


def test_pins_fix_a_trait_and_pull_linked_traits():
    v = voices(n=200)
    model = T.measure(v, PLAN)
    ds = model["dims"]
    free = T.sample(model, "a", ["neutral"] * 200, random.Random(5))
    pinned = T.sample(model, "a", ["neutral"] * 200, random.Random(5), {"tech_savvy": 0.95})
    assert all(p["tech_savvy"] == 0.95 for p in pinned)
    a, b = ds[0], ds[1]  # budget_sensitivity and tech_savvy are linked in the test data
    assert abs(sum(p[a] for p in pinned) / 200 - sum(p[a] for p in free) / 200) > 0.05


def test_pin_parsing_and_checks():
    assert T.parse_level("high") == 0.85 and T.parse_level("0.3") == 0.3
    for bad in ("loud", "2"):
        try:
            T.parse_level(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    T.check_pins({"tech_savvy": 0.5}, T.dims(PLAN))
    try:
        T.check_pins({"nope": 0.5}, T.dims(PLAN))
    except ValueError as exc:
        assert "tech_savvy" in str(exc)
    else:
        raise AssertionError("unknown trait accepted")


def test_design_command_exports_personas_without_votes(voices_file, tmp_path, capsys):
    out = tmp_path / "pop.json"
    assert main(["-q", "design", "vinyl collectors", "--brain", "mock", "--agents", "40", "--no-live",
                 "--voices", str(voices_file), "--pin", "tech_savvy=high", "-o", str(out)]) == 0
    import json as _json

    data = _json.loads(out.read_text())
    assert len(data["personas"]) == 40 and data["pins"] == {"tech_savvy": 0.85}
    assert all(p["traits"]["tech_savvy"] == 0.85 and p["sources"] for p in data["personas"])
    assert data["links"] and out.stat().st_mode & 0o777 == 0o600
    assert not store.list_runs()  # a design is not a run
    assert main(["-q", "design", "x", "--brain", "mock", "--no-live", "--voices", str(voices_file), "--pin", "nope=low"]) == 2
