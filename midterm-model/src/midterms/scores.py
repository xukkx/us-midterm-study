"""零依赖的概率评分函数。

所有公开函数都拒绝非法输入，不做静默裁剪。方向约定：损失越小越好；
``normal_log_score`` 是唯一的例外，它是对数预测密度，越大越好。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations_with_replacement
from statistics import NormalDist
from typing import Iterable, Sequence


NORMAL = NormalDist()


@dataclass(frozen=True)
class ExactBootstrapMean:
    """一个周期块多重集均值及其在有序 bootstrap 中的精确重数。"""

    counts: tuple[int, ...]
    mean: float
    multiplicity: int


def _finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是有限数值")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须是有限数值")
    return number


def probability(value: float) -> float:
    """校验概率；故意不把越界值裁到 [0, 1]。"""
    number = _finite_number(value, "概率")
    if not 0.0 <= number <= 1.0:
        raise ValueError("概率必须位于 [0, 1]")
    return number


def binary_outcome(value: int | bool) -> int:
    if value in (0, 1, False, True):
        return int(value)
    raise ValueError("二元结果必须是 0 或 1")


def brier_score(predicted_probability: float, observed: int | bool) -> float:
    p = probability(predicted_probability)
    y = binary_outcome(observed)
    return (p - y) ** 2


def binary_log_loss(predicted_probability: float, observed: int | bool) -> float:
    """二元负对数损失（越小越好）；0/1 的错误确定性预测返回无穷。"""
    p = probability(predicted_probability)
    y = binary_outcome(observed)
    if (p == 0.0 and y == 1) or (p == 1.0 and y == 0):
        return math.inf
    if y == 1:
        return -math.log(p)
    return -math.log1p(-p)


def normal_log_score(observed: float, mean: float, standard_deviation: float) -> float:
    """正态预测密度的自然对数（越大越好，单位为 nat）。"""
    y = _finite_number(observed, "观测值")
    mu = _finite_number(mean, "均值")
    sigma = _finite_number(standard_deviation, "标准差")
    if sigma <= 0:
        raise ValueError("标准差必须大于 0")
    z = (y - mu) / sigma
    return -math.log(sigma) - 0.5 * math.log(2.0 * math.pi) - 0.5 * z * z


def normal_crps(observed: float, mean: float, standard_deviation: float) -> float:
    """正态预测分布的连续排名概率分数（越小越好）。"""
    y = _finite_number(observed, "观测值")
    mu = _finite_number(mean, "均值")
    sigma = _finite_number(standard_deviation, "标准差")
    if sigma <= 0:
        raise ValueError("标准差必须大于 0")
    z = (y - mu) / sigma
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return sigma * (z * (2.0 * NORMAL.cdf(z) - 1.0) + 2.0 * phi - 1.0 / math.sqrt(math.pi))


def normal_win_probability(mean_margin: float, standard_deviation: float) -> float:
    mu = _finite_number(mean_margin, "预测优势")
    sigma = _finite_number(standard_deviation, "标准差")
    if sigma <= 0:
        raise ValueError("标准差必须大于 0")
    return NORMAL.cdf(mu / sigma)


def quantile(samples: Sequence[float], q: float) -> float:
    """R-7/NumPy 默认风格的线性插值分位数。"""
    if not samples:
        raise ValueError("分位数样本不能为空")
    level = probability(q)
    values = sorted(_finite_number(value, "样本") for value in samples)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * level
    nearest = round(position)
    if math.isclose(position, nearest, rel_tol=0.0, abs_tol=1e-12):
        return values[nearest]
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def central_interval(samples: Sequence[float], level: float) -> tuple[float, float]:
    coverage = probability(level)
    if coverage <= 0.0:
        raise ValueError("区间覆盖水平必须大于 0")
    tail = (1.0 - coverage) / 2.0
    return quantile(samples, tail), quantile(samples, 1.0 - tail)


def empirical_crps(samples: Sequence[float], observed: float) -> float:
    """经验预测分布 CRPS；确定性预测的结果退化为绝对误差。

    使用 ``E|X-y| - 1/2 E|X-X'|`` 的排序等价式，避免 O(n²)。
    """
    if not samples:
        raise ValueError("经验分布不能为空")
    y = _finite_number(observed, "观测值")
    values = sorted(_finite_number(value, "样本") for value in samples)
    n = len(values)
    first = sum(abs(value - y) for value in values) / n
    half_pairwise = sum((2 * index - n - 1) * value for index, value in enumerate(values, 1)) / (n * n)
    return first - half_pairwise


def exact_block_bootstrap_mean_distribution(
    block_values: Sequence[float],
) -> tuple[ExactBootstrapMean, ...]:
    """精确枚举等样本量周期块 bootstrap 的多重集均值分布。

    对 ``n`` 个独立块抽 ``n`` 次，有序样本虽有 ``n**n`` 个，但仅需枚举
    ``C(2n-1,n)`` 个多重集；``multiplicity`` 保留每个多重集在普通有放回
    bootstrap 中的精确权重。该入口不含随机种子，也不追溯改判既有报告。
    """

    if isinstance(block_values, (str, bytes)) or not isinstance(block_values, Sequence):
        raise ValueError("周期块指标必须是非空序列")
    values = tuple(_finite_number(value, "周期块指标") for value in block_values)
    if not values:
        raise ValueError("周期块指标必须是非空序列")
    n = len(values)
    numerator = math.factorial(n)
    distribution: list[ExactBootstrapMean] = []
    for indices in combinations_with_replacement(range(n), n):
        counts = tuple(indices.count(index) for index in range(n))
        denominator = math.prod(math.factorial(count) for count in counts)
        distribution.append(
            ExactBootstrapMean(
                counts=counts,
                mean=math.fsum(value * count for value, count in zip(values, counts, strict=True))
                / n,
                multiplicity=numerator // denominator,
            )
        )
    if sum(item.multiplicity for item in distribution) != n**n:
        raise AssertionError("精确 bootstrap 多重集重数未覆盖全部有序样本")
    return tuple(distribution)


def exact_block_bootstrap_probability_below(
    block_values: Sequence[float], threshold: float = 0.0
) -> float:
    """返回 bootstrap 均值严格小于阈值的精确概率。"""

    cutoff = _finite_number(threshold, "阈值")
    distribution = exact_block_bootstrap_mean_distribution(block_values)
    favorable = sum(item.multiplicity for item in distribution if item.mean < cutoff)
    total = sum(item.multiplicity for item in distribution)
    return favorable / total


def mean(values: Iterable[float]) -> float:
    numbers = [_finite_number(value, "指标") for value in values]
    if not numbers:
        raise ValueError("不能对空序列求均值")
    return sum(numbers) / len(numbers)


def rmse(errors: Iterable[float]) -> float:
    numbers = [_finite_number(value, "误差") for value in errors]
    if not numbers:
        raise ValueError("不能对空序列计算 RMSE")
    return math.sqrt(sum(value * value for value in numbers) / len(numbers))
