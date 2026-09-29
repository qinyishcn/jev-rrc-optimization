"""Fit Choice temperature and a guard fallback on calibration; score frozen test."""
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.policies import OPTIONS, cost, eligible, guard_choice
from rrcopt.simulation import Scenario
from rrcopt.temperature import choose_with_fallback, rescale

BASE_T = 1.164
TEMPERATURES = [0.5, 0.75, 1.0, BASE_T, 1.5, 2.0, 3.0, 4.0]
THRESHOLDS = [0.0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def load_split(name):
    root = Path('artifacts/experiment')
    path = (Path('artifacts/temperature/calibration_decisions.jsonl') if name == 'calibration'
            else root / 'decisions.jsonl')
    scenarios = {row['uid']: Scenario(**row) for row in json.loads((root / f'{name}_scenarios.json').read_text(encoding='utf-8'))}
    metrics = json.loads((root / f'{name}_metrics.json').read_text(encoding='utf-8'))
    decisions = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        decisions[row['uid']] = row
    if set(scenarios) != set(decisions) or set(scenarios) != set(metrics):
        raise ValueError(f'Incomplete {name} evidence')
    return scenarios, metrics, decisions


def oracle(scenario, outcomes):
    return min(OPTIONS, key=lambda profile: cost(outcomes[profile], scenario.deadline_ms))


def evaluate(split, temperature, threshold=None):
    scenarios, metrics, decisions = split
    records = []
    for uid, scenario in scenarios.items():
        probs = rescale(decisions[uid]['result']['probs'], BASE_T, temperature)
        choice = max(probs, key=probs.__getitem__)
        if threshold is not None:
            fallback = guard_choice(scenario)
            choice = (choose_with_fallback(probs, threshold, fallback)
                      if choice in eligible(scenario) else fallback)
        result = metrics[uid][choice]
        records.append({'uid': uid, 'service': scenario.service, 'choice': choice,
                        'confidence': probs[choice], 'miss_rate': result['miss_rate'],
                        'p99_ms': result['p99_ms'], 'rx_duty': result['rx_duty'],
                        'violates': result['miss_rate'] > 0.01 + 1e-12})
    return {'n': len(records), 'scenario_violations': sum(r['violates'] for r in records),
            'mean_miss_rate': statistics.mean(r['miss_rate'] for r in records),
            'mean_p99_ms': statistics.mean(r['p99_ms'] for r in records),
            'mean_rx_duty': statistics.mean(r['rx_duty'] for r in records),
            'records': records}


def main():
    calibration = load_split('calibration')
    evaluation = load_split('evaluation')
    labels = {uid: oracle(scenario, calibration[1][uid]) for uid, scenario in calibration[0].items()}
    table = []
    for temperature in TEMPERATURES:
        nll = statistics.mean(-math.log(max(rescale(calibration[2][uid]['result']['probs'], BASE_T, temperature)[label], 1e-300))
                              for uid, label in labels.items())
        cal_raw = evaluate(calibration, temperature)
        test_raw = evaluate(evaluation, temperature)
        table.append({'temperature': temperature, 'calibration_oracle_nll': nll,
                      'calibration_raw': {k: v for k, v in cal_raw.items() if k != 'records'},
                      'test_raw': {k: v for k, v in test_raw.items() if k != 'records'}})
    best_temperature = min(table, key=lambda row: row['calibration_oracle_nll'])['temperature']
    candidates = []
    for threshold in THRESHOLDS:
        result = evaluate(calibration, best_temperature, threshold)
        candidates.append({'threshold': threshold, **{k: v for k, v in result.items() if k != 'records'}})
    # Predeclared safety condition: no calibration scenario > 1% late packets.
    safe = [row for row in candidates if row['scenario_violations'] == 0]
    chosen = min(safe or candidates,
                 key=lambda row: (row['scenario_violations'], row['mean_rx_duty'], row['mean_p99_ms'], row['threshold']))
    test_gated = evaluate(evaluation, best_temperature, chosen['threshold'])
    output = {'base_temperature': BASE_T, 'temperature_grid': table,
              'selected_temperature': best_temperature, 'threshold_grid': candidates,
              'selected_threshold': chosen['threshold'],
              'test_gated': {k: v for k, v in test_gated.items() if k != 'records'},
              'test_gated_records': test_gated['records'],
              'fitting_rule': 'minimize calibration oracle NLL; then choose zero-calibration-violation confidence threshold with lowest mean RX duty, else minimum violations'}
    dest = Path('artifacts/temperature/analysis.json')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: output[k] for k in ['selected_temperature', 'selected_threshold', 'test_gated']}, indent=2))


if __name__ == '__main__':
    main()
