"""Zero-shot autoregressive Qwen3.5-2B-Base A3 choice baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrcopt.qwen_baseline import QwenGenerator
from system_validation.decider_a3 import OPTIONS, QUESTION, state
from system_validation.run_sweep import scenarios


def prompt_for(case: dict) -> str:
    lines = [
        "LTE RRC Event A3 handover configuration selection.",
        QUESTION,
        "Candidates:",
    ]
    lines += [f"P{i}: {option}" for i, option in enumerate(OPTIONS)]
    lines += ["Reply with exactly one candidate ID (P0 to P4), with no explanation.",
              "Scenario: " + state(case), "Answer: P"]
    return "\n".join(lines)


def main() -> None:
    model = QwenGenerator("models/qwen3.5-2b-base")
    result = []
    for case in scenarios():
        prompt = prompt_for(case)
        raw, elapsed, tokens = model.generate(prompt, max_new_tokens=16)
        parsed = "P" + raw.strip()
        valid = parsed in {f"P{i}" for i in range(len(OPTIONS))}
        result.append({"case": case["name"], "prompt": prompt, "raw": raw,
                       "parsed_choice": OPTIONS[int(parsed[1:])] if valid else None,
                       "valid": valid, "inference_ms": elapsed, "generated_tokens": tokens})
        print(case["name"], repr(raw), round(elapsed, 1), flush=True)
    dest = Path("artifacts/system_validation/qwen_a3_base.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
