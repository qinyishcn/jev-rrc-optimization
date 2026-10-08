# Execution plan

1. Preserve old evidence, create research branch, run existing `pytest -q tests`.
2. Add tests for observed-input whitelisting, paired numeric states, template
   split separation, option permutation decoding and complete simulation joins.
   Run red before implementing `system_validation/semantic_uc.py`.
3. Implement frozen synthetic text cases and packet simulation manifest, plus
   `system_validation/diagnose_a3.py` interventions. Persist complete inputs,
   probabilities, option order, token lengths, checkpoint hashes and timings.
4. Run diagnostics on base and existing A3 adapter, then semantic comparisons on
   base Decider and official Qwen. CPU full-information TF-IDF/rule baselines use
   only training families. No external paid APIs or new model downloads.
5. Run ns-3 all-five-profile counterfactual trajectory sweeps on fresh RNG seeds.
   Reuse a physics realization across text paraphrases explicitly, never pretend
   that paraphrases are independent network experiments.
6. Analyze packet-weighted metrics and paired family bootstrap; audit training
   labels, predictability from descriptors and the oracle gap in prior evidence.
   If knowledge/training remains ambiguous, say so rather than inventing a cause.
7. Write `docs/rrc_cause_semantic_uc.md`, machine-readable summaries, an example,
   and reproduction commands. Run relevant tests, verify artifacts/hashes/counts.
8. Publish the explicitly scoped files and verify the public report remotely.

Review: keep LTE A3 separate from NR DRX; prohibit future-trajectory fields in
numeric inputs; test text has no gold labels; comparable full-info baselines get
the same observations; attribution and latency boundaries are part of acceptance.
