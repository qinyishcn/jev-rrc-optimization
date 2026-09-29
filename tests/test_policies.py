import unittest
from dataclasses import replace

from rrcopt.simulation import Scenario, PROFILES
from rrcopt.policies import context, eligible, guard_choice, configuration_fragment, cost


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.s = Scenario('private-id', 'industrial_control', 5, 10, 0, 1, .1, 1, 1000, 98765)

    def test_context_does_not_leak_future_or_oracle(self):
        text = context(self.s)
        self.assertNotIn('98765', text)
        self.assertNotIn('private-id', text)
        self.assertNotIn('oracle', text.lower())
        self.assertEqual(text, context(replace(self.s, seed=1, uid='another')))

    def test_guard_keeps_off_and_rejects_long_sleep(self):
        choices = eligible(self.s)
        self.assertIn('off', choices)
        self.assertIn('10/8', choices)
        self.assertNotIn('80/4', choices)
        self.assertEqual(guard_choice(self.s), '10/8')

    def test_tight_deadline_falls_back_to_off(self):
        s = replace(self.s, deadline_ms=1.2)
        self.assertEqual(guard_choice(s), 'off')

    def test_fragment_uses_legal_fields_and_releases_off(self):
        self.assertEqual(configuration_fragment('off')['drx-Config'], {'release': None})
        setup = configuration_fragment('20/8')['drx-Config']['setup']
        self.assertEqual(setup['longDRX-CycleStartOffset'], {'sf20': 0})
        self.assertEqual(setup['onDurationTimer'], 'psf8')
        self.assertEqual(setup['drx-InactivityTimer'], 'psf1')

    def test_objective_prefers_feasibility_then_duty(self):
        self.assertLess(cost({'miss_rate':0,'rx_duty':1,'p99_ms':3}, 5),
                        cost({'miss_rate':.5,'rx_duty':.1,'p99_ms':30}, 5))


if __name__ == '__main__':
    unittest.main()
