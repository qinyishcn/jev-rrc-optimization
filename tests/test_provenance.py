import unittest
from rrcopt.provenance import request_hash


class ProvenanceTests(unittest.TestCase):
    def test_model_or_engine_change_invalidates_cache(self):
        request = {'state':'test','options':['a','b']}
        first = request_hash(request, {'weights':'abc','engine':'eager'})
        self.assertNotEqual(first, request_hash(request, {'weights':'def','engine':'eager'}))
        self.assertNotEqual(first, request_hash(request, {'weights':'abc','engine':'compiled'}))

    def test_key_order_is_irrelevant_but_option_order_is_relevant(self):
        self.assertEqual(request_hash({'a':1,'b':2}, {}),request_hash({'b':2,'a':1}, {}))
        self.assertNotEqual(request_hash({'options':['a','b']}, {}),request_hash({'options':['b','a']}, {}))
