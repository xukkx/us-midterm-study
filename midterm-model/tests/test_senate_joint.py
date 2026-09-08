import math
import sys
import unittest
from pathlib import Path
from statistics import NormalDist


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.senate_joint import (  # noqa: E402
    COMPONENT_ID,
    SenateJointValidationError,
    SharedResidualCycleSummary,
    SharedResidualScale,
    average_pairwise_covariance_from_count_pmf,
    central_interval,
    discrete_crps,
    discrete_log_score,
    discrete_quantile,
    fit_shared_residual_scale,
    normal_random_intercept_count_pmf,
    pmf_bytes,
    pmf_mean,
    pmf_variance,
    poisson_binomial_pmf,
    scale_bytes,
    validate_pmf,
)


def paired_row(cycle, number, observed, predicted, **changes):
    row = {
        "race_id": f"SENATE-{cycle}-ST-{number}",
        "cycle": cycle,
        "office": "SENATE",
        "two_party_margin": observed,
        "predicted_margin": predicted,
        "margin_sd": 3.0,
    }
    row.update(changes)
    return row


def training_rows(margin_sd=3.0):
    return [
        paired_row(1978, 1, 3.0, 1.0, margin_sd=margin_sd),  # residual 2
        paired_row(1978, 2, 8.0, 4.0, margin_sd=margin_sd),  # residual 4；届均值 3，平方 9
        paired_row(1982, 1, -2.0, -1.0, margin_sd=margin_sd),  # residual -1
        paired_row(1982, 2, 2.0, 1.0, margin_sd=margin_sd),  # residual 1；届均值 0，平方 0
        paired_row(1982, 3, None, 9.0, margin_sd=margin_sd),  # 保留但不进入残差分母
    ]


def l1(left, right):
    return math.fsum(abs(a - b) for a, b in zip(left, right, strict=True))


