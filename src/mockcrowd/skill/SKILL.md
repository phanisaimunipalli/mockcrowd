---
name: mockcrowd
description: Use when the user wants to validate a product idea, test demand before building, check whether people would pay, test a price or feature, or asks "would people use this". Runs mockcrowd, a local simulation of hundreds of personas grounded in real Reddit, Hacker News and App Store posts, and reports a demand verdict with a confidence score and the top objections.
---

# mockcrowd

mockcrowd simulates a crowd of real-world-grounded personas reacting to a product idea:
a blind vote against a bland control pitch, a Reddit-style discussion, then a final vote.

## When to use

- "Validate my idea for X", "would people pay for X", "test this price", "is there demand for X"
- Comparing two versions of a pitch, price or feature (run once per version, same `--seed`)

## Steps

1. Check it is installed: `mockcrowd --version`. If not:
   `uv tool install git+https://github.com/phanisaimunipalli/mockcrowd`
2. Write the pitch the way a founder would post it: what it does, for whom, and the price.
   Ask the user for the price and audience if they did not give them. Do not invent them.
3. Run:
   ```bash
   mockcrowd validate "<pitch>" --price "<price>" --audience "<audience>"
   ```
   Defaults: 500 agents, 2 discussion rounds, live sources reddit, hn and bluesky. Reddit needs
   REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (a free "script" app); without them it is skipped. It prints
   progress to stderr and a markdown report to stdout, and saves the run under `~/.mockcrowd/runs/`.
   For a quick look first, use `--agents 60 --rounds 1`.
4. If live sources fail (look for "Source errors" in the report) or the audience lives
   elsewhere (X, Threads, Instagram, Discord, support tickets), gather real posts yourself
   with your web tools, save them as JSONL lines `{"text": "...", "url": "...", "community": "..."}`,
   and rerun with `--voices posts.jsonl` (add `--no-live` to skip web search).
5. Report back to the user: the verdict, would-pay share blind and after discussion, the lift
   over the control, the confidence score with its caveats, and the top three objections.
   Quote the numbers from the report. Do not soften a weak verdict.
6. Remind the user that the strongest signal is what really happens. When they have it:
   `mockcrowd outcome <run-id> --demand high|medium|low --note "what happened"`

## Rules

- Never present the simulation as proof of demand. It is a direction and an objection map.
- A lift under 5 points over the control means no signal, whatever the would-pay share says.
- Use the user's model names exactly as given with `--model`.
- Runs use the user's own AI subscription or API key. For 500 agents expect roughly
  100 to 150 LLM calls. Tell the user before running large or repeated runs.
