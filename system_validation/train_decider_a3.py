"""Fit a small A3-specific Decider LoRA on separate ns-3 scenario descriptors."""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.domain_training import inject_lora, save_adapter
from rrcopt.provenance import file_hash
from scripts.train_decider_rrc import KeepOrder, loss_for, validation_loss
from system_validation.decider_a3 import OPTIONS, QUESTION, state
from system_validation.run_sweep import PROFILES, adaptation_scenarios, scenarios

OUT = Path("artifacts/system_validation/a3_train_result.json")
ADAPTER = Path("models/decider-a3-adapter")


def labels(path: Path, cases: list[dict], required_runs: set[int]) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    grouped = defaultdict(lambda: defaultdict(list))
    for row in records:
        grouped[row["case"]][(row["hysteresis_db"], row["ttt_ms"])].append(row)
    if set(grouped) != {x["name"] for x in cases}:
        raise ValueError("scenario mismatch")
    output = []
    for case in cases:
        by_profile = grouped[case["name"]]
        if set(by_profile) != set(PROFILES):
            raise ValueError("profile mismatch")
        if any({r["run"] for r in rows} != required_runs for rows in by_profile.values()):
            raise ValueError("RNG split mismatch")
        choice = min(PROFILES, key=lambda p: (
            sum(r["deadline_miss_including_loss"] for r in by_profile[p]),
            sum(r["lost"] for r in by_profile[p]),
            sum(r["handover_starts"] for r in by_profile[p]),
        ))
        output.append({"case": case, "label": OPTIONS[PROFILES.index(choice)]})
    return output


def items_for(rows, tokenizer, chat):
    from decider.infer import Example, Q
    from decider.prompt import build

    items = []
    for row in rows:
        question = Q(QUESTION, OPTIONS, OPTIONS.index(row["label"]))
        item = build(Example(state(row["case"]), [question]), tokenizer,
                     KeepOrder(), max_options=5, chat=chat)
        items.append(item)
    return items


def main() -> None:
    import torch
    from decider.model import DecisionModel
    from decider.prompt import chat_for_model

    train = labels(Path("artifacts/system_validation/adaptation_labels.jsonl"),
                   adaptation_scenarios(), {31, 32})
    validation = labels(Path("artifacts/system_validation/exploratory.jsonl"),
                        scenarios(), {1, 2})
    torch.manual_seed(2601001)
    torch.set_num_threads(8)
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = DecisionModel("models/decider-2b", dtype=torch.bfloat16, grad_ckpt=True).to("cuda")
    targets = inject_lora(model, rank=4, alpha=8)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=2e-4, weight_decay=0)
    chat = chat_for_model("models/decider-2b", model.tok)
    training = items_for(train, model.tok, chat)
    validating = items_for(validation, model.tok, chat)
    base_loss = validation_loss(model, validating, "cuda")
    rng = random.Random(2601001)
    losses = []
    model.train()
    optimizer.zero_grad(set_to_none=True)
    for epoch in range(2):
        order = list(range(len(training)))
        rng.shuffle(order)
        for step, index in enumerate(order, 1):
            loss = loss_for(model, training[index], "cuda")
            (loss / 4).backward()
            if step % 4 == 0 or step == len(order):
                torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            losses.append(float(loss.detach().item()))
        print(f"epoch {epoch + 1} loss {sum(losses[-len(order):])/len(order):.4f}", flush=True)
    trained_loss = validation_loss(model, validating, "cuda")
    metadata = {
        "base": "Mapika/decider-2b",
        "base_weights_sha256": file_hash(Path("models/decider-2b/model.safetensors")),
        "rank": 4, "alpha": 8, "targets": targets,
        "trainable_parameters": sum(p.numel() for p in trainable),
        "train_source_sha256": file_hash(Path("artifacts/system_validation/adaptation_labels.jsonl")),
        "validation_source_sha256": file_hash(Path("artifacts/system_validation/exploratory.jsonl")),
        "train_scenario_count": len(train), "validation_scenario_count": len(validation),
        "train_label_counts": dict(Counter(x["label"] for x in train)),
        "validation_label_counts": dict(Counter(x["label"] for x in validation)),
        "epochs": 2, "learning_rate": 2e-4, "gradient_accumulation": 4,
        "base_validation_loss": base_loss, "trained_validation_loss": trained_loss,
        "train_loss_mean": sum(losses) / len(losses),
        "elapsed_s": time.perf_counter() - started,
        "device": torch.cuda.get_device_name(),
        "peak_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
    }
    save_adapter(model, ADAPTER, metadata)
    metadata["adapter_sha256"] = file_hash(ADAPTER / "adapter.safetensors")
    OUT.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT, flush=True)


if __name__ == "__main__":
    main()
