"""Frozen paired AGV dispatch-intent UC; no model sees future simulator fields."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_validation.run_sweep import PROFILES

OUT = Path("artifacts/semantic_uc")
INTENTS = [
    ("cross", "One-way transit: continue across the cell boundary toward the destination without returning."),
    ("patrol", "Local patrol: repeatedly move back and forth near the cell boundary, reversing direction."),
]
INTENT_QUESTION = "What future movement does the currently active AGV dispatch order describe?"
POLICY = {"cross": (0, 0), "patrol": (1, 80)}
GEOMETRIES = [(250, 6), (300, 8), (375, 9)]

# A family is a PAIR. Splits are by writing pattern, not by shuffled sentences.
# Both meanings occur in every family and geometry. Frozen before inference.
TEXTS = {
    "train": [
        ("Drive east through the handoff area and continue to the far loading dock.",
         "Patrol the handoff area: drive east, reverse, drive west, and repeat."),
        ("Deliver the crate to the warehouse beyond the boundary. Do not come back during this job.",
         "Inspect the local boundary segment by shuttling between its two ends."),
        ("Proceed across the boundary to the next destination in one direction.",
         "Move back and forth around the boundary for the whole inspection."),
        ("Cross the boundary once, then keep moving east for the rest of the shift segment.",
         "Repeat short east-west passes near the boundary, reversing at each endpoint."),
        ("Leave this area, pass the boundary and finish the delivery at the east dock.",
         "Stay in this area and repeatedly reverse direction around the boundary."),
        ("This is a one-way transit to the next station. Continue east after the boundary.",
         "This is a recurring patrol. Return over the same short boundary segment each time."),
    ],
    "dev": [
        ("Take the pallet past the coverage boundary and onward to receiving; the journey ends there.",
         "Survey this short coverage-boundary stretch repeatedly in alternating directions."),
        ("The assigned route carries the robot from the west side to the east depot with no return leg.",
         "The assigned route is a loop of short out-and-back movements straddling the boundary."),
        ("Keep going east when reaching the cell seam. This job has a remote final stop.",
         "At each end of the local cell-seam inspection strip, turn around and traverse it again."),
    ],
    "test": [
        ("Carry the parcel through the seam to dispatch at the eastern building. Remain there after arrival.",
         "Spend this job sweeping the seam: reach one end, turn around, reach the other, then do it again."),
        ("Navigate to the eastern depot via the seam; it is the final stop of this assignment.",
         "Alternate between the two nearby seam markers until the assignment expires."),
        ("A delivery to the far-side workshop is active. Keep advancing after leaving this local area.",
         "A local inspection is active. Retrace the short path in both directions for its entire duration."),
        ("Old order: local patrol. CANCELLED. Active order: cross the seam and continue to the eastern dock.",
         "Old order: eastbound delivery. CANCELLED. Active order: shuttle repeatedly around the seam."),
        ("Do not shuttle here. Take the cargo across to the remote destination and stay on that side.",
         "Do not depart for the remote dock. Keep making short out-and-back trips in this area."),
        ("The robot's job finishes on the far side; after passing the seam it will not revisit this strip.",
         "The robot's job stays on this strip; after each short leg it heads back to the opposite endpoint."),
        ("Inspection mode is disabled. Current task: a single passage to the facility east of the seam.",
         "Delivery mode is disabled. Current task: repeated sweeps of the local seam in alternating directions."),
        ("Advance into the other cell toward packaging. The itinerary includes no turnaround in this area.",
         "Oscillate between the near-side and far-side markers; neither endpoint is a final destination."),
        ("Supervisor revision: stop repeating the inspection. Now head through the seam to the far dock.",
         "Supervisor revision: stop the trip to the far dock. Now reverse at the local markers over and over."),
        ("For this run, the waypoint sequence goes west, seam, east depot, end of job.",
         "For this run, the waypoint sequence goes west marker, east marker, west marker, east marker, repeatedly."),
    ],
}


def physics_cases():
    result = []
    for geo, (spacing, speed) in enumerate(GEOMETRIES):
        for label in ("cross", "patrol"):
            result.append(dict(name=f"agv_g{geo}_{label}", trajectory="cross" if label == "cross" else "oscillate",
                               speedMps=speed, startX=-speed, turnPeriodS=2,
                               cellSpacingM=spacing, durationS=24,
                               packetIntervalMs=1, packetBytes=1200, deadlineMs=20))
    return result


def make_dataset():
    data = {}
    for split, families in TEXTS.items():
        rows = []
        for family, texts in enumerate(families):
            for geo in range(len(GEOMETRIES)):
                for label, text in zip(("cross", "patrol"), texts):
                    rows.append(dict(id=f"{split}_{family}_{geo}_{label}",
                                     family=f"{split}_{family}", geometry=geo,
                                     label=label, text=text, case=f"agv_g{geo}_{label}"))
        data[split] = rows
    return data


def observed_state(row):
    spacing, speed = GEOMETRIES[row["geometry"]]
    # Whitelist; no route/period/dataset ID, label or KPI oracle.
    return {"initial_x_m": -speed, "initial_velocity_mps": speed,
            "cell_spacing_m": spacing, "initial_serving_cell": "west",
            "packet_interval_ms": 1, "packet_bytes": 1200,
            "deadline_ms": 20, "session_duration_s": 24,
            "dispatch_text": row["text"]}


def rotated(pairs, offset):
    offset %= len(pairs)
    return pairs[offset:] + pairs[:offset]


def decode_choice(choice, pairs):
    matches = [label for label, text in pairs if text == choice]
    if len(matches) != 1:
        raise ValueError(f"invalid or ambiguous choice {choice!r}")
    return matches[0]


def parse_letter_completion(raw, pairs):
    """Allow a legal option-letter prefix followed by its textual description."""
    match = re.match(r"([AB])(?:\)|\s|$)", raw.strip())
    return pairs[ord(match[1])-65][0] if match else None


def validate_simulations(rows, cases, runs):
    expected = {(c["name"], run, h, t) for c in cases for run in runs for h, t in PROFILES}
    actual = [(r["case"], r["run"], r["hysteresis_db"], r["ttt_ms"]) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("missing/duplicate/unexpected simulation realizations")
    for r in rows:
        if r["sent"] != r["received"] + r["lost"] or r["duplicate_packets"] != 0:
            raise ValueError("packet accounting")
        if r["deadline_miss_including_loss"] != r["lost"] + r["late_received"]:
            raise ValueError("deadline accounting")


def keyword(text):
    """Frozen modest baseline from training vocabulary; no test-label fitting."""
    text = text.lower()
    # Latest active instruction supersedes an explicitly cancelled order.
    for marker in ("active order:", "current task:", "now "):
        if marker in text:
            text = text.rsplit(marker, 1)[1]
    patrol = re.findall(r"patrol|shuttl\w*|back and forth|repeat\w*|revers\w*|return|out-and-back", text)
    cross = re.findall(r"deliver\w*|dock|destination|one-way|continue|cross\w*|proceed", text)
    return "patrol" if len(patrol) > len(cross) else "cross"


def simulate(args):
    source = Path("system_validation/ns3_lte_handover.cc")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    with args.output.open("w", encoding="utf-8") as f:
        for case in physics_cases():
            for run in args.runs:
                for h, t in PROFILES:
                    fields = {k: v for k, v in case.items() if k != "name"}
                    fields.update(run=run, hysteresisDb=h, tttMs=t)
                    start = time.perf_counter()
                    p = subprocess.run([args.binary] + [f"--{k}={v}" for k, v in fields.items()],
                                       capture_output=True, text=True, timeout=120, check=True)
                    row = json.loads(p.stdout.strip().splitlines()[-1])
                    row.update(case=case["name"], wall_s=time.perf_counter()-start, source_sha256=sha)
                    f.write(json.dumps(row, sort_keys=True) + "\n")
                    f.flush()
                print(case["name"], run, flush=True)


def infer_decider(args):
    import torch
    from decider.infer import Decider
    from system_validation.decider_a3 import OPTIONS, QUESTION

    torch.set_num_threads(8)
    model = Decider("models/decider-2b", device="cuda", use_graphs=False)
    for _ in range(3):
        model.decide("Warmup route.", [{"question": INTENT_QUESTION, "options": [x[1] for x in INTENTS]}])
    results = []
    for split in ("dev", "test"):
        for i, row in enumerate(make_dataset()[split]):
            context = json.dumps(observed_state(row), separators=(",", ":"))
            for variant in ("semantic", "direct"):
                orders = (0, 1) if variant == "semantic" else (0,)
                for order in orders:
                    pairs = rotated(INTENTS, order) if variant == "semantic" else list(zip(range(5), OPTIONS))
                    question = INTENT_QUESTION if variant == "semantic" else QUESTION
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    answer = model.decide(context, [{"question": question, "options": [p[1] for p in pairs]}])[0]
                    torch.cuda.synchronize()
                    results.append(dict(id=row["id"], variant=variant, order=order,
                                        input=context, question=question, options=pairs,
                                        prediction=decode_choice(answer["choice"], pairs),
                                        answer=answer, inference_ms=1000*(time.perf_counter()-start),
                                        context_tokens=len(model.m.tok.encode("Context:\n"+context, add_special_tokens=False))))
            if (i + 1) % 10 == 0:
                print(split, i+1, flush=True)
    save(args.output, results)


def infer_qwen(args):
    from rrcopt.qwen_baseline import QwenGenerator

    model = QwenGenerator("models/qwen3.5-2b-base")
    model.torch.set_num_threads(8)
    # Two training examples per meaning, same examples for all requests.
    examples = [make_dataset()["train"][i] for i in (0, 1, 6, 7)]
    def prompt(row, pairs):
        lines = [INTENT_QUESTION, "Read the ACTIVE order, not a cancelled or negated one."]
        lines += [f"{i}: {t}" for i, (_, t) in enumerate(pairs)]
        for e in examples:
            j = [p[0] for p in pairs].index(e["label"])
            lines += ["State: " + json.dumps(observed_state(e)), f"Answer: {j}"]
        return "\n".join(lines + ["State: " + json.dumps(observed_state(row)), "Answer: "])
    for _ in range(3):
        model.generate(prompt(examples[0], INTENTS), max_new_tokens=4)
    results = []
    for split in ("dev", "test"):
        for i, row in enumerate(make_dataset()[split]):
            for order in (0, 1):
                pairs = rotated(INTENTS, order)
                matched = ("Context:\n" + json.dumps(observed_state(row), separators=(",", ":"))
                           + "\n\nQuestion: " + INTENT_QUESTION + "\nOptions:"
                           + "".join(f"\n({chr(65+j)}) {t}" for j, (_, t) in enumerate(pairs))
                           + "\nAnswer: (")
                for variant, request in (("fewshot", prompt(row, pairs)), ("matched", matched)):
                    raw, ms, n = model.generate(request, max_new_tokens=4)
                    if variant == "fewshot":
                        match = re.fullmatch(r"[01]\s*", raw)
                        prediction = pairs[int(raw.strip())][0] if match else None
                    else:
                        match = re.fullmatch(r"([AB])\)?\.?\s*", raw)
                        prediction = pairs[ord(match[1])-65][0] if match else None
                    results.append(dict(id=row["id"], variant=variant, order=order, input=request,
                                        raw=raw, prediction=prediction, inference_ms=ms, output_tokens=n,
                                        input_tokens=len(model.tokenizer.encode(request, add_special_tokens=False))))
            if (i+1) % 10 == 0:
                print(split, i+1, flush=True)
    save(args.output, results)


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("dataset", "simulate", "decider", "qwen"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--binary", default="/home/qinyi/rrc-ns3/rrc-handover")
    p.add_argument("--runs", default="101,102,103,104,105")
    args = p.parse_args()
    args.runs = [int(x) for x in args.runs.split(",")]
    if args.action == "dataset":
        save(args.output, {"dataset": make_dataset(), "physics": physics_cases(),
                           "intent_options": INTENTS, "policy": POLICY,
                           "protocol": "Frozen family split; paired numeric states; pre-session decision."})
    elif args.action == "simulate":
        simulate(args)
    elif args.action == "decider":
        infer_decider(args)
    else:
        infer_qwen(args)


if __name__ == "__main__":
    main()
