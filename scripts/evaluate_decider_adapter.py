"""One-time held-out evaluation of a frozen RRC adapter through Decider API."""
import argparse
import gc
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rrcopt.domain_training import TEST_SEED, load_adapter, split_hash
from rrcopt.simulation import PROFILES, generate_arrivals, generate_scenarios, simulate
from rrcopt.policies import OPTIONS, QUESTION, context, eligible, guard_choice
from rrcopt.provenance import file_hash
from scripts.run_experiment import summarize, save

OUT = Path("artifacts/adaptation")
ADAPTER = Path("models/decider-rrc-adapter")
FRESH_SEED = 26093013


def fresh_decisions(model, scenarios, current_mac, path):
    import torch
    saved = []
    for idx, scenario in enumerate(scenarios):
        options = OPTIONS.copy()
        random.Random(8171 + idx).shuffle(options)
        state = context(scenario, current_mac)
        started = time.perf_counter()
        answer = model.decide(state, [{"question": QUESTION, "options": options}])[0]
        torch.cuda.synchronize()
        probs = answer["probs"]
        if (set(probs) != set(options) or not np.all(np.isfinite(list(probs.values())))
                or abs(sum(probs.values()) - 1) > 1e-5 or answer["choice"] not in options):
            raise ValueError("invalid fresh Decider probabilities")
        saved.append({"uid": scenario.uid, "state": state, "question": QUESTION,
                      "options": options, "result": answer,
                      "inference_ms": 1000 * (time.perf_counter() - started)})
        if (idx + 1) % 10 == 0:
            save(path, saved)
            print(f"{path.name}: {idx+1}/{len(scenarios)}", flush=True)
    return saved


