"""Muse 实际验收的四维固定收缩内核（只保留函数本体）。"""
import math


def shrink_kernel(cell_counts, training_parent, mass=20.0):
    if not isinstance(cell_counts, (list, tuple)) or len(cell_counts) != 4:
        raise ValueError("cell_counts须为长度4向量")
    total = 0.0
    counts = []
    for value in cell_counts:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("cell_counts元素须为数值")
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError("cell_counts元素须有限且非负")
        counts.append(number)
        total += number
    if not isinstance(training_parent, (list, tuple)) or len(training_parent) != 4:
        raise ValueError("training_parent须为长度4向量")
    prior = []
    prior_sum = 0.0
    for value in training_parent:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("training_parent元素须为数值")
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError("training_parent元素须有限且非负")
        prior.append(number)
        prior_sum += number
    if abs(prior_sum - 1.0) > 1e-9:
        raise ValueError("training_parent求和须为1")
    if isinstance(mass, bool) or not isinstance(mass, (int, float)):
        raise ValueError("mass须为数值")
    mass = float(mass)
    if not math.isfinite(mass) or mass < 0.0:
        raise ValueError("mass须有限且非负")
    denominator = total + mass
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("分母须为正有限值")
    return [(counts[k] + mass * prior[k]) / denominator for k in range(4)]
