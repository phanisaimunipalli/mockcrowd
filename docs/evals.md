# Evals and continuous improvement

`mockcrowd eval` scores the simulator itself and appends to `~/.mockcrowd/evals/history.jsonl`. With `--gate` it exits 1 when any metric falls more than 5 points below its best.

```bash
mockcrowd eval --suite quick|full|backtest [--gate]
```

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

The backtest ships with 13 cases: six with record crowdfunding or user growth (for example Pebble Time, Exploding Kittens, Flow Hive) and seven well known flops (for example Juicero, Quibi, Fire Phone). Each case cites its source, and pitches are anonymized. The leakage metric reports how often the model recognizes them anyway.

**Your outcomes are the strongest signal.** After you test or launch, run `mockcrowd outcome <run-id> --demand high|medium|low --note "what happened"`. The run becomes a backtest case, and future confidence scores include how well mockcrowd did on cases like yours.

## Does trait structure improve verdicts? A first test

The trait metrics above check that the crowd reproduces the measured links, not that the links improve predictions. To test that, six real open source feature requests (Ollama reranking, smolagents async, datasets cloud paths, Hub RSS, two Gradio requests) were run in `--free` mode with 40 personas, in three arms on identical evidence (same plan, same scored posts, via `--reuse-run`):

* **A:** traits drawn from the measured links
* **B:** traits drawn independently (`--independent-traits`)
* **A2:** a second run of A, to measure run to run noise

| Measure | Result |
|---|---|
| Mean change in interest, A vs B | 0.039 |
| Mean change in interest, A vs A2 (noise) | 0.032 |
| Mean change in lift, A vs B | 0.094 |
| Mean change in lift, A vs A2 (noise) | 0.046 |
| Same verdict as A | B: 5 of 6, A2: 5 of 6 |
| Rank correlation of interest with real reactions | A 0.35, B 0.64, A2 0.35 |

**Reading it.** Changing from linked to independent traits moved results about as much as rerunning the same arm, and the identical arms A and A2 differ as much on rank correlation as A and B do. This test cannot detect an effect of that size. It does not show that structure helps or hurts.

**Limits.** Six cases, one run per arm. Two Gradio cases kept only 1 and 7 relevant posts (the GitHub search is not limited to the project's repo, so it returned unrelated issues), so those cases barely tested traits. A repeat needs more cases, repeated runs per arm, and project scoped GitHub search.
