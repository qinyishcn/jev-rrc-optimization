"""Second frozen language-family test, including a matched one-pass Base control.

Pilot test labels may now train the classical classifier; confirmation labels
are never used. Physics and intent-to-policy mapping remain unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_validation.semantic_uc import INTENTS, INTENT_QUESTION, make_dataset, observed_state, rotated, decode_choice, save

PAIRS = [
    ("Transport the package to the building east of the coverage seam and terminate the mission there.",
     "Measure coverage along the seam by retracing this local strip continuously from end to end."),
    ("Only the eastbound leg is scheduled; the vehicle will remain at the receiving station afterwards.",
     "Both eastbound and westbound legs are scheduled repeatedly inside this small inspection strip."),
    ("The local inspection has finished. The remaining task is to travel across to the eastern warehouse.",
     "The distant delivery has been withdrawn. The remaining task is to traverse the local strip in alternating directions."),
    ("Although this robot normally patrols locally, today's assignment sends it onward into the eastern cell.",
     "Although this robot normally serves the distant dock, today's assignment keeps it pacing around the seam."),
    ("If inspection were requested it would reverse here, but inspection is not requested. It must proceed to the far depot.",
     "If delivery were requested it would leave this area, but delivery is not requested. It must shuttle on this strip."),
    ("New instruction superseding the earlier shuttle plan: make a single trip to the east-side packing station.",
     "New instruction superseding the earlier depot trip: repeatedly turn around at the two nearby seam markers."),
    ("The route has one terminal waypoint beyond the cell seam, with no scheduled movement back into this area.",
     "The route has alternating local waypoints on opposite sides of the seam, with neither designated as terminal."),
    ("Finish carrying the tote across the boundary and wait in the east depot once the trip is complete.",
     "Keep inspecting the boundary by traversing the same short stretch first eastward and then westward."),
    ("Delivery to the remote station remains enabled; local return sweeps have been disabled for this session.",
     "Local return sweeps remain enabled; delivery to the remote station has been disabled for this session."),
    ("Proceed beyond the seam. References to reversing in the archived route are obsolete.",
     "Reverse at the nearby markers. References to proceeding to a remote dock in the archived route are obsolete."),
    ("For the next twenty-four seconds keep moving east beyond this cell junction, without a local return journey.",
     "For the next twenty-four seconds keep moving in alternating directions across this short cell junction."),
    ("The active waypoint list ends at the east warehouse after passing the cell junction exactly once.",
     "The active waypoint list cycles between the west and east ends of a short junction segment."),
    ("Pass the junction toward the distant workshop. The mission never instructs a turn back at a local marker.",
     "Turn back at every local endpoint around the junction. The mission never instructs leaving for the distant workshop."),
    ("This shift segment transfers material out of the current area into the eastern facility.",
     "This shift segment surveys the current area using recurring short passes in opposing directions."),
    ("Carry out the final leg to the far receiving area; the formerly repeated inspection is complete.",
     "Carry out repeated local inspection legs; the formerly planned final trip to receiving is cancelled."),
    ("Advance east after the seam and stay away from this strip until the session is over.",
     "Stay near the seam and alternate your heading after every short leg until the session is over."),
    ("The supervisor confirms a one-direction relocation past the boundary into the adjacent cell.",
     "The supervisor confirms recurring traversals in both directions around the boundary of the adjacent cells."),
    ("Take the load over the seam and conclude the route on the opposite side.",
     "Take successive short trips over the seam in opposite directions without concluding at either end."),
    ("Return to the western marker is prohibited; keep travelling toward the eastern receiving bay.",
     "Departure for the eastern receiving bay is prohibited; keep returning across the local inspection strip."),
    ("The next leg is west-to-east through the seam, followed by termination at the eastern facility.",
     "The next legs are west-to-east, east-to-west, and so on, all confined to this short seam segment."),
    ("Continue to the other cell's destination. The note about shuttling describes a different robot.",
     "Continue shuttling between the local endpoints. The note about the remote destination describes a different robot."),
    ("Despite the word patrol in the job title, the operative order sends this AGV through to the eastern depot.",
     "Despite the word delivery in the job title, the operative order sends this AGV back across the same short strip repeatedly."),
    ("This AGV has a terminal eastward route. Another AGV handles the recurring boundary patrol.",
     "This AGV has a recurring boundary patrol. Another AGV handles the terminal eastward route."),
    ("Cross the seam to the distant station. Do not execute the obsolete back-and-forth inspection.",
     "Inspect back and forth at the seam. Do not execute the obsolete crossing to the distant station."),
]


def confirmation():
    rows = []
    for family, pair in enumerate(PAIRS):
        for geometry in range(3):
            for label, text in zip(("cross","patrol"), pair):
                rows.append(dict(id=f"confirm_{family}_{geometry}_{label}", family=f"confirm_{family}",
                                 geometry=geometry, text=text, label=label, case=f"agv_g{geometry}_{label}"))
    pilot = make_dataset()
    return {"train":pilot["train"]+pilot["test"], "dev":pilot["dev"], "test":rows}


def improved_keyword(text):
    """Post-pilot engineering, frozen before the confirmation inference.

    Deliberately finite vocabulary and cancellation/negation handling; no list
    of confirmation answers, no IDs, no trajectory/packet oracle.
    """
    text = text.lower()
    for marker in ("active order:", "current task:", "now "):
        if marker in text:
            text = text.rsplit(marker, 1)[1]
    text = re.sub(r"do not[^.]*\.", "", text)
    text = re.sub(r"[^.]*mode is disabled\.", "", text)
    patrol = re.findall(r"patrol|shuttl\w*|back.and.forth|repeat\w*|revers\w*|return|out.and.back|sweep\w*|alternat\w*|retrac\w*|oscillat\w*|over and over",text)
    cross = re.findall(r"deliver\w*|dock|destination|one.way|continue|cross\w*|proceed|far.side|far side|far dock|east depot",text)
    return "patrol" if len(patrol)>len(cross) else "cross"


def infer(args):
    import torch
    from decider.infer import Decider

    torch.set_num_threads(8)
    model = Decider(args.model, device="cuda", use_graphs=False)
    data = confirmation()
    frozen = json.loads(Path("artifacts/semantic_uc/confirmation_dataset.json").read_text(encoding="utf-8"))
    assert frozen == data
    for _ in range(3):
        model.decide("The vehicle keeps moving east to a remote destination.",
                     [{"question":INTENT_QUESTION,"options":[x[1] for x in INTENTS]}])
    rows = []
    # Pilot is evaluated too for the Base-only control. Decider's existing pilot
    # results remain untouched and are used as that comparator.
    suites = [("confirmation",data["test"])]
    if args.include_pilot:
        suites.insert(0,("pilot",make_dataset()["test"]))
    for suite, cases in suites:
        for i,row in enumerate(cases):
            context = json.dumps(observed_state(row),separators=(",",":"))
            for order in (0,1):
                pairs = rotated(INTENTS,order)
                torch.cuda.synchronize()
                start = time.perf_counter()
                answer = model.decide(context,[{"question":INTENT_QUESTION,"options":[x[1] for x in pairs]}])[0]
                torch.cuda.synchronize()
                # Exact prompt size (right-padding is part of Decider's API).
                _,items=model._decide_items([(context,[{"question":INTENT_QUESTION,"options":[x[1] for x in pairs]}])])
                rows.append(dict(id=row["id"],suite=suite,order=order,model=args.model,
                                 input=context,question=INTENT_QUESTION,options=pairs,
                                 prediction=decode_choice(answer["choice"],pairs),answer=answer,
                                 inference_ms=1000*(time.perf_counter()-start),prompt_tokens=len(items[0]["ids"])))
            if (i+1)%24 == 0:
                print(suite,i+1,flush=True)
    save(args.output,rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","infer"))
    p.add_argument("--model",default="models/decider-2b")
    p.add_argument("--include-pilot",action="store_true")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.action=="freeze":
        save(args.output,confirmation())
    else:
        infer(args)


if __name__=="__main__":
    main()
