"""Frozen, reproducible paired DRX experiment; checkpoint every model decision."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from rrcopt.simulation import PROFILES, generate_scenarios, generate_arrivals, simulate
from rrcopt.policies import (OPTIONS, QUESTION, context, eligible, guard_choice,
                             service_rule, cost, configuration_fragment)
from rrcopt.provenance import model_identity, request_hash, file_hash
from rrcopt.protocol import integrate_fragment

OUT = Path('artifacts/experiment')
SERVICES = ['industrial_control', 'xr', 'gaming']
CAL_SEED, TEST_SEED = 26092801, 26092902


def evaluate(s):
    arrivals = generate_arrivals(s)
    return {p.name: simulate(arrivals, p, s.packet_service_ms, s.base_delay_ms,
                            s.deadline_ms, s.duration_ms) for p in PROFILES}


def fit_fixed(scenarios, outcomes):
    def score(name):
        rows = [outcomes[s.uid][name] for s in scenarios]
        # No validation or test labels in this fixed-profile selection.
        return (sum(r['miss_rate'] > .01 for r in rows),
                float(np.mean([max(0, r['miss_rate']-.01) for r in rows])),
                float(np.mean([r['rx_duty'] for r in rows])),
                float(np.mean([r['p99_ms'] for r in rows])))
    return min(OPTIONS, key=score)


def save(path, obj):
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['service'], row['method'])].append(row)
        grouped[('all', row['method'])].append(row)
    result = []
    for (service, method), group in grouped.items():
        result.append({
            'service': service, 'method': method, 'n_scenarios': len(group),
            'mean_delay_ms': float(np.mean([r['mean_ms'] for r in group])),
            'mean_scenario_p99_ms': float(np.mean([r['p99_ms'] for r in group])),
            'mean_miss_rate': float(np.mean([r['miss_rate'] for r in group])),
            'mean_rx_duty': float(np.mean([r['rx_duty'] for r in group])),
            'scenario_violation_rate': float(np.mean([r['miss_rate'] > .01 for r in group])),
            'mean_inference_ms': float(np.mean([r['inference_ms'] for r in group])),
            'profile_counts': dict(Counter(r['profile'] for r in group)),
        })
    return result


def paired_intervals(rows):
    """Scenario-level paired bootstrap, not packet pseudo-replication."""
    lookup = {(r['uid'], r['method']): r for r in rows}
    result = []
    methods = {r['method'] for r in rows}
    for service in ['all', *SERVICES]:
        ids = sorted({r['uid'] for r in rows if service == 'all' or r['service'] == service})
        for method in ['decider_raw', 'decider_screened', 'guard_only']:
            if method not in methods:
                continue
            for baseline in ['fixed_balanced', 'fixed_low_latency', 'service_rule', 'calibrated_per_service', 'guard_only']:
                if method == baseline:
                    continue
                for metric in ['p99_ms', 'miss_rate', 'rx_duty','scenario_violation']:
                    # baseline - proposed: positive means a reduction.
                    def value(uid, name):
                        row = lookup[(uid, name)]
                        return float(row['miss_rate']>.01) if metric=='scenario_violation' else row[metric]
                    delta = np.array([value(uid, baseline)-value(uid, method) for uid in ids])
                    rng = np.random.default_rng(104729)
                    if service == 'all':
                        # Preserve the deliberately balanced service composition.
                        group_means = []
                        for svc in SERVICES:
                            values = np.array([delta[i] for i,uid in enumerate(ids) if lookup[(uid,baseline)]['service']==svc])
                            group_means.append(values[rng.integers(0,len(values),size=(2000,len(values)))].mean(axis=1))
                        means = np.mean(group_means,axis=0)
                    else:
                        means = delta[rng.integers(0, len(delta), size=(2000, len(delta)))].mean(axis=1)
                    result.append({'service': service, 'method': method, 'baseline': baseline,
                                   'metric': metric, 'baseline_minus_method': float(delta.mean()),
                                   'ci95': np.quantile(means, [.025, .975]).tolist()})
    return result


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='models/decider-2b')
    parser.add_argument('--n-per-service', type=int, default=30)
    parser.add_argument('--baselines-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    OUT = args.output or Path('artifacts/baselines' if args.baselines_only else 'artifacts/experiment')
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT/'status.json', {'state':'running', 'evaluation_seed':TEST_SEED,
                           'model_evaluated':not args.baselines_only})
    calibration = generate_scenarios(30, CAL_SEED)
    evaluation = generate_scenarios(args.n_per_service, TEST_SEED)
    cal_results = {s.uid: evaluate(s) for s in calibration}
    source_context = json.loads(Path('artifacts/protocol_context.json').read_text(encoding='utf-8'))
    current_mac = source_context['current_mac']
    fixed = fit_fixed(calibration, cal_results)
    per_service = {svc: fit_fixed([s for s in calibration if s.service == svc], cal_results) for svc in SERVICES}
    metadata = {
        'model_evaluated': not args.baselines_only, 'model_revision': '533964dae8be954c5b5e19fa4948e48408094c1e',
        'calibration_seed': CAL_SEED, 'evaluation_seed': TEST_SEED,
        'n_calibration': len(calibration), 'n_evaluation': len(evaluation),
        'fit_fixed': fixed, 'fit_per_service': per_service,
        'question': QUESTION, 'profiles': [asdict(p) for p in PROFILES],
        'interpretation': 'Synthetic LTE FDD periodic receive-window queue; no real radio measurement.',
        'aggregation': 'Equal scenario weights; mean_scenario_p99 is NOT pooled packet p99.',
        'constraint': 'At most 1% packets later than per-service deadline in each scenario.',
        'protocol_context':source_context,
        'intervals':'Pointwise exploratory paired bootstrap, 2000 replicates; service-stratified overall.',
    }
    save(OUT/'design.json', metadata)
    save(OUT/'calibration_scenarios.json', [asdict(s) for s in calibration])
    save(OUT/'evaluation_scenarios.json', [asdict(s) for s in evaluation])
    save(OUT/'calibration_metrics.json', cal_results)
    cache = {}
    decision_file = OUT/'decisions.jsonl'
    if decision_file.exists():
        lines = decision_file.read_text(encoding='utf-8').splitlines()
        valid_lines = []
        for i,line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if i != len(lines)-1:
                    raise
                # An interrupted final append is recoverable; retain evidence locally.
                decision_file.with_suffix('.interrupted').write_text(line,encoding='utf-8')
                decision_file.write_text(''.join(x+'\n' for x in valid_lines),encoding='utf-8')
                break
            cache[row['request_hash']] = row
            valid_lines.append(line)
    model = None
    identity = None
    if not args.baselines_only:
        import torch
        from decider.infer import Decider
        torch.set_num_threads(8)
        identity = model_identity(args.model)
        save(OUT/'model_identity.json', identity)
        model = Decider(args.model, device='cuda', use_graphs=False)
        # Separate warmup is excluded from steady-state experiment inference timing.
        model.decide('A duplicate invoice charge needs correction.',
                     [{'question':'Which team?', 'options':['billing','technical']}])
        torch.cuda.synchronize()
    rows, all_outcomes, cases = [], {}, []
    for idx, s in enumerate(evaluation):
        choices = {
            'always_on': 'off', 'fixed_balanced':'40/4', 'fixed_low_latency':'10/8',
            'service_rule': service_rule(s), 'calibrated_fixed': fixed,
            'calibrated_per_service': per_service[s.service], 'guard_only': guard_choice(s),
        }
        latency_ms, decision = 0., None
        if model:
            options = OPTIONS.copy()
            random.Random(8171+idx).shuffle(options)  # independent of traffic seed/outcomes
            state = context(s, current_mac)
            request = {'state':state, 'question':QUESTION, 'options':options,
                       'model_revision':metadata['model_revision']}
            key = request_hash(request, identity)
            decision = cache.get(key)
            if decision is not None:
                cached_request = {k:decision[k] for k in request}
                if cached_request != request or request_hash(cached_request,identity) != key:
                    raise ValueError('Checkpoint request identity mismatch')
                probabilities = decision['result']['probs']
                if (set(probabilities)!=set(OPTIONS) or not np.all(np.isfinite(list(probabilities.values())))
                        or abs(sum(probabilities.values())-1)>1e-5 or decision['result']['choice'] not in OPTIONS):
                    raise ValueError('Invalid cached model response')
            if decision is None:
                start = time.perf_counter()
                result = model.decide(state, [{'question': QUESTION, 'options': options}])[0]
                torch.cuda.synchronize()
                latency_ms = 1000*(time.perf_counter()-start)
                probs = result['probs']
                assert set(probs) == set(OPTIONS) and np.all(np.isfinite(list(probs.values())))
                assert abs(sum(probs.values())-1) < 1e-5
                decision = {'uid':s.uid, 'request_hash':key, **request,
                            'inference_ms':latency_ms, 'result':result}
                with decision_file.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(decision)+'\n')
                    output.flush()
            latency_ms = decision['inference_ms']
            choices['decider_raw'] = decision['result']['choice']
            safe_names = eligible(s)
            choices['decider_screened'] = max(safe_names, key=decision['result']['probs'].__getitem__)
        # Test outcomes become visible only after all online policies have chosen.
        outcomes = evaluate(s)
        all_outcomes[s.uid] = outcomes
        choices['hindsight_oracle'] = min(OPTIONS, key=lambda name:cost(outcomes[name], s.deadline_ms))
        for method, profile in choices.items():
            rows.append({'uid':s.uid, 'service':s.service, 'deadline_ms':s.deadline_ms,
                         'method':method, 'profile':profile,
                         'inference_ms':latency_ms if method.startswith('decider') else 0.,
                         **outcomes[profile]})
        if idx % args.n_per_service == 0:
            cases.append({'scenario':asdict(s), 'eligible':eligible(s), 'choices':choices,
                          'metrics':{m:outcomes[p] for m,p in choices.items()},
                          'recommended_fragment':integrate_fragment(current_mac,configuration_fragment(choices.get('decider_screened',choices['guard_only'])))})
        print(f'{idx+1}/{len(evaluation)} {s.service} {choices.get("decider_raw","baseline")} {latency_ms:.1f}ms',flush=True)
    save(OUT/'evaluation_metrics.json', all_outcomes)
    save(OUT/'rows.json', rows)
    save(OUT/'summary.json', summarize(rows))
    save(OUT/'paired_intervals.json', paired_intervals(rows))
    save(OUT/'case_studies.json', cases)
    evidence_hashes = {p.name:file_hash(p) for p in OUT.glob('*.json') if p.name!='status.json'}
    if not args.baselines_only:
        evidence_hashes['decisions.jsonl'] = file_hash(decision_file)
    save(OUT/'status.json', {'state':'complete', 'evaluation_seed':TEST_SEED,
                           'model_evaluated':not args.baselines_only, 'n_rows':len(rows),
                           'evidence_sha256':evidence_hashes,
                           'source_sha256': {p:file_hash(p) for p in
                               ['rrcopt/simulation.py','rrcopt/policies.py','scripts/run_experiment.py']}})
    print('EXPERIMENT_OK', flush=True)


if __name__ == '__main__':
    main()
