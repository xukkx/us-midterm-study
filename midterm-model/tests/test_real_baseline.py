import copy
import math
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.real_baseline import (  # noqa: E402
    R0ValidationError,
    fit_r0,
    model_bytes,
    predict_r0,
    prediction_bytes,
)


def target(
    cycle,
    number,
    margin,
    winner,
    office="HOUSE",
    **extra,
):
    return {
        "race_id": f"{office}-{cycle}-{number}",
        "cycle": cycle,
        "office": office,
        "forecast_horizon": "final_target_backtest",
        "two_party_margin": margin,
        "winner_group": winner,
        **extra,
    }


def training_panel(office="HOUSE"):
    return [
        target(1998, 1, -10.0, "R", office),
        target(1998, 2, 10.0, "D", office),
        target(2002, 1, 20.0, "D", office),
        target(2002, 2, 20.0, "D", office),
        target(2002, 3, None, "OTHER", office),
    ]


class IdentityOnlyMapping(Mapping):
    """若预测器读取测试结果或诊断字段，测试立即失败。"""

    def __init__(self, values):
        self._values = values

    def __getitem__(self, key):
        if key not in {"race_id", "cycle", "office"}:
            raise AssertionError(f"预测器非法读取测试字段：{key}")
        return self._values[key]

    def __iter__(self):
        # predict_r0 不应遍历或复制整行。
        raise AssertionError("预测器非法遍历测试行")

    def __len__(self):
        return len(self._values)


