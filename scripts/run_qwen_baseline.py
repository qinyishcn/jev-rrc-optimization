"""Download pinned Qwen weights and run a resumable autoregressive DRX baseline."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import threading
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rrcopt.policies import OPTIONS, configuration_fragment, cost
from rrcopt.provenance import file_hash
from rrcopt.qwen_baseline import QwenGenerator, parse_profile, prompt_for
from rrcopt.simulation import PROFILES, generate_arrivals, generate_scenarios, simulate


REPO = "Qwen/Qwen3.5-2B-Base"
REVISION = "b1485b2fa6dfa1287294f269f5fb618e03d52d7c"
MODEL = Path("models/qwen3.5-2b-base")
OUTPUT = Path("artifacts/qwen")
CAL_SEED, TEST_SEED = 26092801, 26092902
FILES = {"LICENSE", "README.md", "config.json", "merges.txt", "vocab.json",
         "model.safetensors-00001-of-00001.safetensors", "model.safetensors.index.json",
         "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
         "video_preprocessor_config.json"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def repo_manifest():
    response = requests.get(f"https://huggingface.co/api/models/{REPO}/tree/{REVISION}", timeout=30)
    response.raise_for_status()
    entries = {entry["path"]: entry for entry in response.json() if entry["path"] in FILES}
    if set(entries) != FILES:
        raise RuntimeError(f"Pinned model file list changed: {set(entries) ^ FILES}")
    if entries["model.safetensors-00001-of-00001.safetensors"].get("lfs", {}).get("oid") != "928acbf11878c32185bbd863514d191769285065ab9ea14fbfe431303f5fdf2d":
        raise RuntimeError("Pinned model weight SHA256 changed")
    return entries


def download_file(name, entry, dest):
    size = entry["size"]
    expected = entry.get("lfs", {}).get("oid")
    target = dest / name
    if target.exists() and target.stat().st_size == size:
        digest = sha256(target)
        if expected is None or digest == expected:
            print(f"verified {name}: {size} bytes SHA256 {digest}", flush=True)
            return digest
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
    if size < 30_000_000:
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        temp = target.with_suffix(target.suffix + ".part")
        temp.write_bytes(response.content)
        if temp.stat().st_size != size or (expected and sha256(temp) != expected):
            raise RuntimeError(f"Downloaded file failed integrity check: {name}")
        os.replace(temp, target)
    else:
        part_dir = dest / ".http_parts_8m" / name
        part_dir.mkdir(parents=True, exist_ok=True)
        chunk = 8 * 1024 * 1024
        manifest = {"repo": REPO, "revision": REVISION, "name": name,
                    "size": size, "sha256": expected, "chunk": chunk}
        manifest_path = part_dir / "manifest.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise RuntimeError("Saved range manifest differs from pinned model")
        atomic_json(manifest_path, manifest)
        local = threading.local()
        count = (size + chunk - 1) // chunk

        def fetch(i):
            first, last = i * chunk, min(size, (i + 1) * chunk) - 1
            part = part_dir / f"{i:04d}.part"
            for attempt in range(20):
                offset = part.stat().st_size if part.exists() else 0
                if offset == last - first + 1:
                    return
                if offset > last - first + 1:
                    raise RuntimeError(f"Oversized saved range {i}")
                if not hasattr(local, "session"):
                    local.session = requests.Session()
                start = first + offset
                try:
                    with local.session.get(url, headers={"Range": f"bytes={start}-{last}",
                                                         "Accept-Encoding": "identity"},
                                           stream=True, timeout=(15, 30)) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{last}/{size}":
                            raise RuntimeError(f"Incorrect byte range response for part {i}")
                        with part.open("ab") as output:
                            for data in response.iter_content(128 * 1024):
                                output.write(data)
                    if part.stat().st_size == last - first + 1:
                        return
                except Exception as exc:
                    # Signed CDN URLs can contain private query parameters; report the type only.
                    print(f"range {i} retry {attempt + 1}: {type(exc).__name__}", flush=True)
                if attempt == 19:
                    raise RuntimeError(f"Failed to download range {i}")
                time.sleep(min(attempt + 1, 5))

        beginning = time.monotonic()
        initial = sum(p.stat().st_size for p in part_dir.glob("*.part"))
        last_report = beginning
        with ThreadPoolExecutor(max_workers=64) as pool:
            futures = [pool.submit(fetch, i) for i in range(count)]
            for done, future in enumerate(as_completed(futures), 1):
                future.result()
                now = time.monotonic()
                if now - last_report > 20 or done == count:
                    received = sum(p.stat().st_size for p in part_dir.glob("*.part"))
                    rate = (received - initial) / max(now - beginning, .001)
                    print(f"{name}: {done}/{count} ranges {received}/{size} bytes "
                          f"{rate/2**20:.1f} MiB/s", flush=True)
                    last_report = now
        temp = target.with_suffix(target.suffix + ".assembling")
        with temp.open("wb") as output:
            for i in range(count):
                with (part_dir / f"{i:04d}.part").open("rb") as source:
                    while block := source.read(8 * 1024 * 1024):
                        output.write(block)
        if temp.stat().st_size != size or (expected and sha256(temp) != expected):
            raise RuntimeError(f"Assembled file failed integrity check: {name}")
        os.replace(temp, target)
    digest = sha256(target)
    print(f"verified {name}: {size} bytes SHA256 {digest}", flush=True)
    return digest


def download():
    MODEL.mkdir(parents=True, exist_ok=True)
    manifest = repo_manifest()
    hashes = {name: download_file(name, manifest[name], MODEL) for name in sorted(FILES)}
    atomic_json(MODEL / "download_identity.json", {"repo": REPO, "revision": REVISION,
                                                    "files_sha256": hashes})
    print("DOWNLOAD_OK", flush=True)


def evaluate(s):
    arrivals = generate_arrivals(s)
    return {p.name: simulate(arrivals, p, s.packet_service_ms, s.base_delay_ms,
                             s.deadline_ms, s.duration_ms) for p in PROFILES}


def calibration_examples(current_mac):
    """Fixed one-per-service examples, labeled from calibration traces only."""
    cases = generate_scenarios(30, CAL_SEED)
    selected = [cases[i] for i in (0, 30, 60)]
    examples = []
    for s in selected:
        metrics = evaluate(s)
        examples.append((s, min(OPTIONS, key=lambda name: cost(metrics[name], s.deadline_ms))))
    return examples


def request_hash(prompt, identity):
    payload = json.dumps({"prompt": prompt, "model": identity, "generation":
                          {"do_sample": False, "max_new_tokens": 16}}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cache(path):
    cache = {}
    if not path.exists():
        return cache
    lines = path.read_text(encoding="utf-8").splitlines()
    valid = []
    for i, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
            path.with_suffix(".interrupted").write_text(line, encoding="utf-8")
            path.write_text("".join(x + "\n" for x in valid), encoding="utf-8")
            break
        if row["request_hash"] in cache:
            raise ValueError("Duplicate Qwen decision checkpoint")
        cache[row["request_hash"]] = row
        valid.append(line)
    return cache


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["service"]].append(row)
        groups["all"].append(row)
    result = []
    for service, group in groups.items():
        valid = [r for r in group if r["profile"] is not None]
        result.append({"service": service, "n_scenarios": len(group),
                       "valid": len(valid), "invalid": len(group) - len(valid),
                       "invalid_rate": (len(group) - len(valid)) / len(group),
                       "mean_inference_ms": sum(r["inference_ms"] for r in group) / len(group),
                       "profile_counts": dict(Counter(r["profile"] for r in group)),
                       "valid_only_mean_scenario_p99_ms": (sum(r["metrics"]["p99_ms"] for r in valid) / len(valid)
                                                           if valid else None),
                       "valid_only_mean_miss_rate": (sum(r["metrics"]["miss_rate"] for r in valid) / len(valid)
                                                    if valid else None),
                       "valid_only_mean_rx_duty": (sum(r["metrics"]["rx_duty"] for r in valid) / len(valid)
                                                   if valid else None),
                       "valid_only_scenario_violations": sum(r["metrics"]["miss_rate"] > .01 for r in valid),
                       "invalid_or_constraint_violation": (len(group) - len(valid)
                                                           + sum(r["metrics"]["miss_rate"] > .01 for r in valid))})
    return result


def run():
    if not (MODEL / "download_identity.json").exists():
        raise RuntimeError("Run the download subcommand and verify the pinned weights first")
    model_identity = json.loads((MODEL / "download_identity.json").read_text(encoding="utf-8"))
    if model_identity["repo"] != REPO or model_identity["revision"] != REVISION:
        raise RuntimeError("Wrong model identity")
    for name, expected in model_identity["files_sha256"].items():
        if sha256(MODEL / name) != expected:
            raise RuntimeError(f"Local file changed: {name}")
    import importlib.metadata
    import platform
    source_hashes = {name: file_hash(name) for name in
                     ("rrcopt/simulation.py", "rrcopt/policies.py",
                      "rrcopt/qwen_baseline.py", "scripts/run_qwen_baseline.py")}
    identity = {"model": model_identity, "source_sha256": source_hashes,
                "packages": {p: importlib.metadata.version(p) for p in
                             ("torch", "transformers", "numpy")},
                "python": platform.python_version(),
                "frozen_scenarios_sha256": file_hash("artifacts/experiment/evaluation_scenarios.json"),
                "protocol_context_sha256": file_hash("artifacts/protocol_context.json")}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_context = json.loads(Path("artifacts/protocol_context.json").read_text(encoding="utf-8"))
    current_mac = source_context["current_mac"]
    examples = calibration_examples(current_mac)
    scenarios = generate_scenarios(30, TEST_SEED)
    frozen_scenarios = json.loads(Path("artifacts/experiment/evaluation_scenarios.json").read_text(encoding="utf-8"))
    if [asdict(s) for s in scenarios] != frozen_scenarios:
        raise RuntimeError("Qwen evaluation scenarios differ from the frozen Decider evaluation")
    atomic_json(OUTPUT / "design.json", {"repo": REPO, "revision": REVISION,
                "model_identity": identity, "calibration_seed": CAL_SEED,
                "evaluation_seed": TEST_SEED, "n_evaluation": len(scenarios),
                "calibration_examples": [{"scenario": asdict(s), "answer": answer} for s, answer in examples],
                "generation": {"do_sample": False, "max_new_tokens": 16,
                               "mode": "unconstrained autoregressive text generation"},
                "parser": "Only one bare exact profile name is valid; invalid means no configuration.",
                "current_mac": current_mac})
    decision_path = OUTPUT / "decisions.jsonl"
    cache = load_cache(decision_path)
    requests_to_run = []
    for idx, s in enumerate(scenarios):
        options = OPTIONS.copy()
        random.Random(8171 + idx).shuffle(options)
        prompt = prompt_for(s, current_mac, examples, options)
        key = request_hash(prompt, identity)
        decision = cache.get(key)
        if decision and (decision["uid"] != s.uid or decision["prompt"] != prompt
                         or decision["profile"] != parse_profile(decision["raw_text"])):
            raise ValueError("Checkpoint request or parsed response mismatch")
        requests_to_run.append((s, prompt, key))
    unexpected = set(cache) - {key for _, _, key in requests_to_run}
    if unexpected:
        raise ValueError("Checkpoint contains requests from another Qwen run or code revision")
    generator = QwenGenerator(MODEL) if any(key not in cache for _, _, key in requests_to_run) else None
    if generator:
        generator.generate("Profile: off\nProfile:", max_new_tokens=4)
    rows = []
    for idx, (s, prompt, key) in enumerate(requests_to_run):
        decision = cache.get(key)
        if decision is None:
            raw, latency_ms, n_tokens = generator.generate(prompt)
            decision = {"uid": s.uid, "service": s.service, "request_hash": key,
                        "prompt": prompt, "raw_text": raw, "profile": parse_profile(raw),
                        "inference_ms": latency_ms, "new_tokens": n_tokens}
            with decision_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(decision, ensure_ascii=False) + "\n")
                output.flush()
            cache[key] = decision
        row = {"uid": s.uid, "service": s.service, "deadline_ms": s.deadline_ms,
               "profile": decision["profile"], "inference_ms": decision["inference_ms"],
               "configuration_fragment": (configuration_fragment(decision["profile"])
                                          if decision["profile"] else None),
               "metrics": evaluate(s)[decision["profile"]] if decision["profile"] else None}
        rows.append(row)
        print(f"{idx + 1}/{len(scenarios)} {s.uid} {repr(decision['raw_text'])} "
              f"{decision['inference_ms']:.1f}ms", flush=True)
    atomic_json(OUTPUT / "rows.json", rows)
    atomic_json(OUTPUT / "summary.json", summarize(rows))
    hashes = {p.name: sha256(p) for p in OUTPUT.glob("*.json") if p.name != "status.json"}
    hashes["decisions.jsonl"] = sha256(decision_path)
    atomic_json(OUTPUT / "status.json", {"state": "complete", "n_evaluation": len(rows),
                                          "valid": sum(r["profile"] is not None for r in rows),
                                          "invalid": sum(r["profile"] is None for r in rows),
                                          "evidence_sha256": hashes})
    print("QWEN_BASELINE_OK", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("download", "run"))
    args = parser.parse_args()
    if args.command == "download":
        download()
    else:
        run()


if __name__ == "__main__":
    main()
