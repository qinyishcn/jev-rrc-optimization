"""Hash actual local model inputs; prevent stale cross-model decision reuse."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def model_identity(path):
    folder = Path(path)
    files = sorted([*folder.glob('*.safetensors'), *folder.glob('*.json'), *folder.glob('*.jinja')])
    if not any(p.suffix == '.safetensors' for p in files):
        raise ValueError('A downloaded local safetensors model is required')
    import torch
    import decider
    package = Path(decider.__file__).parent
    hashes = {p.name:file_hash(p) for p in files}
    expected = 'acaef2228b134dcdc20cad4ee79219482c927ec819aa3687b9b8a575c338817f'
    if hashes.get('model.safetensors') != expected:
        raise ValueError('Checkpoint differs from the pinned Decider 2B v11 experiment')
    return {
        'files_sha256': hashes,
        'inference_code_sha256': {name:file_hash(package/name) for name in
                                  ['infer.py','model.py','prompt.py','temperature.py']},
        'engine':'Decider torch eager, bfloat16, use_graphs=False',
        'packages': {p:importlib.metadata.version(p) for p in
                     ['torch','transformers','numpy','decider-ai']},
        'python':platform.python_version(), 'gpu':torch.cuda.get_device_name(),
    }


def request_hash(request, identity):
    return hashlib.sha256(json.dumps({'request':request, 'identity':identity}, sort_keys=True).encode()).hexdigest()
