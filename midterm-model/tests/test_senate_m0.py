import copy
import math
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from statistics import NormalDist


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.senate_m0 import (  # noqa: E402
    FEATURE_ID,
    TRANSFORM_ID,
    SenateM0ValidationError,
    SenateRaceIdentity,
    fit_senate_m0,
    model_bytes,
    predict_senate_m0,
    prediction_bytes,
    sanitize_senate_identities,
    validate_feature_ledger,
)


def feature(target_cycle, state, margin, **changes):
    row = {
        "schema_version": "1.0",
        "feature_id": FEATURE_ID,
        "transform_id": TRANSFORM_ID,
        "office": "SENATE",
        "target_cycle": target_cycle,
        "state": state,
        "partisan_baseline_margin": margin,
        "presidential_source_cycle": target_cycle - 2,
        "forecast_as_of": f"{target_cycle}-10-01T00:00:00Z",
        "available_at": f"{target_cycle - 1}-01-31T00:00:00Z",
        "fact_available_at": f"{target_cycle - 1}-01-31T00:00:00Z",
        "vintage": "MEDSL_CSV_VERSION_20171015_ARCHIVAL",
        "archival_reconstruction": True,
        "strict_original_vintage_available": False,
        "modern_mirror_published_at": "2018-01-01T00:00:00Z",
        "modern_mirror_retrieved_at": "2026-08-12T00:00:00Z",
        "source": {"lines": [1], "dataset_id": "fixture"},
    }
    row.update(changes)
    return row


def target(cycle, state, suffix, margin, **changes):
    row = {
        "race_id": f"SENATE-{cycle}-{state}-{suffix}",
        "cycle": cycle,
        "office": "SENATE",
        "state": state,
        "two_party_margin": margin,
        "winner_group": "DEMOCRATIC" if margin is not None and margin > 0 else "REPUBLICAN",
        "realized_national_swing": 99.0,
    }
    row.update(changes)
    return row


def feature_panel():
    return [
        feature(1978, "AL", 1.0),
        feature(1982, "AL", 2.0),
        feature(1982, "AK", -2.0),
        feature(1986, "AL", 7.5),
        feature(1986, "AK", -6.0),
        feature(1990, "AL", 20.0),
    ]


def training_panel():
    return [
        target(1978, "AL", "REGULAR", 3.0),  # residual=2，cycle MSE=4
        target(1982, "AL", "REGULAR", 2.0),  # residual=0
        target(1982, "AK", "REGULAR", 2.0),  # residual=4，cycle MSE=8
        target(1982, "AK", "SPECIAL", None, winner_group="OTHER"),
    ]


class IdentityGuard(Mapping):
    """身份清洗若读取结果字段或遍历整行就立即失败。"""

    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        if key not in {"race_id", "cycle", "office", "state"}:
            raise AssertionError(f"非法读取测试结果字段：{key}")
        return self.values[key]

    def __iter__(self):
        raise AssertionError("不得遍历或复制测试目标")

    def __len__(self):
        return len(self.values)


