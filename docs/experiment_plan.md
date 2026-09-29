# Jev-class RRC configuration experiment plan

User goal: deploy and test Decider, use EEzim/RRC and nrRRC_Simulator where applicable, optimize latency-critical RRC configuration, compare with traditional methods, and publish the report publicly.

## Design and evidence boundary

1. Pin source commits and model revision. Run actual Decider 2B inference on the local RTX 3070. Use the upstream typed choice API, not text generation or an imitation of the model.
2. Audit all public RRC records. Test parsing and configuration-template extraction. This dataset supplies protocol context, not network performance labels. Do not republish trace identifiers.
3. Inspect and test the upstream simulator's usable Python components. Do not interpret randomly generated telemetry as measured latency. Avoid a full Linux/srsRAN radio deployment unless necessary for these checks.
4. Implement an explicit, reproducible synthetic connected-mode DRX packet evaluator with feasible LTE timer profiles, packet arrival traces, service time and finite receive windows. Compare Decider-selected profiles with fixed balanced, fixed low-latency, service rules, calibration-set optimized fixed/per-service profiles, and an evaluation-only hindsight oracle. Include DRX-disabled as the minimum-sleep-delay reference.
5. Separate raw Decider decisions from any deterministic safety guard. Report guard-only ablation, violations, energy/duty proxy, packet delay and measured decision runtime. Inference must run outside the per-packet critical path; no claim of sub-millisecond inference without measurements.
6. Use separate calibration/evaluation seeds. Never show evaluation outcomes or optimal labels to Decider. Freeze prompts and rules before held-out evaluation. Report null/negative results as well as positive ones.
7. Deliver runnable scripts, tests, checksums, raw aggregate experiment evidence, plots and a Chinese Markdown report in a new public repository under the authenticated GitHub account. Exclude model weights, raw identifiers, credentials, caches and unrelated files.

## Acceptance checks

- Actual model weights loaded; finite normalized choice probabilities; independently measured wall-clock latency.
- Dataset counts, revision/hash and scope established; upstream parser smoke results recorded honestly.
- DRX evaluator tested on hand-computable packets, no-DRX bound, queueing, conservation and deterministic seeded generation.
- Paired common-random-number comparisons on held-out traces; uncertainty intervals across independent scenarios, not pseudo-replication across packets.
- No claim that LTE traces prove NR URLLC compliance, no translation of a duty proxy into battery-life improvement, and no claim of gains beyond the modelled conditions.
- Public repository contents and remote visibility verified after push.

## Work units

- Source audit: `scripts/audit_rrc_sources.py`, `docs/source_audit.md`, `artifacts/rrc_audit.json`.
- Model setup/smoke: isolated environment, `scripts/model_smoke.py`, pinned model snapshot and artifact evidence.
- Experiment: `rrcopt/` with traffic/evaluator/policies, `scripts/run_experiment.py`, unit tests and results.
- Publication: README, reproducibility instructions, source/license manifest, report and plots.

Routine reversible choices follow the user's AGENTS.md authorization. There is no production network access, paid inference API, firmware write or order execution in scope.
