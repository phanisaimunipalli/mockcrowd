"""Trait model: how a crowd's traits relate, measured on real posts and sampled to design personas."""

from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Any

from .sources import Voice
from .util import seed_from, slugify

CORE = {
    "budget_sensitivity": "how much price and subscription cost drive their decisions",
    "tech_savvy": "comfort with technical tools and workarounds",
    "status_quo_attachment": "how happy they are with what they use today",
    "switching_cost": "how much effort or risk it takes them to change tools",
    "vendor_trust": "how much they trust companies and new products",
    "pain_urgency": "how badly the problem hurts them today",
}
STANCE_ORDER = ["negative", "skeptical", "neutral", "positive"]
STANCE_CODE = {s: i / 3 for i, s in enumerate(STANCE_ORDER)}
MAX_AUDIENCE_DIMS = 4
MIN_FIT = 8  # labeled posts needed before a correlation is trusted
SHRINK = 20  # segment posts that weigh as much as the pooled prior
RIDGE = 0.1  # pulls every matrix toward "no relation", so weak evidence cannot invent structure
ND = NormalDist()


def audience_dims(plan: dict[str, Any]) -> list[dict[str, str]]:
    seen = set(CORE) | {"stance"}
    out = []
    for item in plan.get("trait_dims") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        key = slugify(str(item["name"]), 30).replace("-", "_")
        if key not in seen:
            seen.add(key)
            out.append({"key": key, "description": str(item.get("description", ""))[:120]})
    return out[:MAX_AUDIENCE_DIMS]


def definitions(plan: dict[str, Any]) -> dict[str, str]:
    return CORE | {d["key"]: d["description"] for d in audience_dims(plan)}


def dims(plan: dict[str, Any]) -> list[str]:
    return list(definitions(plan)) + ["stance"]


def clean(raw: Any, keys: list[str]) -> tuple[dict[str, float], list[str]]:
    """Scores for known dimensions, clipped to 0..1, and which of them the post itself stated.

    Each trait is {"score": 0..1, "basis": "stated" | "inferred"}; a bare number counts as inferred."""
    scores: dict[str, float] = {}
    stated: list[str] = []
    if isinstance(raw, dict):
        for key in keys:
            item = raw.get(key)
            try:
                x = float(item["score"] if isinstance(item, dict) else item)
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(x):
                scores[key] = round(min(1.0, max(0.0, x)), 2)
                if isinstance(item, dict) and item.get("basis") == "stated":
                    stated.append(key)
    return scores, stated


def vector(labels: dict[str, Any], ds: list[str]) -> list[float | None]:
    traits = labels.get("traits") or {}
    return [STANCE_CODE.get(labels.get("stance", "")) if d == "stance" else traits.get(d) for d in ds]


# ---------------------------------------------------------------- statistics


def pearson(a: list[float | None], b: list[float | None]) -> float:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 5:
        return 0.0
    mx, my = sum(x for x, _ in pairs) / len(pairs), sum(y for _, y in pairs) / len(pairs)
    sx, sy = sum((x - mx) ** 2 for x, _ in pairs), sum((y - my) ** 2 for _, y in pairs)
    if sx < 1e-9 or sy < 1e-9:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in pairs) / math.sqrt(sx * sy)


