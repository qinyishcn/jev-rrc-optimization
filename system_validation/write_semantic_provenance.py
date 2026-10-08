"""Record the measured checkpoint/runtime/evidence hashes without model weights."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def command(args):
    return subprocess.run(args,capture_output=True,encoding="utf-8",errors="replace",check=True).stdout.strip()


def main():
    import torch
    root=Path("artifacts/semantic_uc")
    binary_output=command(["wsl","--","sha256sum","/home/qinyi/rrc-ns3/rrc-handover","/home/qinyi/rrc-ns3/rrc-handover-confirm"])
    binary_hashes={line.split()[1]:line.split()[0] for line in binary_output.splitlines()}
    assert len(set(binary_hashes.values()))==1
    packages={name:importlib.metadata.version(name) for name in ("torch","transformers","numpy","scipy","scikit-learn","decider-ai")}
    paths=list(root.glob("*"))+list(Path("system_validation").glob("*semantic*.py"))
    paths += list(Path("docs/superpowers").rglob("*.md"))
    paths += [Path("system_validation/diagnose_a3.py"),Path("system_validation/probe_representation.py"),
              Path("system_validation/ns3_lte_handover.cc"),Path("tests/test_semantic_uc.py"),
              Path("requirements_semantic_uc.txt"),Path("docs/rrc_cause_semantic_uc.md"),
              Path("docs/figures/semantic_uc_comparison.png"),Path("README.md")]
    paths=[p for p in paths if p.is_file() and p.name!="provenance.json"]
    models={name:sha(path) for name,path in {
        "decider_2b":"models/decider-2b/model.safetensors",
        "qwen_3_5_2b_base":"models/qwen3.5-2b-base/model.safetensors-00001-of-00001.safetensors",
        "old_a3_adapter_diagnostics_only":"models/decider-a3-adapter/adapter.safetensors",
    }.items()}
    assert models["decider_2b"]=="acaef2228b134dcdc20cad4ee79219482c927ec819aa3687b9b8a575c338817f"
    assert models["qwen_3_5_2b_base"]=="928acbf11878c32185bbd863514d191769285065ab9ea14fbfe431303f5fdf2d"
    output={"recorded_at_utc":datetime.now(timezone.utc).isoformat(),"experiment_date":"2026-10-08",
            "python":platform.python_version(),"packages":packages,"device":torch.cuda.get_device_name(),
            "cuda_runtime":torch.version.cuda,"decider_source_commit":command(["git","-C","external/decider","rev-parse","HEAD"]),
            "base_repository_commit":command(["git","rev-parse","956535e"]),
            "ns3_version":command(["wsl","--","pkg-config","--modversion","ns3-lte"]),
            "binary_hashes":binary_hashes,"checkpoint_sha256":models,
            "model_revisions":{"decider":"533964dae8be954c5b5e19fa4948e48408094c1e","qwen":"b1485b2fa6dfa1287294f269f5fb618e03d52d7c"},
            "sha256":{p.as_posix():sha(p) for p in sorted(set(paths))},
            "timing_notes":["GPU batch=1 bf16 eager; no CUDA graphs or fused FLA; 8 torch CPU threads.",
                            "Model loading excluded; at least 3 warmup calls before measurements.",
                            "Confirmation head timers include a second CPU prompt-size tokenization after GPU synchronization, identically for both models.",
                            "Pilot Decider ran alongside CPU simulation; confirmation GPU models ran sequentially; timings are not randomized interleaved trials.",
                            "CPU timing is five batch-one repeats per sample; values may vary on analysis recomputation."],
            "evidence_notes":["210 actual ns-3 simulations; 1794 stored model requests excluding warmups.",
                              "Text variants reuse 6 physics cases and 5 evaluation RNG runs; never count replayed packets as independent trials.",
                              "Confirmation template families frozen before either model's confirmation inference; pilot labels are allowed training for its classical baseline.",
                              "Qwen matched raw prediction fields reflect initial strict parser; analysis recomputes legal letter prefixes from preserved raw strings."],
            "verification":{"unit_tests":"59 passed; 39 subtests passed","accounting":"verify_semantic_uc.py passed"}}
    (root/"provenance.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps({"files_hashed":len(output["sha256"]),"checkpoints":models,"binary_sha256":next(iter(binary_hashes.values()))},indent=2))


if __name__=="__main__":
    main()
