import unittest
from rrcopt.temperature import rescale, choose_with_fallback


class TemperatureTests(unittest.TestCase):
    def test_positive_temperature_preserves_argmax(self):
        original={'a':.7,'b':.2,'c':.1}
        for t in [.1,.5,1,2,5]:
            converted=rescale(original,1.164,t)
            self.assertEqual(max(converted,key=converted.get),'a')
            self.assertAlmostEqual(sum(converted.values()),1)

    def test_gate_does_change_action_on_low_confidence(self):
        p={'a':.51,'b':.49}
        self.assertEqual(choose_with_fallback(p,.5,'b'),'a')
        self.assertEqual(choose_with_fallback(p,.6,'b'),'b')

    def test_zero_probability_kept_and_bad_temperature_rejected(self):
        self.assertEqual(rescale({'a':1.,'b':0.},1.,2.),{'a':1.,'b':0.})
        with self.assertRaises(ValueError):rescale({'a':.5,'b':.5},0.,1.)
        with self.assertRaises(ValueError):rescale({'a':.5,'b':.5},1.,float('nan'))

    def test_bad_probability_vector_rejected(self):
        with self.assertRaises(ValueError):rescale({'a':.6,'b':.6},1.,2.)
        with self.assertRaises(ValueError):rescale({'a':-.1,'b':1.1},1.,2.)

if __name__=='__main__':unittest.main()