def corr_matrix(rows: list[list[float | None]], k: int) -> list[list[float]]:
    cols = [[r[i] for r in rows] for i in range(k)]
    out = [[1.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i):
            out[i][j] = out[j][i] = round(pearson(cols[i], cols[j]), 4)
    return out


def blend(a: list[list[float]], b: list[list[float]], w: float) -> list[list[float]]:
    return [[w * x + (1 - w) * y for x, y in zip(ra, rb)] for ra, rb in zip(a, b)]


def identity(k: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]


def cholesky(m: list[list[float]]) -> list[list[float]]:
    """Lower triangle L with L L^T = m. Adds a little diagonal jitter until the matrix is positive definite."""
    n, jitter = len(m), 1e-6
    for _ in range(12):
        low = [[0.0] * n for _ in range(n)]
        ok = True
        for i in range(n):
            for j in range(i + 1):
                s = m[i][j] + (jitter if i == j else 0.0) - sum(low[i][t] * low[j][t] for t in range(j))
                if i == j:
                    if s <= 1e-12:
                        ok = False
                        break
                    low[i][i] = math.sqrt(s)
                else:
                    low[i][j] = s / low[j][j]
            if not ok:
                break
        if ok:
            return low
        jitter *= 10
    return identity(n)


def quantile(values: list[float], p: float) -> float:
    if not values:
        return round(min(1.0, max(0.0, p)), 2)
    pos = min(1.0, max(0.0, p)) * (len(values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 2)


# ---------------------------------------------------------------- measuring


def _ridge(m: list[list[float]]) -> list[list[float]]:
    k = len(m)
    return [[1.0 if i == j else (1 - RIDGE) * m[i][j] for j in range(k)] for i in range(k)]


def measure(voices: list[Voice], plan: dict[str, Any]) -> dict[str, Any]:
    """Per segment trait spread and correlations, shrunk toward the pooled posts when a segment is small."""
    ds = dims(plan)
    k = len(ds)
    rows = []
    for v in voices:
        vec = vector(v.labels, ds) if v.labels else []
        if vec and sum(x is not None for x in vec) >= k / 2:
            rows.append((v.labels.get("segment"), vec))
    structured = len(rows) >= MIN_FIT
    pooled_c = corr_matrix([r for _, r in rows], k) if structured else identity(k)
    pooled_vals = {d: sorted(r[i] for _, r in rows if r[i] is not None) for i, d in enumerate(ds)}
    scored = [(v.labels.get("traits") or {}, set(v.labels.get("stated") or [])) for v in voices if v.labels]
    cells = sum(len(t) for t, _ in scored)
    stated_share = round(sum(len(st & set(t)) for t, st in scored) / cells, 3) if cells else 0.0
    model: dict[str, Any] = {"dims": ds, "structured": structured, "n": len(rows), "stated_share": stated_share,
                             "pooled": {"n": len(rows), "corr": _ridge(pooled_c), "values": pooled_vals,
                                        "raw_corr": pooled_c},
                             "segments": {}}
    for seg in [s["name"] for s in plan["segments"]]:
        group = [r for s, r in rows if s == seg]
        if structured and len(group) >= 5:
            c = blend(corr_matrix(group, k), pooled_c, len(group) / (len(group) + SHRINK))
        else:
            c = pooled_c
        vals = {d: sorted(r[i] for r in group if r[i] is not None) for i, d in enumerate(ds)}
        vals = {d: v if len(v) >= MIN_FIT else pooled_vals[d] for d, v in vals.items()}
        model["segments"][seg] = {"n": len(group), "corr": _ridge(c), "values": vals}
    return model


def structure(model: dict[str, Any]) -> float:
    """Mean absolute off-diagonal correlation measured on the pooled real posts (0 means unrelated traits)."""
    m, k = model["pooled"]["raw_corr"], len(model["dims"])
    cells = [abs(m[i][j]) for i in range(k) for j in range(i)]
    return round(sum(cells) / len(cells), 3) if cells else 0.0


def top_links(model: dict[str, Any], n: int = 6) -> list[tuple[str, str, float]]:
    ds, m = model["dims"], model["pooled"]["raw_corr"]
    links = [(ds[i], ds[j], m[i][j]) for i in range(len(ds)) for j in range(i)]
    return sorted(links, key=lambda x: abs(x[2]), reverse=True)[:n]


# ---------------------------------------------------------------- sampling


def _stance_bounds(values: list[float]) -> dict[str, tuple[float, float]]:
    """Cumulative stance intervals in 0..1, from the real stance mix (add half a post so none has zero width)."""
    counts = [0.5 + sum(1 for x in values if abs(x - STANCE_CODE[s]) < 1e-6) for s in STANCE_ORDER]
    total, acc, out = sum(counts), 0.0, {}
    for s, c in zip(STANCE_ORDER, counts):
        out[s] = (acc / total, (acc + c) / total)
        acc += c
    return out


LEVELS = {"low": 0.15, "medium": 0.5, "high": 0.85}


def parse_level(raw: str) -> float:
    """'low', 'medium', 'high' or a number from 0 to 1."""
    text = raw.strip().lower()
    try:
        value = LEVELS[text] if text in LEVELS else float(text)
    except ValueError:
        raise ValueError(f"trait value must be low, medium, high or a number from 0 to 1, got {raw!r}") from None
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"trait value must be between 0 and 1, got {value}")
    return value


def check_pins(pins: dict[str, float], ds: list[str]) -> None:
    allowed = [d for d in ds if d != "stance"]
    for name in pins:
        if name not in allowed:
            raise ValueError(f"unknown trait {name!r}; this audience has: {', '.join(allowed)}")


def _solve(low: list[list[float]], b: list[float]) -> list[float]:
    """Solve (L L^T) x = b given the Cholesky factor L."""
    n = len(b)
    y = [0.0] * n
    for i in range(n):
        y[i] = (b[i] - sum(low[i][t] * y[t] for t in range(i))) / low[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - sum(low[t][i] * x[t] for t in range(i + 1, n))) / low[i][i]
    return x


def _z_of(values: list[float], v: float) -> float:
    """Normal score of a value within the real spread of that trait (mid-rank, kept off the extremes)."""
    if not values:
        return ND.inv_cdf(min(0.98, max(0.02, v)))
    below = sum(1 for x in values if x < v) + 0.5 * sum(1 for x in values if x == v)
    return ND.inv_cdf(min(0.98, max(0.02, below / len(values))))


def sample(model: dict[str, Any], seg: str, stances: list[str], rng: random.Random,
           pins: dict[str, float] | None = None) -> list[dict[str, float]]:
    """One trait profile per stance, drawn conditional on that stance and on any pinned traits."""
    ds = model["dims"]
    spec = model["segments"].get(seg) or model["pooled"]
    si = ds.index("stance")
    pins = {d: v for d, v in (pins or {}).items() if d in ds and d != "stance"}
    given = [si] + [ds.index(d) for d in pins]
    free = [i for i in range(len(ds)) if i not in given]
    corr = spec["corr"]
    cc = [[corr[a][b] for b in given] for a in given]
    fc = [[corr[a][b] for b in given] for a in free]
    lcc = cholesky(cc)
    kmat = [_solve(lcc, [corr[g][f] for g in given]) for f in free]  # row f: Scc^-1 Scf
    cond = [[corr[f][g] - sum(fc[a][t] * kmat[b][t] for t in range(len(given))) for b, g in enumerate(free)]
            for a, f in enumerate(free)]
    low = cholesky(cond)
    bounds = _stance_bounds(spec["values"].get("stance", []))
    pin_z = [_z_of(spec["values"].get(d, []), v) for d, v in pins.items()]
    out = []
    for st in stances:
        lo, hi = bounds[st]
        zs = ND.inv_cdf(min(0.999, max(0.001, lo + (hi - lo) * rng.random())))
        zc = [zs] + pin_z
        eps = [rng.gauss(0, 1) for _ in free]
        profile = dict(pins)
        for a, i in enumerate(free):
            z = sum(kmat[a][t] * zc[t] for t in range(len(given))) + sum(low[a][b] * eps[b] for b in range(a + 1))
            profile[ds[i]] = quantile(spec["values"].get(ds[i], []), ND.cdf(z))
        out.append(profile)
    return out


def closest(pool: list[tuple[Voice, list[float | None]]], target: dict[str, float], stance: str,
            ds: list[str], k: int = 3) -> list[Voice]:
    """The k real posts whose measured traits sit nearest this persona's profile."""
    want = [STANCE_CODE[stance] if d == "stance" else target.get(d) for d in ds]

    def dist(vec: list[float | None]) -> float:
        gaps = [(a - b) ** 2 for a, b in zip(want, vec) if a is not None and b is not None]
        return sum(gaps) / len(gaps) if gaps else 1.0

    return [v for v, vec in sorted(pool, key=lambda item: dist(item[1]))[:k]]


def label_level(x: float) -> str:
    return "low" if x < 0.34 else "high" if x > 0.66 else "medium"


# ---------------------------------------------------------------- checking


def _crowd_corr(profiles: list[list[float | None]], k: int) -> list[list[float]]:
    return corr_matrix([list(p) for p in profiles], k)


def _error(a: list[list[float]], b: list[list[float]]) -> float:
    k = len(a)
    cells = [abs(a[i][j] - b[i][j]) for i in range(k) for j in range(i)]
    return sum(cells) / len(cells) if cells else 0.0


def fidelity(personas: list[Any], model: dict[str, Any], seed: int = 0, min_group: int = 15) -> dict[str, float] | None:
    """How closely the crowd's trait correlations match the measured ones, against a crowd with independent traits.

    The independent crowd uses the same marginals and stance mix, and the same size, so sampling noise cancels."""
    if not model.get("structured"):
        return None
    ds = model["dims"]
    k = len(ds)
    flat = {**model, "segments": {s: {**v, "corr": identity(k)} for s, v in model["segments"].items()},
            "pooled": {**model["pooled"], "corr": identity(k)}}
    got = base = weight = 0.0
    spread_rows: list[list[float]] = []
    for seg in model["segments"]:
        group = [p for p in personas if p.segment == seg and p.traits]
        if len(group) < min_group:
            continue
        rows = [[STANCE_CODE[p.stance] if d == "stance" else p.traits.get(d) for d in ds] for p in group]
        spread_rows += [[x or 0.0 for x in r] for r in rows]
        target = model["segments"][seg]["corr"]
        rng = random.Random(seed_from(seed, "fidelity", seg))
        indep = sample(flat, seg, [p.stance for p in group], rng)
        indep_rows = [[STANCE_CODE[p.stance] if d == "stance" else t.get(d) for d in ds] for p, t in zip(group, indep)]
        got += _error(_crowd_corr(rows, k), target) * len(group)
        base += _error(_crowd_corr(indep_rows, k), target) * len(group)
        weight += len(group)
    if not weight:
        return None
    rng = random.Random(seed_from(seed, "spread"))
    pairs = [rng.sample(spread_rows, 2) for _ in range(min(300, len(spread_rows)))]
    spread = sum(math.dist(a, b) for a, b in pairs) / (len(pairs) * math.sqrt(k)) if pairs else 0.0
    return {"trait_error": round(got / weight, 3), "trait_error_independent": round(base / weight, 3),
            "trait_spread": round(spread, 3)}
