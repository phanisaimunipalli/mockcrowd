<p align="center"><img src="https://raw.githubusercontent.com/phanisaimunipalli/mockcrowd/main/docs/images/hero.gif" alt="mockcrowd: an AI population designer. A crowd of colored dots drifts as opinions shift" width="100%"></p>

[![ci](https://github.com/phanisaimunipalli/mockcrowd/actions/workflows/ci.yml/badge.svg)](https://github.com/phanisaimunipalli/mockcrowd/actions/workflows/ci.yml) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![license](https://img.shields.io/badge/license-Apache%202.0-green)

<p align="center"><img src="https://raw.githubusercontent.com/phanisaimunipalli/mockcrowd/main/docs/images/debate.gif" alt="Replay of a real mockcrowd run: persona characters debate a vinyl scanning app in a chat, votes flip from Try free to Pass, ending in a weak demand verdict" width="100%"></p>

**An AI population designer.** mockcrowd designs crowds of AI personas whose traits connect the way real people's do. It scores real posts on traits such as budget sensitivity, trust and how much a problem hurts, measures how those traits move together, and designs each persona to fit. Every persona cites the real posts behind it.

Then put the population to work: they vote blind against a bland control, argue in a simulated Reddit thread, and tell you whether your idea has demand, who would pay, and why the rest would not.

It runs on your machine, on the AI you already have: Claude Code, Codex, Code Puppy, Ollama, or any OpenAI compatible API.

```bash
pip install mockcrowd
mockcrowd design "people who forget about their subscriptions" --pin vendor_trust=low -o crowd.json   # design a population
mockcrowd validate "An app that finds and cancels forgotten subscriptions" --price "\$4.99/month"             # test an idea on one
```

## How personas are designed

Most persona tools invent people from a prompt, one trait at a time, so traits never relate to each other. mockcrowd measures the relations first.

1. **Score real posts.** Each post is scored from 0 to 1 on six core traits (budget sensitivity, tech savvy, status quo attachment, switching cost, vendor trust, pain urgency) and up to four traits the planner picks for your audience. Each score is marked **stated** (the post shows it) or **inferred** (the AI is estimating).
2. **Measure the links.** How the traits move together in each segment. Small segments are pulled toward the pooled posts, so thin evidence cannot invent structure.
3. **Sample personas from the links.** Each persona's trait profile is drawn conditional on its stance, and on any traits you pin. The links move the other traits with it.
4. **Ground each one.** The profile is matched to the three real posts nearest to it, and the AI writes the person to fit. Each persona cites those posts.

A real example: 40 personas for a subscription cancelling idea, built from 130 real posts. The strongest links in those posts were cancellation friction pain with pain urgency (+0.57), pain urgency with status quo attachment (-0.57) and cancellation friction pain with vendor trust (-0.51). Pinning a core trait such as `vendor_trust=low` shifts the traits linked to it, and the rest of the profile follows.

The report shows the strongest links and how closely the crowd reproduces them, next to a crowd that draws traits independently. `mockcrowd personas <run-id>` exports any run's personas with their traits and source posts.

## Test an idea on the population

<p align="center"><img src="https://raw.githubusercontent.com/phanisaimunipalli/mockcrowd/main/docs/images/discussion.png" alt="mockcrowd discussion: personas debate a vinyl scanning app in a simulated r/vinyl thread; would try free falls from 60% to 35%, would pay from 5% to 0%, with the top objections" width="100%"></p>

<p align="center"><img src="https://raw.githubusercontent.com/phanisaimunipalli/mockcrowd/main/docs/images/demo.gif" alt="Terminal recording of a real 20 persona mockcrowd run, sped up 9x, ending in a weak demand verdict" width="100%"></p>

A real small run (20 personas, 1 discussion round, Claude, Hacker News and Bluesky voices): alone, 60% said they would try the idea free and 5% would pay. After the discussion, 35% would try it and nobody would pay. That is the kind of answer you want before you spend a month building.

| Problem with asking an LLM "would people buy this?" | What mockcrowd does |
|---|---|
| Models are agreeable and say yes to everything | Every persona also rates a **bland control pitch** in the same blind vote. The verdict is the lift over the control, not the raw yes rate. |
| One voice, no social dynamics | A **Reddit style discussion**: threads of about 20 personas, a ranked feed, and a fixed action space (comment, reply, upvote, downvote, do nothing), following the design of [OASIS](https://github.com/camel-ai/oasis). You see the vote before and after people talk. |
| No way to know if the tool is right | **Evals and a backtest** on products with known outcomes, plus your own recorded outcomes. |

For something nobody pays for, such as an open source feature, add `--free`: the crowd is asked whether they would use it, and the verdict compares interest with a bland control. To backtest on a real feature request, add `--exclude github.com/owner/repo/issues/123` so the crowd never sees the issue it is scored against.

## Install

```bash
pip install mockcrowd      # or: uv tool install mockcrowd
mockcrowd brains           # shows which AI it can use
```

Python 3.10 or newer. One small dependency (`certifi`). Once a day mockcrowd prints one line when a newer version is on PyPI, and never installs anything. Upgrade with `pip install -U mockcrowd`. Turn the check off with `MOCKCROWD_NO_UPDATE_CHECK=1`.

## Pick the brain

mockcrowd uses the first one it finds, or the one you pass with `--brain`.

| Brain | How it runs | Setup |
|---|---|---|
| `claude` | `claude -p` on your Claude Code plan | Claude Code installed |
| `codex` | `codex exec` on your ChatGPT or API plan | Codex CLI installed |
| `code-puppy` | `code-puppy -p` with your configured model | Code Puppy installed |
| `ollama` | Local models, free and private, slower | `ollama serve`, then `--model <name>` |
| `openai` | Any OpenAI compatible endpoint (OpenAI, OpenRouter, LM Studio, vLLM) | `MOCKCROWD_API_BASE`, `MOCKCROWD_API_KEY`, `--model` |

Claude has been run live end to end. The Codex, Code Puppy, Ollama and OpenAI adapters are tested against the flags and API each tool documents, but not yet in a live run; reports are welcome. Claude and Code Puppy run with tools off. Codex runs in its read only sandbox, which blocks writes but not reads, so prefer the others if your machine holds sensitive files.

`--model` is passed through exactly as you write it. A 500 persona run makes roughly 100 to 150 LLM calls, because one call steps a whole batch or thread of personas. `OPENAI_API_KEY` is only used with api.openai.com; other endpoints need `MOCKCROWD_API_KEY`.

## Real voices

| Source | Key needed | Notes |
|---|---|---|
| Reddit | Yes, free | Create a "script" app at reddit.com/prefs/apps and set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`. Reddit blocks keyless requests. Free access is for non commercial use. |
| Hacker News | No | Comments through the Algolia search API |
| Bluesky | No | Public post search |
| GitHub | No | Issues and their top comments, only when the audience is developers. Set `GITHUB_TOKEN` for a higher rate limit. |
| App Store | No | Opt in with `--source appstore`. Apple's public review feed returned no reviews when last tested. |
| Anything else | | X, Threads, Instagram, Discord, surveys, support tickets, interview notes: put the posts in a file and pass `--voices posts.jsonl` (JSONL, CSV or text). |

Each source that fails is listed in the report, and confidence drops when evidence is thin.

## Use it from an AI agent

**Skill.** `mockcrowd install-skill` installs it for Claude Code (`--dir <skills dir>` for any agent that reads SKILL.md files). Then ask: *"design 100 personas for people who forget subscriptions"* or *"validate my idea for a vinyl app at \$3.99 a month"*. When a source is blocked, the agent can gather posts with its own web tools and pass them in.

**MCP.** Any MCP client (Claude Code, Cursor, Codex, Claude Desktop, your own agent) can use mockcrowd over stdio. It is listed in the official MCP Registry as `io.github.phanisaimunipalli/mockcrowd`.

```bash
pip install "mockcrowd[mcp]"
claude mcp add mockcrowd -- mockcrowd mcp
```

```json
{"mcpServers": {"mockcrowd": {"command": "mockcrowd", "args": ["mcp"]}}}
```

To always run the newest release without installing: `{"command": "uvx", "args": ["--python", "3.12", "mockcrowd[mcp]@latest", "mcp"]}`.

| Tool | What it does |
|---|---|
| `design_personas` | Designs a population with connected traits from real posts. Pin traits, get personas with traits and sources. No votes. |
| `validate_idea` | Runs a crowd on an idea and returns the verdict, shares, lift, confidence, top objections and the full report |
| `get_report` | The report of a past run |
| `list_runs` | Past runs with their verdicts |
| `record_outcome` | What really happened after a run, which becomes a backtest case |
| `list_brains` | Which AI backends are available |

Agent runs default to 60 personas and 1 round to keep them quick.

## Commands

```bash
mockcrowd design "audience" [--agents 100] [--pin TRAIT=low|medium|high|0.8] [-o crowd.json]
                            [--voices file.jsonl] [--no-live] [--source reddit|hn|bluesky|github|appstore]
mockcrowd validate "idea" [--price P | --free] [--audience A] [--agents 500] [--rounds 2]
                          [--voices file.jsonl] [--no-live] [--source reddit|hn|bluesky|github|appstore]
                          [--exclude TEXT]
                          [--question "choice:first:Which feature first?:scan|alerts|wishlist"]
                          [--brain auto|claude|codex|code-puppy|ollama|openai] [--model M]
mockcrowd collect "idea" -o voices.jsonl   # only gather real posts
mockcrowd runs                             # list past runs
mockcrowd report <run-id> [--json]
mockcrowd personas <run-id> [-o file.json] # export a run's personas, traits and source posts
mockcrowd outcome <run-id> --demand high|medium|low --note "what really happened"
mockcrowd eval --suite quick|full|backtest [--gate]
```

Trait names for `--pin` are printed in the `design` output (`dims`). Runs are saved in `~/.mockcrowd/runs/<run-id>/` as `report.md` and `run.json` (every voice, persona, vote and comment). A design is printed, or written where you point `-o`; it is not saved as a run.

## How a validation run works

<p align="center"><img src="https://raw.githubusercontent.com/phanisaimunipalli/mockcrowd/main/docs/images/how-it-works.svg" alt="Plan, collect, label, design, blind vote, discuss, report" width="100%"></p>

1. **Plan.** The brain reads your idea and lists the segments (including people who would not buy), subreddits, search queries and audience specific traits.
2. **Collect and label.** Real posts from the sources above, each given a segment, relevance, pain, stance and trait scores. Irrelevant posts are dropped.
3. **Design.** The personas, as described above, in the segment shares and stance mix the real posts show.
4. **Blind vote.** Every persona answers alone: interest, would try free, would pay, biggest objection, plus your own typed questions. The real idea and a bland control appear side by side in random order.
5. **Discuss.** Threads of about 20 mixed personas, one action each per round on a ranked feed.
6. **Final vote and report.** Shares with 95% intervals, lift over control, shift after discussion, results by segment, objection themes, trait links and a confidence score.

## Evals and continuous improvement

`mockcrowd eval` scores the simulator itself and appends to `~/.mockcrowd/evals/history.jsonl`. With `--gate` it exits 1 when any metric falls more than 5 points below its best.

| Metric | What it checks |
|---|---|
| grounding, citation_valid | Personas are built from real posts, and their citations exist |
| mix_fidelity | The crowd's stance mix matches the real posts |
| trait_error, trait_gain, trait_spread | The crowd's trait links match the measured ones, how much closer than independent traits, and how spread out the crowd is |
| diversity | Personas are not copies of each other |
| control_lift, agreeableness | The crowd does not reward a bland idea |
| persuasion_drift | How much the discussion moved the vote |
| stability | Rerunning the vote gives the same answer |
| realism | A judge cannot tell real posts from persona comments |
| backtest_accuracy, backtest_auc | Known hits score above known flops |
| leakage | How many backtest products the brain recognizes from memory |

The backtest ships with 13 cases: six with record crowdfunding or user growth (for example Pebble Time, Exploding Kittens, Flow Hive) and seven well known flops (for example Juicero, Quibi, Fire Phone). Each case cites its source, and pitches are anonymized.

**Your outcomes are the strongest signal.** After you test or launch, run `mockcrowd outcome <run-id> --demand ...`. The run becomes a backtest case, and future confidence scores include how well mockcrowd did on cases like yours.

## Honest limits

* It is a simulation. Use it to rank ideas, find objections and choose what to test for real, not to forecast revenue.
* Personas reflect the people who post online, who are louder and more opinionated than most buyers. A post is not a person.
* Most trait scores are inferred by the AI, not stated in the post, so the measured links partly reflect the AI's own assumptions. Reports print the stated share. Links are correlations, not causes. Below 8 scored posts, traits are drawn independently and the report says so.
* Whether structured traits make verdicts more accurate is not yet measured.
* Backtest products are famous, so models may know how they ended. Watch the leakage metric.
* The verdict thresholds are starting points. The backtest reports how well they separate hits from flops on your brain.

## Credits

Simulation design follows [OASIS](https://github.com/camel-ai/oasis) by CAMEL-AI (Apache 2.0). The idea of building a world from seed material and simulating it was inspired by [MiroFish](https://github.com/666ghj/MiroFish). No code from either project is included. See `NOTICE`.

## License

Apache 2.0

<!-- mcp-name: io.github.phanisaimunipalli/mockcrowd -->