class SharedResidualScaleTests(unittest.TestCase):
    def test_component_id_is_contract_name(self):
        self.assertEqual(COMPONENT_ID, "SENATE_CONTEST_COUNT_SHARED_RESIDUAL")

    def test_zero_mean_cycle_equal_moment_hand_calculation(self):
        scale = fit_shared_residual_scale(training_rows(), 3.0, test_cycle=1986)
        self.assertEqual(scale.train_cycles, (1978, 1982))
        self.assertEqual(scale.n_train_margin, 4)
        self.assertEqual(scale.shared_variance_raw, 4.5)
        self.assertEqual(scale.shared_variance_used, 4.5)
        self.assertAlmostEqual(scale.shared_sd, math.sqrt(4.5))
        self.assertAlmostEqual(scale.local_sd, math.sqrt(4.5))
        self.assertFalse(scale.clipped)

    def test_estimator_is_not_recentered_sample_variance(self):
        rows = [
            paired_row(1978, 1, 3.0, 1.0, margin_sd=10.0),  # 届均值 2
            paired_row(1982, 1, 5.0, 1.0, margin_sd=10.0),  # 届均值 4
        ]
        scale = fit_shared_residual_scale(rows, 10.0, 1986)
        # 零均值 MoM=(2²+4²)/2=10；若重中心化则会错误得到1。
        self.assertEqual(scale.shared_variance_raw, 10.0)

    def test_cycle_equal_weighting_ignores_race_count_imbalance(self):
        rows = [paired_row(1978, 1, 10.0, 0.0, margin_sd=20.0)] + [
            paired_row(1982, index, 0.0, 0.0, margin_sd=20.0) for index in range(1, 10)
        ]
        scale = fit_shared_residual_scale(rows, 20.0, 1986)
        self.assertEqual(scale.shared_variance_raw, 50.0)
        self.assertEqual([s.n_margin for s in scale.cycle_summaries], [1, 9])

    def test_raw_shared_variance_above_parent_is_clipped(self):
        scale = fit_shared_residual_scale(training_rows(2.0), 2.0, 1986)
        self.assertEqual(scale.shared_variance_raw, 4.5)
        self.assertEqual(scale.shared_variance_used, 4.0)
        self.assertEqual(scale.shared_sd, 2.0)
        self.assertEqual(scale.local_sd, 0.0)
        self.assertTrue(scale.clipped)

    def test_total_marginal_variance_is_machine_locked(self):
        scale = fit_shared_residual_scale(training_rows(), 3.0, 1986)
        self.assertEqual(scale.marginal_variance, 9.0)
        self.assertAlmostEqual(scale.shared_sd**2 + scale.local_sd**2, 9.0)
        self.assertAlmostEqual(scale.variance_identity_error, 0.0)

    def test_manual_scale_with_wrong_variance_identity_is_rejected(self):
        summaries = (
            SharedResidualCycleSummary(1978, 1.0, 1.0, 1),
            SharedResidualCycleSummary(1982, 1.0, 1.0, 1),
        )
        with self.assertRaisesRegex(SenateJointValidationError, "必须等于"):
            SharedResidualScale(
                parent_total_sd=2.0,
                shared_sd=1.0,
                local_sd=1.0,
                shared_variance_raw=1.0,
                shared_variance_used=1.0,
                train_cycles=(1978, 1982),
                n_train_margin=2,
                clipped=False,
                cycle_summaries=summaries,
            )

    def test_manual_scale_summary_invariants_are_locked(self):
        good = (
            SharedResidualCycleSummary(1978, 1.0, 1.0, 2),
            SharedResidualCycleSummary(1982, 0.0, 0.0, 1),
        )
        kwargs = {
            "parent_total_sd": 2.0,
            "shared_sd": math.sqrt(0.5),
            "local_sd": math.sqrt(3.5),
            "shared_variance_raw": 0.5,
            "shared_variance_used": 0.5,
            "train_cycles": (1978, 1982),
            "n_train_margin": 3,
            "clipped": False,
        }
        SharedResidualScale(cycle_summaries=good, **kwargs)
        with self.assertRaisesRegex(SenateJointValidationError, "周期必须精确"):
            SharedResidualScale(cycle_summaries=tuple(reversed(good)), **kwargs)
        bad_square = (
            SharedResidualCycleSummary(1978, 1.0, 2.0, 2),
            good[1],
        )
        with self.assertRaisesRegex(SenateJointValidationError, "residual_mean_square"):
            SharedResidualScale(cycle_summaries=bad_square, **kwargs)
        with self.assertRaisesRegex(SenateJointValidationError, "分母之和"):
            SharedResidualScale(cycle_summaries=good, **dict(kwargs, n_train_margin=4))

    def test_scale_serialization_is_order_invariant(self):
        left = fit_shared_residual_scale(training_rows(), 3.0, 1986)
        right = fit_shared_residual_scale(list(reversed(training_rows())), 3.0, 1986)
        self.assertEqual(scale_bytes(left), scale_bytes(right))
        self.assertEqual(left.as_dict()["n_train_cycles"], 2)
        self.assertEqual(left.as_dict()["shared_mean"], 0.0)

    def test_fit_rejects_too_few_independent_cycles(self):
        with self.assertRaisesRegex(SenateJointValidationError, "至少需要 2"):
            fit_shared_residual_scale(training_rows()[:2], 3.0, 1982)

    def test_fit_rejects_non_midterm_and_future_cycles(self):
        non_midterm = training_rows() + [paired_row(1980, 1, 1.0, 0.0)]
        with self.assertRaisesRegex(SenateJointValidationError, "中期周期"):
            fit_shared_residual_scale(non_midterm, 3.0, 1986)
        future = training_rows() + [paired_row(1986, 1, 1.0, 0.0)]
        with self.assertRaisesRegex(SenateJointValidationError, "不严格早于"):
            fit_shared_residual_scale(future, 3.0, 1986)

    def test_fit_rejects_house_duplicate_and_empty_cycle_residual(self):
        house = training_rows() + [paired_row(1982, 9, 1.0, 0.0, office="HOUSE")]
        with self.assertRaisesRegex(SenateJointValidationError, "House"):
            fit_shared_residual_scale(house, 3.0, 1986)
        duplicate = training_rows() + [dict(training_rows()[0])]
        with self.assertRaisesRegex(SenateJointValidationError, "重复 race_id"):
            fit_shared_residual_scale(duplicate, 3.0, 1986)
        empty = [paired_row(1978, 1, None, 0.0), paired_row(1982, 1, 1.0, 0.0)]
        with self.assertRaisesRegex(SenateJointValidationError, "没有可用残差"):
            fit_shared_residual_scale(empty, 3.0, 1986)

    def test_fit_requires_and_checks_parent_margin_sd(self):
        missing = training_rows()
        del missing[0]["margin_sd"]
        with self.assertRaisesRegex(SenateJointValidationError, "缺少.*margin_sd"):
            fit_shared_residual_scale(missing, 3.0, 1986)
        rows = training_rows()
        rows[0]["margin_sd"] = 3.0000001
        with self.assertRaisesRegex(SenateJointValidationError, "逐字等于"):
            fit_shared_residual_scale(rows, 3.0, 1986)

    def test_fit_rejects_nonpositive_parent_scale(self):
        for value in (0.0, -1.0, float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(SenateJointValidationError):
                    fit_shared_residual_scale(training_rows(), value, 1986)


class CountDistributionTests(unittest.TestCase):
    def test_poisson_binomial_two_fair_coins_hand_calculation(self):
        self.assertEqual(poisson_binomial_pmf([0.5, 0.5]), (0.25, 0.5, 0.25))

    def test_poisson_binomial_deterministic_bernoulli_hand_calculation(self):
        self.assertEqual(poisson_binomial_pmf([0.0, 1.0]), (0.0, 1.0, 0.0))

    def test_poisson_binomial_moments_match_bernoulli_sum(self):
        probabilities = [0.1, 0.4, 0.8]
        pmf = poisson_binomial_pmf(probabilities)
        self.assertAlmostEqual(pmf_mean(pmf), sum(probabilities))
        self.assertAlmostEqual(
            pmf_variance(pmf), sum(p * (1.0 - p) for p in probabilities)
        )

    def test_poisson_binomial_bytes_ignore_input_order(self):
        left = poisson_binomial_pmf([0.2, 0.7, 0.4])
        right = poisson_binomial_pmf([0.4, 0.2, 0.7])
        self.assertEqual(pmf_bytes(left), pmf_bytes(right))

    def test_poisson_binomial_rejects_empty_and_illegal_probability(self):
        with self.assertRaisesRegex(SenateJointValidationError, "至少需要"):
            poisson_binomial_pmf([])
        for value in (-0.1, 1.1, float("nan"), True):
            with self.subTest(value=value):
                with self.assertRaises(SenateJointValidationError):
                    poisson_binomial_pmf([0.5, value])

    def test_tau_zero_is_exactly_independent_not_approximate(self):
        means = [-1.0, 0.5, 2.0]
        total_sd = 3.0
        expected = poisson_binomial_pmf([NormalDist().cdf(value / total_sd) for value in means])
        for grid in (512, 2048, 8192):
            with self.subTest(grid=grid):
                self.assertEqual(
                    normal_random_intercept_count_pmf(
                        means, total_sd, 0.0, grid_size=grid
                    ),
                    expected,
                )

    def test_shared_scale_widens_count_variance_and_positive_covariance(self):
        means = [0.0] * 6
        independent = normal_random_intercept_count_pmf(means, 1.0, 0.0)
        correlated = normal_random_intercept_count_pmf(
            means, 1.0, 0.8, grid_size=2048
        )
        self.assertGreater(pmf_variance(correlated), pmf_variance(independent))
        self.assertGreater(correlated[0] + correlated[-1], independent[0] + independent[-1])
        self.assertGreater(
            average_pairwise_covariance_from_count_pmf(correlated, [0.5] * 6),
            0.0,
        )

    def test_random_intercept_preserves_count_mean_as_grid_converges(self):
        means = [-2.0, -0.5, 1.0, 3.0]
        total_sd = 4.0
        expected = sum(NormalDist().cdf(value / total_sd) for value in means)
        pmf = normal_random_intercept_count_pmf(
            means, total_sd, 2.5, grid_size=8192
        )
        self.assertAlmostEqual(pmf_mean(pmf), expected, places=5)

    def test_512_2048_8192_quantile_grids_converge(self):
        means = [-2.5, -0.2, 0.7, 1.8]
        p512 = normal_random_intercept_count_pmf(means, 3.0, 2.0, grid_size=512)
        p2048 = normal_random_intercept_count_pmf(means, 3.0, 2.0, grid_size=2048)
        p8192 = normal_random_intercept_count_pmf(means, 3.0, 2.0, grid_size=8192)
        self.assertLess(l1(p2048, p8192), l1(p512, p2048))
        self.assertLess(l1(p2048, p8192), 0.0002)

    def test_random_intercept_repeats_byte_for_byte(self):
        args = ([-1.0, 0.0, 2.0], 3.0, 2.0)
        left = normal_random_intercept_count_pmf(*args, grid_size=2048)
        right = normal_random_intercept_count_pmf(*args, grid_size=2048)
        self.assertEqual(pmf_bytes(left), pmf_bytes(right))

    def test_random_intercept_rejects_illegal_scale_grid_and_empty(self):
        with self.assertRaisesRegex(SenateJointValidationError, "至少需要"):
            normal_random_intercept_count_pmf([], 1.0, 0.5)
        with self.assertRaisesRegex(SenateJointValidationError, "不得超过"):
            normal_random_intercept_count_pmf([0.0], 1.0, 1.1)
        with self.assertRaisesRegex(SenateJointValidationError, "grid_size"):
            normal_random_intercept_count_pmf([0.0], 1.0, 0.5, grid_size=1)
        with self.assertRaises(SenateJointValidationError):
            normal_random_intercept_count_pmf([float("inf")], 1.0, 0.5)

    def test_pmf_validation_rejects_empty_negative_nonfinite_and_unnormalized(self):
        bad = (
            [],
            [0.5, -0.5, 1.0],
            [0.5, float("nan")],
            [0.2, 0.2],
            [1.00000000005, 0.0],
        )
        for pmf in bad:
            with self.subTest(pmf=pmf):
                with self.assertRaises(SenateJointValidationError):
                    validate_pmf(pmf)

    def test_discrete_crps_matches_bernoulli_brier(self):
        # P(Y=1)=0.8；观测1时 CRPS=(1-0.8)^2。
        self.assertAlmostEqual(discrete_crps([0.2, 0.8], 1), 0.04)
        # 观测0时 CRPS=0.8^2。
        self.assertAlmostEqual(discrete_crps([0.2, 0.8], 0), 0.64)

    def test_discrete_log_score_hand_calculation_and_zero_mass(self):
        self.assertAlmostEqual(discrete_log_score([0.2, 0.8], 1), math.log(0.8))
        self.assertEqual(discrete_log_score([1.0, 0.0], 1), -math.inf)

    def test_discrete_scores_reject_out_of_support_and_noninteger(self):
        for observed in (-1, 2, 0.5, True):
            with self.subTest(observed=observed):
                with self.assertRaises(SenateJointValidationError):
                    discrete_crps([0.5, 0.5], observed)
                with self.assertRaises(SenateJointValidationError):
                    discrete_log_score([0.5, 0.5], observed)

    def test_discrete_quantile_and_central_interval(self):
        pmf = [0.1, 0.2, 0.4, 0.3]
        self.assertEqual(discrete_quantile(pmf, 0.1), 0)
        self.assertEqual(discrete_quantile(pmf, 0.5), 2)
        self.assertEqual(central_interval(pmf, 0.8), (0, 3))

    def test_average_covariance_checks_dimensions(self):
        with self.assertRaisesRegex(SenateJointValidationError, "数量不一致"):
            average_pairwise_covariance_from_count_pmf([0.5, 0.5], [0.5, 0.5])
        with self.assertRaisesRegex(SenateJointValidationError, "至少需要两场"):
            average_pairwise_covariance_from_count_pmf([0.5, 0.5], [0.5])


if __name__ == "__main__":
    unittest.main()
