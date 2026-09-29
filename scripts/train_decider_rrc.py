"""Build independent synthetic RRC labels and train a Decider LoRA adapter."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.domain_training import (TRAIN_SEED, VALIDATION_SEED, TEST_SEED,
                                    PHASES, adapter_state, canonical_hash,
                                    inject_lora, label_scenario, split_hash)
from rrcopt.simulation import generate_scenarios
from rrcopt.policies import QUESTION, context
from rrcopt.provenance import file_hash

OUT = Path("artifacts/adaptation")
ADAPTER = Path("models/decider-rrc-adapter")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def prepare_split(path, scenarios):
    """Checkpoint each CPU simulation label; verify every resumed descriptor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            completed[row["scenario"]["uid"]] = row
    for scenario in scenarios:
        old = completed.get(scenario.uid)
        if old is not None:
            if old["scenario"] != asdict(scenario):
                raise ValueError(f"checkpoint descriptor mismatch: {scenario.uid}")
            continue
        row = label_scenario(scenario)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
        completed[scenario.uid] = row
        if len(completed) % 25 == 0:
            print(f"{path.name}: {len(completed)}/{len(scenarios)} labels", flush=True)
    if set(completed) != {s.uid for s in scenarios}:
        raise ValueError("checkpoint contains unexpected or missing descriptors")
    return [completed[s.uid] for s in scenarios]


class KeepOrder:
    def shuffle(self, values):
        pass

    def sample(self, values, count):
        return values[:count]


def items_for(rows, tok, current_mac, chat):
    from decider.infer import Example, Q
    from decider.prompt import build
    items = []
    for row in rows:
        from rrcopt.simulation import Scenario
        scenario = Scenario(**row["scenario"])
        options = row["options"]
        q = Q(QUESTION, options, options.index(row["label"]))
        item = build(Example(context(scenario, current_mac), [q]), tok,
                     KeepOrder(), max_options=9, chat=chat)
        assert item["golds"] == [options.index(row["label"])]
        items.append(item)
    return items


def loss_for(model, item, device):
    import torch.nn.functional as F
    from decider.model import collate
    batch = collate([item], model.tok.pad_token_id)
    logits = model.slot_logits(*[batch[k].to(device) for k in
                                 ("input_ids", "attention_mask", "slot_idx", "slot_batch", "nopts")])
    return F.cross_entropy(logits, batch["golds"].to(device))


