"""Run a fixed, reproducible ns-3 A3 parameter sweep (no model calls)."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


PROFILES = [(0, 0), (1, 80), (2, 160), (3, 256), (6, 320)]


def scenarios() -> list[dict]:
    cases = []
    for speed in (8, 15, 25):
        for interval_ms, packet_bytes in ((10, 200), (1, 1200)):
            cases.append(dict(
                name=f"cross_{speed}_{interval_ms}", trajectory="cross",
                speedMps=speed, startX=-120, turnPeriodS=2,
                cellSpacingM=300, durationS=32,
                packetIntervalMs=interval_ms, packetBytes=packet_bytes,
                deadlineMs=20,
            ))
    for speed, period in ((8, 2), (15, 2), (20, 3)):
        for interval_ms, packet_bytes in ((10, 200), (1, 1200)):
            cases.append(dict(
                name=f"oscillate_{speed}_{period}_{interval_ms}", trajectory="oscillate",
                speedMps=speed, startX=-speed * period / 2, turnPeriodS=period,
                cellSpacingM=300, durationS=24,
                packetIntervalMs=interval_ms, packetBytes=packet_bytes,
                deadlineMs=20,
            ))
    return cases


def generalization_scenarios() -> list[dict]:
    """Different speeds, eNB spacing, and turn periods from the initial grid."""
    cases = []
    for spacing in (200, 450):
        for speed in (10, 18):
            for interval_ms, packet_bytes in ((10, 200), (1, 1200)):
                cases.append(dict(
                    name=f"new_cross_{spacing}_{speed}_{interval_ms}", trajectory="cross",
                    speedMps=speed, startX=-120, turnPeriodS=2,
                    cellSpacingM=spacing, durationS=32,
                    packetIntervalMs=interval_ms, packetBytes=packet_bytes,
                    deadlineMs=20,
                ))
        for speed in (6, 9, 12, 18):
            cases.append(dict(
                name=f"new_oscillate_{spacing}_{speed}_2_1", trajectory="oscillate",
                speedMps=speed, startX=-speed, turnPeriodS=2,
                cellSpacingM=spacing, durationS=24,
                packetIntervalMs=1, packetBytes=1200,
                deadlineMs=20,
            ))
    for speed in (6, 12):
        for interval_ms, packet_bytes in ((10, 200), (1, 1200)):
            cases.append(dict(
                name=f"new_oscillate_300_{speed}_3_{interval_ms}", trajectory="oscillate",
                speedMps=speed, startX=-1.5 * speed, turnPeriodS=3,
                cellSpacingM=300, durationS=24,
                packetIntervalMs=interval_ms, packetBytes=packet_bytes,
                deadlineMs=20,
            ))
    return cases


def adaptation_scenarios() -> list[dict]:
    """A3 adapter labels; disjoint trajectories from both reported test suites."""
    cases = []
    for speed in (4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18):
        for period in (1.5, 2.5):
            cases.append(dict(
                name=f"train_oscillate_{speed}_{period}", trajectory="oscillate",
                speedMps=speed, startX=-speed * period / 2, turnPeriodS=period,
                cellSpacingM=300, durationS=24,
                packetIntervalMs=1, packetBytes=1200, deadlineMs=20,
            ))
    for speed in (6, 11, 20, 30):
        for interval_ms, packet_bytes in ((10, 200), (1, 1200)):
            cases.append(dict(
                name=f"train_cross_{speed}_{interval_ms}", trajectory="cross",
                speedMps=speed, startX=-120, turnPeriodS=2,
                cellSpacingM=300, durationS=32,
                packetIntervalMs=interval_ms, packetBytes=packet_bytes,
                deadlineMs=20,
            ))
    return cases


def fresh_geometry_scenarios() -> list[dict]:
    """Untouched geometry grid for a rule frozen after the first transfer test."""
    cases = []
    period = 2.3
    for spacing in (250, 375, 550):
        for speed in (5, 8, 11, 15, 20):
            cases.append(dict(
                name=f"fresh_oscillate_{spacing}_{speed}", trajectory="oscillate",
                speedMps=speed, startX=-speed * period / 2,
                turnPeriodS=period, cellSpacingM=spacing, durationS=24,
                packetIntervalMs=1, packetBytes=1200, deadlineMs=20,
            ))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", default="1,2")
    parser.add_argument("--suite", choices=("core", "generalization", "adaptation", "fresh_geometry"), default="core")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = hashlib.sha256(args.source.read_bytes()).hexdigest()
    total = 0
    with args.output.open("w", encoding="utf-8") as output:
        for run in [int(x) for x in args.runs.split(",")]:
            for case in {"core": scenarios, "generalization": generalization_scenarios,
                         "adaptation": adaptation_scenarios,
                         "fresh_geometry": fresh_geometry_scenarios}[args.suite]():
                for hysteresis, ttt in PROFILES:
                    argv = [str(args.binary)]
                    fields = {k: v for k, v in case.items() if k != "name"}
                    fields.update(hysteresisDb=hysteresis, tttMs=ttt, run=run)
                    argv += [f"--{k}={v}" for k, v in fields.items()]
                    start = time.perf_counter()
                    proc = subprocess.run(argv, text=True, capture_output=True, timeout=120)
                    if proc.returncode:
                        raise RuntimeError(f"{case['name']} run={run} profile={hysteresis}/{ttt}: {proc.stderr}")
                    result = json.loads(proc.stdout.strip().splitlines()[-1])
                    result.update(case=case["name"], wall_s=time.perf_counter() - start,
                                  source_sha256=source_sha256)
                    output.write(json.dumps(result, sort_keys=True) + "\n")
                    output.flush()
                    total += 1
                    if total % 10 == 0:
                        print(f"completed {total}", flush=True)
    print(f"wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
