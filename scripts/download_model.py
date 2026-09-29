"""Pinned HF snapshot; resumable HTTP range fallback for hosts where Xet stalls."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import threading
import time

import requests

REPO = 'Mapika/decider-2b'
REVISION = '533964dae8be954c5b5e19fa4948e48408094c1e'
DEST = Path('models/decider-2b')


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    tree = session.get(f'https://huggingface.co/api/models/{REPO}/tree/{REVISION}', timeout=30)
    tree.raise_for_status()
    entries = tree.json()
    for entry in entries:
        name = entry['path']
        if name not in ['model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json',
                        'decider_config.json', 'chat_template.jinja', 'generation_config.json', 'README.md']:
            continue
        target = DEST / name
        size = entry['size']
        expected = entry.get('lfs', {}).get('oid')
        if target.exists() and target.stat().st_size == size:
            if expected is None or hashlib.file_digest(target.open('rb'), 'sha256').hexdigest() == expected:
                continue
        url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
        if size < 30_000_000:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            target.write_bytes(response.content)
        else:
            parts = DEST / '.http_parts_4m'
            parts.mkdir(exist_ok=True)
            chunk = 4 * 1024 * 1024
            manifest = {'repo': REPO, 'revision': REVISION, 'name': name,
                        'size': size, 'sha256': expected, 'chunk': chunk}
            manifest_path = parts / 'manifest.json'
            if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
                raise RuntimeError('Range download manifest mismatch')
            manifest_path.write_text(json.dumps(manifest, indent=2))
            local = threading.local()
            def fetch(i):
                first, last = i*chunk, min(size, (i+1)*chunk)-1
                part = parts / f'{name}.{i:04}'
                if part.exists() and part.stat().st_size == last-first+1:
                    return i
                if not hasattr(local, 'session'):
                    local.session = requests.Session()
                for attempt in range(20):
                    try:
                        offset = part.stat().st_size if part.exists() else 0
                        if offset == last-first+1:
                            return i
                        if offset > last-first+1:
                            raise RuntimeError('Oversized saved range')
                        start = first + offset
                        with local.session.get(url,
                                          headers={'Range': f'bytes={start}-{last}',
                                                   'Accept-Encoding': 'identity'},
                                          stream=True, timeout=(10, 20)) as response:
                            response.raise_for_status()
                            if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{last}/{size}':
                                raise RuntimeError(f'Incorrect HTTP byte range for part {i}')
                            with part.open('ab') as output:
                                for data in response.iter_content(64*1024):
                                    output.write(data)
                        if part.stat().st_size != last-first+1:
                            raise RuntimeError('Truncated range')
                        return i
                    except Exception as exc:
                        # Do not expose signed CDN URLs from exception text.
                        print(f'part {i} retry {attempt}: {type(exc).__name__}', flush=True)
                        if attempt == 19:
                            raise RuntimeError(f'Download failed for part {i}') from None
                        time.sleep(min(attempt + 1, 5))
            count = (size+chunk-1)//chunk
            initial = sum(p.stat().st_size for p in parts.glob(f'{name}.*'))
            began = time.monotonic()
            last_report = began
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                futures = [pool.submit(fetch, i) for i in range(count)]
                for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    future.result()
                    now = time.monotonic()
                    if now-last_report >= 20 or done == count:
                        received = sum(p.stat().st_size for p in parts.glob(f'{name}.*'))
                        rate = (received-initial)/max(now-began, 0.001)
                        eta = (size-received)/max(rate, 1)
                        print(f'progress {done}/{count} ranges; {received}/{size} bytes; '
                              f'{rate/1024/1024:.2f} MiB/s; ETA {eta:.0f}s', flush=True)
                        last_report = now
            assembling = target.with_suffix(target.suffix + '.assembling')
            with assembling.open('wb') as output:
                for i in range((size+chunk-1)//chunk):
                    with (parts / f'{name}.{i:04}').open('rb') as source:
                        while block := source.read(8*1024*1024):
                            output.write(block)
            with assembling.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            if not expected or digest != expected:
                raise RuntimeError(f'Checksum mismatch: {name}')
            assembling.replace(target)
        assert target.stat().st_size == size, name
        digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
        if expected:
            assert digest == expected, f'Checksum mismatch: {name}'
        print(f'{name}: {size} bytes SHA256 {digest}', flush=True)
    print('DOWNLOAD_OK', flush=True)


if __name__ == '__main__':
    main()
