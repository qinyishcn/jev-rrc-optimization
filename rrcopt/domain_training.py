"""Reproducible synthetic labels and a small Decider low-rank adapter.

The final experiment seed is never used to fit the adapter or select settings.
"""
from dataclasses import asdict, replace
import hashlib
import json
import random
from pathlib import Path

import numpy as np

from rrcopt.simulation import PROFILES, generate_arrivals, generate_scenarios, simulate

TRAIN_SEED = 26093011
VALIDATION_SEED = 26093012
TEST_SEED = 26092902
PHASES = 3
PROFILE_NAMES = tuple(p.name for p in PROFILES)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def split_scenarios(n_per_service=100):
    return tuple(generate_scenarios(n_per_service, seed)
                 for seed in (TRAIN_SEED, VALIDATION_SEED, TEST_SEED))


def split_hash(scenarios):
    return canonical_hash([asdict(s) for s in scenarios])


def ordered_options(uid):
    """Fixed per-descriptor permutation determined before any outcome exists."""
    options = list(PROFILE_NAMES)
    random.Random(int(hashlib.sha256(("options:" + uid).encode()).hexdigest()[:16], 16)).shuffle(options)
    return options


def make_phase_scenarios(scenario, n_phases=PHASES):
    if n_phases < 3:
        raise ValueError("at least three independent phases are required")
    entropy = hashlib.sha256(("phases:" + scenario.uid + ":" + str(scenario.seed)).encode()).digest()
    rng = np.random.default_rng(int.from_bytes(entropy[:8], "big"))
    seeds = set()
    result = []
    for _ in range(n_phases):
        seed = int(rng.integers(0, 2**63 - 1))
        while seed == scenario.seed or seed in seeds:
            seed = int(rng.integers(0, 2**63 - 1))
        seeds.add(seed)
        result.append(replace(scenario, seed=seed))
    return result


def choose_label(outcomes):
    """Require <=1% misses in *each* phase; minimize receiver duty thereafter."""
    if set(outcomes) != set(PROFILE_NAMES) or any(len(v) < 3 for v in outcomes.values()):
        raise ValueError("every profile needs at least three phase results")

    def key(name):
        rows = outcomes[name]
        excess = [max(0.0, r["miss_rate"] - .01) for r in rows]
        feasible = all(x <= 1e-12 for x in excess)
        return (0 if feasible else 1, 0.0 if feasible else max(excess),
                0.0 if feasible else float(np.mean(excess)),
                rows[0]["rx_duty"], float(np.mean([r["p99_ms"] for r in rows])),
                PROFILE_NAMES.index(name))

    return min(PROFILE_NAMES, key=key)


def label_scenario(scenario):
    outcomes = {name: [] for name in PROFILE_NAMES}
    for phase in make_phase_scenarios(scenario):
        arrivals = generate_arrivals(phase)
        for profile in PROFILES:
            metrics = simulate(arrivals, profile, phase.packet_service_ms,
                               phase.base_delay_ms, phase.deadline_ms, phase.duration_ms)
            outcomes[profile.name].append({k: metrics[k] for k in ("miss_rate", "rx_duty", "p99_ms")})
    return {"scenario": asdict(scenario), "label": choose_label(outcomes),
            "options": ordered_options(scenario.uid), "phase_seeds": [s.seed for s in make_phase_scenarios(scenario)],
            "outcomes": outcomes}


def label_split(scenarios):
    return [label_scenario(s) for s in scenarios]


def inject_lora(decision_model, rank=4, alpha=8):
    """Attach trainable LoRA to q/v projections in Qwen3.5 full-attention layers."""
    import torch
    from torch import nn
    from torch.nn import functional as F

    class LoRALinear(nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base
            self.lora_A = nn.Parameter(torch.empty(rank, base.in_features, device=base.weight.device))
            self.lora_B = nn.Parameter(torch.zeros(base.out_features, rank, device=base.weight.device))
            nn.init.normal_(self.lora_A, std=.02)

        def forward(self, x):
            update = F.linear(F.linear(x.float(), self.lora_A), self.lora_B)
            return self.base(x) + (update * (alpha / rank)).to(x.dtype)

    for param in decision_model.parameters():
        param.requires_grad_(False)
    replaced = []
    model_root = decision_model.lm.model
    layer_root = getattr(model_root, "language_model", model_root)
    prefix = "lm.model.language_model.layers" if layer_root is not model_root else "lm.model.layers"
    for layer_number in range(3, 24, 4):
        layer = layer_root.layers[layer_number]
        for name in ("q_proj", "v_proj"):
            parent = layer.self_attn
            base = getattr(parent, name)
            if not isinstance(base, nn.Linear):
                raise TypeError(f"unexpected {layer_number}.{name}: {type(base)}")
            setattr(parent, name, LoRALinear(base))
            replaced.append(f"{prefix}.{layer_number}.self_attn.{name}")
    decision_model.lm.config.use_cache = False
    if hasattr(decision_model.lm, "enable_input_require_grads"):
        decision_model.lm.enable_input_require_grads()
    return replaced


def adapter_state(model):
    return {name: param.detach().cpu().contiguous()
            for name, param in model.named_parameters() if ".lora_A" in name or ".lora_B" in name}


def save_adapter(model, path, metadata):
    from safetensors.torch import save_file
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    save_file(adapter_state(model), str(path / "adapter.safetensors"))
    (path / "adapter_config.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def load_adapter(model, path):
    from safetensors.torch import load_file
    path = Path(path)
    cfg = json.loads((path / "adapter_config.json").read_text(encoding="utf-8"))
    names = inject_lora(model, cfg["rank"], cfg["alpha"])
    if names != cfg["targets"]:
        raise ValueError("adapter target mismatch")
    tensor_state = load_file(str(path / "adapter.safetensors"))
    expected = {name: param for name, param in model.named_parameters() if param.requires_grad}
    if set(tensor_state) != set(expected):
        raise ValueError("adapter tensor mismatch")
    for name, tensor in tensor_state.items():
        if tensor.shape != expected[name].shape:
            raise ValueError(f"adapter tensor shape mismatch: {name}")
        expected[name].data.copy_(tensor.to(expected[name].device))
    return cfg
