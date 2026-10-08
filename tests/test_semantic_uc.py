"""Protect the information boundary and counterfactual comparison."""
import unittest

from system_validation.semantic_uc import (
    make_dataset, observed_state, physics_cases, rotated, decode_choice,
    validate_simulations,
)


class SemanticUCTests(unittest.TestCase):
    def test_no_future_or_label_in_observation(self):
        row = make_dataset()["test"][0]
        state = observed_state(row)
        for key in ("label", "trajectory", "gold", "family", "case", "turnPeriodS"):
            self.assertNotIn(key, state)
        self.assertEqual(state["dispatch_text"], row["text"])

    def test_counterfactual_numeric_observations_identical(self):
        rows = make_dataset()["test"]
        groups = {}
        for row in rows:
            numeric = observed_state(row).copy()
            numeric.pop("dispatch_text")
            key = (row["family"], row["geometry"])
            groups.setdefault(key, []).append((row["label"], numeric))
        for pair in groups.values():
            self.assertEqual({x[0] for x in pair}, {"cross", "patrol"})
            self.assertEqual(pair[0][1], pair[1][1])

    def test_template_families_separated(self):
        data = make_dataset()
        seen = set()
        for split in ("train", "dev", "test"):
            families = {r["family"] for r in data[split]}
            self.assertFalse(seen & families)
            seen |= families

    def test_option_rotation_preserves_semantic_decoding(self):
        pairs = [("cross", "One-way"), ("patrol", "Back and forth")]
        for offset in range(2):
            options = rotated(pairs, offset)
            for label, text in options:
                self.assertEqual(decode_choice(text, options), label)
        with self.assertRaises(ValueError):
            decode_choice("unknown", pairs)

    def test_missing_or_duplicate_simulations_rejected(self):
        with self.assertRaises(ValueError):
            validate_simulations([], physics_cases(), [101])
        row = {"case": physics_cases()[0]["name"], "run": 101,
               "hysteresis_db": 0, "ttt_ms": 0}
        with self.assertRaises(ValueError):
            validate_simulations([row, row], physics_cases(), [101])

    def test_base_completion_can_include_option_description(self):
        from system_validation.semantic_uc import parse_letter_completion
        pairs = [("cross", "One-way"), ("patrol", "Back and forth")]
        self.assertEqual(parse_letter_completion("A) One-way", pairs), "cross")
        self.assertEqual(parse_letter_completion("B) Back and", pairs), "patrol")
        self.assertIsNone(parse_letter_completion("C) Other", pairs))
        self.assertIsNone(parse_letter_completion("Ambiguous", pairs))

    def test_confirmation_families_not_in_training(self):
        from system_validation.confirm_semantic_uc import confirmation
        data = confirmation()
        self.assertFalse({r["family"] for r in data["train"]} &
                         {r["family"] for r in data["test"]})
        self.assertEqual(len({r["text"] for r in data["test"]}), 48)
        self.assertFalse({r["text"] for r in data["train"]} &
                         {r["text"] for r in data["test"]})

    def test_paired_bootstrap_has_zero_difference_for_identical_methods(self):
        import numpy as np
        from system_validation.analyze_semantic_uc import bootstrap_family_run
        rows=[]
        for family in ("f0","f1"):
            for run in (1,2):
                for method in ("a","b"):
                    rows.append(dict(family=family,run=run,method=method,sent=100,
                                     deadline_miss_including_loss=run))
        result=bootstrap_family_run(rows,"a","b",np.random.default_rng(1),100)
        self.assertEqual(result["difference"],0)
        self.assertEqual(result["ci95"],[0,0])


if __name__ == "__main__":
    unittest.main()
