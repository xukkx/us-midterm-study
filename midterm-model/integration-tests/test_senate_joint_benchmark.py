"""LH-050 联合计数报告的职责守门、探索状态与确定性测试。"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODEL_ROOT = Path(__file__).resolve().parents[1]
SRC = MODEL_ROOT / "src"
for search_path in (MODEL_ROOT, SRC):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

SPEC = importlib.util.spec_from_file_location(
    "lh050_senate_joint_benchmark", MODEL_ROOT / "senate_joint_benchmark.py"
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("无法加载 senate_joint_benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def frozen_historical_feature_prefix() -> list[dict]:
    path = MODEL_ROOT / "data" / "processed" / "senate-state-baselines.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[:550]]


def count_metric(value: float, direction: str = "lower") -> dict:
    return {
        "denominator_n": 1,
        "denominator_unit": "held_out_midterm_contest_set",
        "direction": direction,
        "value": value,
    }


def comparison_fold(cycle: int, correlated: float, independent: float) -> dict:
    return {
        "test_cycle": cycle,
        "models": {
            "CORRELATED": {
                "count_distribution": {
                    "senate_contested_d_count_crps": count_metric(correlated)
                }
            },
            "INDEPENDENT": {
                "count_distribution": {
                    "senate_contested_d_count_crps": count_metric(independent)
                }
            },
        },
    }


class CountScoreAndGateTests(unittest.TestCase):
    def test_actual_count_保留_other_conflict_null并只数_d(self):
        rows = [
            {"race_id": "A", "winner_group": "DEMOCRATIC", "two_party_margin": 1.0},
            {"race_id": "B", "winner_group": "OTHER", "two_party_margin": None},
            {"race_id": "C", "winner_group": "CONFLICT", "two_party_margin": None},
            {"race_id": "D", "winner_group": None, "two_party_margin": None},
        ]
        self.assertEqual(benchmark.actual_democratic_count(rows), 1)

    def test_actual_count_拒绝空集合与重复身份(self):
        with self.assertRaises(benchmark.SenateJointBenchmarkError):
            benchmark.actual_democratic_count([])
        with self.assertRaisesRegex(benchmark.SenateJointBenchmarkError, "重复"):
            benchmark.actual_democratic_count(
                [{"race_id": "A"}, {"race_id": "A"}]
            )

    def test_count_summary_手算_crps_log与矩(self):
        result = benchmark.count_distribution_summary((0.25, 0.5, 0.25), 1)
        self.assertAlmostEqual(
            result["senate_contested_d_count_crps"]["value"], 0.125
        )
        self.assertAlmostEqual(
            result["senate_contested_d_count_log_score_nats"]["value"],
            math.log(0.5),
            places=9,
        )
        self.assertEqual(result["count_mean"], 1.0)
        self.assertAlmostEqual(result["count_sd"], math.sqrt(0.5), places=9)
        self.assertEqual(result["support"], [0, 2])

    def test_count_summary_零实际质量禁止epsilon裁剪(self):
        with self.assertRaisesRegex(benchmark.SenateJointBenchmarkError, "质量为 0"):
            benchmark.count_distribution_summary((1.0, 0.0), 1)

    def test_count_summary_实际计数越界失败(self):
        with self.assertRaisesRegex(benchmark.SenateJointBenchmarkError, "支持集"):
            benchmark.count_distribution_summary((0.5, 0.5), 2)

    def test_聚合先届内后届等权(self):
        folds = [
            {
                "models": {
                    "M": {
                        "count_distribution": {
                            "senate_contested_d_count_crps": count_metric(1.0),
                            "senate_contested_d_count_log_score_nats": count_metric(
                                -2.0, "higher"
                            ),
                        }
                    }
                }
            },
            {
                "models": {
                    "M": {
                        "count_distribution": {
                            "senate_contested_d_count_crps": count_metric(3.0),
                            "senate_contested_d_count_log_score_nats": count_metric(
                                -4.0, "higher"
                            ),
                        }
                    }
                }
            },
        ]
        aggregate = benchmark.aggregate_count_metrics(folds, "M")
        self.assertEqual(aggregate["senate_contested_d_count_crps"]["value"], 2.0)
        self.assertEqual(aggregate["senate_contested_d_count_log_score_nats"]["value"], -3.0)
        self.assertEqual(aggregate["senate_contested_d_count_crps"]["n_cycles"], 2)

    def test_bootstrap_固定种子且单位是周期(self):
        deltas = [-1.0, -0.5, 0.2, -0.1]
        left = benchmark.cycle_bootstrap_probability(deltas, seed=71, draws=1000)
        right = benchmark.cycle_bootstrap_probability(deltas, seed=71, draws=1000)
        self.assertEqual(left, right)

    def test_bootstrap_拒绝非法draws(self):
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(benchmark.SenateJointBenchmarkError):
                    benchmark.cycle_bootstrap_probability([-1.0], draws=invalid)

    def test_三闸全过也只给探索信号字段(self):
        folds = [
            comparison_fold(cycle, 0.5, 1.0)
            for cycle in benchmark.PAIRED_MIDTERMS
        ]
        aggregate = {
            "CORRELATED": {"senate_contested_d_count_crps": {"value": 0.5}},
            "INDEPENDENT": {"senate_contested_d_count_crps": {"value": 1.0}},
        }
        with mock.patch.object(
            benchmark, "cycle_bootstrap_probability", return_value=0.99
        ):
            result = benchmark.build_comparison(folds, aggregate)
        self.assertTrue(result["gate_passed"])
        self.assertTrue(result["exploratory_comparative_signal"])
        self.assertNotIn("comparative_support", result)
        self.assertFalse(result["preregistered_before_outcome_inspection"])

    def test_bootstrap闸单独失败关闭三闸(self):
        folds = [
            comparison_fold(cycle, 0.8, 1.0)
            for cycle in benchmark.PAIRED_MIDTERMS
        ]
        aggregate = {
            "CORRELATED": {"senate_contested_d_count_crps": {"value": 0.8}},
            "INDEPENDENT": {"senate_contested_d_count_crps": {"value": 1.0}},
        }
        with mock.patch.object(
            benchmark, "cycle_bootstrap_probability", return_value=0.89
        ):
            result = benchmark.build_comparison(folds, aggregate)
        self.assertFalse(result["criteria_passed"]["crps_bootstrap"])
        self.assertFalse(result["gate_passed"])


class RealExploratoryReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = benchmark.build_report(feature_rows=frozen_historical_feature_prefix())

    def test_八折身份与有效k精确(self):
        self.assertEqual(
            self.report["paired_midterm_cycle_values"], list(range(1986, 2018, 4))
        )
        self.assertEqual(self.report["paired_midterm_cycles"], 8)
        self.assertEqual(
            [len(fold["train_cycles"]) for fold in self.report["folds"]],
            list(range(2, 10)),
        )

    def test_生产入口拒绝549行州基线(self):
        features = frozen_historical_feature_prefix()
        with self.assertRaisesRegex(ValueError, "必须为 550 行"):
            benchmark.build_report(feature_rows=features[:-1])

    def test_每折完整contest_set且不去重special(self):
        by_cycle = benchmark.select_formal_senate_midterms(
            benchmark.load_target_ledger()
        )
        for fold in self.report["folds"]:
            cycle = fold["test_cycle"]
            self.assertEqual(fold["n_contested_seats"], len(by_cycle[cycle]))
            self.assertEqual(fold["models"]["CORRELATED"]["count_distribution"]["support"], [0, len(by_cycle[cycle])])

    def test_父边际预测字节及proper_scores逐折相同(self):
        for fold in self.report["folds"]:
            correlated = fold["models"]["CORRELATED"]
            independent = fold["models"]["INDEPENDENT"]
            self.assertEqual(
                correlated["race_marginal_prediction_sha256"],
                independent["race_marginal_prediction_sha256"],
            )
            self.assertEqual(correlated["race_metrics"], independent["race_metrics"])
            self.assertTrue(fold["race_marginals_exactly_equal"])

    def test_共享局部方差逐折守恒且报告raw_used(self):
        for fold in self.report["folds"]:
            scale = fold["shared_residual_scale"]
            self.assertAlmostEqual(
                scale["shared_variance_used"] + scale["local_sd"] ** 2,
                scale["parent_total_sd"] ** 2,
                places=7,
            )
            self.assertEqual(
                scale["shared_variance_used"],
                min(scale["shared_variance_raw"], scale["parent_total_sd"] ** 2),
            )
            self.assertEqual(scale["n_train_cycles"], len(fold["train_cycles"]))

    def test_相关版本只改变pmf且计数均值近似守恒(self):
        for fold in self.report["folds"]:
            correlated = fold["models"]["CORRELATED"]["count_distribution"]
            independent = fold["models"]["INDEPENDENT"]["count_distribution"]
            self.assertNotEqual(correlated["pmf_sha256"], independent["pmf_sha256"])
            self.assertAlmostEqual(
                correlated["count_mean"], independent["count_mean"], delta=0.01
            )

    def test_post_selection旗标和无条件queued(self):
        status = self.report["component_status"]
        self.assertEqual(self.report["analysis_status"], "exploratory_post_selection")
        self.assertFalse(self.report["preregistered_before_outcome_inspection"])
        self.assertEqual(status["real_history_activation"], "queued")
        if self.report["paired_comparison"]["gate_passed"]:
            self.assertEqual(status["evidence_status"], "exploratory_comparative_signal")
            self.assertEqual(status["valid_nonpositive_run"], 0)
        else:
            self.assertEqual(status["evidence_status"], "exploratory_not_supported")
            self.assertEqual(status["valid_nonpositive_run"], 1)

    def test_边界旗标拒绝控制与2026(self):
        self.assertTrue(self.report["conditional_on_final_contest_set"])
        self.assertFalse(self.report["contains_2026_probability"])
        self.assertFalse(self.report["senate_control_probability"])
        self.assertFalse(self.report["holdovers_modeled"])

    def test_正式bootstrap参数和周期块精确(self):
        bootstrap = self.report["paired_comparison"]["bootstrap"]
        self.assertEqual(bootstrap["seed"], 50071)
        self.assertEqual(bootstrap["draws"], 50_000)
        self.assertEqual(bootstrap["resampling_unit"], "held_out_midterm_cycle")

    def test_registry角色指标与父组件守门(self):
        guard = self.report["registry_guard"]
        self.assertEqual(guard["component_id"], benchmark.COMPONENT_ID)
        self.assertEqual(guard["parent"], "M0_SENATE")
        self.assertEqual(guard["role"], "contest_set_distribution")
        self.assertEqual(guard["status"], "queued")

    def test_json_markdown确定且不含非有限数(self):
        left = benchmark.render_json(self.report)
        right = benchmark.render_json(self.report)
        self.assertEqual(left, right)
        self.assertNotIn("Infinity", left)
        self.assertNotIn("NaN", left)
        self.assertEqual(
            benchmark.render_markdown(self.report),
            benchmark.render_markdown(self.report),
        )
        self.assertEqual(
            json.loads(left)["report_id"],
            "LH-050-senate-joint-post-selection-exploratory",
        )

    def test_write_check临时文件及漂移失败(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "report.json"
            md_path = root / "report.md"
            with (
                mock.patch.object(benchmark, "JSON_REPORT", json_path),
                mock.patch.object(benchmark, "MD_REPORT", md_path),
                mock.patch.object(benchmark, "ARTIFACTS", root),
            ):
                benchmark.write_reports(self.report)
                benchmark.check_reports()
                json_path.write_text("{}\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "冻结字节漂移"):
                    benchmark.check_reports()


if __name__ == "__main__":
    unittest.main()
