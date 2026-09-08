"""生态敏锐界模块测试（LH-099）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODEL_ROOT / "src"))

from midterms import ecological_bounds as eb


class 县级界测试(unittest.TestCase):
    def test_手算锚点(self):
        # x=0.4, y=0.5 → L=max(0,(0.5-0.6)/0.4)=0, U=min(1,0.5/0.4)=1 → 无信息宽界
        self.assertEqual(eb.county_bounds(0.4, 0.5), (0.0, 1.0))
        # x=0.8, y=0.5 → L=(0.5-0.2)/0.8=0.375, U=0.5/0.8=0.625
        l, u = eb.county_bounds(0.8, 0.5)
        self.assertAlmostEqual(l, 0.375)
        self.assertAlmostEqual(u, 0.625)

    def test_极端例(self):
        self.assertEqual(eb.county_bounds(1.0, 0.42), (0.42, 0.42))  # x=1 收点
        self.assertEqual(eb.county_bounds(0.0, 0.7), (0.0, 1.0))     # x=0 满界
        with self.assertRaises(eb.EcologicalBoundsError):
            eb.county_bounds(0.5, 1.2)

    def test_界包含真值_模拟(self):
        # 构造已知 p 的合成县：x=0.6, 亚群 p=0.3, 其余 q=0.9 → y=0.6*0.3+0.4*0.9=0.54
        l, u = eb.county_bounds(0.6, 0.54)
        self.assertLessEqual(l, 0.3)
        self.assertGreaterEqual(u, 0.3)


class 聚合界测试(unittest.TestCase):
    ROWS = [
        {"x": 0.9, "y": 0.5, "w": 100.0},
        {"x": 0.2, "y": 0.6, "w": 300.0},
    ]

    def test_手算锚点(self):
        # 分母 = 100*0.9 + 300*0.2 = 150
        # L 分子 = 100*max(0,0.5-0.1) + 300*max(0,0.6-0.8) = 40
        # U 分子 = 100*min(0.9,0.5) + 300*min(0.2,0.6) = 50+60 = 110
        b = eb.aggregate_bounds(self.ROWS)
        self.assertAlmostEqual(b["lower"], 40.0 / 150.0)
        self.assertAlmostEqual(b["upper"], 110.0 / 150.0)
        self.assertIn("近似声明", b["approximation_statement"])

    def test_聚合界不宽于加权平均县界的包络性质(self):
        # 敏锐界必包含任一可行分配的真值：以 p_c 全 0.5 检验（可行仅当每县 0.5 在县界内）
        rows = [{"x": 0.8, "y": 0.5, "w": 50.0}, {"x": 0.7, "y": 0.55, "w": 70.0}]
        b = eb.aggregate_bounds(rows)
        for r in rows:
            l, u = eb.county_bounds(r["x"], r["y"])
            self.assertLessEqual(l, u)
        self.assertLess(b["lower"], b["upper"])

    def test_零亚群权重拒绝(self):
        with self.assertRaises(eb.EcologicalBoundsError):
            eb.aggregate_bounds([{"x": 0.0, "y": 0.5, "w": 10.0}])


class 密度收紧测试(unittest.TestCase):
    def test_密度升界宽不增(self):
        rows = [
            {"x": 0.95, "y": 0.45, "w": 10.0},
            {"x": 0.75, "y": 0.5, "w": 20.0},
            {"x": 0.55, "y": 0.6, "w": 30.0},
            {"x": 0.15, "y": 0.7, "w": 40.0},
        ]
        seq = eb.density_tightening(rows)
        widths = [e["width"] for e in seq if e["width"] is not None]
        for earlier, later in zip(widths, widths[1:]):
            self.assertLessEqual(later, earlier + 1e-12)
        self.assertAlmostEqual(seq[-1]["upper"] - seq[-1]["lower"], seq[-1]["width"])

    def test_空子集如实(self):
        seq = eb.density_tightening([{"x": 0.3, "y": 0.5, "w": 1.0}], thresholds=(0.9,))
        self.assertEqual(seq[0]["counties"], 0)
        self.assertIsNone(seq[0]["width"])


if __name__ == "__main__":
    unittest.main()
