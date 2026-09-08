"""LH-049 Senate M0 配对竞速报告的口径、职责闸与确定性测试。"""

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
    "lh049_senate_m0_benchmark", MODEL_ROOT / "senate_m0_benchmark.py"
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - 导入器异常时明确失败
    raise RuntimeError("无法加载 senate_m0_benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def frozen_historical_feature_prefix() -> list[dict]:
    lines = benchmark.FEATURE_LEDGER.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[:550]]


def actual(race_id, margin, winner):
    return {
        "race_id": race_id,
        "two_party_margin": margin,
        "winner_group": winner,
    }


def prediction(race_id, mean=0.0, sigma=2.0, probability=0.5):
    return {
        "race_id": race_id,
        "predicted_margin": mean,
        "margin_sd": sigma,
        "democratic_win_probability": probability,
    }


def metric(value, denominator=10, direction="lower", unit="two_party_margin_race"):
    return {
        "denominator_n": denominator,
        "denominator_unit": unit,
        "direction": direction,
        "value": value,
    }


def comparison_fold(cycle, m0_crps, r0_crps, m0_brier=0.20, r0_brier=0.20):
    return {
        "test_cycle": cycle,
        "models": {
            "M0_SENATE": {
                "metrics": {
                    "margin_normal_crps": metric(m0_crps),
                    "brier_democratic_win": metric(
                        m0_brier, unit="D/R_winner_race"
                    ),
                }
            },
            "R0_SENATE_MIDTERM_ONLY": {
                "metrics": {
                    "margin_normal_crps": metric(r0_crps),
                    "brier_democratic_win": metric(
                        r0_brier, unit="D/R_winner_race"
                    ),
                }
            },
        },
    }


class ScoreAndDistributionTests(unittest.TestCase):
    def test_score_显式区分_margin_与_brier_分母(self):
        rows = [
            actual("A", 1.0, "D"),
            actual("B", None, "R"),
            actual("C", -1.0, "OTHER"),
        ]
        predictions = [
            prediction("A", probability=0.75),
            prediction("B", probability=0.25),
            prediction("C", probability=0.50),
        ]
        scores = benchmark.score_predictions(rows, predictions)
        self.assertEqual(scores["margin_mae"]["denominator_n"], 2)
        self.assertEqual(scores["brier_democratic_win"]["denominator_n"], 2)
        self.assertEqual(
            scores["brier_democratic_win"]["denominator_unit"],
            "D/R_winner_race",
        )
        self.assertEqual(scores["margin_normal_crps"]["direction"], "lower")
        self.assertEqual(scores["margin_normal_log_score_nats"]["direction"], "higher")

    def test_score_预测顺序不影响结果(self):
        rows = [actual("A", 1.0, "D"), actual("B", -1.0, "R")]
        predictions = [prediction("A"), prediction("B")]
        self.assertEqual(
            benchmark.score_predictions(rows, predictions),
            benchmark.score_predictions(list(reversed(rows)), list(reversed(predictions))),
        )

    def test_score_身份不一致拒绝(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "身份"):
            benchmark.score_predictions(
                [actual("A", 1.0, "D")], [prediction("B")]
            )

    def test_score_重复预测拒绝(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "重复"):
            benchmark.score_predictions(
                [actual("A", 1.0, "D")], [prediction("A"), prediction("A")]
            )

    def test_score_非法概率拒绝而不裁剪(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "胜率非法"):
            benchmark.score_predictions(
                [actual("A", 1.0, "D")], [prediction("A", probability=1.01)]
            )

    def test_score_布尔数值字段拒绝(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "有限数值"):
            benchmark.score_predictions(
                [actual("A", 1.0, "D")], [prediction("A", probability=True)]
            )

    def test_score_非正_sigma_拒绝(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "分布非法"):
            benchmark.score_predictions(
                [actual("A", 1.0, "D")], [prediction("A", sigma=0.0)]
            )

    def test_score_没有连续边际失败关闭(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "没有可用"):
            benchmark.score_predictions(
                [actual("A", None, "D")], [prediction("A")]
            )

    def test_score_没有_d_r_赢家失败关闭(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "Brier"):
            benchmark.score_predictions(
                [actual("A", 1.0, "OTHER")], [prediction("A")]
            )

    def test_poisson_binomial_手算两枚公平硬币(self):
        probabilities = benchmark._poisson_binomial_probabilities([0.5, 0.5])
        self.assertEqual(probabilities, [0.25, 0.5, 0.25])
        self.assertAlmostEqual(sum(probabilities), 1.0, places=14)

    def test_poisson_binomial_保留零一边界(self):
        self.assertEqual(
            benchmark._poisson_binomial_probabilities([0.0, 1.0]),
            [0.0, 1.0, 0.0],
        )

    def test_poisson_binomial_非法概率拒绝(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "概率非法"):
            benchmark._poisson_binomial_probabilities([0.5, math.nan])

    def test_contested_count_只数当届竞选席(self):
        rows = [actual("A", 1.0, "D"), actual("B", -1.0, "OTHER")]
        predictions = [
            prediction("A", probability=0.8),
            prediction("B", probability=0.3),
        ]
        result = benchmark.contested_seat_d_count_diagnostic(rows, predictions)
        self.assertEqual(result["n_contested_seats"], 2)
        self.assertEqual(result["actual_democratic_winner_count"], 1)
        self.assertEqual(result["predicted_count_mean"], 1.1)
        self.assertTrue(result["diagnostic_only"])
        self.assertTrue(result["not_senate_control"])
        self.assertEqual(result["probability_mass_sum"], 1.0)

    def test_contested_count_不接受错配身份(self):
        with self.assertRaisesRegex(benchmark.SenateM0BenchmarkError, "身份"):
            benchmark.contested_seat_d_count_diagnostic(
                [actual("A", 1.0, "D")], [prediction("B")]
            )


