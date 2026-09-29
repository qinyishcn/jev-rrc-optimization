"""Plain autoregressive Qwen baseline for the frozen synthetic DRX task."""

from rrcopt.policies import OPTIONS, QUESTION, context


def parse_profile(text):
    """Only a single bare candidate name is an actionable configuration."""
    answer = text.strip()
    return answer if answer in OPTIONS else None


def prompt_for(scenario, current_mac, examples, option_order):
    """Completion prompt for a pretrained Base model; examples are calibration only."""
    lines = [
        "LTE connected-mode DRX profile selection.",
        QUESTION,
        "Valid profiles: " + ", ".join(option_order) + ".",
        "Reply with exactly one profile name, with no explanation.",
    ]
    for example_scenario, answer in examples:
        lines.extend(("State: " + context(example_scenario, current_mac),
                      "Profile: " + answer))
    lines.extend(("State: " + context(scenario, current_mac), "Profile:"))
    return "\n".join(lines)


class QwenGenerator:
    """GPU text generation from the official, local Qwen3.5 Base checkpoint."""

    def __init__(self, model_path):
        import torch
        from transformers import AutoModelForMultimodalLM, AutoTokenizer

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU required for measured baseline")
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, local_files_only=True,
            attn_implementation="sdpa").eval().to("cuda")

    def generate(self, prompt, max_new_tokens=16):
        import time

        self.torch.cuda.synchronize()
        start = time.perf_counter()
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
        with self.torch.inference_mode():
            ids = self.model.generate(**inputs, do_sample=False,
                                      max_new_tokens=max_new_tokens,
                                      stop_strings=["\n"], tokenizer=self.tokenizer,
                                      pad_token_id=self.tokenizer.eos_token_id)
        self.torch.cuda.synchronize()
        new_ids = ids[0, inputs["input_ids"].shape[-1]:]
        raw_text = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        elapsed_ms = 1000 * (time.perf_counter() - start)
        return raw_text, elapsed_ms, len(new_ids)
