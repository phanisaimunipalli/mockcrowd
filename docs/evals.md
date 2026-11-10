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

Trait structure and verdict accuracy: whether structured traits make verdicts more accurate is not yet measured. The trait metrics above check that the crowd reproduces the measured links, not that the links improve predictions.