def run_fresh(manifest, train_result, rescore_only=False):
    """Fresh confirmatory seed is scored only after adapter and settings freeze."""
    import torch
    from decider.infer import Decider

    scenarios = generate_scenarios(30, FRESH_SEED)
    if {s.uid for s in scenarios} & {s.uid for s in generate_scenarios(30, TEST_SEED)}:
        raise ValueError("fresh seed overlaps reused evaluation")
    save(OUT / "fresh_design.json", {
        "seed": FRESH_SEED, "descriptor_sha256": split_hash(scenarios),
        "n_scenarios": len(scenarios), "adapter_sha256": train_result["adapter_sha256"],
        "train_labels_sha256": train_result["train_label_sha256"],
        "question": QUESTION, "option_order_seed": 8171,
        "role": "fresh confirmatory, no model or threshold selection",
    })
    if rescore_only:
        adapted = json.loads((OUT / "fresh_adapter_decisions.json").read_text(encoding="utf-8"))
        original = json.loads((OUT / "fresh_base_decisions.json").read_text(encoding="utf-8"))
    else:
        model = Decider("models/decider-2b", device="cuda", use_graphs=False)
        load_adapter(model.m, ADAPTER)
        model.m.eval()
        model.decide("Warmup invoice.", [{"question": "Which?", "options": ["billing", "sales"]}])
        torch.cuda.synchronize()
        adapted = fresh_decisions(model, scenarios, manifest["current_mac"], OUT / "fresh_adapter_decisions.json")
        del model
        gc.collect()
        torch.cuda.empty_cache()
        base = Decider("models/decider-2b", device="cuda", use_graphs=False)
        base.decide("Warmup invoice.", [{"question": "Which?", "options": ["billing", "sales"]}])
        torch.cuda.synchronize()
        original = fresh_decisions(base, scenarios, manifest["current_mac"], OUT / "fresh_base_decisions.json")
        del base
        gc.collect()
        torch.cuda.empty_cache()

    if ([x["uid"] for x in original] != [s.uid for s in scenarios]
            or [x["uid"] for x in adapted] != [s.uid for s in scenarios]):
        raise ValueError("fresh decision descriptors do not match")
    for idx, scenario in enumerate(scenarios):
        expected_options = OPTIONS.copy()
        random.Random(8171 + idx).shuffle(expected_options)
        expected_state = context(scenario, manifest["current_mac"])
        for item in (original[idx], adapted[idx]):
            probs = item["result"]["probs"]
            if (item["options"] != expected_options or item["state"] != expected_state
                    or item["question"] != QUESTION or set(probs) != set(expected_options)
                    or not np.all(np.isfinite(list(probs.values())))
                    or abs(sum(probs.values()) - 1) > 1e-5
                    or item["result"]["choice"] not in expected_options):
                raise ValueError(f"invalid saved fresh decision: {scenario.uid}")

    rows = []
    for scenario, base_decision, adapted_decision in zip(scenarios, original, adapted):
        arrivals = generate_arrivals(scenario)
        outcome = {p.name: simulate(arrivals, p, scenario.packet_service_ms, scenario.base_delay_ms,
                                    scenario.deadline_ms, scenario.duration_ms) for p in PROFILES}
        for method, choice, elapsed in (
            ("decider_base", base_decision["result"]["choice"], base_decision["inference_ms"]),
            ("decider_base_screened", max(eligible(scenario), key=base_decision["result"]["probs"].__getitem__), base_decision["inference_ms"]),
            ("decider_adapter", adapted_decision["result"]["choice"], adapted_decision["inference_ms"]),
            ("decider_adapter_screened", max(eligible(scenario), key=adapted_decision["result"]["probs"].__getitem__), adapted_decision["inference_ms"]),
            ("guard_only", guard_choice(scenario), 0.0),
        ):
            rows.append({"uid": scenario.uid, "service": scenario.service,
                         "deadline_ms": scenario.deadline_ms, "method": method,
                         "profile": choice, "inference_ms": elapsed, **outcome[choice]})
    save(OUT / "fresh_rows.json", rows)
    save(OUT / "fresh_summary.json", summarize(rows))
    lookup = {(r["uid"], r["method"]): r for r in rows}
    comparisons = []
    for method, baselines in (("decider_adapter", ("decider_base", "guard_only")),
                              ("decider_adapter_screened", ("decider_base_screened", "guard_only"))):
        for baseline in baselines:
            for metric in ("p99_ms", "miss_rate", "rx_duty", "scenario_violation"):
                def value(uid, name):
                    row = lookup[(uid, name)]
                    return float(row["miss_rate"] > .01) if metric == "scenario_violation" else row[metric]
                delta = np.array([value(s.uid, baseline) - value(s.uid, method) for s in scenarios])
                rng = np.random.default_rng(26093019)
                means = []
                for service in ("industrial_control", "xr", "gaming"):
                    vals = np.array([delta[i] for i, s in enumerate(scenarios) if s.service == service])
                    means.append(vals[rng.integers(0, len(vals), size=(2000, len(vals)))].mean(axis=1))
                comparisons.append({"method": method, "baseline": baseline, "metric": metric,
                                    "baseline_minus_adapter": float(delta.mean()),
                                    "ci95": np.quantile(np.mean(means, axis=0), [.025, .975]).tolist()})
    save(OUT / "fresh_comparisons.json", comparisons)
    save(OUT / "fresh_status.json", {
        "state": "complete", "seed": FRESH_SEED, "n_scenarios": len(scenarios),
        "adapter_sha256": train_result["adapter_sha256"],
        "base_decisions_sha256": file_hash(OUT / "fresh_base_decisions.json"),
        "adapter_decisions_sha256": file_hash(OUT / "fresh_adapter_decisions.json"),
        "rows_sha256": file_hash(OUT / "fresh_rows.json"),
        "summary_sha256": file_hash(OUT / "fresh_summary.json"),
        "comparisons_sha256": file_hash(OUT / "fresh_comparisons.json"),
        "simulation_source_sha256": file_hash("rrcopt/simulation.py"),
        "screen_source_sha256": file_hash("rrcopt/policies.py"),
    })
    print("FRESH_CONFIRMATORY_EVALUATED", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-only", action="store_true")
    parser.add_argument("--fresh-rescore-only", action="store_true")
    args = parser.parse_args()
    import torch
    from decider.infer import Decider

    manifest = json.loads((OUT / "split_manifest.json").read_text(encoding="utf-8"))
    result = json.loads((OUT / "train_result.json").read_text(encoding="utf-8"))
    if result["train_label_sha256"] != file_hash(OUT / "train_labels.jsonl"):
        raise ValueError("training labels changed after adapter fit")
    if result["adapter_sha256"] != file_hash(ADAPTER / "adapter.safetensors"):
        raise ValueError("adapter changed after training")
    if result["base_weights_sha256"] != file_hash("models/decider-2b/model.safetensors"):
        raise ValueError("base model changed after training")
    test = generate_scenarios(30, TEST_SEED)
    if split_hash(test) != manifest["held_out_test_descriptor_sha256"]:
        raise ValueError("held-out descriptor hash changed")
    original = json.loads(Path("artifacts/experiment/evaluation_scenarios.json").read_text(encoding="utf-8"))
    if original != [s.__dict__ for s in test]:
        raise ValueError("test is not the prior paired set")
    outcomes = json.loads(Path("artifacts/experiment/evaluation_metrics.json").read_text(encoding="utf-8"))
    existing_rows = json.loads(Path("artifacts/experiment/rows.json").read_text(encoding="utf-8"))

    if args.fresh_only or args.fresh_rescore_only:
        run_fresh(manifest, result, rescore_only=args.fresh_rescore_only)
        return

    torch.set_num_threads(8)
    model = Decider("models/decider-2b", device="cuda", use_graphs=False)
    adapter_cfg = load_adapter(model.m, ADAPTER)
    model.m.eval()
    # Warmup is excluded from steady-state decision latency.
    model.decide("A duplicate invoice charge needs correction.",
                 [{"question": "Which team?", "options": ["billing", "technical"]}])
    torch.cuda.synchronize()
    decisions, rows = [], []
    for idx, scenario in enumerate(test):
        options = OPTIONS.copy()
        random.Random(8171 + idx).shuffle(options)  # identical to base Decider evaluation
        state = context(scenario, manifest["current_mac"])
        started = time.perf_counter()
        answer = model.decide(state, [{"question": QUESTION, "options": options}])[0]
        torch.cuda.synchronize()
        inference_ms = 1000 * (time.perf_counter() - started)
        probs = answer["probs"]
        if (set(probs) != set(options) or not np.all(np.isfinite(list(probs.values())))
                or abs(sum(probs.values()) - 1) > 1e-5):
            raise ValueError("invalid adapted Decider probabilities")
        screened = max(eligible(scenario), key=probs.__getitem__)
        decisions.append({"uid": scenario.uid, "state": state, "question": QUESTION,
                          "options": options, "raw": answer["choice"],
                          "screened": screened, "probs": probs, "inference_ms": inference_ms})
        for method, name in (("decider_adapter_raw", answer["choice"]),
                             ("decider_adapter_screened", screened)):
            rows.append({"uid": scenario.uid, "service": scenario.service,
                         "deadline_ms": scenario.deadline_ms, "method": method,
                         "profile": name, "inference_ms": inference_ms,
                         **outcomes[scenario.uid][name]})
        if (idx + 1) % 10 == 0:
            save(OUT / "test_decisions.json", decisions)
            print(f"{idx+1}/{len(test)} held-out decisions", flush=True)
    save(OUT / "test_rows.json", rows)
    save(OUT / "test_summary.json", summarize(rows))

    lookup = {(r["uid"], r["method"]): r for r in existing_rows + rows}
    comparisons = []
    for method in ("decider_adapter_raw", "decider_adapter_screened"):
        for baseline in ("decider_raw", "decider_screened", "guard_only", "calibrated_per_service"):
            for metric in ("p99_ms", "miss_rate", "rx_duty", "scenario_violation"):
                def value(uid, name):
                    row = lookup[(uid, name)]
                    return float(row["miss_rate"] > .01) if metric == "scenario_violation" else row[metric]
                delta = np.array([value(s.uid, baseline) - value(s.uid, method) for s in test])
                rng = np.random.default_rng(26093019)
                group_means = []
                for svc in ("industrial_control", "xr", "gaming"):
                    values = np.array([delta[i] for i, s in enumerate(test) if s.service == svc])
                    group_means.append(values[rng.integers(0, len(values), size=(2000, len(values)))].mean(axis=1))
                means = np.mean(group_means, axis=0)
                comparisons.append({"method": method, "baseline": baseline, "metric": metric,
                                    "baseline_minus_adapter": float(delta.mean()),
                                    "ci95": np.quantile(means, [.025, .975]).tolist()})
    save(OUT / "test_comparisons.json", comparisons)
    save(OUT / "test_status.json", {"state": "complete", "test_seed": TEST_SEED,
                                    "n_scenarios": len(test), "adapter_sha256": result["adapter_sha256"],
                                    "source_labels": result["train_label_sha256"],
                                    "decisions_sha256": file_hash(OUT / "test_decisions.json"),
                                    "rows_sha256": file_hash(OUT / "test_rows.json"),
                                    "summary_sha256": file_hash(OUT / "test_summary.json"),
                                    "comparisons_sha256": file_hash(OUT / "test_comparisons.json"),
                                    "simulation_source_sha256": file_hash("rrcopt/simulation.py"),
                                    "screen_source_sha256": file_hash("rrcopt/policies.py")})
    print("ADAPTER_EVALUATED", flush=True)


if __name__ == "__main__":
    main()
