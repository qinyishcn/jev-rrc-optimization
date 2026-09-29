"""CPU-only independent re-evaluation of the published paired experiment."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from rrcopt.simulation import Scenario, PROFILES, generate_arrivals, simulate
from rrcopt.provenance import file_hash, request_hash


def main():
    root = Path('artifacts/experiment')
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    status = read(root/'status.json')
    assert status['state']=='complete' and status['model_evaluated']
    for name,digest in status['evidence_sha256'].items():
        assert file_hash(root/name)==digest, name
    for name,digest in status['source_sha256'].items():
        assert file_hash(name)==digest, name
    freeze = read('artifacts/experiment_freeze.json')
    for name,digest in freeze['files'].items():
        assert file_hash(name)==digest, f'Protocol changed after freeze: {name}'
    design = read(root/'design.json')
    scenarios = [Scenario(**row) for row in read(root/'evaluation_scenarios.json')]
    assert len(scenarios)==design['n_evaluation']==90
    identity = read(root/'model_identity.json')
    decisions = [json.loads(line) for line in (root/'decisions.jsonl').read_text().splitlines()]
    assert len(decisions)==90 and len({r['uid'] for r in decisions})==90
    request_keys = ['state','question','options','model_revision']
    for row in decisions:
        request = {k:row[k] for k in request_keys}
        assert request_hash(request,identity)==row['request_hash']
        p = row['result']['probs']
        assert set(p)=={profile.name for profile in PROFILES}
        assert all(np.isfinite(v) and 0<=v<=1 for v in p.values())
        assert abs(sum(p.values())-1)<1e-5
        assert row['result']['choice']==max(p,key=p.__getitem__)
        assert row['inference_ms']>0
    original = read(root/'evaluation_metrics.json')
    count = 0
    for s in scenarios:
        a = generate_arrivals(s)
        for profile in PROFILES:
            actual = simulate(a,profile,s.packet_service_ms,s.base_delay_ms,s.deadline_ms,s.duration_ms)
            for key,value in actual.items():
                assert np.isclose(value,original[s.uid][profile.name][key],rtol=1e-12,atol=1e-12), (s.uid,profile.name,key)
            count += 1
    rows = read(root/'rows.json')
    assert len(rows)==900
    assert len({(r['uid'],r['method']) for r in rows})==900
    for row in rows:
        for key,value in original[row['uid']][row['profile']].items():
            assert row[key]==value
    report = {'status':'passed','scenarios':len(scenarios),'typed_model_decisions':len(decisions),
              'independently_recomputed_profile_scenarios':count,'verified_method_rows':len(rows),
              'protocol_freeze_hashes_match':True,'output_hashes_match':True,
              'command':'python scripts/verify_evidence.py'}
    Path('artifacts/evidence_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
