import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODEL_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("midterm_benchmark", MODEL_ROOT / "benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = benchmark.build_report()

    def test_report_is_deterministic(self):
        self.assertEqual(benchmark.render_json(self.report), benchmark.render_json(benchmark.build_report()))

    def test_report_declares_synthetic_boundary(self):
        self.assertTrue(self.report["synthetic_only"])
        self.assertFalse(self.report["contains_2026_probability"])

    def test_house_and_senate_are_separate_tracks(self):
        self.assertEqual(set(self.report["tracks"]), {"HOUSE", "SENATE"})

    def test_every_training_cycle_precedes_test_cycle(self):
        for track in self.report["tracks"].values():
            for model in track.values():
                for fold in model["folds"]:
                    self.assertLess(max(fold["train_cycles"]), fold["test_cycle"])

    def test_b1_passes_synthetic_gate_but_is_not_retained(self):
        for decision in self.report["component_comparisons"].values():
            self.assertTrue(decision["synthetic_gate_passed"])
            self.assertEqual(decision["implementation_status"], "synthetic_verified")
            self.assertEqual(decision["retention_status"], "queued")

    def test_all_required_metrics_exist(self):
        race = next(iter(self.report["tracks"]["HOUSE"].values()))["race_cycle_equal_weighted"]
        chamber = next(iter(self.report["tracks"]["HOUSE"].values()))["chamber_cycle_equal_weighted"]
        self.assertTrue({"mae", "rmse", "brier_democratic_win", "continuous_log_predictive_score_nats", "coverage_50", "coverage_80", "coverage_95"} <= set(race))
        self.assertTrue({"seat_count_absolute_error", "seat_count_crps", "majority_brier", "coverage_50", "coverage_80", "coverage_95", "seats_per_point_sensitivity_error"} <= set(chamber))

    def test_metric_registry_agrees_with_implementation(self):
        registry = json.loads((MODEL_ROOT / "config" / "component-registry.json").read_text(encoding="utf-8"))
        metrics = registry["metric_catalog"]
        self.assertEqual(metrics["race_continuous_log_score"]["direction"], "higher")
        self.assertIn("对数预测密度", metrics["race_continuous_log_score"]["definition"])
        self.assertEqual(metrics["race_margin_crps"]["direction"], "lower")

    def test_advanced_components_remain_queued(self):
        self.assertEqual(set(self.report["advanced_components"].values()), {"queued"})

    def test_every_registered_component_has_a_reported_reason(self):
        self.assertEqual(len(self.report["component_inventory"]), 20)
        self.assertTrue(all(item["reason"] != "未登记理由" for item in self.report["component_inventory"]))

    def test_correlated_tail_is_wider(self):
        self.assertTrue(self.report["correlated_error_diagnostic"]["tail_widening_verified"])

    def test_correlated_components_win_role_specific_benchmark(self):
        for office, comparison in self.report["correlation_component_comparisons"].items():
            self.assertTrue(comparison["synthetic_gate_passed"], office)
            self.assertEqual(comparison["implementation_status"], "synthetic_verified")
            self.assertEqual(comparison["retention_status"], "queued")
            self.assertLess(comparison["correlated_seat_crps"], comparison["independent_seat_crps"])
            self.assertEqual(comparison["race_guard_delta"], 0.0)

    def test_reported_correlation_status_matches_registry(self):
        registry = json.loads((MODEL_ROOT / "config" / "component-registry.json").read_text(encoding="utf-8"))
        statuses = {item["id"]: item["status"] for item in registry["components"]}
        for comparison in self.report["correlation_component_comparisons"].values():
            self.assertEqual(statuses[comparison["component_id"]], comparison["implementation_status"])

    def test_json_round_trip(self):
        self.assertEqual(json.loads(benchmark.render_json(self.report))["report_id"], "LH-047-foundation-benchmark")


if __name__ == "__main__":
    unittest.main()
