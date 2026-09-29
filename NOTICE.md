# Attribution and scope

Copyright 2026 The contributors to this RRC configuration experiment.

The original experiment code, tests, documentation and aggregate results in this
repository are provided under the Apache License, Version 2.0; see [LICENSE](LICENSE).
This license does not replace the licenses or terms of external sources fetched
by the setup scripts. Third-party source checkouts, model weights, raw traces and
standards/paper PDFs are not redistributed in this repository.

## Decider

- Project: [Mapika/decider](https://github.com/Mapika/decider).
- Audited source revision: `23579f7a7e8f10e1045be492af3c1c05a005d67c`.
- Upstream copyright: Copyright 2026 Mark Marosi.
- Source license: [Apache License 2.0](https://github.com/Mapika/decider/blob/23579f7a7e8f10e1045be492af3c1c05a005d67c/LICENSE).
- Model: [Mapika/decider-2b](https://huggingface.co/Mapika/decider-2b/tree/533964dae8be954c5b5e19fa4948e48408094c1e), revision `533964dae8be954c5b5e19fa4948e48408094c1e`.
  Its pinned model card declares Apache-2.0 and identifies
  [Qwen/Qwen3.5-2B-Base](https://huggingface.co/Qwen/Qwen3.5-2B-Base) as the base model.

This project uses the upstream typed-decision inference API. It is not the
proprietary Jev model, and does not assert affiliation with or endorsement by
TypeSafe AI, Mapika, Qwen or the upstream authors. Model probabilities are not
assumed calibrated for the synthetic RRC task.

The expanded comparison also evaluates the unmodified
[Qwen/Qwen3.5-2B-Base](https://huggingface.co/Qwen/Qwen3.5-2B-Base/tree/b1485b2fa6dfa1287294f269f5fb618e03d52d7c)
at revision `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` under its stated
Apache-2.0 license. Its weights are fetched locally and are not redistributed.

## RRC sources

- Dataset: [EEzim/RRC](https://huggingface.co/datasets/EEzim/RRC/tree/e473ea8b9891f608afb7d9ad89c412e2dda27e18), by Ziming Liu,
  revision `e473ea8b9891f608afb7d9ad89c412e2dda27e18`.
  The pinned dataset card declares Apache-2.0; no separate LICENSE file was present.
  The 16-row public sample is fetched locally. Terminal identifiers, NAS payloads
  and raw message content are excluded from public experiment artifacts.
- Simulator: [EE-zim/nrRRC_Simulator](https://github.com/EE-zim/nrRRC_Simulator/tree/228ad4bc7ebce1093e215a9285ee126eb862ee95),
  revision `228ad4bc7ebce1093e215a9285ee126eb862ee95`.
  No LICENSE/COPYING file was found in the audited source snapshot. This project
  links to that repository and tests a locally fetched checkout; it does not
  redistribute or relicense the simulator source or bundled traces.
- Paper: Ziming Liu, Bryan Liu, Alvaro Valcarce and Xiaoli Chu,
  [LLM-Based Emulation of the Radio Resource Control Layer: Towards AI-Native RAN Protocols](https://arxiv.org/abs/2505.16821),
  arXiv:2505.16821v5, 15 January 2026. The paper is referenced for methodological
  context; its private evaluation corpora and published scores are not this
  project's measurements.

## Standards and other dependencies

LTE DRX parameter references are attributed to 3GPP TS 36.331 / ETSI TS 136 331;
see the direct official document links in [source_audit.md](docs/source_audit.md)
and [simulation.md](docs/simulation.md). Standards text and PDFs are not included.
Using allowed timer values does not make this project's simplified queue a
standards-compliant radio stack.

PyTorch, Transformers, NumPy and other Python dependencies remain under their
respective upstream licenses. They are installed by the user into a local
environment, not vendored here. The standard Apache 2.0 terms in `LICENSE` were
obtained from the licensed Decider checkout; that text does not transfer
authorship of this project's original work to its upstream author.
