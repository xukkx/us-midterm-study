"""数据合同与时间泄漏闸的聚焦测试。"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from midterms.schema import (
    SnapshotValidationError,
    audit_panel,
    validate_snapshot,
    validate_snapshots,
)


REGISTRY = {
    "schema_version": "1.0",
    "features": [
        {
            "id": "partisan_baseline_margin",
            "role": "predictor",
            "dtype": "number",
            "minimum": -100.0,
            "maximum": 100.0,
            "requires_vintage": False,
            "predictor_allowed": True,
            "allowed_in_current_contract": True,
            "offices": ["HOUSE", "SENATE"],
        },
        {
            "id": "national_swing",
            "role": "predictor",
            "dtype": "number",
            "allowed_range": [-25.0, 25.0],
            "requires_vintage": True,
            "predictor_allowed": True,
            "allowed_in_current_contract": True,
            "offices": ["HOUSE", "SENATE"],
        },
        {
            "id": "actual_democratic_margin",
            "role": "outcome",
            "dtype": "number",
            "minimum": -100.0,
            "maximum": 100.0,
            "requires_vintage": False,
            "predictor_allowed": False,
            "allowed_in_current_contract": False,
            "offices": ["HOUSE", "SENATE"],
        },
    ],
}


def house_snapshot() -> dict:
    return {
        "race_id": "HOUSE-PA-07-2022",
        "cycle": 2022,
        "forecast_horizon": "8_weeks",
        "forecast_as_of": "2022-09-13T12:00:00-04:00",
        "office": "HOUSE",
        "state": "PA",
        "district": 7,
        "map": {
            "map_id": "PA-2022-v1",
            "known_at": "2022-02-23",
            "effective_from": "2022-05-17",
        },
        "feature_values": {
            "partisan_baseline_margin": {
                "value": -1.4,
                "available_at": "2022-02-23",
            },
            "national_swing": {
                "value": 2.0,
                "available_at": "2022-09-13T12:00:00-04:00",
                "vintage": "2022-09-13",
            },
        },
        "predictors": ["partisan_baseline_margin", "national_swing"],
        "actual_result": {
            "democratic_margin": 2.2,
            "democratic_win": True,
            "available_at": "2022-11-09T00:00:00Z",
            "source_id": "fixture-result",
        },
    }


def senate_snapshot() -> dict:
    row = house_snapshot()
    row.update(
        {
            "race_id": "SENATE-NV-2022",
            "office": "SENATE",
            "state": "NV",
            "district": None,
            "senate_class": 1,
            "is_special_election": False,
            "election_stage": "general",
            "map": {
                "map_id": "NV-statewide-2022",
                "known_at": "2020-01-01",
                "effective_from": "2020-01-01",
            },
        }
    )
    return row


class SnapshotContractTests(unittest.TestCase):
    def assert_rejected(self, row: dict, phrase: str) -> None:
        with self.assertRaisesRegex(SnapshotValidationError, phrase):
            validate_snapshot(row, REGISTRY)

    def test_合法_house_竞选放行(self) -> None:
        row = house_snapshot()
        self.assertIs(validate_snapshot(row, REGISTRY), row)

    def test_合法_senate_竞选放行(self) -> None:
        row = senate_snapshot()
        self.assertIs(validate_snapshot(row, REGISTRY), row)

    def test_合成辖区与字符串_district_放行(self) -> None:
        row = house_snapshot()
        row["state"] = "X01"
        row["district"] = "001"
        row["feature_values"]["national_swing"]["vintage_id"] = row["feature_values"]["national_swing"].pop("vintage")
        self.assertEqual(validate_snapshots([row], REGISTRY), [row])

    def test_未知_feature_value_拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["secret_future_rating"] = {
            "value": 1.0,
            "available_at": "2022-09-01",
        }
        self.assert_rejected(row, "未知特征")

    def test_未知_predictor_拒绝(self) -> None:
        row = house_snapshot()
        row["predictors"].append("unknown_poll")
        self.assert_rejected(row, "未知特征")

    def test_feature_available_at_晚于截点拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-14"
        self.assert_rejected(row, "available_at 晚于 forecast_as_of")

    def test_仅日期预测截点不再被加一天放宽(self) -> None:
        row = house_snapshot()
        row["forecast_as_of"] = "2022-09-13"
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-13T23:59:00Z"
        # 修复前 forecast_as_of 与 available_at 都按 +1 日解释，此泄漏会放行；
        # 修复后截点取当日 00:00 UTC，而数据仍是 23:59 才可用，必须拒绝。
        self.assert_rejected(row, "available_at 晚于 forecast_as_of")

    def test_naive_datetime_两种角色都拒绝(self) -> None:
        row = house_snapshot()
        row["forecast_as_of"] = "2022-09-13T12:00:00"
        self.assert_rejected(row, "必须显式携带时区")
        row = house_snapshot()
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-13T12:00:00"
        self.assert_rejected(row, "必须显式携带时区")

    def test_feature_available_at_恰好截点放行(self) -> None:
        row = house_snapshot()
        row["forecast_as_of"] = "2022-09-13T16:00:00Z"
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-13T16:00:00Z"
        validate_snapshot(row, REGISTRY)

    def test_map_known_at_晚于截点拒绝(self) -> None:
        row = house_snapshot()
        row["map"]["known_at"] = "2022-09-14"
        self.assert_rejected(row, "known_at 晚于 forecast_as_of")

    def test_map_effective_from_晚于截点拒绝(self) -> None:
        row = house_snapshot()
        row["map"]["effective_from"] = "2022-11-08"
        self.assert_rejected(row, "effective_from 晚于 forecast_as_of")

    def test_outcome_role_混入_predictors_拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["actual_democratic_margin"] = {
            "value": 2.2,
            "available_at": "2022-09-01",
        }
        row["predictors"].append("actual_democratic_margin")
        self.assert_rejected(row, "结果/非预测字段")

    def test_actual_result_键混入_predictors_拒绝(self) -> None:
        registry = copy.deepcopy(REGISTRY)
        registry["features"].append(
            {
                "id": "democratic_margin",
                "role": "predictor",
                "dtype": "number",
                "minimum": -100,
                "maximum": 100,
                "predictor_allowed": True,
                "allowed_in_current_contract": True,
                "offices": ["HOUSE", "SENATE"],
            }
        )
        row = house_snapshot()
        row["feature_values"]["democratic_margin"] = {
            "value": 2.2,
            "available_at": "2022-09-01",
        }
        row["predictors"].append("democratic_margin")
        with self.assertRaisesRegex(SnapshotValidationError, "结果/非预测字段"):
            validate_snapshot(row, registry)

    def test_actual_result_键集缺失或多余都拒绝(self) -> None:
        row = house_snapshot()
        del row["actual_result"]["democratic_margin"]
        self.assert_rejected(row, "actual_result 键集.*缺少 democratic_margin")
        row = house_snapshot()
        row["actual_result"]["legacy_margin"] = 2.2
        self.assert_rejected(row, "actual_result 键集.*多出 legacy_margin")

    def test_未知或缺失_dtype_拒绝(self) -> None:
        for dtype in ("numbr", None):
            with self.subTest(dtype=dtype):
                registry = copy.deepcopy(REGISTRY)
                if dtype is None:
                    del registry["features"][0]["dtype"]
                else:
                    registry["features"][0]["dtype"] = dtype
                with self.assertRaisesRegex(SnapshotValidationError, "dtype 未知或缺失"):
                    validate_snapshot(house_snapshot(), registry)

    def test_需要_vintage_却缺失时拒绝(self) -> None:
        row = house_snapshot()
        del row["feature_values"]["national_swing"]["vintage"]
        self.assert_rejected(row, "需要修订 vintage")

    def test_低于数值下界拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["national_swing"]["value"] = -25.1
        self.assert_rejected(row, "数值越界")

    def test_高于数值上界拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["partisan_baseline_margin"]["value"] = 100.1
        self.assert_rejected(row, "数值越界")

    def test_布尔值不能冒充数值(self) -> None:
        row = house_snapshot()
        row["feature_values"]["partisan_baseline_margin"]["value"] = True
        self.assert_rejected(row, "必须是数值")

    def test_同_race_cycle_horizon_重复拒绝(self) -> None:
        first = house_snapshot()
        second = copy.deepcopy(first)
        second["forecast_as_of"] = "2022-09-13T13:00:00-04:00"
        second["feature_values"]["national_swing"]["available_at"] = "2022-09-13T13:00:00-04:00"
        with self.assertRaisesRegex(SnapshotValidationError, "重复快照"):
            audit_panel([first, second], REGISTRY)

    def test_不同_horizon_不是重复(self) -> None:
        first = house_snapshot()
        second = copy.deepcopy(first)
        second["forecast_horizon"] = "4_weeks"
        self.assertEqual(len(audit_panel([first, second], REGISTRY)), 2)

    def test_senate_不得带_house_district(self) -> None:
        row = senate_snapshot()
        row["district"] = 1
        self.assert_rejected(row, "district 必须为 null")

    def test_senate_缺少席位类别被拒绝(self) -> None:
        row = senate_snapshot()
        del row["senate_class"]
        self.assert_rejected(row, "senate_class")

    def test_senate_缺少特殊选举标记被拒绝(self) -> None:
        row = senate_snapshot()
        del row["is_special_election"]
        self.assert_rejected(row, "is_special_election")

    def test_senate_非法选举阶段被拒绝(self) -> None:
        row = senate_snapshot()
        row["election_stage"] = "unknown"
        self.assert_rejected(row, "election_stage")

    def test_predictor_必须有观测(self) -> None:
        row = house_snapshot()
        del row["feature_values"]["national_swing"]
        self.assert_rejected(row, "没有观测")

    def test_只有日期的同日发布在日内截点被拒绝(self) -> None:
        row = house_snapshot()
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-13"
        self.assert_rejected(row, "available_at 晚于 forecast_as_of")

    def test_只有日期的发布在次日才放行(self) -> None:
        row = house_snapshot()
        row["forecast_as_of"] = "2022-09-14T00:00:00Z"
        row["feature_values"]["national_swing"]["available_at"] = "2022-09-13"
        validate_snapshot(row, REGISTRY)

    def test_只有日期的地图知悉日在同日截点被拒绝(self) -> None:
        row = house_snapshot()
        row["map"]["known_at"] = "2022-09-13"
        self.assert_rejected(row, "known_at 晚于 forecast_as_of")

    def test_predictor_allowed_false_拒绝(self) -> None:
        registry = copy.deepcopy(REGISTRY)
        registry["features"][1]["predictor_allowed"] = False
        row = house_snapshot()
        with self.assertRaisesRegex(SnapshotValidationError, "predictor_allowed"):
            validate_snapshot(row, registry)

    def test_queued_feature_即使登记也不得在本合同启用(self) -> None:
        registry = copy.deepcopy(REGISTRY)
        registry["features"][1]["allowed_in_current_contract"] = False
        row = house_snapshot()
        with self.assertRaisesRegex(SnapshotValidationError, "allowed_in_current_contract"):
            validate_snapshot(row, registry)

    def test_house_only_predictor_不得用于_senate(self) -> None:
        registry = copy.deepcopy(REGISTRY)
        registry["features"][1]["offices"] = ["HOUSE"]
        row = senate_snapshot()
        with self.assertRaisesRegex(SnapshotValidationError, "不允许用于 SENATE"):
            validate_snapshot(row, registry)


if __name__ == "__main__":
    unittest.main()
