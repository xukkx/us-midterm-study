"""匿名联合格的独立验收与政策编码回归测试。"""
import json
import itertools
import unittest
from pathlib import Path

from project_raw import PID_MAP, check_anonymous, fold_for, policy_code
from r1_sensitivity import FixedMargins, build_strata


HERE = Path(__file__).parent


class PolicyEncodingTests(unittest.TestCase):
    def test_policy_codes_and_unknowns(self):
        self.assertEqual([policy_code(x) for x in ("1", "2", "", "NA", "NaN", "__NA__")], [2, 1, 0, 0, 0, 0])

    def test_fold_is_deterministic(self):
        self.assertEqual(fold_for("abc"), fold_for("abc"))
        self.assertIn(fold_for("abc"), range(5))

    def test_pid_map_is_declared(self):
        self.assertEqual([PID_MAP[i] for i in range(1, 9)], [0, 0, 0, 1, 2, 2, 2, 3])


class AnonymousGridTests(unittest.TestCase):
    def test_generated_grid_closes_and_matches_margins(self):
        data = json.loads((HERE / "joint-counts.json").read_text(encoding="utf-8"))
        result = check_anonymous(data)
        self.assertEqual(result["n"], 6175)
        self.assertGreater(result["rows"], 0)

    def test_unknown_category_is_retained_in_anonymous_grid(self):
        data = json.loads((HERE / "joint-counts.json").read_text(encoding="utf-8"))
        self.assertEqual(data["unknown_policy_n"], 7)
        self.assertTrue(any(0 in (r["policy20"], r["policy22"], r["policy24"]) for r in data["rows"]))

    def test_grid_rejects_tampered_fold(self):
        data = json.loads((HERE / "joint-counts.json").read_text(encoding="utf-8"))
        data["rows"][0]["fold_counts"][0] += 1
        with self.assertRaises(AssertionError):
            check_anonymous(data)

    def test_independent_old_raw8_and_pid4_policy_margins(self):
        """与旧公开投影逐项核对，避免把边际拼成联合格。"""
        data = json.loads((HERE / "joint-counts.json").read_text(encoding="utf-8"))
        old_path = HERE / "lh266-joint-trajectories.json"
        if not old_path.exists():
            old_path = HERE.parent / "ces-policy-calibration-2026-09-09" / "lh266-joint-trajectories.json"
        old = json.loads(old_path.read_text(encoding="utf-8"))
        self.assertEqual(data["raw8_counts"], old["raw8_counts"])
        self.assertEqual(data["raw8_fold_counts"], old["raw8_fold_counts"])
        expected = [[[0] * 3 for _ in range(4)] for _ in range(3)]
        for pid4_path, policy_counts in zip(itertools.product(range(4), repeat=3), old["joint_counts"]["conditional_legalization"]):
            for policy_path, n in zip(itertools.product(range(3), repeat=3), policy_counts):
                for wave in range(3):
                    expected[wave][pid4_path[wave]][policy_path[wave]] += n
        self.assertEqual(data["pid4_policy_counts"], expected)

    def test_r1_strata_are_complete_and_use_three_groups(self):
        data = json.loads((HERE / "joint-counts.json").read_text(encoding="utf-8"))
        strata = build_strata(data)
        self.assertEqual(sum(sum(map(sum, row["table"])) for row in strata), 6168)
        self.assertTrue(all(len(row["table"]) == 3 and len(row["table"][0]) == 4 for row in strata))

    def test_fixed_margin_draw_preserves_both_margins(self):
        ref = FixedMargins([[2, 1, 0, 0], [0, 1, 1, 0], [1, 0, 0, 2]])
        drawn = ref.draw(__import__("random").Random(268))
        self.assertEqual([sum(x) for x in drawn], ref.rows)
        self.assertEqual([sum(drawn[i][j] for i in range(3)) for j in range(4)], ref.cols)


if __name__ == "__main__":
    unittest.main()