class SenateM0Tests(unittest.TestCase):
    def test_feature_ledger_returns_deterministically_sorted_rows(self):
        rows = [feature(1986, "WY", 1.0), feature(1982, "AL", -1.0)]
        result = validate_feature_ledger(rows)
        self.assertEqual([(r["target_cycle"], r["state"]) for r in result], [(1982, "AL"), (1986, "WY")])

    def test_feature_source_cycle_must_equal_t_minus_two(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "t-2"):
            validate_feature_ledger([feature(1986, "AL", 1.0, presidential_source_cycle=1986)])

    def test_duplicate_state_cycle_feature_is_rejected(self):
        row = feature(1986, "AL", 1.0)
        with self.assertRaisesRegex(SenateM0ValidationError, "重复州基线"):
            validate_feature_ledger([row, copy.deepcopy(row)])

    def test_available_at_must_not_be_after_forecast_as_of(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "晚于"):
            validate_feature_ledger([feature(1986, "AL", 1.0, available_at="1986-10-02T00:00:00Z", fact_available_at="1986-10-02T00:00:00Z")])

    def test_forecast_as_of_is_target_october_first(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "10 月 1 日"):
            validate_feature_ledger([feature(1986, "AL", 1.0, forecast_as_of="1986-11-01T00:00:00Z")])

    def test_fact_availability_must_match_available_at(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "不一致"):
            validate_feature_ledger([feature(1986, "AL", 1.0, fact_available_at="1985-02-01T00:00:00Z")])

    def test_feature_ledger_rejects_house_and_dc(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "House"):
            validate_feature_ledger([feature(1986, "AL", 1.0, office="HOUSE")])
        with self.assertRaisesRegex(SenateM0ValidationError, "DC"):
            validate_feature_ledger([feature(1986, "DC", 1.0)])

    def test_feature_margin_rejects_nan_and_out_of_range(self):
        for value in (float("nan"), float("inf"), 100.1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(SenateM0ValidationError, "有限数值"):
                    validate_feature_ledger([feature(1986, "AL", value)])

    def test_archival_flags_and_vintage_are_mandatory(self):
        bad = (
            {"archival_reconstruction": False},
            {"strict_original_vintage_available": True},
            {"vintage": ""},
        )
        for changes in bad:
            with self.subTest(changes=changes):
                with self.assertRaises(SenateM0ValidationError):
                    validate_feature_ledger([feature(1986, "AL", 1.0, **changes)])

    def test_identity_sanitizer_reads_only_four_identity_fields(self):
        guarded = IdentityGuard({"race_id": "SENATE-1986-AL-REGULAR", "cycle": 1986, "office": "SENATE", "state": "AL"})
        result = sanitize_senate_identities([guarded], 1986)
        self.assertEqual(result, (SenateRaceIdentity("SENATE-1986-AL-REGULAR", 1986, "SENATE", "AL"),))

    def test_identity_sanitizer_rejects_house_mixed_cycle_and_duplicates(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "House"):
            sanitize_senate_identities([target(1986, "AL", "R", 1.0, office="HOUSE")], 1986)
        with self.assertRaisesRegex(SenateM0ValidationError, "一个预测批次"):
            sanitize_senate_identities([target(1986, "AL", "R", 1.0), target(1990, "AK", "R", 1.0)])
        row = target(1986, "AL", "R", 1.0)
        with self.assertRaisesRegex(SenateM0ValidationError, "重复 race_id"):
            sanitize_senate_identities([row, copy.deepcopy(row)], 1986)

    def test_sigma_is_zero_mean_residual_rms_cycle_equal_weighted(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        self.assertAlmostEqual(model.margin_sd, math.sqrt(6.0))
        self.assertEqual(model.train_cycles, (1978, 1982))
        self.assertEqual(model.n_train_margin, 3)
        self.assertEqual([s.residual_mse for s in model.residual_cycle_summaries], [4.0, 8.0])

    def test_sigma_floor_is_point_two_five(self):
        rows = [target(1978, "AL", "R", 1.0), target(1982, "AL", "R", 2.0)]
        model = fit_senate_m0(rows, feature_panel(), 1986)
        self.assertEqual(model.margin_sd, 0.25)

    def test_at_least_two_residual_cycles_are_required(self):
        rows = [target(1982, "AL", "R", 2.0)]
        with self.assertRaisesRegex(SenateM0ValidationError, "insufficient_calibration_cycles"):
            fit_senate_m0(rows, feature_panel(), 1986)

    def test_training_must_be_strictly_past_midterm_only(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "中期周期"):
            fit_senate_m0(training_panel() + [target(1980, "AL", "R", 1.0)], feature_panel(), 1986)
        with self.assertRaisesRegex(SenateM0ValidationError, "不严格早于"):
            fit_senate_m0(training_panel() + [target(1986, "AL", "R", 1.0)], feature_panel(), 1986)

    def test_training_house_duplicate_and_missing_feature_fail_closed(self):
        with self.assertRaisesRegex(SenateM0ValidationError, "House"):
            fit_senate_m0(training_panel() + [target(1982, "AK", "X", 1.0, office="HOUSE")], feature_panel(), 1986)
        duplicate = training_panel() + [copy.deepcopy(training_panel()[0])]
        with self.assertRaisesRegex(SenateM0ValidationError, "重复 race_id"):
            fit_senate_m0(duplicate, feature_panel(), 1986)
        features = [row for row in feature_panel() if not (row["target_cycle"] == 1982 and row["state"] == "AK")]
        with self.assertRaisesRegex(SenateM0ValidationError, "整折关闭"):
            fit_senate_m0(training_panel(), features, 1986)

    def test_each_training_cycle_needs_a_non_null_residual(self):
        rows = [target(1978, "AL", "R", None), target(1982, "AL", "R", 2.0)]
        with self.assertRaisesRegex(SenateM0ValidationError, "没有可用"):
            fit_senate_m0(rows, feature_panel(), 1986)

    def test_model_records_independent_predictor_lineage(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        keys = {(line.target_cycle, line.state, line.presidential_source_cycle) for line in model.lineage}
        self.assertEqual(keys, {(1978, "AL", 1976), (1982, "AL", 1980), (1982, "AK", 1980)})
        serialized = model.as_dict()
        self.assertIn("no_fitted_offset", serialized["margin_mean_formula"])
        self.assertFalse(hasattr(model, "intercept"))
        self.assertFalse(hasattr(model, "slope"))
        self.assertFalse(hasattr(model, "calibration"))

    def test_prediction_mean_is_exact_baseline_and_probability_is_phi(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        identities = sanitize_senate_identities([target(1986, "AL", "REGULAR", -99.0)], 1986)
        prediction = predict_senate_m0(model, identities, feature_panel())[0]
        self.assertEqual(prediction["predicted_margin"], 7.5)
        self.assertEqual(prediction["democratic_win_probability"], NormalDist().cdf(7.5 / model.margin_sd))

    def test_regular_and_special_same_state_both_receive_predictions(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        tests = [target(1986, "AL", "REGULAR", 1.0), target(1986, "AL", "SPECIAL", None, winner_group="OTHER")]
        identities = sanitize_senate_identities(tests, 1986)
        predictions = predict_senate_m0(model, identities, feature_panel())
        self.assertEqual(len(predictions), 2)
        self.assertEqual({p["predicted_margin"] for p in predictions}, {7.5})

    def test_predict_requires_sanitized_identities(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        with self.assertRaisesRegex(SenateM0ValidationError, "只接受"):
            predict_senate_m0(model, [target(1986, "AL", "R", 1.0)], feature_panel())

    def test_missing_test_feature_closes_entire_fold(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        identities = sanitize_senate_identities([target(1986, "WY", "R", 1.0)], 1986)
        with self.assertRaisesRegex(SenateM0ValidationError, "整折关闭"):
            predict_senate_m0(model, identities, feature_panel())

    def test_test_actual_winner_and_realized_swing_mutations_do_not_change_bytes(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        original = [target(1986, "AL", "REGULAR", -4.0, actual_result={"margin": -4.0})]
        mutated = copy.deepcopy(original)
        mutated[0]["two_party_margin"] = 90.0
        mutated[0]["winner_group"] = "DEMOCRATIC"
        mutated[0]["realized_national_swing"] = -88.0
        mutated[0]["actual_result"] = {"margin": 90.0}
        left = prediction_bytes(predict_senate_m0(model, sanitize_senate_identities(original, 1986), feature_panel()))
        right = prediction_bytes(predict_senate_m0(model, sanitize_senate_identities(mutated, 1986), feature_panel()))
        self.assertEqual(left, right)

    def test_unrelated_future_feature_change_does_not_change_prediction(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        identities = sanitize_senate_identities([target(1986, "AL", "R", 1.0)], 1986)
        left_features = feature_panel()
        right_features = copy.deepcopy(left_features)
        next(row for row in right_features if row["target_cycle"] == 1990)["partisan_baseline_margin"] = -90.0
        left = prediction_bytes(predict_senate_m0(model, identities, left_features))
        right = prediction_bytes(predict_senate_m0(model, identities, right_features))
        self.assertEqual(left, right)

    def test_model_and_prediction_serialization_ignore_input_order(self):
        left_model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        right_model = fit_senate_m0(list(reversed(training_panel())), list(reversed(feature_panel())), 1986)
        self.assertEqual(model_bytes(left_model), model_bytes(right_model))
        tests = [target(1986, "AK", "R", 1.0), target(1986, "AL", "R", 1.0)]
        left = predict_senate_m0(left_model, sanitize_senate_identities(tests, 1986), feature_panel())
        right = predict_senate_m0(left_model, sanitize_senate_identities(list(reversed(tests)), 1986), feature_panel())
        self.assertEqual(prediction_bytes(left), prediction_bytes(right))

    def test_prediction_serializer_rejects_extra_fields_and_duplicate_races(self):
        model = fit_senate_m0(training_panel(), feature_panel(), 1986)
        identities = sanitize_senate_identities([target(1986, "AL", "R", 1.0)], 1986)
        prediction = predict_senate_m0(model, identities, feature_panel())[0]
        extra = dict(prediction, actual_result=1)
        with self.assertRaisesRegex(SenateM0ValidationError, "只能包含"):
            prediction_bytes([extra])
        with self.assertRaisesRegex(SenateM0ValidationError, "重复 race_id"):
            prediction_bytes([prediction, copy.deepcopy(prediction)])


if __name__ == "__main__":
    unittest.main()

