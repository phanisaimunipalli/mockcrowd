# mockcrowd design

## Intent

Let anyone check whether people want a product idea before building it, on their own machine,
using the AI they already pay for, and finish in minutes. The output must be trustworthy enough
to rank ideas: grounded in real people, resistant to LLM agreeableness, and measured by evals
that get stronger as users report real outcomes.

## Goals and non goals

| Goals | Non goals |
|---|---|
| Personas built from real posts, matching the real stance mix | Revenue or market size forecasts |
| 500 interacting agents in minutes | A hosted service or web UI (v0.1) |
| Runs on Claude Code, Codex, Code Puppy, Ollama or any OpenAI compatible API | Scraping platforms against their terms |
| Typed answers (yes/no, score, choice) that aggregate into probabilities | |
| Evals, backtest on known outcomes, regression gate, user outcome loop | |

Anti goal: a tool that says "people want this" for any idea. Every design choice below exists to prevent that.

## Architecture

```
idea ──► plan (segments, communities, queries)
     ──► collect real voices (reddit, hn, bluesky, files)
     ──► label voices (segment, relevance, pain, stance)
     ──► design personas (segment shares x stance mix, cited source ids)
     ──► blind vote: idea vs bland control, randomized A/B order
     ──► discussion: threads of ~20, ranked feed, one action per persona per round
     ──► final vote ──► report (shares + 95% CI, lift, shift, segments, objections, confidence)
```

| Module | Role |
|---|---|
| `brains/` | One interface, `Brain.run(Task) -> JSON`. CLI brains shell out to `claude -p`, `codex exec -o`, `code-puppy -p`. HTTP brain covers OpenAI compatible endpoints and Ollama. Mock brain answers every Task deterministically for tests. |
| `sources/` | Voice collectors. Each failure is recorded in the report, never fatal. |
| `personas.py` | Planning, labeling, quota allocation (largest remainder), batched persona design with citation validation. |
| `sim.py` | Typed questions, control pitch, blind and final votes, Reddit style platform following OASIS's design. |
| `report.py` | Bootstrap intervals, score indexes, objection themes, confidence score, verdict, markdown. |
| `evals/` | Run metrics, brain judged metrics, backtest, history and regression gate. |

## Key decisions

| Decision | Why |
|---|---|
| Reimplement OASIS's design instead of depending on OASIS | OASIS needs Python 3.10 to 3.11, torch and other heavy pins, and calls model APIs only. Reimplementing keeps the proven design while letting one call step a whole thread, which makes subscription CLIs and minutes possible. |
| Batch personas per call | 500 agents in about 100 to 150 calls instead of thousands |
| Control pitch in the blind vote | Measures and subtracts agreeableness |
| Blind vote before discussion | Captures private opinion before herding; the shift is reported |
| Confidence = grounding, evidence volume, source breadth, interval width, backtest accuracy | Each part is something the user can improve |
| Outcomes feed the backtest | Real behavior is the strongest signal |

## Known limits

Online posters are not all buyers. Backtest cases are famous, so leakage is measured and reported.
Apple's public review feed returned no reviews in testing, so App Store is opt in. Reddit requires a free OAuth app.
