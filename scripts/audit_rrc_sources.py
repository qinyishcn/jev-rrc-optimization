"""Download and audit the public EEzim/RRC snapshot without publishing trace content.

Requires pandas + pyarrow already present in the local environment. Downloads remain
under data/rrc; the public artifact contains only aggregates and source hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import subprocess
import sys
from types import SimpleNamespace
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "rrc-source-audit/1.0"}), timeout=90) as response:
        return response.read()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Reuse the downloaded pinned snapshot")
    parser.add_argument("--revision", default="e473ea8b9891f608afb7d9ad89c412e2dda27e18")
    args = parser.parse_args()
    data = ROOT / "data/rrc"
    data.mkdir(parents=True, exist_ok=True)
    meta_path = data / "dataset_metadata.json"
    tree_path = data / "dataset_tree.json"
    if not args.offline:
        meta_path.write_bytes(fetch(f"https://huggingface.co/api/datasets/EEzim/RRC/revision/{args.revision}"))
        revision = json.loads(meta_path.read_bytes())["sha"]
        tree_path.write_bytes(fetch(f"https://huggingface.co/api/datasets/EEzim/RRC/tree/{revision}?recursive=true"))
    metadata = json.loads(meta_path.read_bytes())
    revision = metadata["sha"]
    tree = json.loads(tree_path.read_bytes())
    inventory = []
    for item in tree:
        if item["type"] != "file":
            continue
        name = item["path"]
        path = data / name
        if not path.resolve().is_relative_to(data.resolve()):
            raise ValueError("Unsafe upstream path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not args.offline:
            path.write_bytes(fetch(f"https://huggingface.co/datasets/EEzim/RRC/resolve/{revision}/{name}"))
        digest = sha(path)
        expected = item.get("lfs", {}).get("oid")
        if expected and digest != expected:
            raise ValueError(f"LFS hash mismatch: {name}")
        inventory.append({"path": name, "bytes": path.stat().st_size, "sha256": digest,
                          "lfs_hash_verified": digest == expected if expected else None})
    import pandas as pd
    df = pd.read_parquet(data / "demo.parquet")
    def message_names(column):
        names = re.findall(r"\bc1:\s*([A-Za-z][A-Za-z0-9-]*)\s*\(", "\n".join(df[column]))
        return dict(Counter(name for name in names if not re.search(r"-r\d+$", name)))
    texts = df["Q_Content"].tolist() + df["A_Content"].tolist()
    parameter_names = ["t-PollRetransmit", "pollPDU", "pollByte", "maxRetxThreshold", "t-Reordering",
                       "t-StatusProhibit", "periodicBSR-Timer", "retxBSR-Timer", "timeAlignmentTimerDedicated",
                       "prioritisedBitRate", "bucketSizeDuration", "logicalChannelGroup", "priority",
                       "a3-Offset", "hysteresis", "timeToTrigger", "reportInterval", "reportAmount",
                       "drx-Config", "onDurationTimer", "longDRX-CycleStartOffset", "shortDRX-Cycle"]
    parameters = {}
    for name in parameter_names:
        vals = Counter()
        for text in texts:
            vals.update(re.findall(r"(?m)^\s*" + re.escape(name) + r":\s*([^\n\r]+)", text))
        if vals:
            parameters[name] = dict(vals)
    delta = (df["A_Timestamp"] - df["Q_Timestamp"]) * 1000
    repo = ROOT / "external/nrrrc"
    git_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    utility = module("rrc_audit_utils", repo / "rrc_utils.py")
    parsed = utility.parse_rrc_log(str(repo / "demo.txt"))
    pairs = utility.create_qa_dataset(parsed)
    synthetic_pairs = utility.create_qa_dataset([
        {"timestamp": 1., "direction": "UL", "content": "request"},
        {"timestamp": 2., "direction": "DL", "content": "response"}])
    channel = module("rrc_audit_channel", repo / "srsRAN_5G/srsRAN_5G/channel_models.py")
    random.seed(7)
    gnb = SimpleNamespace(position=channel.Position(0, 0), frequency=3500, power=46)
    model = channel.SimplifiedChannelModel()
    near = model.calculate_rsrp(gnb, channel.Position(10, 0))
    random.seed(7)
    far = model.calculate_rsrp(gnb, channel.Position(1000, 0))
    toolkit = subprocess.run([sys.executable, str(repo / "rrc_toolkit.py"), "--help"],
                             capture_output=True, text=True, timeout=30)
    error_lines = toolkit.stderr.strip().splitlines()
    paper = data / "2505.16821v5.pdf"
    paper_download_error = None
    if not args.offline and not paper.exists():
        try:
            paper.write_bytes(fetch("https://arxiv.org/pdf/2505.16821v5"))
        except Exception as error:
            # A paper transport failure must not hide the dataset audit. Never
            # disable certificate verification; PowerShell's OS trust can be
            # used for a separate verified download on Windows if needed.
            paper_download_error = str(error)
    report = {
        "audit_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {"url": "https://huggingface.co/datasets/EEzim/RRC", "revision": revision,
                    "files": inventory, "rows": len(df), "schema": {k: str(v) for k,v in df.dtypes.items()},
                    "null_counts": df.isna().sum().to_dict(), "duplicate_rows": int(df.duplicated().sum()),
                    "question_message_types": message_names("Q_Content"),
                    "answer_message_types": message_names("A_Content"), "configuration_values": parameters,
                    "lte_text_count": sum("LTE Radio Resource Control" in t for t in texts),
                    "trace_text_count": len(texts),
                    "q_to_a_gap_ms": {"min": float(delta.min()), "median": float(delta.median()),
                                      "max": float(delta.max()), "p95": float(delta.quantile(.95))},
                    "gap_interpretation": "Paired trace wall-clock gaps, NOT user-plane packet latency or action outcome labels",
                    "missing_required_labels": ["packet latency", "packet loss", "traffic load", "QoS target",
                                                "configuration intervention outcome", "counterfactual outcome"],
                    "license": "Dataset card states Apache 2.0; no separate LICENSE file in snapshot",
                    "card_schema_matches_actual": False,
                    "raw_trace_policy": "Downloaded locally; no raw trace, identities, or NAS payload in public artifact"},
        "upstream": {"url": "https://github.com/EE-zim/nrRRC_Simulator", "revision": git_sha,
                     "license_files": [str(p.relative_to(repo)) for p in repo.rglob("*")
                                       if p.is_file() and p.name.lower() in ("license", "license.md", "license.txt", "copying")],
                     "dataset_demo_identical": sha(repo / "demo.parquet") == sha(data / "demo.parquet"),
                     "core_files": {str(p.relative_to(repo)): sha(p) for p in [repo / "rrc_utils.py",
                         repo / "srsRAN_5G/srsRAN_5G/channel_models.py",
                         repo / "srsRAN_5G/srsRAN_5G/enhanced_performance_metrics_collector.py"]},
                     "finding": "Linux srsRAN orchestration, trace extraction, mobility helpers; no verified standalone packet-latency evaluator",
                     "random_latency_placeholder": "enhanced_performance_metrics_collector.py:1254-1258"},
        "smoke": {"python_utf8_mode": sys.flags.utf8_mode,
                  "upstream_parser_demo_messages": len(parsed), "upstream_parser_demo_qa_pairs": len(pairs),
                  "synthetic_pair_pass": len(synthetic_pairs) == 1 and synthetic_pairs.iloc[0]["A_Content"] == "response",
                  "channel_near_rsrp": near, "channel_far_rsrp": far, "channel_monotonic_with_fixed_fading": near > far,
                  "toolkit_help_exit_code": toolkit.returncode, "toolkit_help_last_error": error_lines[-1] if error_lines else None,
                  "full_radio_stack_run": False, "real_network_latency_measured": False},
        "paper": {"url": "https://arxiv.org/pdf/2505.16821v5", "version": "v5", "date": "2026-01-15",
                  "sha256": sha(paper) if paper.exists() else None,
                  "bytes": paper.stat().st_size if paper.exists() else None,
                  "download_error": paper_download_error,
                  "metrics": ["semantic similarity", "ASN.1 micro-schema round-trip", "field coverage", "UL-DL state machine conformance", "DL message inference latency"],
                  "network_configuration_optimization_gain_measured": False,
                  "public_dataset_reproduces_full_paper": False}
    }
    out = ROOT / "artifacts/rrc_audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out.relative_to(ROOT)), "rows": len(df), "revision": revision,
                      "parameter_fields": len(parameters), "smoke": report["smoke"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
