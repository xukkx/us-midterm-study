import copy
import sys
import unittest
from pathlib import Path
from statistics import pstdev


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.models import PartisanBaseline, UniformNationalSwing, fit_error_structure  # noqa: E402
from midterms.simulation import (  # noqa: E402
    average_pair_covariance,
    simulate_race_outcomes,
    simulate_seat_counts,
)
from midterms.synthetic import build_panel, chamber_rule  # noqa: E402


class ModelAndSimulationTests(unittest.TestCase):
    def test_m0_uses_only_partisan_baseline(self):
        row = build_panel()[0]
        expected = row["feature_values"]["partisan_baseline_margin"]["value"]
        self.assertEqual(PartisanBaseline.predict_margin(row), expected)

    def test_b1_adds_uniform_swing(self):
        row = build_panel()[0]
        values = row["feature_values"]
        expected = values["partisan_baseline_margin"]["value"] + values["national_swing"]["value"]
        self.assertEqual(UniformNationalSwing.predict_margin(row), expected)

    def test_error_structure_depends_only_on_passed_training_rows(self):
        panel = [row for row in build_panel() if row["office"] == "SENATE"]
        train = [row for row in panel if row["cycle"] <= 2006]
        test = [row for row in panel if row["cycle"] == 2010]
        before = fit_error_structure(UniformNationalSwing(), train)
        mutated = copy.deepcopy(test)
        for row in mutated:
            row["actual_result"]["democratic_margin"] += 80.0
        after = fit_error_structure(UniformNationalSwing(), train)
        self.assertEqual(before, after)

    def test_simulation_repeats_with_same_seed(self):
        left = simulate_seat_counts([-.5, .5, 1.0], 2.0, 1.0, 100, 47)
        right = simulate_seat_counts([-.5, .5, 1.0], 2.0, 1.0, 100, 47)
        self.assertEqual(left, right)

    def test_default_rng_path_frozen_bytes_unchanged(self):
        correlated = simulate_race_outcomes([-.5, .5, 1.0], 2.0, 1.0, 5, 47)
        independent = simulate_race_outcomes(
            [-.5, .5, 1.0], 2.0, 1.0, 5, 47, correlated=False
        )
        self.assertEqual(correlated, [[0, 0, 0], [0, 0, 0], [1, 1, 1], [0, 0, 0], [0, 0, 0]])
        self.assertEqual(independent, [[0, 1, 0], [1, 0, 1], [1, 1, 1], [0, 0, 1], [0, 1, 1]])

    def test_per_race_substreams_增删竞选不扰动其余噪声(self):
        base_ids = ["A", "B", "C"]
        base = simulate_race_outcomes(
            [-.5, .5, 1.0],
            2.0,
            1.0,
            50,
            47,
            per_race_substreams=True,
            race_ids=base_ids,
        )
        extended_ids = ["X", *base_ids]
        extended = simulate_race_outcomes(
            [3.0, -.5, .5, 1.0],
            2.0,
            1.0,
            50,
            47,
            per_race_substreams=True,
            race_ids=extended_ids,
        )
        self.assertEqual(base, [row[1:] for row in extended])

    def test_per_race_substreams_要求一一对应唯一身份(self):
        with self.assertRaisesRegex(ValueError, "一一对应"):
            simulate_race_outcomes(
                [0.0], 1.0, 1.0, 2, 1, per_race_substreams=True
            )
        with self.assertRaisesRegex(ValueError, "不得重复"):
            simulate_race_outcomes(
                [0.0, 0.0],
                1.0,
                1.0,
                2,
                1,
                per_race_substreams=True,
                race_ids=["A", "A"],
            )

    def test_different_seed_changes_draws(self):
        left = simulate_seat_counts([0.0] * 5, 2.0, 1.0, 100, 47)
        right = simulate_seat_counts([0.0] * 5, 2.0, 1.0, 100, 48)
        self.assertNotEqual(left, right)

    def test_shared_error_induces_positive_covariance(self):
        outcomes = simulate_race_outcomes([0.0] * 8, 3.0, 0.3, 4000, 7, correlated=True)
        self.assertGreater(average_pair_covariance(outcomes), 0.15)

    def test_independent_error_has_near_zero_covariance(self):
        outcomes = simulate_race_outcomes([0.0] * 8, 3.0, 0.3, 4000, 7, correlated=False)
        self.assertLess(abs(average_pair_covariance(outcomes)), 0.01)

    def test_shared_error_widens_seat_distribution(self):
        correlated = simulate_seat_counts([0.0] * 10, 3.0, 0.5, 4000, 9, correlated=True)
        independent = simulate_seat_counts([0.0] * 10, 3.0, 0.5, 4000, 9, correlated=False)
        self.assertGreater(pstdev(correlated), pstdev(independent) * 2.0)

    def test_negative_error_scale_rejected(self):
        with self.assertRaises(ValueError):
            simulate_seat_counts([0.0], -1.0, 1.0, 10, 1)

    def test_holdovers_are_added_to_every_draw(self):
        seats = simulate_seat_counts([100.0], 0.0, 0.0, 5, 1, democratic_holdovers=33)
        self.assertEqual(seats, [34] * 5)

    def test_senate_rule_accounts_for_all_seats(self):
        rule = chamber_rule("SENATE", 2022, 34)
        raw_holdovers = (
            rule["democratic_party_holdovers"]
            + rule["independent_holdovers"]
            + rule["republican_holdovers"]
        )
        self.assertEqual(raw_holdovers + rule["contested_seats"], rule["seats_total"])
        self.assertEqual(rule["democratic_caucus_holdovers"], 34)

    def test_senate_control_threshold_follows_vp_rule(self):
        democratic_vp = chamber_rule("SENATE", 2022, 34)
        republican_vp = chamber_rule("SENATE", 2018, 34)
        self.assertEqual(democratic_vp["control_threshold"], 50)
        self.assertEqual(republican_vp["control_threshold"], 51)

    def test_wrong_contested_seat_count_rejected(self):
        with self.assertRaises(ValueError):
            chamber_rule("SENATE", 2022, 33)


if __name__ == "__main__":
    unittest.main()
