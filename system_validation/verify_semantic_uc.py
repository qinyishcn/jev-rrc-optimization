"""CPU-only accounting, input-boundary and result-join verification."""
import hashlib
import json
from pathlib import Path
import sys
from collections import defaultdict

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from system_validation.semantic_uc import OUT, POLICY, make_dataset, observed_state, physics_cases, validate_simulations, decode_choice
from system_validation.confirm_semantic_uc import confirmation
from system_validation.analyze_sweep import summarize


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    source=Path("system_validation/ns3_lte_handover.cc")
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    sims={}
    for filename,runs in (("calibration.jsonl",[91,92]),("holdout.jsonl",[101,102,103,104,105])):
        rows=[json.loads(s) for s in (OUT/filename).read_text(encoding="utf-8").splitlines()]
        validate_simulations(rows,physics_cases(),runs)
        assert all(r["source_sha256"]==sha for r in rows)
        if filename=="holdout.jsonl":
            sims={(r["case"],r["run"],(r["hysteresis_db"],r["ttt_ms"])):r for r in rows}
    summary=read(OUT/"summary.json")
    assert read(OUT/"frozen_dataset.json")["dataset"]==make_dataset()
    assert read(OUT/"confirmation_dataset.json")==confirmation()
    for dataset,filename,metrics in ((make_dataset(),"selected_results.json",summary["metrics"]),
                                     (confirmation(),"confirmation_selected_results.json",summary["confirmation"]["metrics"])):
        index={r["id"]:r for r in dataset["test"]}
        selected=read(OUT/filename)
        expected={(uid,run,method) for uid in index for run in range(101,106) for method in metrics}
        keys=[(r["id"],r["run"],r["method"]) for r in selected]
        assert set(keys)==expected and len(keys)==len(expected)
        grouped=defaultdict(list)
        for r in selected:
            original=sims[(index[r["id"]]["case"],r["run"],tuple(r["profile"]))]
            assert r["family"]==index[r["id"]]["family"]
            if r["prediction"] in POLICY:
                assert tuple(r["profile"])==POLICY[r["prediction"]]
            for field in ("sent","received","lost","late_received","deadline_miss_including_loss","p99_delay_ms","handover_starts"):
                assert r[field]==original[field]
            grouped[r["method"]].append(original)
        for method,rows in grouped.items():
            for field,value in summarize(rows).items():
                assert abs(metrics[method][field]-value)<1e-12,(method,field)
            if "intent_accuracy" in metrics[method]:
                choices={r["id"]:r["prediction"] for r in selected if r["method"]==method}
                accuracy=sum(pred==index[uid]["label"] for uid,pred in choices.items())/len(index)
                assert abs(metrics[method]["intent_accuracy"]-accuracy)<1e-12
    all_rows={r["id"]:r for ds in (make_dataset(),confirmation()) for rows in ds.values() for r in rows}
    request_count=0
    for filename in ("decider.json","confirmation_decider.json","confirmation_qwen_onepass.json"):
        rows=read(OUT/filename)
        request_count+=len(rows)
        keys=[]
        for r in rows:
            assert json.loads(r["input"])==observed_state(all_rows[r["id"]])
            assert r["prediction"]==decode_choice(r["answer"]["choice"],r["options"])
            assert abs(sum(r["answer"]["probs_list"])-1)<1e-5
            assert r["inference_ms"]>0
            keys.append((r["id"],r.get("variant"),r["order"]))
        assert len(keys)==len(set(keys))
    for filename in ("diagnose_base.json","diagnose_adapter.json"):
        rows=read(OUT/filename)["rows"]
        assert len(rows)==204
        request_count+=len(rows)
        assert max(r["context_tokens"] for r in rows)<1536
    request_count+=len(read(OUT/"representation.json"))+len(read(OUT/"qwen.json"))
    assert request_count==1794
    print(json.dumps(dict(status="passed",ns3_runs=210,heldout_physics_realizations=150,
                          model_requests=request_count,source_sha256=sha,
                          text_rows_pilot=60,text_rows_confirmation=144),indent=2))


if __name__=="__main__":
    main()
