"""Check ns-3 result completeness, provenance, and packet accounting."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "artifacts" / "system_validation"
SOURCE = ROOT / "system_validation" / "ns3_lte_handover.cc"
PROFILES = {(0.0, 0), (1.0, 80), (2.0, 160), (3.0, 256), (6.0, 320)}


def verify(name: str, expected_runs: set[int]) -> None:
    rows = [json.loads(x) for x in (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
    groups = defaultdict(set)
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    for row in rows:
        assert row["source_sha256"] == digest
        assert row["run"] in expected_runs
        assert row["duplicate_packets"] == 0
        assert row["sent"] == row["received"] + row["lost"]
        assert row["deadline_miss_including_loss"] == row["lost"] + row["late_received"]
        assert row["late_received"] <= row["received"]
        assert row["handover_starts"] >= row["handover_ends"]
        assert row["handover_failures"] == 0
        profile = (row["hysteresis_db"], row["ttt_ms"])
        assert profile not in groups[(row["case"], row["run"])]
        groups[(row["case"], row["run"])].add(profile)
    assert len(groups) == 12 * len(expected_runs)
    assert all(value == PROFILES for value in groups.values())
    print(name, len(rows), "rows", len(groups), "complete scenario-seed pairs")


if __name__ == "__main__":
    verify("exploratory", {1, 2})
    verify("holdout", {11, 12, 13, 14, 15})
    decider = json.loads((DATA / "decider_a3_base.json").read_text(encoding="utf-8"))
    qwen = json.loads((DATA / "qwen_a3_base.json").read_text(encoding="utf-8"))
    assert len(decider) == len(qwen) == 12
    assert {x["case"] for x in decider} == {x["case"] for x in qwen}
    assert all(x["choice"] in x["options"] for x in decider)
    assert all(x["valid"] for x in qwen)
    print("MODEL_CHOICE_EVIDENCE_OK")
