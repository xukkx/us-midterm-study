"""LH-048 真实历史基准驱动器的边界与确定性测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODEL_ROOT = Path(__file__).resolve().parents[1]
SRC = MODEL_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SPEC = importlib.util.spec_from_file_location(
    "lh048_real_benchmark", MODEL_ROOT / "real_benchmark.py"
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - 导入器异常时明确失败
    raise RuntimeError("无法加载 real_benchmark.py")
real_benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(real_benchmark)

from midterms.real_baseline import prediction_bytes  # noqa: E402
from midterms.split import expanding_window_splits  # noqa: E402


class RealBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.all_targets = real_benchmark.load_target_ledger()
        cls.formal = real_benchmark.validate_and_select_formal_targets(cls.all_targets)
        cls.report = real_benchmark.build_report(cls.all_targets)

    def test_报告声明真实目标且没有_2026_概率(self) -> None:
        self.assertTrue(self.report["real_historical_targets"])
        self.assertFalse(self.report["contains_2026_probability"])
        reported_cycles = {
            fold["test_cycle"]
            for track in self.report["tracks"].values()
            for fold in track["folds"]
        }
        self.assertNotIn(2026, reported_cycles)

    def test_两院各有九个中期测试届并标_provisional(self) -> None:
        expected = list(range(1982, 2018, 4))
        for office in ("HOUSE", "SENATE"):
            track = self.report["tracks"][office]
            self.assertEqual(track["held_out_midterm_cycles"], expected)
            self.assertEqual(track["n_held_out_midterm_cycles"], 9)
            self.assertEqual(track["evidence_status"], "provisional")
            self.assertFalse(track["promotion_eligible"])
            self.assertEqual(track["retention_status"], "benchmark_only")

    def test_训练使用全部更早周期而非只用中期(self) -> None:
        for office in ("HOUSE", "SENATE"):
            for fold in self.report["tracks"][office]["folds"]:
                expected = list(range(1976, fold["test_cycle"], 2))
                self.assertEqual(fold["train_cycles"], expected)
                self.assertLess(max(fold["train_cycles"]), fold["test_cycle"])
                self.assertTrue(any(cycle % 4 == 0 for cycle in fold["train_cycles"]))

    def test_每个指标显式报告正确分母(self) -> None:
        for office in ("HOUSE", "SENATE"):
            track = self.report["tracks"][office]
            for fold in track["folds"]:
                denominators = fold["denominators"]
                self.assertGreater(denominators["all_test_races"], 0)
                self.assertGreater(denominators["two_party_margin_races"], 0)
                self.assertGreater(denominators["dr_winner_races"], 0)
                self.assertLessEqual(
                    denominators["two_party_margin_races"], denominators["all_test_races"]
                )
                self.assertLessEqual(
                    denominators["dr_winner_races"], denominators["all_test_races"]
                )
                for name, metric in fold["metrics"].items():
                    expected = (
                        denominators["dr_winner_races"]
                        if name == "brier_democratic_win"
                        else denominators["two_party_margin_races"]
                    )
                    self.assertEqual(metric["denominator_n"], expected, (office, name))
            for metric in track["aggregate_metrics"].values():
                self.assertEqual(metric["n_cycles"], 9)
                self.assertEqual(len(metric["observation_n_by_cycle"]), 9)
                self.assertEqual(metric["observation_n_sum"], sum(metric["observation_n_by_cycle"]))

    def test_brier_只以_d_r_赢家为分母(self) -> None:
        for office in ("HOUSE", "SENATE"):
            source_by_cycle = {}
            for row in self.formal:
                if row["office"] == office:
                    source_by_cycle.setdefault(row["cycle"], []).append(row)
            for fold in self.report["tracks"][office]["folds"]:
                expected = sum(
                    row["winner_group"] in {"DEMOCRATIC", "REPUBLICAN", "D", "R"}
                    for row in source_by_cycle[fold["test_cycle"]]
                )
                self.assertEqual(fold["denominators"]["dr_winner_races"], expected)
                self.assertEqual(
                    fold["metrics"]["brier_democratic_win"]["denominator_unit"],
                    "D/R_winner_race",
                )

    def test_连续指标只以可用两党边际为分母(self) -> None:
        for office in ("HOUSE", "SENATE"):
            for fold in self.report["tracks"][office]["folds"]:
                expected = sum(
                    row["office"] == office
                    and row["cycle"] == fold["test_cycle"]
                    and row["two_party_margin"] is not None
                    for row in self.formal
                )
                self.assertEqual(fold["denominators"]["two_party_margin_races"], expected)

    def test_预测字节不含_actual_且改写测试结果不变(self) -> None:
        rows = [row for row in self.formal if row["office"] == "HOUSE"]
        fold = next(
            item
            for item in expanding_window_splits(rows, min_train_cycles=3)
            if item.test_cycle == 1982
        )
        model, predictions = real_benchmark.make_fold_predictions(fold, "HOUSE")
        original_bytes = prediction_bytes(predictions)
        self.assertNotIn(b"actual", original_bytes.lower())
        self.assertNotIn(b"winner", original_bytes.lower())
        mutated = copy.deepcopy(list(fold.test))
        for row in mutated:
            row["two_party_margin"] = 99.0
            row["winner_group"] = "DEMOCRATIC"
            row["realized_national_swing"] = 88.0
        mutated_predictions = real_benchmark.predict_r0(model, mutated)
        self.assertEqual(original_bytes, prediction_bytes(mutated_predictions))

    def test_预测字段严格限定为身份和_r0_输出(self) -> None:
        expected = {
            "cycle",
            "democratic_win_probability",
            "margin_sd",
            "office",
            "predicted_margin",
            "race_id",
        }
        for office in ("HOUSE", "SENATE"):
            for fold in self.report["tracks"][office]["folds"]:
                self.assertEqual(set(fold["prediction_fields"]), expected)
                self.assertEqual(len(fold["prediction_sha256"]), 64)

    def test_house_只报告_435_竞选席独立分布诊断(self) -> None:
        for fold in self.report["tracks"]["HOUSE"]["folds"]:
            diagnostic = fold["seat_scope_diagnostic"]
            self.assertEqual(
                diagnostic["label"],
                "independent_435_contested_house_seat_democratic_count",
            )
            self.assertEqual(diagnostic["n_contested_voting_seats"], 435)
            self.assertTrue(diagnostic["diagnostic_only"])
            self.assertEqual(set(diagnostic["central_count_intervals"]), {"50", "80", "95"})

    def test_senate_诊断只叫_contested_seat_count(self) -> None:
        for fold in self.report["tracks"]["SENATE"]["folds"]:
            diagnostic = fold["seat_scope_diagnostic"]
            self.assertEqual(set(diagnostic), {"diagnostic_only", "label", "n_contested_seats", "scope_note"})
            self.assertEqual(diagnostic["label"], "contested_seat_count")
            serialized = json.dumps(diagnostic, ensure_ascii=False).lower()
            self.assertNotIn("control", serialized)
            self.assertNotIn("majority", serialized)

    def test_2018_只保留为不合格负证据(self) -> None:
        for office in ("HOUSE", "SENATE"):
            rejected = self.report["rejected_source_cycles"][office]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["cycle"], 2018)
            self.assertFalse(rejected[0]["benchmark_eligible"])
            self.assertTrue(all(
                not row["benchmark_eligible"]
                for row in self.all_targets
                if row["office"] == office and row["cycle"] == 2018
            ))

    def test_m0_b1_及高级组件真实历史激活保持排队(self) -> None:
        activation = self.report["real_history_activation"]
        self.assertEqual(
            set(activation["primary_components"]),
            {"M0_HOUSE", "M0_SENATE", "B1_HOUSE", "B1_SENATE"},
        )
        self.assertTrue(all(
            item["real_history_activation"] == "queued"
            for item in activation["primary_components"].values()
        ))
        self.assertTrue(activation["advanced_components"])
        self.assertEqual(set(activation["advanced_components"].values()), {"queued"})

    def test_证据层级边界精确(self) -> None:
        self.assertEqual(real_benchmark.evidence_status(0), "experimental")
        self.assertEqual(real_benchmark.evidence_status(7), "experimental")
        self.assertEqual(real_benchmark.evidence_status(8), "provisional")
        self.assertEqual(real_benchmark.evidence_status(11), "provisional")
        self.assertEqual(real_benchmark.evidence_status(12), "historically_supported")

    def test_账本验证拒绝把_2018_开启为正式评分(self) -> None:
        mutated = copy.deepcopy(self.all_targets)
        row = next(item for item in mutated if item["cycle"] == 2018)
        row["benchmark_eligible"] = True
        with self.assertRaisesRegex(real_benchmark.RealBenchmarkError, "2018"):
            real_benchmark.validate_and_select_formal_targets(mutated)

    def test_账本验证拒绝_house_不满_435(self) -> None:
        mutated = [
            row
            for row in self.all_targets
            if row["race_id"] != next(
                item["race_id"]
                for item in self.all_targets
                if item["office"] == "HOUSE" and item["cycle"] == 1976
            )
        ]
        with self.assertRaisesRegex(real_benchmark.RealBenchmarkError, "435"):
            real_benchmark.validate_and_select_formal_targets(mutated)

    def test_二项分布边界和为一(self) -> None:
        self.assertEqual(real_benchmark._binomial_probabilities(3, 0.0), [1.0, 0.0, 0.0, 0.0])
        self.assertEqual(real_benchmark._binomial_probabilities(3, 1.0), [0.0, 0.0, 0.0, 1.0])
        probabilities = real_benchmark._binomial_probabilities(435, 0.53)
        self.assertAlmostEqual(sum(probabilities), 1.0, places=12)
        self.assertEqual(len(probabilities), 436)

    def test_json_和_markdown_渲染确定(self) -> None:
        second = real_benchmark.build_report(self.all_targets)
        self.assertEqual(real_benchmark.render_json(self.report), real_benchmark.render_json(second))
        self.assertEqual(real_benchmark.render_markdown(self.report), real_benchmark.render_markdown(second))
        self.assertEqual(
            json.loads(real_benchmark.render_json(self.report))["report_id"],
            "LH-048-real-target-r0-benchmark",
        )


if __name__ == "__main__":
    unittest.main()
