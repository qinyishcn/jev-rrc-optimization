# RRC negative-result diagnosis and semantic dispatch UC

User scope: explain missing gains and experimentally test the most plausible
Decider use case. Existing permission includes public GitHub research reports.
Routine design and implementation proceed under the user's AGENTS instructions.

Three alternatives: (1) raw numeric A3 optimization (cheap but rules nearly solve
the measured domain); (2) historical KPI minimization (a deterministic optimizer
already solves the supplied table); (3) interpreting an unstructured AGV dispatch
plan before selecting a calibrated RRC policy. Test (3), where language processing
has a reason to exist. No promise of superiority to learned text classifiers.

Diagnosis: audit prompt length, checkpoint/API, training support and tied labels;
rotate option positions, supply domain rules, derive geometric features, and
compare binary semantic policies to five opaque numeric configurations. These
are interventions, not proof of an unobserved internal knowledge deficit.

UC: one AGV's next 24 s route is either a one-way boundary crossing or a local
back-and-forth patrol. Position, speed, offered load and cell geometry are paired
identically; only the dispatch text disambiguates the future route. Numeric-only
controllers are information ablations. Fair full-information baselines receive
the exact same text. Inference occurs once before traffic, never per packet.

Train/development/test text template families are disjoint. Language is synthetic
English, matching the checkpoint; no claims about Chinese or real dispatcher data.
Physics runs use the existing unchanged ns-3 LTE/EPC/X2 source, all five A3 profiles
and fresh RNG runs. A deterministic mapping from inferred route class to H0/T0
or H1/T80 is frozen from prior calibration, not fit on test packet outcomes.

Baselines: default, best fixed selected using calibration only, numeric rule,
keyword rules, word/character TF-IDF logistic regression, Qwen3.5-2B-Base,
Decider direct five-way choice, Decider semantic two-way choice and known-intent
mapping. Report classification, illegal outputs, end-to-end packet deadline
misses/loss/handovers and warmed batch-one inference time. Pair sampling and
bootstrap by language family, avoid treating repeated packets as independent.

Acceptance: complete reproducible evidence; an unfavorable result is acceptable.
Any positive gain is attributed separately to information, mapping and model.
No test-outcome tuning, no retrofit of templates to model failures. If structural
checks or the pilot expose a design flaw, document the change before final runs.