class RealBaselineTests(unittest.TestCase):
    def test_fit_is_cycle_equal_weighted_not_race_weighted(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        # 1998 周期均值 0，2002 周期均值 20；两周期等权得到 10。
        self.assertEqual(model.mean_margin, 10.0)
        # 周期胜率分别为 1/2 和 1，两周期等权得到 3/4。
        self.assertEqual(model.democratic_win_probability, 0.75)

    def test_fit_exposes_counts_cycles_and_lineage(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        self.assertEqual(model.train_cycles, (1998, 2002))
        self.assertEqual(model.n_train_margin, 4)
        self.assertEqual(model.n_train_winner, 4)
        self.assertEqual(
            [item.source_cycle for item in model.lineage], [1998, 2002]
        )

    def test_margin_scale_is_cycle_equal_weighted(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        # 周期 MSE 分别为 200 与 100，等权方差为 150。
        self.assertAlmostEqual(model.margin_sd, math.sqrt(150.0))

    def test_house_and_senate_fit_separately(self):
        house = fit_r0(training_panel("HOUSE"), 2006)
        senate = fit_r0(training_panel("SENATE"), 2006)
        self.assertEqual(house.office, "HOUSE")
        self.assertEqual(senate.office, "SENATE")
        with self.assertRaisesRegex(R0ValidationError, "分轨"):
            fit_r0(
                training_panel("HOUSE") + [target(2002, 9, 1.0, "D", "SENATE")],
                2006,
            )

    def test_training_cycle_must_be_strictly_past(self):
        leaking = training_panel() + [target(2006, 9, 1.0, "D")]
        with self.assertRaisesRegex(R0ValidationError, "不早于"):
            fit_r0(leaking, test_cycle=2006)

    def test_at_least_two_training_cycles_are_required(self):
        rows = [item for item in training_panel() if item["cycle"] == 1998]
        with self.assertRaisesRegex(R0ValidationError, "两个独立训练周期"):
            fit_r0(rows, test_cycle=2002)

    def test_each_cycle_needs_a_margin(self):
        rows = training_panel() + [target(2004, 1, None, "D")]
        with self.assertRaisesRegex(R0ValidationError, "没有可用"):
            fit_r0(rows, test_cycle=2006)

    def test_each_cycle_needs_a_dr_winner(self):
        rows = training_panel() + [target(2004, 1, 4.0, "OTHER")]
        with self.assertRaisesRegex(R0ValidationError, "D/R 赢家"):
            fit_r0(rows, test_cycle=2006)

    def test_prediction_copies_only_identity_and_model_outputs(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        prediction = predict_r0(
            model,
            [target(2006, 1, -99.0, "R", realized_national_swing=50.0)],
        )[0]
        self.assertEqual(
            set(prediction),
            {
                "cycle",
                "democratic_win_probability",
                "margin_sd",
                "office",
                "predicted_margin",
                "race_id",
            },
        )
        self.assertEqual(prediction["predicted_margin"], model.mean_margin)

    def test_mutating_test_actual_and_realized_swing_cannot_change_bytes(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        original = [
            target(
                2006,
                1,
                -2.0,
                "R",
                actual_result={"democratic_margin": -2.0},
                realized_national_swing=-4.0,
            )
        ]
        mutated = copy.deepcopy(original)
        mutated[0]["two_party_margin"] = 88.0
        mutated[0]["winner_group"] = "D"
        mutated[0]["actual_result"]["democratic_margin"] = 88.0
        mutated[0]["realized_national_swing"] = 77.0
        before = prediction_bytes(predict_r0(model, original))
        after = prediction_bytes(predict_r0(model, mutated))
        self.assertEqual(before, after)

    def test_prediction_never_reads_non_identity_test_fields(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        guarded = IdentityOnlyMapping(
            {
                "race_id": "HOUSE-2006-1",
                "cycle": 2006,
                "office": "HOUSE",
            }
        )
        prediction = predict_r0(model, [guarded])[0]
        self.assertEqual(prediction["race_id"], "HOUSE-2006-1")

    def test_model_and_prediction_bytes_ignore_input_order(self):
        rows = training_panel()
        left_model = fit_r0(rows, 2006)
        right_model = fit_r0(list(reversed(rows)), 2006)
        self.assertEqual(model_bytes(left_model), model_bytes(right_model))
        tests = [target(2006, 2, 1.0, "D"), target(2006, 1, -1.0, "R")]
        self.assertEqual(
            prediction_bytes(predict_r0(left_model, tests)),
            prediction_bytes(predict_r0(left_model, list(reversed(tests)))),
        )

    def test_duplicate_test_race_is_rejected(self):
        model = fit_r0(training_panel(), test_cycle=2006)
        race = target(2006, 1, 1.0, "D")
        with self.assertRaisesRegex(R0ValidationError, "重复 race_id"):
            predict_r0(model, [race, copy.deepcopy(race)])

    def test_nested_actual_result_fixture_is_supported(self):
        rows = []
        for cycle, margin in ((1998, -1.0), (2002, 3.0)):
            rows.append(
                {
                    "race_id": f"HOUSE-{cycle}-1",
                    "cycle": cycle,
                    "office": "HOUSE",
                    "actual_result": {
                        "democratic_margin": margin,
                        "democratic_win": margin > 0.0,
                    },
                }
            )
        model = fit_r0(rows, 2006)
        self.assertEqual(model.mean_margin, 1.0)
        self.assertEqual(model.democratic_win_probability, 0.5)

    def test_ingested_winner_object_is_supported(self):
        rows = []
        for cycle, party, margin in (
            (1998, "REPUBLICAN", -2.0),
            (2002, "DEMOCRATIC", 4.0),
        ):
            item = target(cycle, 1, margin, "OTHER")
            item.pop("winner_group")
            item["winner"] = {"canonical_party": party}
            rows.append(item)
        model = fit_r0(rows, 2006)
        self.assertEqual(model.democratic_win_probability, 0.5)

    def test_nested_unknown_and_conflict_winners_are_other(self):
        rows = training_panel()
        for number, party in enumerate(("UNKNOWN", "CONFLICT"), 1):
            item = target(2002, 10 + number, None, "OTHER")
            item.pop("winner_group")
            item["winner"] = {"canonical_party": party}
            rows.append(item)
        model = fit_r0(rows, 2006)
        # OTHER 保留在账本，但不改变 D/R 胜率分母。
        self.assertEqual(model.n_train_winner, 4)
        self.assertEqual(model.democratic_win_probability, 0.75)


if __name__ == "__main__":
    unittest.main()
