"""有限概率律的独立恒等式检验；不估计CES中的未知真分布。"""
import math
import random
import unittest

def norm(values):
    s = sum(values)
    return [v / s for v in values]

def identity(mass, p, q0, q1):
    """mass[h][w]是真联合权重，p[h][w][y]是真条件分布。"""
    hmass = [sum(row) for row in mass]
    p0 = [[sum(mass[h][w] * p[h][w][y] for w in range(len(mass[h]))) / hmass[h]
           for y in range(len(p[h][0]))] for h in range(len(mass))]
    info = fitted = error0 = error1 = 0.0
    for h, row in enumerate(mass):
        for w, weight in enumerate(row):
            for y, probability in enumerate(p[h][w]):
                if probability == 0:
                    continue
                if min(q0[h][y], q1[h][w][y]) <= 0:
                    raise ValueError('在真分布支持上预测必须为正')
                m = weight * probability
                info += m * math.log(probability / p0[h][y])
                fitted += m * math.log(q1[h][w][y] / q0[h][y])
                error0 += m * math.log(p0[h][y] / q0[h][y])
                error1 += m * math.log(probability / q1[h][w][y])
    return info, fitted, error0, error1

class InformationIdentity(unittest.TestCase):
    def test_finite_laws(self):
        rng = random.Random(269)
        for _ in range(500):
            flat = norm([rng.random() + .01 for _ in range(6)])
            mass = [flat[:3], flat[3:]]
            p = [[norm([rng.random() + .01 for _ in range(4)]) for _ in range(3)] for _ in range(2)]
            q0 = [norm([rng.random() + .01 for _ in range(4)]) for _ in range(2)]
            q1 = [[norm([rng.random() + .01 for _ in range(4)]) for _ in range(3)] for _ in range(2)]
            info, fitted, e0, e1 = identity(mass, p, q0, q1)
            self.assertAlmostEqual(fitted, info - e1 + e0, places=12)
            self.assertGreaterEqual(min(info, e0, e1), -1e-12)

    def test_real_information_can_coexist_with_predictive_loss(self):
        info, fitted, e0, e1 = identity([[.5, .5]], [[[.9, .1], [.1, .9]]], [[.5, .5]], [[[.1, .9], [.9, .1]]])
        self.assertGreater(info, 0)
        self.assertLess(fitted, 0)
        self.assertAlmostEqual(fitted, info - e1 + e0)

    def test_no_information_can_coexist_with_predictive_gain(self):
        info, fitted, e0, e1 = identity([[.5, .5]], [[[.8, .2], [.8, .2]]], [[.5, .5]], [[[.8, .2], [.8, .2]]])
        self.assertAlmostEqual(info, 0)
        self.assertGreater(fitted, 0)

    def test_oracle_gain_is_information(self):
        p = [[[.9, .1], [.1, .9]]]
        info, fitted, e0, e1 = identity([[.5, .5]], p, [[.5, .5]], p)
        self.assertAlmostEqual(fitted, info)
        self.assertAlmostEqual(e0 + e1, 0)

    def test_zero_predictive_support_fails(self):
        with self.assertRaises(ValueError):
            identity([[1]], [[[.5, .5]]], [[0, 1]], [[[.5, .5]]])

if __name__ == '__main__': unittest.main()
