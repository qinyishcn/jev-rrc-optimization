"""Checks for the generated-answer boundary of the Qwen baseline."""

import json

import pytest

from rrcopt.qwen_baseline import parse_profile, prompt_for
from rrcopt.simulation import generate_scenarios
from rrcopt.policies import OPTIONS, context
from scripts.run_qwen_baseline import load_cache, request_hash, summarize


@pytest.mark.parametrize("answer, expected", [
    ("off", "off"),
    (" 10/8\n", "10/8"),
    ("80/4", "80/4"),
    ("10/8 or off", None),
    ("Choose 10/8", None),
    ("10/8\n20/4", None),
    ("10/3", None),
    ("", None),
])
def test_parse_profile_requires_one_bare_allowed_name(answer, expected):
    assert parse_profile(answer) == expected


def test_prompt_reuses_descriptor_context_and_never_discloses_trace_seed():
    calibration = generate_scenarios(1, 26092801)[0]
    evaluation = generate_scenarios(1, 26092902)[0]
    current_mac = {"periodicBSR-Timer": "sf20"}
    prompt = prompt_for(evaluation, current_mac, [(calibration, "off")], OPTIONS)
    assert context(evaluation, current_mac) in prompt
    assert set(OPTIONS) <= set(prompt.split("Valid profiles: ", 1)[1].split(".\n", 1)[0].split(", "))
    assert str(evaluation.seed) not in prompt
    assert evaluation.uid not in prompt
    assert "miss_rate" not in prompt


def test_request_hash_binds_prompt_and_model_identity():
    assert request_hash("Profile:", {"revision": "a"}) != request_hash("Profile: off", {"revision": "a"})
    assert request_hash("Profile:", {"revision": "a"}) != request_hash("Profile:", {"revision": "b"})


def test_checkpoint_recovers_only_truncated_final_line(tmp_path):
    path = tmp_path / "decisions.jsonl"
    good = {"request_hash": "abc", "uid": "case"}
    path.write_text(json.dumps(good) + "\n{" , encoding="utf-8")
    assert load_cache(path) == {"abc": good}
    assert path.read_text(encoding="utf-8") == json.dumps(good) + "\n"
    assert path.with_suffix(".interrupted").read_text(encoding="utf-8") == "{"


def test_invalid_generation_is_counted_without_assigned_metrics():
    row = {"service": "xr", "profile": None, "metrics": None, "inference_ms": 12.0}
    overall = next(item for item in summarize([row]) if item["service"] == "all")
    assert overall["valid"] == 0
    assert overall["invalid"] == 1
    assert overall["invalid_or_constraint_violation"] == 1
    assert overall["valid_only_mean_rx_duty"] is None
