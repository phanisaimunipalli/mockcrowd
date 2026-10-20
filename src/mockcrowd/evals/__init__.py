"""Evals: how real is the crowd, and does it tell hits from flops?

Run metrics (computed on any finished run):
  grounding        share of personas built from at least one real post
  citation_valid   share of persona source ids that point to collected posts
  mix_fidelity     1 minus total variation distance between the stance mix of real
                   voices and the stance mix of personas (1.0 = identical)
  diversity        1 minus mean pairwise word overlap of persona bios (higher = more varied)
  control_lift     would-pay share of the idea minus a bland control (bias check)
  agreeableness    would-pay share given to the bland control (lower is more honest)
  persuasion_drift absolute change in would-pay between blind and final votes

Brain metrics (cost extra LLM calls):
  realism          a judge tries to tell real posts from persona comments;
                   1.0 means it cannot (50% accuracy), 0.0 means it always can
  stability        1 minus the change in would-pay when the blind vote is rerun
  leakage          share of backtest pitches the brain can name (memorized history)

Backtest:
  backtest_accuracy  share of known hits and flops classified correctly
  backtest_auc       chance a random hit outranks a random flop
"""
