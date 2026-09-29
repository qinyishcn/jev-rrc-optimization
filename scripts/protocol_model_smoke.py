"""Small protocol sanity probe, explicitly not a training/generalization benchmark."""
from collections import defaultdict
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from decider.infer import Decider
from rrcopt.provenance import model_identity


def main():
    rows = json.loads(Path('artifacts/protocol_labels.json').read_text(encoding='utf-8'))
    torch.set_num_threads(8)
    identity = model_identity('models/decider-2b')
    model = Decider('models/decider-2b',device='cuda',use_graphs=False)
    options = ['rrcConnectionSetup','dlInformationTransfer','securityModeCommand',
               'ueCapabilityEnquiry','rrcConnectionReconfiguration','rrcConnectionRelease','paging']
    observations = defaultdict(set)
    for row in rows:
        observations[tuple(row['ul_types'])].add(row['observed_dl_types'][0])
    records = []
    for i,(ul, observed) in enumerate(observations.items()):
        choices = options.copy()
        random.Random(2048+i).shuffle(choices)
        context = 'LTE RRC signaling. The UE has sent: '+', then '.join(ul)+'. No NAS payload or additional network state is available.'
        start = time.perf_counter()
        result = model.decide(context,[{'question':'What is the likely next downlink RRC message from the eNB?', 'options':choices}])[0]
        torch.cuda.synchronize()
        records.append({'ul_types':list(ul),'observed_first_dl_options':sorted(observed),
                        'ambiguous_in_public_data':len(observed)>1,'result':result,
                        'matches_any_observed_first_dl':result['choice'] in observed,
                        'elapsed_ms_including_first_cold_call':1000*(time.perf_counter()-start)})
    payload = {'model_identity':identity,'input_rows':len(rows),'unique_ul_contexts':len(records),
               'matching_contexts':sum(r['matches_any_observed_first_dl'] for r in records),
               'scope':'Protocol sanity only: tiny repeated sample; stripped NAS creates ambiguity; no held-out generalization claim.',
               'records':records}
    Path('artifacts/protocol_model_smoke.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k not in ['records','model_identity']}))


if __name__=='__main__':
    main()
