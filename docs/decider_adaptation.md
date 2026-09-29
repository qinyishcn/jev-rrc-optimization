# Decider RRC domain adaptation

This experiment fits a small, trainable adapter to the locally pinned `Mapika/decider-2b` checkpoint. It asks Decider to select one of nine LTE connected-mode DRX profiles for the same synthetic traffic descriptors and objective as the original experiment. No external paid model API or live radio data is used.

## Data separation and target

`scripts/train_decider_rrc.py --prepare-only` generates 100 descriptors per service from seed `26093011` and 30 per service from independent validation seed `26093012`. The 90 final test descriptors keep the existing seed `26092902` and must hash to `artifacts/experiment/evaluation_scenarios.json`. Each training or validation descriptor is replayed under three independent traffic phases. All nine options are simulated for each phase. A label is feasible only if **each phase** has at most 1% late packets; among feasible labels, the minimum receiver duty wins, then mean P99 delay. Option order is permuted from a hash of the descriptor UID before simulation. The model sees the same context and question as the original experiment, including only the three whitelisted static MAC values; it never sees phase seeds, traffic arrivals, candidate outcomes, or labels.

The synthetic label is an experimental target, not a measured 3GPP RRC optimum. The periodic receive-window FIFO simulator excludes inactivity extension, short DRX, HARQ, radio errors, shared scheduler effects and reconfiguration cost. In particular, a held-out gain on this simulator does not establish an over-the-air gain.

The split manifest and per-descriptor label evidence are in `artifacts/adaptation`. The frozen adapter is evaluated with `scripts/evaluate_decider_adapter.py` on the original 90 descriptors, question, model context, nine options, and option permutations; original baseline and rule outcomes are taken from the prior paired experiment. This is a **reused evaluation set** whose aggregate results had already been inspected before adaptation work, so it is not a pristine blind test. No training setting or label is chosen from these outcomes.

A stronger fresh confirmation uses independent seed `26093013` (30 descriptors per service) after adapter/settings freeze. `--fresh-only` runs unmodified and adapted Decider plus the deterministic guard on identical scenarios and reports paired outcomes. That seed is never used for training, validation, threshold selection, or model selection.

## Trainable parameters and reproduction

The implementation freezes the Decider 2B backbone and trains rank-4, alpha-8 LoRA matrices on `q_proj` and `v_proj` in its six full-attention layers (12 linear projections). It uses the original Decider `DecisionModel.slot_logits` and `decider.prompt.build`, one supervised answer per descriptor, BF16 backbone, gradient checkpointing, AdamW at `2e-4`, accumulation across four examples, and one epoch. The adapter is stored separately as `models/decider-rrc-adapter/adapter.safetensors`; the base model remains unmodified. The adapter is loaded into the original `Decider(..., use_graphs=False)` API for inference. The local model files are intentionally ignored by Git; the adapter configuration records the base weights hash, targets, split/label hashes, settings, validation loss, and trainable parameter count.

Actual run on an RTX 3070 trained 208,896 parameters over 300 examples in 377.4 seconds, with 3.98 GB peak allocated GPU memory. Independent validation cross-entropy fell from 1.954 to 1.117. The adapter is 838,192 bytes, SHA-256 `9b82de92e67d5fc20ede0c60d4844867b00b0533ca7071d30d93a3e962927c84`; the base `model.safetensors` SHA-256 is `acaef2228b134dcdc20cad4ee79219482c927ec819aa3687b9b8a575c338817f`. These hashes and the recipe in `adapter_config.json` identify the uncommitted weights needed to reproduce inference.

## Observed paired results

Each row is the mean over 90 equally weighted scenarios. A violating scenario has more than 1% late packets. RX duty is the configured ON fraction. Screened rows apply the **same pre-existing** descriptor-only candidate rule to model probabilities; this rule was not fitted to these results.

| Evaluation | Policy | Violating scenarios | Mean packet miss | Mean RX duty | Mean scenario P99 |
|---|---|---:|---:|---:|---:|
| Reused `26092902` | Base Decider raw | 36/90 | 19.20% | 46.56% | 14.363 ms |
| Reused `26092902` | Adapted Decider raw | 10/90 | 4.33% | 57.78% | 7.358 ms |
| Reused `26092902` | Adapted Decider + screen | 0/90 | 0% | 66.89% | 6.564 ms |
| Reused `26092902` | Guard only | 0/90 | 0% | 54.67% | 7.773 ms |
| Fresh `26093013` | Base Decider raw | 47/90 | 20.84% | 46.56% | 14.639 ms |
| Fresh `26093013` | Adapted Decider raw | 11/90 | 3.88% | 59.78% | 8.294 ms |
| Fresh `26093013` | Base Decider + screen | 0/90 | 0% | 69.11% | 6.593 ms |
| Fresh `26093013` | Adapted Decider + screen | 0/90 | 0% | 69.11% | 6.258 ms |
| Fresh `26093013` | Guard only | 0/90 | 0% | 56.44% | 7.524 ms |

On the fresh set, adaptation reduces violating scenarios versus base raw by 40 percentage points (paired scenario bootstrap 95% interval 31.11–48.89 points), while consuming 13.22 percentage points more RX duty. The screened adapter and screened base tie on feasibility and average duty; their 0.335 ms mean P99 difference has a 95% interval of −0.207 to +0.875 ms. Compared with the guard, the screened adapter improves P99 by 1.267 ms but consumes 12.67 duty points more (95% interval 8.66–16.67 points more). The original feasibility-first, then minimum-duty objective therefore still favors the deterministic guard. This is a synthetic simulator result, not a physical RRC measurement.

From the project root, after installing the dependencies documented in `README.md` and reserving the GPU:

```powershell
.venv/Scripts/python.exe scripts/train_decider_rrc.py --prepare-only
.venv/Scripts/python.exe -m pytest tests/test_domain_training.py -q
.venv/Scripts/python.exe scripts/train_decider_rrc.py
.venv/Scripts/python.exe scripts/evaluate_decider_adapter.py
.venv/Scripts/python.exe scripts/evaluate_decider_adapter.py --fresh-only
.venv/Scripts/python.exe scripts/evaluate_decider_adapter.py --fresh-rescore-only
```

The scripts check the reused evaluation descriptor hash and adapter/base/label hashes before evaluation. `train_result.json` records losses, time and peak allocated GPU memory; `test_summary.json` and `test_comparisons.json` report the reused paired result; `fresh_summary.json` and `fresh_comparisons.json` report fresh confirmation. The `--fresh-rescore-only` option recomputes simulator outcomes and applies the already frozen screen from the saved base and adapter probability files without loading either model.
