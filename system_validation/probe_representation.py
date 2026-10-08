"""Equivalent movement facts with versus without distracting definitions."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_validation.decider_a3 import OPTIONS, QUESTION, state
from system_validation.diagnose_a3 import KNOWLEDGE
from system_validation.run_sweep import scenarios
from system_validation.semantic_uc import INTENTS, rotated, decode_choice, save


def main():
    import torch
    from decider.infer import Decider

    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    torch.set_num_threads(8)
    m = Decider("models/decider-2b", device="cuda", use_graphs=False)
    for _ in range(3):
        m.decide("Warmup.", [{"question": "Which?", "options": ["a", "b"]}])
    rows = []
    for case in scenarios():
        facts = {k: v for k, v in case.items() if k != "name"}
        movement = ("The UE travels in one direction from west to east across the boundary and keeps going."
                    if case["trajectory"] == "cross" else
                    "The UE repeatedly moves back and forth near the boundary, reversing at each end.")
        for variant, text in [
            ("definitions_json", state(case)),
            ("json_only", json.dumps(facts)),
            ("plain_movement", movement + " Session parameters: " + json.dumps(facts)),
            ("plain_with_rule", movement + " Session parameters: " + json.dumps(facts) + KNOWLEDGE),
        ]:
            for task in ("route", "a3"):
                pairs = INTENTS if task == "route" else list(zip(range(5), OPTIONS))
                question = "How will this UE move during this session?" if task == "route" else QUESTION
                for order in ((0, 1) if task == "route" else (0,)):
                    opts = rotated(pairs, order)
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    answer = m.decide(text, [{"question": question, "options": [x[1] for x in opts]}])[0]
                    torch.cuda.synchronize()
                    rows.append(dict(case=case["name"], variant=variant, task=task, order=order,
                                     input=text, question=question, options=opts,
                                     prediction=decode_choice(answer["choice"], opts), answer=answer,
                                     inference_ms=1000*(time.perf_counter()-start)))
        print(case["name"], flush=True)
    save(args.output, rows)


if __name__ == "__main__":
    main()
