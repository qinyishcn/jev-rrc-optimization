"""Intervene on A3 representation, supplied knowledge, and option order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_validation.decider_a3 import OPTIONS, QUESTION, state
from system_validation.run_sweep import scenarios
from system_validation.semantic_uc import INTENTS, INTENT_QUESTION, decode_choice, rotated, save

KNOWLEDGE = (
    " Calibration rule from earlier independent simulations: for a single crossing, "
    "use 0 dB and 0 ms to avoid delaying handover. For repeated local patrols with "
    "packetIntervalMs <= 1 and speedMps*turnPeriodS/(2*cellSpacingM) <= 0.033, "
    "use 1 dB and 80 ms to suppress ping-pong. Otherwise use 0 dB and 0 ms."
)


def context(case, variant):
    raw = state(case)
    if variant == "raw":
        return raw
    if variant == "derived":
        feature = dict(movement="one-way crossing" if case["trajectory"] == "cross" else "repeated local patrol",
                       half_swing_over_cell_spacing=case["speedMps"]*case["turnPeriodS"]/(2*case["cellSpacingM"]))
        return raw + " Derived motion features: " + json.dumps(feature)
    if variant == "knowledge":
        return raw + KNOWLEDGE
    raise ValueError(variant)


def main():
    import torch
    from decider.infer import Decider

    p = argparse.ArgumentParser()
    p.add_argument("--adapter", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    torch.set_num_threads(8)
    model = Decider("models/decider-2b", device="cuda", use_graphs=False)
    if args.adapter:
        from rrcopt.domain_training import load_adapter
        load_adapter(model.m, args.adapter)
        model.m.eval()
    for _ in range(3):
        model.decide("Warmup.", [{"question": "Which?", "options": ["a", "b"]}])
    rows = []
    for case in scenarios():
        for variant in ("raw", "derived", "knowledge", "route_control"):
            # Route control is an easier component, not an A3 output.
            pairs = INTENTS if variant == "route_control" else list(zip(range(5), OPTIONS))
            text = state(case) if variant == "route_control" else context(case, variant)
            question = INTENT_QUESTION if variant == "route_control" else QUESTION
            for order in range(len(pairs)):
                opts = rotated(pairs, order)
                torch.cuda.synchronize()
                start = time.perf_counter()
                answer = model.decide(text, [{"question": question, "options": [x[1] for x in opts]}])[0]
                torch.cuda.synchronize()
                rows.append(dict(case=case["name"], variant=variant, order=order, input=text,
                                 question=question, options=opts, prediction=decode_choice(answer["choice"], opts),
                                 answer=answer, inference_ms=1000*(time.perf_counter()-start),
                                 context_tokens=len(model.m.tok.encode("Context:\n"+text, add_special_tokens=False))))
        print(case["name"], flush=True)
    save(args.output, {"adapter": str(args.adapter), "temperature": model.T, "rows": rows})


if __name__ == "__main__":
    main()