class AggregationAndGateTests(unittest.TestCase):
    def test_聚合先届内后届等权而非按_race_加权(self):
        folds = [
            {
                "models": {
                    "M": {"metrics": {"loss": metric(1.0, denominator=1)}}
                }
            },
            {
                "models": {
                    "M": {"metrics": {"loss": metric(3.0, denominator=100)}}
                }
            },
        ]
        aggregate = benchmark.aggregate_metrics(folds, "M")["loss"]
        self.assertEqual(aggregate["value"], 2.0)
        self.assertEqual(aggregate["n_cycles"], 2)
        self.assertEqual(aggregate["observation_n_sum"], 101)

    def test_bootstrap_固定种子重复一致(self):
        deltas = [-1.0, -0.5, 0.2, -0.1]
        left = benchmark.cycle_bootstrap_probability(deltas, seed=17, draws=1000)
        right = benchmark.cycle_bootstrap_probability(deltas, seed=17, draws=1000)
        self.assertEqual(left, right)

    def test_bootstrap_全负与全正边界(self):
        self.assertEqual(
            benchmark.cycle_bootstrap_probability([-1.0] * 8, draws=100), 1.0
        )
        self.assertEqual(
            benchmark.cycle_bootstrap_probability([1.0] * 8, draws=100), 0.0
        )

    def test_bootstrap_只接受正整数_draws(self):
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(benchmark.SenateM0BenchmarkError):
                    benchmark.cycle_bootstrap_probability([-1.0], draws=invalid)

    def test_四项预注册条件全部通过才给比较支持(self):
        folds = [
            comparison_fold(cycle, 0.75, 1.0)
            for cycle in benchmark.PAIRED_MIDTERMS
        ]
        aggregate = {
            "M0_SENATE": {
                "margin_normal_crps": {"value": 0.75},
                "brier_democratic_win": {"value": 0.20},
            },
            "R0_SENATE_MIDTERM_ONLY": {
                "margin_normal_crps": {"value": 1.0},
                "brier_democratic_win": {"value": 0.20},
            },
        }
        result = benchmark.build_comparison(folds, aggregate)
        self.assertTrue(result["gate_passed"])
        self.assertTrue(all(result["criteria_passed"].values()))
        self.assertEqual(result["bootstrap"]["seed"], benchmark.BOOTSTRAP_SEED)
        self.assertEqual(
            result["bootstrap"]["resampling_unit"], "held_out_midterm_cycle"
        )

    def test_brier_退化单独阻止比较支持(self):
        folds = [
            comparison_fold(cycle, 0.75, 1.0, m0_brier=0.30, r0_brier=0.20)
            for cycle in benchmark.PAIRED_MIDTERMS
        ]
        aggregate = {
            "M0_SENATE": {
                "margin_normal_crps": {"value": 0.75},
                "brier_democratic_win": {"value": 0.30},
            },
            "R0_SENATE_MIDTERM_ONLY": {
                "margin_normal_crps": {"value": 1.0},
                "brier_democratic_win": {"value": 0.20},
            },
        }
        result = benchmark.build_comparison(folds, aggregate)
        self.assertFalse(result["criteria_passed"]["brier_guard"])
        self.assertFalse(result["gate_passed"])

    def test_crps_delta_方向锁为_m0_减_r0(self):
        folds = [
            comparison_fold(cycle, 0.9, 1.0)
            for cycle in benchmark.PAIRED_MIDTERMS
        ]
        aggregate = {
            "M0_SENATE": {
                "margin_normal_crps": {"value": 0.9},
                "brier_democratic_win": {"value": 0.2},
            },
            "R0_SENATE_MIDTERM_ONLY": {
                "margin_normal_crps": {"value": 1.0},
                "brier_democratic_win": {"value": 0.2},
            },
        }
        result = benchmark.build_comparison(folds, aggregate)
        self.assertEqual(result["cycle_crps_delta_m0_minus_r0"], [-0.1] * 8)
        self.assertEqual(result["winning_direction"], "M0_CRPS - R0_CRPS < 0")


class RealReportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = benchmark.build_report(feature_rows=frozen_historical_feature_prefix())

    def test_正式配对精确为_1986_至_2014_八届(self):
        self.assertEqual(
            self.report["paired_midterm_cycle_values"],
            list(range(1986, 2018, 4)),
        )
        self.assertEqual(self.report["paired_midterm_cycles"], 8)
        self.assertEqual(self.report["evidence_status"], "provisional")

    def test_正式报告拒绝缺少任一固定州基线的_549_行账本(self):
        features = frozen_historical_feature_prefix()
        missing = [
            row
            for row in features
            if not (row["target_cycle"] == 2018 and row["state"] == "WY")
        ]
        self.assertEqual(len(missing), 549)
        with self.assertRaisesRegex(ValueError, "必须为 550 行"):
            benchmark.build_report(feature_rows=missing)

    def test_每折两模型使用完全相同早期中期届(self):
        for fold in self.report["folds"]:
            self.assertEqual(
                fold["train_cycles"], list(range(1978, fold["test_cycle"], 4))
            )
            for model_id in ("M0_SENATE", "R0_SENATE_MIDTERM_ONLY"):
                self.assertEqual(
                    fold["models"][model_id]["model_parameters_from_train_only"][
                        "train_cycles"
                    ],
                    fold["train_cycles"],
                )

    def test_每折两模型的所有评分分母完全一致(self):
        for fold in self.report["folds"]:
            m0 = fold["models"]["M0_SENATE"]["metrics"]
            r0 = fold["models"]["R0_SENATE_MIDTERM_ONLY"]["metrics"]
            self.assertEqual(set(m0), set(r0))
            for name in m0:
                self.assertEqual(m0[name]["denominator_n"], r0[name]["denominator_n"])
                self.assertEqual(
                    m0[name]["denominator_unit"], r0[name]["denominator_unit"]
                )

    def test_所有竞选都有两模型预测且包含_special(self):
        target_rows = benchmark.load_target_ledger()
        formal = benchmark.select_formal_senate_midterms(target_rows)
        for fold in self.report["folds"]:
            cycle = fold["test_cycle"]
            self.assertEqual(
                fold["denominators"]["all_test_races"], len(formal[cycle])
            )
            self.assertTrue(
                any(row["election_type"] == "special" for row in formal[cycle])
                or all(row["election_type"] == "regular" for row in formal[cycle])
            )
            self.assertEqual(
                len(fold["models"]["M0_SENATE"]["prediction_sha256"]), 64
            )
            self.assertEqual(
                len(fold["models"]["R0_SENATE_MIDTERM_ONLY"]["prediction_sha256"]),
                64,
            )

    def test_1982_明确因一个训练周期排除(self):
        excluded = {row["cycle"]: row for row in self.report["excluded_early_midterms"]}
        self.assertEqual(excluded[1982]["reason"], "insufficient_calibration_cycles")
        self.assertEqual(excluded[1982]["n_prior_residual_midterm_cycles"], 1)

    def test_档案与_2026_边界旗标精确(self):
        self.assertTrue(self.report["real_historical_targets"])
        self.assertEqual(
            self.report["historical_evidence_type"], "archival_reconstruction"
        )
        self.assertFalse(self.report["strict_original_vintage_available"])
        self.assertFalse(self.report["contains_2026_probability"])
        self.assertFalse(self.report["senate_control_probability"])

    def test_m0_只激活为档案基准且其余组件排队(self):
        activation = self.report["component_activation"]
        m0 = activation["primary_components"]["M0_SENATE"]
        self.assertEqual(m0["real_history_activation"], "archival_validated_benchmark")
        self.assertEqual(m0["registry_role_preserved"], "required_benchmark")
        self.assertEqual(m0["retention_status"], "benchmark_only")
        self.assertEqual(m0["evidence_status"], "provisional")
        self.assertFalse(m0["promotion_eligible"])
        for component_id in ("M0_HOUSE", "B1_HOUSE", "B1_SENATE"):
            self.assertEqual(
                activation["primary_components"][component_id]["real_history_activation"],
                "queued",
            )
        self.assertEqual(set(activation["advanced_components"].values()), {"queued"})

    def test_contested_count_诊断从不冒充控制模型(self):
        for fold in self.report["folds"]:
            for model_id in ("M0_SENATE", "R0_SENATE_MIDTERM_ONLY"):
                diagnostic = fold["models"][model_id][
                    "contested_seat_d_count_diagnostic"
                ]
                self.assertTrue(diagnostic["diagnostic_only"])
                self.assertTrue(diagnostic["not_senate_control"])
                self.assertEqual(diagnostic["probability_mass_sum"], 1.0)

    def test_json_与_markdown_重复渲染一致(self):
        self.assertEqual(
            benchmark.render_json(self.report), benchmark.render_json(self.report)
        )
        self.assertEqual(
            benchmark.render_markdown(self.report),
            benchmark.render_markdown(self.report),
        )
        decoded = json.loads(benchmark.render_json(self.report))
        self.assertEqual(
            decoded["report_id"], "LH-049-senate-m0-archival-paired-benchmark"
        )

    def test_write_check_临时文件字节一致且漂移会失败(self):
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
