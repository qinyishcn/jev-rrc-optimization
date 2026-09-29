import copy
import tempfile
import unittest

from rrcopt.domain_training import (adapter_state, choose_label, inject_lora,
                                    load_adapter, make_phase_scenarios,
                                    ordered_options, save_adapter, split_scenarios)
from rrcopt.simulation import PROFILES, Scenario


class DomainTrainingTests(unittest.TestCase):
    def test_label_requires_all_independent_phases_to_meet_constraint(self):
        outcomes = {}
        for profile in PROFILES:
            outcomes[profile.name] = [
                {"miss_rate": 0.0, "rx_duty": 1.0 if profile.name == "off" else profile.on_ms / profile.cycle_ms,
                 "p99_ms": 2.0} for _ in range(3)]
        for name, phase in (("10/2", 2), ("20/4", 0), ("32/8", 1),
                            ("40/4", 0), ("80/4", 1)):
            outcomes[name][phase]["miss_rate"] = .02
        # 10/4 is the lowest duty among the remaining feasible profiles.
        self.assertEqual(choose_label(outcomes), "10/4")

    def test_phase_seeds_are_distinct_and_repeatable(self):
        s = Scenario("train", "gaming", 20, 10, 0, 2, .1, 1, 1000, 123)
        a = make_phase_scenarios(s, 3)
        self.assertEqual(a, make_phase_scenarios(s, 3))
        self.assertEqual(len({x.seed for x in a}), 3)
        self.assertTrue(all(x.seed != s.seed for x in a))

    def test_independent_splits_and_outcome_blind_order(self):
        train, val, test = split_scenarios(3)
        self.assertEqual([len(x) for x in (train, val, test)], [9, 9, 9])
        self.assertFalse({s.uid for s in train} & {s.uid for s in val})
        self.assertFalse({s.uid for s in train} & {s.uid for s in test})
        self.assertNotEqual(ordered_options(train[0].uid), ordered_options(train[1].uid))
        self.assertEqual(set(ordered_options(train[0].uid)), {p.name for p in PROFILES})

    def test_lora_changes_only_target_projections_and_has_gradients(self):
        import torch
        from torch import nn

        class Layer(nn.Module):
            def __init__(self):
                super().__init__()
                self.self_attn = nn.Module()
                self.self_attn.q_proj = nn.Linear(4, 4, bias=False)
                self.self_attn.v_proj = nn.Linear(4, 4, bias=False)

        class TinyLM(nn.Module):
            def __init__(self):
                super().__init__()
                self.model = nn.Module()
                self.model.layers = nn.ModuleList(Layer() for _ in range(24))
                self.config = type("Config", (), {"use_cache": True})()

        class TinyDecision(nn.Module):
            def __init__(self):
                super().__init__()
                self.lm = TinyLM()

        model = TinyDecision()
        clone = copy.deepcopy(model)
        targets = inject_lora(model, rank=2, alpha=4)
        self.assertEqual(len(targets), 12)
        self.assertEqual(targets[0], "lm.model.layers.3.self_attn.q_proj")
        self.assertEqual(len(adapter_state(model)), 24)
        self.assertFalse(model.lm.config.use_cache)
        self.assertTrue(all("lora_" in name for name, p in model.named_parameters() if p.requires_grad))
        layer = model.lm.model.layers[3].self_attn.q_proj
        layer(torch.randn(2, 4)).sum().backward()
        self.assertIsNotNone(layer.lora_B.grad)
        with torch.no_grad():
            layer.lora_B.fill_(.01)
        with tempfile.TemporaryDirectory() as directory:
            save_adapter(model, directory, {"rank": 2, "alpha": 4, "targets": targets})
            load_adapter(clone, directory)
            sample = torch.randn(2, 4)
            restored = clone.lm.model.layers[3].self_attn.q_proj(sample)
            self.assertTrue(torch.allclose(layer(sample), restored))


if __name__ == "__main__":
    unittest.main()
