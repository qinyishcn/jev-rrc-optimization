"""Collect held-out-from-test Decider choices for task temperature/gate fitting."""
import hashlib
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from decider.infer import Decider
from rrcopt.policies import OPTIONS, QUESTION, context
from rrcopt.provenance import model_identity, request_hash
from rrcopt.simulation import Scenario


def main():
    folder=Path('artifacts/temperature')
    folder.mkdir(parents=True,exist_ok=True)
    identity=model_identity('models/decider-2b')
    source=json.loads(Path('artifacts/protocol_context.json').read_text(encoding='utf-8'))
    scenarios=[Scenario(**row) for row in json.loads(Path('artifacts/experiment/calibration_scenarios.json').read_text(encoding='utf-8'))]
    output=folder/'calibration_decisions.jsonl'
    existing={}
    if output.exists():
        for line in output.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            existing[row['request_hash']]=row
    torch.set_num_threads(8)
    model=Decider('models/decider-2b',device='cuda',use_graphs=False)
    model.decide('Warm up.',[{'question':'Which?', 'options':['a','b']}])
    torch.cuda.synchronize()
    for i,s in enumerate(scenarios):
        options=OPTIONS.copy()
        random.Random(8171+i).shuffle(options)
        request={'state':context(s,source['current_mac']),'question':QUESTION,'options':options,
                 'model_revision':'533964dae8be954c5b5e19fa4948e48408094c1e'}
        key=request_hash(request,identity)
        if key in existing:
            continue
        start=time.perf_counter()
        result=model.decide(request['state'],[{'question':QUESTION,'options':options}])[0]
        torch.cuda.synchronize()
        latency=1000*(time.perf_counter()-start)
        p=result['probs']
        assert set(p)==set(OPTIONS) and np.all(np.isfinite(list(p.values()))) and abs(sum(p.values())-1)<1e-5
        row={'uid':s.uid,'request_hash':key,**request,'result':result,'inference_ms':latency}
        with output.open('a',encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')
            f.flush()
        print(f'{i+1}/{len(scenarios)} {result["choice"]} {latency:.1f}ms',flush=True)
    print('CALIBRATION_DECISIONS_OK',flush=True)


if __name__=='__main__':main()
