"""政策挑战者的小型合成验收，覆盖泄漏、折排除和空格回退。"""
import copy
import json
import unittest
from pathlib import Path

from challenger import FEATURES, fit_fold, q_for, score, verify_result, run, load_baseline
from project_raw import check_anonymous


class ChallengerSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.base = [[[0.1, 0.2, 0.3, 0.4] for _ in range(8)] for _ in range(4)]

    def test_feature_contract_excludes_future_fields(self):
        self.assertEqual(FEATURES, ("PID20_4", "PID22raw8", "policy20", "policy22"))
        self.assertNotIn("policy24", FEATURES)
        self.assertNotIn("future_path_label", FEATURES)

    def test_shrink_formula_and_empty_cell_baseline(self):
        base = [0.1, 0.2, 0.3, 0.4]
        self.assertEqual(q_for(base, [0, 0, 0, 0], 0), base)
        got = q_for(base, [8, 0, 0, 0], 8)
        expected = [(8 + 20 * 0.1) / 28, (20 * 0.2) / 28, (20 * 0.3) / 28, (20 * 0.4) / 28]
        for a, b in zip(got, expected): self.assertAlmostEqual(a, b)

    def test_whole_test_fold_is_excluded_from_training(self):
        feat = (0, 4, 0, 0)
        test = {(feat, 0): 5}
        train = {(feat, 1): 7}
        result = fit_fold(test, train, self.base, 0)
        cell = result["training_cells"][feat]
        self.assertEqual(result["train_n"], 7)
        self.assertEqual(result["test_n"], 5)
        self.assertEqual(cell["training_target_counts"], [0, 7, 0, 0])

    def test_unknown_policy_is_a_real_feature_category(self):
        feat = (0, 1, 0, 2)
        result = fit_fold({(feat, 0): 2}, {}, self.base, 0)
        self.assertEqual(result["training_cells"][feat]["n_train"], 0)
        self.assertEqual(result["training_cells"][feat]["q_new"], self.base[0][0])

    def test_unchanged_binary_brier_uses_event_complement(self):
        self.assertAlmostEqual(score([.9, .05, .03, .02], 0, 0)["binary_brier"], .01)
        self.assertAlmostEqual(score([1., 0., 0., 0.], 0, 0)["binary_brier"], 0.)
        self.assertAlmostEqual(score([.9, .05, .03, .02], 0, 0)["full_log"], __import__("math").log(.9))

    def test_threeway_summary_is_separate_from_full_event_scores(self):
        feat = (0, 4, 0, 0)
        result = fit_fold({(feat, 1): 2}, {}, self.base, 0)
        self.assertEqual(result["threeway"]["n"], 2)

    def test_check_rejects_tampered_mean_and_path_without_writing(self):
        here = Path(__file__).parent
        path = here / "challenger.json"
        saved = path.read_bytes()
        value = json.loads(saved.decode("utf-8"))
        data = json.loads((here / "joint-counts.json").read_text(encoding="utf-8")); check_anonymous(data)
        expected = run(data, load_baseline())
        bad_mean = copy.deepcopy(value); bad_mean["mean_scores"]["full_log"] += 1e-9
        with self.assertRaises(ValueError): verify_result(bad_mean, expected)
        bad_path = copy.deepcopy(value); bad_path["path_scores"][0]["score"]["full_log"] += 1e-9
        with self.assertRaises(ValueError): verify_result(bad_path, expected)
        self.assertEqual(path.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
