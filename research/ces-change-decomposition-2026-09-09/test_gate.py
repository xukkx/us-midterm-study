"""stage1-gate 失败关闭测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import r1_sensitivity


class GateTests(unittest.TestCase):
    def gate_copy(self):
        return json.loads((r1_sensitivity.GATE).read_text(encoding="utf-8"))

    def write_gate(self, value, root):
        p = root / "stage1-gate.json"
        p.write_text(json.dumps(value), encoding="utf-8")
        return p

    def test_false_gate_rejected(self):
        value = self.gate_copy(); value["scoring_gate_passed"] = False
        with tempfile.TemporaryDirectory() as d:
            with patch.object(r1_sensitivity, "GATE", self.write_gate(value, Path(d))):
                with self.assertRaises(RuntimeError): r1_sensitivity.gate_ok()

    def test_one_bound_artifact_hash_rejected(self):
        value = self.gate_copy(); value["artifact_sha256"]["known-history.csv"] = "0" * 64
        with tempfile.TemporaryDirectory() as d:
            with patch.object(r1_sensitivity, "GATE", self.write_gate(value, Path(d))):
                with self.assertRaises(RuntimeError): r1_sensitivity.gate_ok()


if __name__ == "__main__":
    unittest.main()
