"""Load the real pinned checkpoint and preserve finite typed-decision evidence."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from decider.infer import Decider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='models/decider-2b')
    args = parser.parse_args()
    torch.set_num_threads(8)
    start = time.perf_counter()
    model = Decider(args.model, device='cuda', use_graphs=False)
    torch.cuda.synchronize()
    load_s = time.perf_counter() - start
    questions = [{'question': 'Which department?', 'options': ['billing', 'technical', 'sales']}]
    requests = []
    for i in range(11):
        start = time.perf_counter()
        result = model.decide('My credit card was charged twice for the same purchase.', questions)[0]
        torch.cuda.synchronize()
        elapsed_ms = 1000 * (time.perf_counter() - start)
        p = list(result['probs'].values())
        assert np.all(np.isfinite(p)) and abs(sum(p) - 1) < 1e-5
        assert result['choice'] in questions[0]['options']
        requests.append({'iteration': i, 'elapsed_ms': elapsed_ms, **result})
        print(json.dumps(requests[-1]), flush=True)
    # Exercise the Jev-shaped endpoint, including all three typed outputs.
    structured = model.system_one({'card': 'charged twice', 'policy': 'Route duplicate charges to billing.'}, {
        'team': {'type': 'choice', 'instructions': 'Select the responsible team.',
                 'criteria': {'billing': 'charges and invoices', 'technical': 'software errors'}},
        'duplicate': {'type': 'noul', 'instructions': 'Was the card charged twice?'},
        'urgency': {'type': 'score', 'instructions': 'How urgent is correcting a duplicate charge?',
                    'criteria': ['low', 'medium', 'high']}})
    report = {
        'model': 'Mapika/decider-2b', 'revision': '533964dae8be954c5b5e19fa4948e48408094c1e',
        'device': torch.cuda.get_device_name(), 'dtype': 'bfloat16', 'engine': 'torch eager',
        'python': platform.python_version(), 'packages': {x: importlib.metadata.version(x) for x in
        ['torch', 'transformers', 'numpy', 'huggingface_hub', 'decider-ai']},
        'load_s': load_s, 'peak_allocated_gb': torch.cuda.max_memory_allocated()/1e9,
        'warm_median_ms': float(np.median([r['elapsed_ms'] for r in requests[1:]])),
        'warm_p95_ms': float(np.percentile([r['elapsed_ms'] for r in requests[1:]],95)),
        'requests': requests, 'system_one': structured,
        'weights_sha256': hashlib.file_digest(open(Path(args.model)/'model.safetensors','rb'),'sha256').hexdigest(),
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/model_smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('MODEL_SMOKE_OK', flush=True)


if __name__ == '__main__':
    main()
