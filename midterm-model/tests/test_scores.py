import math
import sys
import unittest
from collections import Counter
from itertools import product
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.scores import (  # noqa: E402
    binary_log_loss,
    brier_score,
    central_interval,
    empirical_crps,
    exact_block_bootstrap_mean_distribution,
    exact_block_bootstrap_probability_below,
    normal_crps,
    normal_log_score,
    probability,
    quantile,
)


class ScoreTests(unittest.TestCase):
    def test_brier_hand_calculation(self):
        self.assertAlmostEqual(brier_score(0.8, 1), 0.04)

    def test_log_loss_hand_calculation(self):
        self.assertAlmostEqual(binary_log_loss(0.8, 1), 0.2231435513142097)

    def test_deterministic_seat_crps_is_absolute_error(self):
        self.assertEqual(empirical_crps([220] * 20, 218), 2.0)

    def test_two_point_empirical_crps(self):
        self.assertAlmostEqual(empirical_crps([0, 2], 1), 0.5)

    def test_probability_does_not_silently_clip(self):
        with self.assertRaises(ValueError):
            probability(1.00001)

    def test_probability_rejects_nan(self):
        with self.assertRaises(ValueError):
            probability(float("nan"))

    def test_wrong_certain_log_loss_is_infinite(self):
        self.assertTrue(math.isinf(binary_log_loss(0.0, 1)))

    def test_normal_log_score_requires_positive_scale(self):
        with self.assertRaises(ValueError):
            normal_log_score(0.0, 0.0, 0.0)

    def test_normal_crps_is_nonnegative_and_zero_centered_smallest(self):
        centered = normal_crps(0.0, 0.0, 1.0)
        shifted = normal_crps(2.0, 0.0, 1.0)
        self.assertGreaterEqual(centered, 0.0)
        self.assertLess(centered, shifted)

    def test_normal_crps_标准正态中心闭式锚点(self):
        expected = 2.0 / math.sqrt(2.0 * math.pi) - 1.0 / math.sqrt(math.pi)
        self.assertAlmostEqual(normal_crps(0.0, 0.0, 1.0), expected, places=15)

    def test_exact_bootstrap_八周期多重集计数为_6435(self):
        distribution = exact_block_bootstrap_mean_distribution(range(8))
        self.assertEqual(len(distribution), math.comb(15, 7))
        self.assertEqual(sum(item.multiplicity for item in distribution), 8**8)

    def test_exact_bootstrap_小例与有序穷举完全一致(self):
        values = (0.0, 3.0)
        exact = Counter()
        for item in exact_block_bootstrap_mean_distribution(values):
            exact[item.mean] += item.multiplicity
        brute_force = Counter(sum(sample) / len(sample) for sample in product(values, repeat=2))
        self.assertEqual(exact, brute_force)
        self.assertEqual(exact_block_bootstrap_probability_below((-1.0, 1.0)), 0.25)

    def test_quantile_uses_linear_interpolation(self):
        self.assertEqual(quantile([0.0, 10.0], 0.25), 2.5)

    def test_central_interval(self):
        self.assertEqual(central_interval(list(range(101)), 0.8), (10.0, 90.0))

    def test_empty_empirical_distribution_rejected(self):
        with self.assertRaises(ValueError):
            empirical_crps([], 0)


if __name__ == "__main__":
    unittest.main()
