"""LH268 验证门负控；只改临时副本，不写共享研究产物。"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import challenger
import r1_sensitivity
import verify


HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "ces-policy-calibration-2026-09-09"
if not OLD.exists():
    OLD = HERE
MAP = [0, 0, 0, 1, 2, 2, 2, 3]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class VerificationGuardTests(unittest.TestCase):
    def run_challenger_check_rejects(self, mutate):
        original = (HERE / "challenger.json").read_bytes()
        value = read_json(HERE / "challenger.json")
        mutate(value)
        with tempfile.TemporaryDirectory(prefix="lh268-challenger-guard-") as d:
            root = Path(d); out = root / "challenger.json"
            shutil.copy2(HERE / "muse_shrink_kernel.py", root / "muse_shrink_kernel.py")
            out.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = out.read_bytes()
            with patch.object(challenger, "HERE", root), patch.object(sys, "argv", ["challenger.py", "--check"]):
                with self.assertRaises((SystemExit, AssertionError, ValueError)):
                    challenger.main()
            self.assertEqual(out.read_bytes(), before)
        self.assertEqual((HERE / "challenger.json").read_bytes(), original)

    def test_challenger_mean_summary_tamper_rejected(self):
        self.run_challenger_check_rejects(lambda x: x["mean_scores"].__setitem__("full_log", 123.456))

    def test_challenger_path_summary_tamper_rejected(self):
        def mutate(x):
            x["path_scores"][0]["score"]["full_log"] += 1.0
        self.run_challenger_check_rejects(mutate)

    def test_challenger_early_threeway_summary_tamper_rejected(self):
        def mutate(x):
            x["early_changed_threeway"]["full_log_mean"] += 1.0
        self.run_challenger_check_rejects(mutate)

    def run_r1_check_rejects(self, field):
        source = read_json(HERE / "r1-sensitivity.json")
        source["gate"]["gate_sha256"] = "guard-gate"
        source[field] = "0" * 64
        with tempfile.TemporaryDirectory(prefix="lh268-r1-guard-") as d:
            root = Path(d)
            for name in ("analysis-plan.json", "joint-counts.json", "r1-strata.csv"):
                (root / name).write_bytes((HERE / name).read_bytes())
            (root / "r1-sensitivity.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = (root / "r1-sensitivity.json").read_bytes()
            # Stub the already-computed deterministic object so this negative control never runs MC.
            expected = read_json(HERE / "r1-sensitivity.json")
            expected.pop("gate", None)
            with patch.object(r1_sensitivity, "HERE", root), patch.object(r1_sensitivity, "PLAN", root / "analysis-plan.json"), patch.object(r1_sensitivity, "GRID", root / "joint-counts.json"), patch.object(r1_sensitivity, "gate_ok", return_value={"gate_sha256": "guard-gate"}), patch.object(r1_sensitivity, "calculate", return_value=expected), patch.object(sys, "argv", ["r1_sensitivity.py", "--check"]):
                with self.assertRaises((SystemExit, AssertionError, ValueError)):
                    r1_sensitivity.main()
            self.assertEqual((root / "r1-sensitivity.json").read_bytes(), before)

    def test_r1_plan_sha_tamper_rejected_without_mc(self):
        self.run_r1_check_rejects("plan_sha256")

    def test_r1_grid_sha_tamper_rejected_without_mc(self):
        self.run_r1_check_rejects("grid_sha256")

    def test_verify_rejects_unobserved_invalid_child_probability(self):
        data = read_json(OLD / "lh266-joint-trajectories.json")
        observed = set()
        for fold in data["raw8_fold_counts"]:
            for index, count in enumerate(fold):
                if count:
                    observed.add((MAP[index // 64], MAP[(index // 8) % 8]))
        unobserved = next((pair for pair in ((a, b) for a in range(4) for b in range(8)) if pair not in observed), None)
        self.assertIsNotNone(unobserved)
        with tempfile.TemporaryDirectory(prefix="lh268-verify-guard-") as d:
            root = Path(d)
            for name in ("joint-counts.json", "decomposition.json"):
                (root / name).write_bytes((HERE / name).read_bytes())
            hist = read_json(OLD / "history-nested.json")
            a, b = unobserved
            hist["folds"][0]["child"][a][b] = [0.25, 0.25, 0.25, 0.25, 0.0]
            hist_path = root / "history-nested.json"
            hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = hist_path.read_bytes()
            with patch.object(verify, "HERE", root), patch.object(verify, "OLD", OLD):
                with self.assertRaises((AssertionError, ValueError, TypeError)):
                    verify.independent()
            self.assertEqual(hist_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
