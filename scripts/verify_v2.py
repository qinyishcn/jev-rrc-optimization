"""Independent consistency checks for the published extended experiment."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.policies import OPTIONS, configuration_fragment
from rrcopt.qwen_baseline import parse_profile
from rrcopt.temperature import rescale


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)


def main():
    original = Path('artifacts/experiment')
    qroot = Path('artifacts/qwen')
    uids = [r['uid'] for r in json.loads((original/'evaluation_scenarios.json').read_text(encoding='utf-8'))]
    expected = json.loads((original/'evaluation_metrics.json').read_text(encoding='utf-8'))
    assert len(uids) == len(set(uids)) == 90 and set(uids) == set(expected)

    status = json.loads((qroot/'status.json').read_text(encoding='utf-8'))
    assert status['state'] == 'complete' and status['n_evaluation'] == 90
    for name, digest in status['evidence_sha256'].items():
        assert sha256(qroot/name) == digest, name
    decisions = [json.loads(line) for line in (qroot/'decisions.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = json.loads((qroot/'rows.json').read_text(encoding='utf-8'))
    assert [r['uid'] for r in decisions] == [r['uid'] for r in rows] == uids
    assert status['valid'] == sum(parse_profile(r['raw_text']) is not None for r in decisions) == 90
    for decision, row in zip(decisions, rows):
        uid = decision['uid']
        profile = decision['profile']
        assert parse_profile(decision['raw_text']) == profile in OPTIONS
        assert profile == row['profile'] and close(decision['inference_ms'], row['inference_ms'])
        assert configuration_fragment(profile) == row['configuration_fragment']
        assert uid not in decision['prompt']
        for field, value in expected[uid][profile].items():
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                assert close(row['metrics'][field], value), (uid, profile, field)
            else:
                assert row['metrics'][field] == value, (uid, profile, field)
    qsummary = next(r for r in json.loads((qroot/'summary.json').read_text(encoding='utf-8')) if r['service'] == 'all')
    assert qsummary['valid'] == 90 and qsummary['invalid'] == 0
    assert qsummary['valid_only_scenario_violations'] == sum(r['metrics']['miss_rate'] > .01 + 1e-12 for r in rows)
    for key, field in [('valid_only_mean_miss_rate', 'miss_rate'),
                       ('valid_only_mean_rx_duty', 'rx_duty'),
                       ('valid_only_mean_scenario_p99_ms', 'p99_ms')]:
        assert close(qsummary[key], statistics.mean(r['metrics'][field] for r in rows)), key

    comparison = json.loads((qroot/'paired_comparison.json').read_text(encoding='utf-8'))
    for method, records in comparison['rows'].items():
        assert [r['uid'] for r in records] == uids, method
        summary = comparison['summary'][method]
        assert summary['scenario_violations'] == sum(r['violates'] for r in records)
        assert close(summary['mean_rx_duty'], statistics.mean(r['rx_duty'] for r in records))
        for row in records:
            metric = expected[row['uid']][row['profile']]
            assert close(row['p99_ms'], metric['p99_ms']) and close(row['miss_rate'], metric['miss_rate'])

    timing = list(csv.DictReader(Path('artifacts/temperature/per_scenario_timing.csv').open(encoding='utf-8', newline='')))
    assert [r['uid'] for r in timing] == uids
    assert all(int(r['n_decider_requests']) == 1 and int(r['n_profile_simulations']) == 9
               and close(float(r['arrivals_horizon_ms']), 1000) for r in timing)
    temp = json.loads(Path('artifacts/temperature/analysis.json').read_text(encoding='utf-8'))
    assert temp['selected_temperature'] == 1.5 and temp['selected_threshold'] == .35
    assert [r['uid'] for r in temp['test_gated_records']] == uids
    base = {r['uid']: r for r in map(json.loads, (original/'decisions.jsonl').read_text(encoding='utf-8').splitlines())}
    assert all(max(rescale(base[uid]['result']['probs'], 1.164, 1.5),
                   key=rescale(base[uid]['result']['probs'], 1.164, 1.5).get)
               == base[uid]['result']['choice'] for uid in uids)

    adapter = json.loads(Path('artifacts/adaptation/test_decisions.json').read_text(encoding='utf-8'))
    assert [r['uid'] for r in adapter] == uids
    adaptation_root = Path('artifacts/adaptation')
    test_status = json.loads((adaptation_root/'test_status.json').read_text(encoding='utf-8'))
    assert test_status['state'] == 'complete' and test_status['n_scenarios'] == 90
    assert sha256(adaptation_root/'test_decisions.json') == test_status['decisions_sha256']
    for row in adapter:
        assert row['raw'] in OPTIONS and row['screened'] in OPTIONS
        assert abs(sum(row['probs'].values()) - 1) < 1e-5
    fresh_status = json.loads((adaptation_root/'fresh_status.json').read_text(encoding='utf-8'))
    assert fresh_status['state'] == 'complete' and fresh_status['n_scenarios'] == 90
    for filename, key in [('fresh_base_decisions.json', 'base_decisions_sha256'),
                          ('fresh_adapter_decisions.json', 'adapter_decisions_sha256'),
                          ('fresh_rows.json', 'rows_sha256'),
                          ('fresh_summary.json', 'summary_sha256'),
                          ('fresh_comparisons.json', 'comparisons_sha256')]:
        assert sha256(adaptation_root/filename) == fresh_status[key], filename
    fresh = json.loads((adaptation_root/'fresh_summary.json').read_text(encoding='utf-8'))
    fresh_all = {r['method']: r for r in fresh if r['service'] == 'all'}
    assert fresh_all['decider_base']['n_scenarios'] == fresh_all['decider_adapter']['n_scenarios'] == 90
    assert fresh_all['guard_only']['scenario_violation_rate'] == 0

    print('VERIFY_V2_OK: 90 Qwen outputs, hashes, paired profile outcomes, timing, temperature, adapter evidence')


if __name__ == '__main__':
    main()
