import math
import unittest

from score_kernel import ProbabilityError, ZeroSupportError, score_one, threeway
from scoring import score_pair


class ScoringTests(unittest.TestCase):
    def test_unchanged_closure(self):
        r = score_one([.7, .1, .1, .1], 0, 0)
        self.assertAlmostEqual(r["full_log"], math.log(.7))
        self.assertAlmostEqual(r["full_log"], r["full_log_from_components"])
        self.assertEqual(r["dest_log"], 0.0)
        self.assertAlmostEqual(r["binary_brier"], .3 ** 2)

    def test_changed_closure(self):
        q = [.2, .3, .4, .1]
        r = score_one(q, 2, 0)
        self.assertAlmostEqual(r["event_log"] + r["dest_log"], math.log(.4))
        self.assertAlmostEqual(r["full_log"], math.log(.4))
        self.assertAlmostEqual(r["binary_brier"], (.8 - 1.0) ** 2)

    def test_threeway_third_closure(self):
        q = [.2, .3, .4, .1]
        r = threeway(q, 0, 1, 3)
        self.assertEqual(r["target"], 2)
        self.assertAlmostEqual(r["full_log"], math.log(.2) + math.log(.1 / .2))
        self.assertAlmostEqual(r["coarse_log"] + r["third_internal_log"], r["full_log"])
        self.assertAlmostEqual(r["third_internal_log"], math.log(.1 / .5))

    def test_reject_bad_dimension_and_zero_support(self):
        with self.assertRaises(ProbabilityError):
            score_one([.5, .5, 0.0], 0, 0)
        with self.assertRaises(ZeroSupportError):
            score_one([1.0, 0.0, 0.0, 0.0], 1, 0)
        with self.assertRaises(ProbabilityError):
            score_one([0.5, 0.5, -0.1, 0.1], 0, 0)
        with self.assertRaises(ProbabilityError):
            score_one([float("nan"), 0.0, 0.0, 1.0], 0, 0)

    def test_pair_delta_direction(self):
        r = score_pair([.6, .2, .1, .1], [.5, .3, .1, .1], 1, 0)
        self.assertAlmostEqual(r["delta"]["full_log"], math.log(.3) - math.log(.2))

    def test_brier_components_are_separate(self):
        r = score_one([.2, .3, .4, .1], 2, 0)
        self.assertNotEqual(r["multiclass_brier"], r["binary_brier"])
        self.assertIn("event_log", r)
        self.assertIn("dest_log", r)


if __name__ == "__main__":
    unittest.main()
