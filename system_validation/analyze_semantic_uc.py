"""Recompute diagnosis and paired text-to-RRC results from saved evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_validation.run_sweep import PROFILES
from system_validation.semantic_uc import (OUT, POLICY, INTENTS, make_dataset, physics_cases,
                                           keyword, validate_simulations, rotated, parse_letter_completion,observed_state)
from system_validation.analyze_sweep import summarize, normalized_geometry_rule


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]


def diagnose():
    old = jsonl("artifacts/system_validation/holdout.jsonl")
    groups = defaultdict(dict)
    for r in old:
        groups[(r["case"], r["run"])][(r["hysteresis_db"], r["ttt_ms"])] = r
    result = {}
    for model in ("base", "adapter"):
        rows = read(OUT/f"diagnose_{model}.json")["rows"]
        variants = {}
        for variant in ("raw", "derived", "knowledge", "route_control"):
            vr = [r for r in rows if r["variant"] == variant]
            order_results = {}
            for order in sorted({r["order"] for r in vr}):
                rs = [r for r in vr if r["order"] == order]
                predictions = {r["case"]: r["prediction"] for r in rs}
                if variant == "route_control":
                    order_results[order] = {"accuracy": sum(
                        r["prediction"] == ("cross" if r["case"].startswith("cross") else "patrol")
                        for r in rs)/len(rs)}
                else:
                    selected = [by[PROFILES[predictions[case]]] for (case, run), by in groups.items()]
                    order_results[order] = summarize(selected)
            consistency = []
            for case in sorted({r["case"] for r in vr}):
                consistency.append(len({r["prediction"] for r in vr if r["case"] == case}) == 1)
            variants[variant] = {"n": len(vr), "counts": dict(Counter(r["prediction"] for r in vr)),
                                 "order_consistent_cases": sum(consistency), "orders": order_results,
                                 "context_token_range": [min(r["context_tokens"] for r in vr), max(r["context_tokens"] for r in vr)]}
        result[model] = variants
    representation = read(OUT/"representation.json")
    result["representation"] = {}
    for variant in sorted({r["variant"] for r in representation}):
        rr = [r for r in representation if r["variant"] == variant and r["task"] == "route"]
        ar = [r for r in representation if r["variant"] == variant and r["task"] == "a3"]
        result["representation"][variant] = {
            "route_correct": sum(r["prediction"] == ("cross" if r["case"].startswith("cross") else "patrol") for r in rr),
            "route_n": len(rr), "a3_counts": dict(Counter(r["prediction"] for r in ar)),
        }
    # Hindsight diagnostic bound: how much variation cannot be resolved by a
    # deterministic function of the already-supplied descriptor (seed excluded)?
    result["old_descriptor_bounds"] = {}
    for suite in ("holdout", "generalization", "fresh_geometry"):
        rows = jsonl(f"artifacts/system_validation/{suite}.jsonl")
        bycase = defaultdict(lambda: defaultdict(list))
        byrun = defaultdict(list)
        for r in rows:
            bycase[r["case"]][(r["hysteresis_db"], r["ttt_ms"])].append(r)
            byrun[(r["case"],r["run"])].append(r)
        key = lambda rs: (sum(r["deadline_miss_including_loss"] for r in rs), sum(r["lost"] for r in rs), sum(r["handover_starts"] for r in rs))
        descriptor_bound = sum(min(key(rs)[0] for rs in profiles.values()) for profiles in bycase.values())
        seed_bound = sum(min(r["deadline_miss_including_loss"] for r in rs) for rs in byrun.values())
        rule_misses = sum(r["deadline_miss_including_loss"] for r in rows
                          if (r["hysteresis_db"],r["ttt_ms"]) == normalized_geometry_rule(r))
        result["old_descriptor_bounds"][suite] = dict(descriptor_hindsight_misses=descriptor_bound,
                                                       per_seed_hindsight_misses=seed_bound, rule_misses=rule_misses)
    training = jsonl("artifacts/system_validation/adaptation_labels.jsonl")
    groups = defaultdict(lambda: defaultdict(list))
    for r in training:
        groups[r["case"]][(r["hysteresis_db"],r["ttt_ms"])].append(r)
    tie_counts = Counter()
    for profiles in groups.values():
        losses = [sum(r["deadline_miss_including_loss"] for r in profiles[p]) for p in PROFILES]
        tie_counts[sum(x == min(losses) for x in losses)] += 1
    result["training"] = {"primary_objective_tie_counts": dict(tie_counts), "metadata": read("artifacts/system_validation/a3_train_result.json"),
                          "optimizer_updates": 16}
    return result


def cpu_baselines(data):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.linear_model import LogisticRegression

    # Identical text is deliberately reused across physics; deduplicate training
    # so three geometries do not pretend to be three independent language labels.
    unique = {r["text"]: r["label"] for r in data["train"]}
    model = Pipeline([
        ("tfidf", FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), sublinear_tf=True)),
        ])),
        ("clf", LogisticRegression(C=1, max_iter=1000, random_state=2601008)),
    ])
    model.fit(list(unique), list(unique.values()))
    rows = data["test"]
    output = {"keyword": {}, "tfidf": {}}
    latencies = {k: [] for k in output}
    # Three warmups and five batch-one measurements per sample, interleaved.
    for _ in range(3):
        model.predict([rows[0]["text"]])
    for row in rows:
        for repeat in range(5):
            start = time.perf_counter()
            prediction = keyword(row["text"])
            latencies["keyword"].append(1000*(time.perf_counter()-start))
            output["keyword"][row["id"]] = prediction
            start = time.perf_counter()
            prediction = str(model.predict([row["text"]])[0])
            latencies["tfidf"].append(1000*(time.perf_counter()-start))
            output["tfidf"][row["id"]] = prediction
    dev_pred = model.predict([r["text"] for r in data["dev"]])
    return output, latencies, {"unique_train_texts": len(unique), "C": 1, "dev_accuracy": float(np.mean(dev_pred == [r["label"] for r in data["dev"]])),
                               "sklearn_version": __import__("sklearn").__version__}


def bootstrap_family_run(rows,a,b,rng,repetitions=10000):
    """Resample text families and common RNG runs on two paired axes.

    All geometry/intent cells within a family remain together. The same RNG
    draw is shared by all sampled text families (physics is reused across text).
    """
    import numpy as np
    groups=defaultdict(list)
    for row in rows:
        if row["method"] in (a,b):
            groups[(row["family"],row["run"],row["method"])].append(row)
    families=sorted({x[0] for x in groups})
    runs=sorted({x[1] for x in groups})
    differences=[]
    for family in families:
        line=[]
        for run in runs:
            rates=[]
            for method in (a,b):
                rs=groups[(family,run,method)]
                if not rs:
                    raise ValueError("incomplete paired bootstrap input")
                rates.append(sum(r["deadline_miss_including_loss"] for r in rs)/sum(r["sent"] for r in rs))
            line.append(rates[0]-rates[1])
        differences.append(line)
    delta=np.array(differences)
    fi=rng.integers(0,len(families),(repetitions,len(families)))
    si=rng.integers(0,len(runs),(repetitions,len(runs)))
    draws=delta[fi[:,:,None],si[:,None,:]].mean(axis=(1,2))
    return {"difference":float(delta.mean()),"ci95":[float(x) for x in np.quantile(draws,[.025,.975])],
            "bootstrap_unit":"paired text family x common RNG run; fixed geometries","repetitions":repetitions}


def analyze_confirmation(mapping,fixed):
    import numpy as np
    from system_validation.confirm_semantic_uc import confirmation,improved_keyword

    data=confirmation()
    assert read(OUT/"confirmation_dataset.json")==data
    predictions,latency,metadata=cpu_baselines(data)
    predictions["improved_keyword"]={r["id"]:improved_keyword(r["text"]) for r in data["test"]}
    for model,path in (("decider","confirmation_decider.json"),("qwen_onepass","confirmation_qwen_onepass.json")):
        for order in (0,1):
            name=model+("_reversed" if order else "")
            rr=[r for r in read(OUT/path) if r["suite"]=="confirmation" and r["order"]==order]
            assert {r["id"] for r in rr}=={r["id"] for r in data["test"]} and len(rr)==len(data["test"])
            predictions[name]={r["id"]:r["prediction"] for r in rr}
            latency[name]=[r["inference_ms"] for r in rr]
    metrics={}
    detailed=[]
    errors={}
    for method in ["calibrated_fixed","known_intent"]+list(predictions):
        selected=[]
        wrong=[]
        for r in data["test"]:
            label=r["label"] if method=="known_intent" else predictions.get(method,{}).get(r["id"])
            profile=fixed if method=="calibrated_fixed" else POLICY[label]
            if method in predictions and label!=r["label"]:
                wrong.append(r["id"])
            for run in range(101,106):
                sim=mapping[(r["case"],run,profile)]
                selected.append(sim)
                detailed.append(dict(id=r["id"],family=r["family"],method=method,run=run,
                                     prediction=label,profile=list(profile),
                                     **{k:sim[k] for k in ("sent","received","lost","late_received","deadline_miss_including_loss","p99_delay_ms","handover_starts")}))
        metrics[method]=summarize(selected)
        metrics[method]["mean_handovers_per_session"]=metrics[method]["handover_starts"]/len(selected)
        if method in predictions:
            metrics[method]["intent_accuracy"]=1-len(wrong)/len(data["test"])
            errors[method]=wrong
        if method in latency:
            metrics[method]["inference_ms"]={"n":len(latency[method]),"p50":float(np.median(latency[method])),"p95":float(np.quantile(latency[method],.95))}
    rng=np.random.default_rng(2601009)
    comparisons={b:bootstrap_family_run(detailed,"decider",b,rng) for b in metrics if b!="decider"}
    (OUT/"confirmation_selected_results.json").write_text(json.dumps(detailed,indent=2),encoding="utf-8")
    return {"counts":{"text_rows":144,"unique_texts":48,"language_families":24,"unique_train_texts":32},
            "metrics":metrics,"errors":errors,"tfidf":metadata,"comparisons_decider_minus_baseline":comparisons}


def main():
    import numpy as np

    data = make_dataset()
    assert read(OUT/"frozen_dataset.json")["dataset"] == data
    sim = jsonl(OUT/"holdout.jsonl")
    cal = jsonl(OUT/"calibration.jsonl")
    validate_simulations(sim, physics_cases(), [101,102,103,104,105])
    validate_simulations(cal, physics_cases(), [91,92])
    digest = hashlib.sha256(Path("system_validation/ns3_lte_handover.cc").read_bytes()).hexdigest()
    assert all(r["source_sha256"] == digest for r in sim+cal)
    fixed = min(PROFILES, key=lambda p: sum(r["deadline_miss_including_loss"] for r in cal if (r["hysteresis_db"],r["ttt_ms"]) == p))
    mapping = {(r["case"],r["run"],(r["hysteresis_db"],r["ttt_ms"])): r for r in sim}
    decisions, latency, tfidf_metadata = cpu_baselines(data)
    for variant, order, name in (("semantic",0,"decider"),("semantic",1,"decider_reversed"),("direct",0,"decider_direct")):
        rr = [r for r in read(OUT/"decider.json") if r["id"].startswith("test_") and r["variant"] == variant and r["order"] == order]
        assert len(rr) == len(data["test"])
        decisions[name] = {r["id"]: r["prediction"] for r in rr}
        latency[name] = [r["inference_ms"] for r in rr]
    for variant in ("fewshot", "matched"):
        for order in (0,1):
            name = f"qwen_{variant}" + ("_reversed" if order else "")
            rr = [r for r in read(OUT/"qwen.json") if r["id"].startswith("test_") and r["variant"] == variant and r["order"] == order]
            assert len(rr) == len(data["test"])
            # The frozen raw generations remain unchanged. Base completions
            # append a description after the legal letter, which is actionable.
            decisions[name] = {r["id"]: (parse_letter_completion(r["raw"],rotated(INTENTS,order))
                                          if variant == "matched" else r["prediction"]) for r in rr}
            latency[name] = [r["inference_ms"] for r in rr]
    methods = ["default", "calibrated_fixed", "numeric_only", "known_intent"] + list(decisions)
    metrics = {}
    detailed = []
    selected_profiles = defaultdict(dict)
    for method in methods:
        chosen = []
        correct = invalid = 0
        for row in data["test"]:
            prediction = None
            if method == "default":
                profile = (3,256)
            elif method in ("calibrated_fixed", "numeric_only"):
                profile = fixed
            elif method == "known_intent":
                profile = POLICY[row["label"]]
            else:
                prediction = decisions[method][row["id"]]
                if method == "decider_direct":
                    profile = PROFILES[prediction]
                else:
                    correct += prediction == row["label"]
                    invalid += prediction is None
                    # Invalid generations fall back to calibration-best fixed.
                    profile = POLICY[prediction] if prediction is not None else fixed
            selected_profiles[row["id"]][method] = list(profile)
            for run in range(101,106):
                result = mapping[(row["case"],run,profile)]
                chosen.append(result)
                detailed.append({"id": row["id"], "family": row["family"], "method": method,
                                 "run": run, "prediction": prediction, "profile": list(profile),
                                 **{k: result[k] for k in ("sent","received","lost","late_received","deadline_miss_including_loss","p99_delay_ms","handover_starts")}})
        metrics[method] = summarize(chosen)
        metrics[method]["mean_handovers_per_session"] = metrics[method]["handover_starts"]/len(chosen)
        if method in decisions and method != "decider_direct":
            metrics[method].update(intent_accuracy=correct/len(data["test"]), invalid=invalid)
        if method in latency:
            metrics[method]["inference_ms"] = {"n":len(latency[method]), "p50":float(np.median(latency[method])), "p95":float(np.quantile(latency[method],.95))}
    rng = np.random.default_rng(2601008)
    comparisons = {b: bootstrap_family_run(detailed,"decider",b,rng)
                   for b in methods if b != "decider"}
    example = next(r for r in data["test"] if r["id"] == "test_7_1_cross")
    example_sim = [r for r in sim if r["case"] == example["case"] and r["run"] == 101]
    output = {"counts": {"train_text_rows":len(data["train"]),"dev_text_rows":len(data["dev"]),"test_text_rows":len(data["test"]),
                         "unique_physics_cases":len(physics_cases()),"calibration_runs":len(cal),"holdout_runs":len(sim),
                         "test_language_families":10,"rng_runs":5},
              "calibrated_fixed":list(fixed), "source_sha256":digest, "metrics":metrics,
              "tfidf":tfidf_metadata,"comparisons_decider_minus_baseline":comparisons,
              "diagnosis":diagnose(), "example":{"row":example,"input":observed_state(example),
              "profiles":selected_profiles[example["id"]],"simulations":example_sim}}
    output["confirmation"]=analyze_confirmation(mapping,fixed)
    example_output={"cross":output["example"]}
    patrol=next(r for r in data["test"] if r["id"]=="test_7_1_patrol")
    example_output["patrol"]={"row":patrol,"input":observed_state(patrol),
                              "profiles":selected_profiles[patrol["id"]],
                              "simulations":[r for r in sim if r["case"]==patrol["case"] and r["run"]==101]}
    for label in ("cross","patrol"):
        uid=example_output[label]["row"]["id"]
        example_output[label]["model_records"]={
            "decider":[r for r in read(OUT/"decider.json") if r["id"]==uid and r["order"]==0],
            "qwen_generation":[r for r in read(OUT/"qwen.json") if r["id"]==uid and r["order"]==0],
            "qwen_onepass":[r for r in read(OUT/"confirmation_qwen_onepass.json") if r["id"]==uid and r["order"]==0]}
    (OUT/"example.json").write_text(json.dumps(example_output,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"summary.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"selected_results.json").write_text(json.dumps(detailed,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:{f:v for f,v in m.items() if f in ("deadline_miss_rate","intent_accuracy","invalid","inference_ms")} for k,m in metrics.items()},indent=2))


if __name__ == "__main__":
    main()
