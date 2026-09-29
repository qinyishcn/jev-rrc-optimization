"""Hand-computable and conservation checks for the synthetic DRX evaluator."""
import dataclasses
import math
import unittest

import numpy as np

from rrcopt.simulation import (
    PROFILES, Profile, Scenario, generate_arrivals, generate_scenarios, simulate,
)


class SimulationTests(unittest.TestCase):
    def evaluate(self, arrivals, profile=None, **overrides):
        args = dict(packet_service_ms=1.0, base_delay_ms=0.0,
                    deadline_ms=5.0, duration_ms=20.0)
        args.update(overrides)
        return simulate(arrivals, profile or Profile("10/2", 10, 2), **args)

    def test_awake_sleep_and_window_boundary(self):
        # Completions 1, 11, 12: delays 1, 8, 2.
        result = self.evaluate([0, 3, 10])
        self.assertAlmostEqual(result["mean_ms"], 11 / 3)
        self.assertEqual(result["max_ms"], 8)
        self.assertAlmostEqual(result["p95_ms"], 7.4)
        self.assertAlmostEqual(result["p99_ms"], 7.88)
        self.assertAlmostEqual(result["miss_rate"], 1 / 3)
        self.assertEqual(result["packets"], 3)
        self.assertEqual(result["rx_duty"], 0.2)

    def test_packet_that_does_not_fit_waits_for_next_window(self):
        self.assertEqual(self.evaluate([1.5])["mean_ms"], 9.5)

    def test_packet_ending_exactly_at_window_end_fits(self):
        self.assertEqual(self.evaluate([1])["mean_ms"], 1)

    def test_fifo_burst_spills_and_drains_after_horizon(self):
        result = self.evaluate([0] * 5, duration_ms=1)
        self.assertEqual(result["packets"], 5)
        self.assertEqual(result["mean_ms"], (1 + 2 + 11 + 12 + 21) / 5)
        self.assertEqual(result["last_completion_ms"], 21)
        self.assertEqual(result["drain_ms"], 20)
        self.assertTrue(result["overloaded"])

    def test_deadline_equality_is_not_a_miss(self):
        result = self.evaluate([0], deadline_ms=3, base_delay_ms=2)
        self.assertEqual(result["mean_ms"], 3)
        self.assertEqual(result["miss_rate"], 0)
        result = self.evaluate([0], deadline_ms=2.999, base_delay_ms=2)
        self.assertEqual(result["miss_rate"], 1)

    def test_base_delay_does_not_hold_server(self):
        result = self.evaluate([0, 0], PROFILES[0], base_delay_ms=100)
        self.assertEqual(result["mean_ms"], 101.5)
        self.assertEqual(result["last_completion_ms"], 2)

    def test_disabled_drx_is_delay_lower_bound_on_common_trace(self):
        arrivals = np.sort(np.random.default_rng(42).uniform(0, 100, 100))
        baseline = self.evaluate(arrivals, PROFILES[0], duration_ms=100,
                                 packet_service_ms=0.3)
        self.assertEqual(baseline["rx_duty"], 1)
        for profile in PROFILES[1:]:
            result = self.evaluate(arrivals, profile, duration_ms=100,
                                   packet_service_ms=0.3)
            for metric in ("mean_ms", "p95_ms", "p99_ms", "miss_rate"):
                self.assertGreaterEqual(result[metric] + 1e-10, baseline[metric])
            self.assertEqual(result["packets"], len(arrivals))

    def test_capacity_accounts_for_nonfragmented_packets(self):
        result = self.evaluate([0], packet_service_ms=0.6, duration_ms=10)
        self.assertAlmostEqual(result["capacity_packets_per_ms"], 0.3)
        self.assertAlmostEqual(result["utilization"], 1 / 3)
        self.assertFalse(result["overloaded"])

    def test_fractional_packets_do_not_lose_window_slot_to_roundoff(self):
        result = self.evaluate([0] * 20, packet_service_ms=0.1)
        self.assertAlmostEqual(result["last_completion_ms"], 2)

    def test_load_stress_keeps_every_packet(self):
        count = 10000
        result = self.evaluate(np.zeros(count), duration_ms=1)
        self.assertEqual(result["packets"], count)
        self.assertEqual(result["last_completion_ms"], 49992)
        self.assertTrue(all(math.isfinite(value) for value in result.values()))

    def test_matches_independent_integer_slot_enumeration(self):
        arrivals = np.sort(np.random.default_rng(77).integers(0, 100, 100))
        for profile in PROFILES[1:]:
            # Independent oracle: enumerate allowed unit slots, then allocate
            # a monotonically increasing slot index to each integer arrival.
            slots = np.array([t for t in range(10000)
                              if t % profile.cycle_ms < profile.on_ms])
            index, finishes = 0, []
            for arrival in arrivals:
                index = max(index, int(np.searchsorted(slots, arrival)))
                finishes.append(slots[index] + 1)
                index += 1
            delays = np.asarray(finishes) - arrivals
            result = self.evaluate(arrivals, profile, duration_ms=100)
            self.assertAlmostEqual(result["mean_ms"], float(np.mean(delays)))
            self.assertEqual(result["p99_ms"], float(np.quantile(delays, .99)))
            self.assertEqual(result["last_completion_ms"], finishes[-1])

    def test_invalid_arrivals_raise(self):
        for arrivals in ([], [-1], [20], [2, 1], [math.nan], [math.inf], [[0]]):
            with self.subTest(arrivals=arrivals), self.assertRaises(ValueError):
                self.evaluate(arrivals)

    def test_invalid_scalar_parameters_raise(self):
        for field, values in {
            "packet_service_ms": [0, -1, math.inf, math.nan, 2.1],
            "base_delay_ms": [-1, math.inf, math.nan],
            "deadline_ms": [0, -1, math.inf, math.nan],
            "duration_ms": [0, -1, math.inf, math.nan],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.evaluate([0], **{field: value})

    def test_numerically_unrepresentable_capacity_raises(self):
        with self.assertRaises(ValueError):
            self.evaluate([0], PROFILES[0], packet_service_ms=5e-324)

    def test_numerically_unrepresentable_service_increment_raises(self):
        with self.assertRaises(ValueError):
            self.evaluate([1], PROFILES[0], packet_service_ms=1e-30)

    def test_profiles_have_legal_long_cycles_and_unique_names(self):
        self.assertEqual([p.name for p in PROFILES],
                         ["off", "10/8", "10/4", "10/2", "20/8", "20/4", "32/8", "40/4", "80/4"])
        self.assertEqual((PROFILES[0].cycle_ms, PROFILES[0].on_ms), (0, 0))
        for profile in PROFILES[1:]:
            self.assertIn(profile.cycle_ms, {10, 20, 32, 40, 64, 80, 128, 160,
                                           256, 320, 512, 640, 1024, 1280, 2048, 2560})

    def test_invalid_profiles_raise(self):
        for cycle, on in ((0, 1), (10, 0), (-1, 1), (10, 11), (math.inf, 2),
                          (10, math.nan), (8, 2), (10, 3.5)):
            with self.subTest(cycle=cycle, on=on), self.assertRaises(ValueError):
                Profile("bad", cycle, on)


class TrafficTests(unittest.TestCase):
    def test_scenarios_are_reproducible_and_services_balanced(self):
        scenarios = generate_scenarios(5, 123)
        self.assertEqual(scenarios, generate_scenarios(5, 123))
        self.assertNotEqual(scenarios, generate_scenarios(5, 124))
        self.assertEqual(len({s.uid for s in scenarios}), 15)
        for service in ("industrial_control", "xr", "gaming"):
            self.assertEqual(sum(s.service == service for s in scenarios), 5)

    def test_trace_seed_determinism_horizon_and_bursts(self):
        scenario = Scenario("a", "gaming", 20, 10, 0, 3, 0.1, 1, 1000, 123)
        arrivals = generate_arrivals(scenario)
        np.testing.assert_array_equal(arrivals, generate_arrivals(scenario))
        self.assertEqual(len(arrivals), 300)
        self.assertTrue(np.all(np.diff(arrivals) >= 0))
        self.assertTrue(np.all((arrivals >= 0) & (arrivals < 1000)))
        np.testing.assert_array_equal(arrivals[::3], arrivals[1::3])
        self.assertGreater(arrivals[0], 0)  # randomized traffic phase
        changed = generate_arrivals(dataclasses.replace(scenario, seed=124))
        self.assertFalse(np.array_equal(arrivals, changed))

    def test_every_generated_trace_is_evaluable_under_every_profile(self):
        for scenario in generate_scenarios(3, 123):
            arrivals = generate_arrivals(scenario)
            for profile in PROFILES:
                result = simulate(arrivals, profile, scenario.packet_service_ms,
                                  scenario.base_delay_ms, scenario.deadline_ms,
                                  scenario.duration_ms)
                self.assertEqual(result["packets"], len(arrivals))

    def test_invalid_generation_inputs_raise(self):
        for count in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                generate_scenarios(count, 1)
        base = Scenario("a", "gaming", 20, 10, 1, 3, 0.1, 1, 1000, 123)
        for field, value in (("period_ms", 0), ("jitter_ms", -1),
                             ("burst_packets", 0), ("burst_packets", 1.5),
                             ("seed", -1), ("duration_ms", math.inf),
                             ("packet_service_ms", 0), ("deadline_ms", 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                generate_arrivals(dataclasses.replace(base, **{field: value}))


if __name__ == "__main__":
    unittest.main()
