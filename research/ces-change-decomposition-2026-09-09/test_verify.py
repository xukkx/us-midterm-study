import math
import unittest

import verify


class IndependentVerifyTests(unittest.TestCase):
    def test_threeway_closure(self):
        full, internal, coarse = verify.three([.2, .3, .4, .1], 0, 1, 3)
        self.assertAlmostEqual(full, math.log(.1))
        self.assertAlmostEqual(coarse + internal, full)

    def test_reject_dimension_and_zero_support(self):
        with self.assertRaises(ValueError):
            verify.score([.5, .5, 0], 0, 0)
        with self.assertRaises(ValueError):
            verify.score([1.0, 0.0, 0.0, 0.0], 1, 0)

    def test_independent_frozen_recalculation(self):
        result = verify.independent()
        self.assertTrue(result["passed"])
        self.assertEqual(result["n"], 6175)
        self.assertEqual(result["changed"], 414)
        self.assertEqual(result["third"], 40)


if __name__ == "__main__":
    unittest.main()