def validation_loss(model, items, device):
    import torch
    model.eval()
    with torch.no_grad():
        losses = [loss_for(model, item, device).item() for item in items]
    return float(sum(losses) / len(losses))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/decider-2b")
    parser.add_argument("--train-per-service", type=int, default=100)
    parser.add_argument("--val-per-service", type=int, default=30)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.train_per_service < 100 or args.val_per_service < 10:
        parser.error("train >=100 and validation >=10 descriptors per service required")

    train_scenarios = generate_scenarios(args.train_per_service, TRAIN_SEED)
    val_scenarios = generate_scenarios(args.val_per_service, VALIDATION_SEED)
    test_scenarios = generate_scenarios(30, TEST_SEED)
    seen = [set(s.uid for s in split) for split in (train_scenarios, val_scenarios, test_scenarios)]
    if any(seen[i] & seen[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("descriptor split overlap")
    existing_test = json.loads(Path("artifacts/experiment/evaluation_scenarios.json").read_text(encoding="utf-8"))
    if canonical_hash(existing_test) != split_hash(test_scenarios):
        raise ValueError("held-out test differs from prior 90-scenario experiment")
    current_mac = json.loads(Path("artifacts/protocol_context.json").read_text(encoding="utf-8"))["current_mac"]
    if current_mac != {"periodicBSR-Timer": "sf20", "retxBSR-Timer": "sf320",
                       "timeAlignmentTimerDedicated": "infinity"}:
        raise ValueError("static MAC whitelist changed")
    manifest = {
        "train_seed": TRAIN_SEED, "validation_seed": VALIDATION_SEED, "held_out_test_seed": TEST_SEED,
        "n_train": len(train_scenarios), "n_validation": len(val_scenarios), "n_held_out_test": len(test_scenarios),
        "phases_per_descriptor": PHASES, "options_per_descriptor": 9,
        "train_descriptor_sha256": split_hash(train_scenarios),
        "validation_descriptor_sha256": split_hash(val_scenarios),
        "held_out_test_descriptor_sha256": split_hash(test_scenarios),
        "label_rule": "all phases miss_rate <= 0.01; then minimum RX duty; then mean p99",
        "test_use": "Final evaluation only, after the adapter and settings are frozen",
        "current_mac": current_mac,
    }
    write_json(OUT / "split_manifest.json", manifest)
    train = prepare_split(OUT / "train_labels.jsonl", train_scenarios)
    val = prepare_split(OUT / "validation_labels.jsonl", val_scenarios)
    manifest["train_label_sha256"] = file_hash(OUT / "train_labels.jsonl")
    manifest["validation_label_sha256"] = file_hash(OUT / "validation_labels.jsonl")
    manifest["train_label_counts"] = dict(Counter(r["label"] for r in train))
    manifest["validation_label_counts"] = dict(Counter(r["label"] for r in val))
    write_json(OUT / "split_manifest.json", manifest)
    if args.prepare_only:
        print("LABELS_READY", flush=True)
        return

    import torch
    from decider.model import DecisionModel
    from decider.prompt import chat_for_model
    from rrcopt.domain_training import save_adapter

    torch.manual_seed(26093011)
    torch.set_num_threads(8)
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = DecisionModel(args.model, dtype=torch.bfloat16, grad_ckpt=True).to("cuda")
    targets = inject_lora(model, rank=4, alpha=8)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=2e-4, weight_decay=0.0)
    chat = chat_for_model(args.model, model.tok)
    train_items = items_for(train, model.tok, current_mac, chat)
    val_items = items_for(val, model.tok, current_mac, chat)
    starting_val = validation_loss(model, val_items, "cuda")
    order = list(range(len(train_items)))
    random.Random(26093011).shuffle(order)
    model.train()
    history = []
    optimizer.zero_grad(set_to_none=True)
    for step, index in enumerate(order, 1):
        loss = loss_for(model, train_items[index], "cuda")
        (loss / 4).backward()
        if step % 4 == 0 or step == len(order):
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        history.append(float(loss.detach().item()))
        if step % 25 == 0 or step == len(order):
            row = {"step": step, "train_loss_last_25": sum(history[-25:]) / len(history[-25:]),
                   "elapsed_s": time.perf_counter() - started,
                   "peak_allocated_gb": torch.cuda.max_memory_allocated() / 1e9}
            write_json(OUT / "training_progress.json", row)
            print(json.dumps(row), flush=True)
    trained_val = validation_loss(model, val_items, "cuda")
    adapter_cfg = {
        "base": "Mapika/decider-2b", "base_weights_sha256": file_hash(Path(args.model) / "model.safetensors"),
        "rank": 4, "alpha": 8, "targets": targets, "trainable_parameters": sum(p.numel() for p in trainable),
        "train_seed": TRAIN_SEED, "validation_seed": VALIDATION_SEED,
        "train_descriptor_sha256": manifest["train_descriptor_sha256"],
        "train_label_sha256": manifest["train_label_sha256"],
        "question_sha256": canonical_hash(QUESTION), "epochs": 1, "learning_rate": 2e-4,
        "gradient_accumulation": 4, "train_examples": len(train_items),
        "validation_examples": len(val_items), "base_validation_loss": starting_val,
        "trained_validation_loss": trained_val,
    }
    save_adapter(model, ADAPTER, adapter_cfg)
    write_json(OUT / "train_result.json", {
        **adapter_cfg, "train_loss_mean": sum(history) / len(history),
        "train_loss_final_25": sum(history[-25:]) / min(25, len(history)),
        "elapsed_s": time.perf_counter() - started,
        "device": torch.cuda.get_device_name(),
        "peak_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
        "adapter_sha256": file_hash(ADAPTER / "adapter.safetensors"),
    })
    print("ADAPTER_TRAINED", flush=True)


if __name__ == "__main__":
    main()
