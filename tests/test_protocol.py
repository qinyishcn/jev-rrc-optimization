import unittest
from rrcopt.protocol import mac_context, message_types, integrate_fragment


class ProtocolTests(unittest.TestCase):
    def test_only_allowlisted_parameters_leave_trace(self):
        text = 'IMSI: SECRET123\n periodicBSR-Timer: sf20 (3)\n retxBSR-Timer: sf320 (0)\n timeAlignmentTimerDedicated: infinity (7)\nNAS: deadbeef'
        self.assertEqual(mac_context(text), {'periodicBSR-Timer':'sf20','retxBSR-Timer':'sf320','timeAlignmentTimerDedicated':'infinity'})
        self.assertNotIn('SECRET', str(mac_context(text)))

    def test_message_list_excludes_release_version_suffix(self):
        self.assertEqual(message_types('c1: rrcConnectionRequest (1) c1: rrcConnectionRequest-r8 (0)'), ['rrcConnectionRequest'])

    def test_bridge_rejects_nonwhitelisted_fields(self):
        with self.assertRaises(ValueError):
            integrate_fragment({'IMSI':'secret'}, {'drx-Config':{'release':None}})
