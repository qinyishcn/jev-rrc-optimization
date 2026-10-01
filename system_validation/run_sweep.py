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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", default="1,2")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = hashlib.sha256(args.source.read_bytes()).hexdigest()
    total = 0
    with args.output.open("w", encoding="utf-8") as output:
        for run in [int(x) for x in args.runs.split(",")]:
            for case in scenarios():
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
