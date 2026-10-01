"""Compare frozen A3 baselines using packet-level ns-3 outcomes."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


DEFAULT = (3.0, 256)
CALIBRATED_FIXED = (0.0, 0)


def frozen_rule(descriptor: dict) -> tuple[float, int]:
    """Fixed after inspecting exploratory runs 1-2; no outcome/seed input."""
    if (descriptor["trajectory"] == "oscillate"
            and descriptor["speed_mps"] <= 8
            and descriptor["packet_interval_ms"] <= 1):
        return (1.0, 80)
    return CALIBRATED_FIXED


def normalized_geometry_rule(descriptor: dict) -> tuple[float, int]:
    """Frozen after inspecting transfer grid, before fresh_geometry runs."""
    excursion = descriptor["speed_mps"] * descriptor["turn_period_s"] / 2
    if (descriptor["trajectory"] == "oscillate"
            and descriptor["packet_interval_ms"] <= 1
            and excursion / descriptor["cell_spacing_m"] <= 0.033):
        return (1.0, 80)
    return CALIBRATED_FIXED


def summarize(rows: list[dict]) -> dict:
    sent = sum(x["sent"] for x in rows)
    return {
        "cases": len(rows), "sent": sent,
        "received": sum(x["received"] for x in rows),
        "lost": sum(x["lost"] for x in rows),
        "late_received": sum(x["late_received"] for x in rows),
        "deadline_miss_including_loss": sum(x["deadline_miss_including_loss"] for x in rows),
        "deadline_miss_rate": sum(x["deadline_miss_including_loss"] for x in rows) / sent,
        "handover_starts": sum(x["handover_starts"] for x in rows),
        "mean_of_case_p99_delay_ms": sum(x["p99_delay_ms"] for x in rows) / len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--decider", type=Path)
    parser.add_argument("--decider-adapted", type=Path)
    parser.add_argument("--qwen", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()]
    groups = defaultdict(dict)
    for row in records:
        key = (row["case"], row["run"])
        profile = (row["hysteresis_db"], row["ttt_ms"])
        if profile in groups[key]:
            raise ValueError(f"duplicate {key} {profile}")
        groups[key][profile] = row
    if not groups or any(len(g) != 5 for g in groups.values()):
        raise ValueError("incomplete profile sweep")
    option_to_profile = {
        f"A3 hysteresis {int(h)} dB, time-to-trigger {ttt} ms": (float(h), ttt)
        for h, ttt in ((0, 0), (1, 80), (2, 160), (3, 256), (6, 320))
    }
    model_choices = {}
    for name, path, field in (("decider_base", args.decider, "choice"),
                              ("decider_a3_adapter", args.decider_adapted, "choice"),
                              ("qwen_base", args.qwen, "parsed_choice")):
        if path:
            model_choices[name] = {}
            for decision in json.loads(path.read_text(encoding="utf-8")):
                if decision["case"] in model_choices[name]:
                    raise ValueError(f"duplicate {name} case")
                choice = decision[field]
                model_choices[name][decision["case"]] = (
                    option_to_profile[choice] if choice is not None else None)
    selections = defaultdict(list)
    case_studies = []
    for key, by_profile in sorted(groups.items()):
        descriptor = next(iter(by_profile.values()))
        oracle = min(by_profile.values(), key=lambda x: (
            x["deadline_miss_including_loss"], x["lost"], x["handover_starts"]))
        chosen = {
            "3db_256ms_default": by_profile[DEFAULT],
            "0db_0ms_calibrated_fixed": by_profile[CALIBRATED_FIXED],
            "descriptor_rule": by_profile[frozen_rule(descriptor)],
            "geometry_rule_v2": by_profile[normalized_geometry_rule(descriptor)],
            "hindsight_oracle": oracle,
        }
        for name, choices in model_choices.items():
            if choices[key[0]] is not None:
                chosen[name] = by_profile[choices[key[0]]]
        for name, row in chosen.items():
            selections[name].append(row)
        case_studies.append({
            "case": key[0], "run": key[1],
            "chosen_profiles": {name: [row["hysteresis_db"], row["ttt_ms"]]
                                for name, row in chosen.items()},
            "by_profile": [{k: row[k] for k in (
                "hysteresis_db", "ttt_ms", "sent", "received", "lost",
                "late_received", "deadline_miss_including_loss", "mean_delay_ms",
                "p95_delay_ms", "p99_delay_ms", "handover_starts",
                "handover_ends", "handover_failures", "first_handover_start_ms")}
                for row in by_profile.values()],
        })
    report = {
        "source": str(args.input),
        "n_scenario_seed_pairs": len(groups),
        "source_sha256": sorted({r["source_sha256"] for r in records}),
        "selection_rule": "oscillate & speed<=8 m/s & interval<=1 ms -> 1dB/80ms; else 0dB/0ms",
        "geometry_rule_v2": "oscillate & interval<=1 ms & (speed*turnPeriod/2)/cellSpacing<=0.033 -> 1dB/80ms; else 0dB/0ms",
        "summary": {name: summarize(rows) for name, rows in selections.items()},
        "valid_model_choices": {name: sum(x is not None for x in choices.values())
                                for name, choices in model_choices.items()},
        "case_studies": case_studies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
