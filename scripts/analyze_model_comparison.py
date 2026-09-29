"""Compare frozen Decider and Qwen decisions on identical RRC scenarios."""
import json
from pathlib import Path
import statistics
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.policies import OPTIONS, eligible, guard_choice
from rrcopt.simulation import Scenario


def summarize(records):
    return {'n': len(records),
            'invalid': sum(r['profile'] is None for r in records),
            'scenario_violations': sum(r['violates'] for r in records),
            'mean_miss_rate': statistics.mean(r['miss_rate'] for r in records),
            'mean_rx_duty': statistics.mean(r['rx_duty'] for r in records),
            'mean_scenario_p99_ms': statistics.mean(r['p99_ms'] for r in records),
            'inference_ms_median': statistics.median(r['inference_ms'] for r in records),
            'inference_ms_p95': float(np.percentile([r['inference_ms'] for r in records], 95))}


def paired_ci(first, second, field, seed=26093021):
    a = np.asarray([r[field] for r in first], dtype=float)
    b = np.asarray([r[field] for r in second], dtype=float)
    delta = a - b
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(delta), (10_000, len(delta)))
    return {'first_minus_second': float(np.mean(delta)),
            'ci95': [float(v) for v in np.quantile(np.mean(delta[indices], axis=1), [0.025, 0.975])]}


def main():
    root = Path('artifacts/experiment')
    scenarios = [Scenario(**s) for s in json.loads((root / 'evaluation_scenarios.json').read_text(encoding='utf-8'))]
    metrics = json.loads((root / 'evaluation_metrics.json').read_text(encoding='utf-8'))
    decider = {r['uid']: r for r in map(json.loads, (root / 'decisions.jsonl').read_text(encoding='utf-8').splitlines())}
    qwen = {r['uid']: r for r in map(json.loads, Path('artifacts/qwen/decisions.jsonl').read_text(encoding='utf-8').splitlines())}
    uids = {s.uid for s in scenarios}
    assert set(decider) == set(qwen) == set(metrics) == uids and len(uids) == 90
    rows = {name: [] for name in ('decider_raw', 'qwen_raw', 'decider_guard', 'qwen_guard', 'guard_only')}
    for scenario in scenarios:
        uid = scenario.uid
        raw = {'decider': decider[uid]['result']['choice'], 'qwen': qwen[uid]['profile']}
        if raw['qwen'] not in OPTIONS or raw['decider'] not in OPTIONS:
            raise ValueError(f'Invalid model choice at {uid}; report it separately rather than substituting a result')
        allowed = eligible(scenario)
        fallback = guard_choice(scenario)
        choices = {'decider_raw': raw['decider'], 'qwen_raw': raw['qwen'],
                   'decider_guard': raw['decider'] if raw['decider'] in allowed else fallback,
                   'qwen_guard': raw['qwen'] if raw['qwen'] in allowed else fallback,
                   'guard_only': fallback}
        for name, profile in choices.items():
            m = metrics[uid][profile]
            inference = (qwen[uid]['inference_ms'] if name.startswith('qwen') else
                         decider[uid]['inference_ms'] if name.startswith('decider') else 0.0)
            rows[name].append({'uid': uid, 'profile': profile, 'miss_rate': m['miss_rate'],
                               'rx_duty': m['rx_duty'], 'p99_ms': m['p99_ms'],
                               'violates': int(m['miss_rate'] > .01 + 1e-12),
                               'inference_ms': inference})
    output = {'summary': {name: summarize(records) for name, records in rows.items()},
              'paired_qwen_minus_decider_raw': {
                  field: paired_ci(rows['qwen_raw'], rows['decider_raw'], field)
                  for field in ('violates', 'miss_rate', 'rx_duty', 'p99_ms')},
              'paired_qwen_minus_decider_guard': {
                  field: paired_ci(rows['qwen_guard'], rows['decider_guard'], field)
                  for field in ('violates', 'miss_rate', 'rx_duty', 'p99_ms')},
              'rows': rows,
              'note': 'same one-choice candidate guard for both models; distinct from Decider probability reranking after eligibility screen'}
    dest = Path('artifacts/qwen/paired_comparison.json')
    dest.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary': output['summary'],
                      'raw_violation_difference': output['paired_qwen_minus_decider_raw']['violates']}, indent=2))


if __name__ == '__main__':
    main()
