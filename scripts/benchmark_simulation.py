"""Measure CPU wall time for each frozen test scenario's nine profile simulations."""
import csv
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.simulation import PROFILES, Scenario, generate_arrivals, simulate


def main():
    root = Path('artifacts/experiment')
    scenarios = [Scenario(**row) for row in json.loads((root / 'evaluation_scenarios.json').read_text(encoding='utf-8'))]
    previous = json.loads((root / 'evaluation_metrics.json').read_text(encoding='utf-8'))
    decisions = {row['uid']: row for row in map(json.loads, (root / 'decisions.jsonl').read_text(encoding='utf-8').splitlines())}
    out = []
    for scenario in scenarios:
        trials = []
        packets = 0
        for _ in range(3):
            start = time.perf_counter()
            arrivals = generate_arrivals(scenario)
            packets = len(arrivals)
            for profile in PROFILES:
                measured = simulate(arrivals, profile, scenario.packet_service_ms, scenario.base_delay_ms,
                                    scenario.deadline_ms, scenario.duration_ms)
                for field in ('mean_ms', 'p95_ms', 'p99_ms', 'max_ms', 'miss_rate', 'rx_duty', 'packets'):
                    assert abs(measured[field] - previous[scenario.uid][profile.name][field]) < 1e-9, (scenario.uid, profile.name, field)
            trials.append(1000 * (time.perf_counter() - start))
        out.append({'uid': scenario.uid, 'service': scenario.service,
                    'arrivals_horizon_ms': scenario.duration_ms, 'n_profile_simulations': len(PROFILES),
                    'packets': packets, 'n_decider_requests': 1,
                    'decider_inference_wall_ms': decisions[scenario.uid]['inference_ms'],
                    'simulation_wall_ms_trials': trials, 'simulation_wall_ms_median': statistics.median(trials)})
    dest = Path('artifacts/temperature/per_scenario_timing.json')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'measurement': '3 serial CPU runs, each generating arrivals and evaluating 9 profiles; Python perf_counter',
                                'rows': out}, indent=2) + '\n', encoding='utf-8')
    with (dest.parent / 'per_scenario_timing.csv').open('w', newline='', encoding='utf-8') as stream:
        columns = ['uid', 'service', 'arrivals_horizon_ms', 'packets', 'n_decider_requests',
                   'decider_inference_wall_ms', 'n_profile_simulations', 'simulation_wall_ms_median']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(out)
    print(json.dumps({'n': len(out), 'packets_min_max': [min(r['packets'] for r in out), max(r['packets'] for r in out)],
                      'decider_inference_wall_ms_median': statistics.median(r['decider_inference_wall_ms'] for r in out),
                      'simulation_wall_ms_median_of_scenarios': statistics.median(r['simulation_wall_ms_median'] for r in out),
                      'simulation_wall_ms_max': max(r['simulation_wall_ms_median'] for r in out)}, indent=2))


if __name__ == '__main__':
    main()
