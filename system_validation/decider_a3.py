"""Evaluate the unmodified Decider Choice head on ns-3 A3 scene descriptors."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system_validation.run_sweep import PROFILES, scenarios

OPTIONS = [f"A3 hysteresis {h} dB, time-to-trigger {ttt} ms" for h, ttt in PROFILES]
QUESTION = (
    "Select one LTE RRC Event A3 handover configuration before this session starts. "
    "Hysteresis is the RSRP margin required before switching to a neighbour; "
    "time-to-trigger is how long that condition must hold. "
    "Prioritize the lowest fraction of UDP packets arriving after the 20 ms deadline "
    "or lost; repeated unnecessary handovers may also disrupt packets. Which configuration?"
)


def state(case: dict) -> str:
    observed = {k: v for k, v in case.items() if k != "name"}
    return (
        "LTE FDD, two eNBs with X2 and EPC, one moving UE and downlink UDP. "
        "The initial serving eNB is left of the origin; the other is right. "
        "Cross means the UE moves left to right; oscillate means its direction "
        "reverses every turnPeriodS. The packet stream runs after attachment. "
        "Choose from the fixed A3 configurations using only these pre-session descriptors: "
        + json.dumps(observed, separators=(",", ":"))
    )


def main() -> None:
    import torch
    from decider.infer import Decider

    model = Decider("models/decider-2b", device="cuda", use_graphs=False)
    model.decide("Warmup.", [{"question": "Which?", "options": ["a", "b"]}])
    torch.cuda.synchronize()
    output = []
    for case in scenarios():
        start = time.perf_counter()
        answer = model.decide(state(case), [{"question": QUESTION, "options": OPTIONS}])[0]
        torch.cuda.synchronize()
        output.append({
            "case": case["name"], "state": state(case), "question": QUESTION,
            "options": OPTIONS, "choice": answer["choice"], "probs": answer["probs"],
            "inference_ms": (time.perf_counter() - start) * 1000,
        })
        print(case["name"], answer["choice"], flush=True)
    dest = Path("artifacts/system_validation/decider_a3_base.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
