"""Senate 当届竞选席共享残差的确定性联合计数分布。

本模块只改变竞选之间的依赖结构。每场竞选的父 M0 均值和总边际标准差
保持不变：训练期残差的周期均值用零均值矩估计得到共享方差，剩余方差归入
局部项。它不是可观测全国环境、B1 或 Senate 100 席控制模型。
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any


NORMAL = NormalDist()
COMPONENT_ID = "SENATE_CONTEST_COUNT_SHARED_RESIDUAL"


class SenateJointValidationError(ValueError):
    """共享尺度、联合分布或离散评分输入违反合同时抛出。"""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SenateJointValidationError(f"{field} 必须是有限数值")
    number = float(value)
    if not math.isfinite(number):
        raise SenateJointValidationError(f"{field} 必须是有限数值")
    return number


def _positive(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise SenateJointValidationError(f"{field} 必须大于 0")
    return number


def _nonnegative(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number < 0.0:
        raise SenateJointValidationError(f"{field} 不得为负")
    return number


def _midterm_cycle(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SenateJointValidationError(f"{field} 必须是整数周期")
    if not 1900 <= value <= 2200:
        raise SenateJointValidationError(f"{field} 必须位于 1900..2200")
    if value % 4 != 2:
        raise SenateJointValidationError(f"{field} 必须是中期周期")
    return value


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise SenateJointValidationError("不能对空序列求均值")
    return math.fsum(sorted(values)) / len(values)


@dataclass(frozen=True)
class SharedResidualCycleSummary:
    """一个训练中期届对共享方差矩估计的贡献。"""

    cycle: int
    residual_mean: float
    residual_mean_square: float
    n_margin: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "n_margin": self.n_margin,
            "residual_mean": self.residual_mean,
            "residual_mean_square": self.residual_mean_square,
        }


@dataclass(frozen=True)
class SharedResidualScale:
    """受父 M0 总边际方差约束的共享/局部尺度分解。"""

    parent_total_sd: float
    shared_sd: float
    local_sd: float
    shared_variance_raw: float
    shared_variance_used: float
    train_cycles: tuple[int, ...]
    n_train_margin: int
    clipped: bool
    cycle_summaries: tuple[SharedResidualCycleSummary, ...]
    component_id: str = COMPONENT_ID

    def __post_init__(self) -> None:
        total = _positive(self.parent_total_sd, "parent_total_sd")
        shared = _nonnegative(self.shared_sd, "shared_sd")
        local = _nonnegative(self.local_sd, "local_sd")
        raw = _nonnegative(self.shared_variance_raw, "shared_variance_raw")
        used = _nonnegative(self.shared_variance_used, "shared_variance_used")
        if not math.isclose(
            shared * shared + local * local,
            total * total,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise SenateJointValidationError(
                "shared_sd² + local_sd² 必须等于 parent_total_sd²"
            )
        if not math.isclose(shared * shared, used, rel_tol=1e-12, abs_tol=1e-12):
            raise SenateJointValidationError("shared_sd² 与 shared_variance_used 不一致")
        expected_used = min(raw, total * total)
        if not math.isclose(used, expected_used, rel_tol=1e-12, abs_tol=1e-12):
            raise SenateJointValidationError("共享方差没有按父总方差约束")
        if self.clipped != (raw > total * total):
            raise SenateJointValidationError("clipped 标记与原始共享方差不一致")
        if tuple(sorted(set(self.train_cycles))) != self.train_cycles:
            raise SenateJointValidationError("train_cycles 必须严格唯一升序")
        if not 2 <= len(self.train_cycles) <= 9:
            raise SenateJointValidationError("共享尺度的有效训练周期数 K 必须位于 2..9")
        for index, cycle in enumerate(self.train_cycles):
            _midterm_cycle(cycle, f"train_cycles[{index}]")
        if (
            isinstance(self.n_train_margin, bool)
            or not isinstance(self.n_train_margin, int)
            or self.n_train_margin <= 0
        ):
            raise SenateJointValidationError("n_train_margin 必须为正整数")
        if len(self.cycle_summaries) != len(self.train_cycles):
            raise SenateJointValidationError("cycle_summaries 与 train_cycles 数量不一致")
        if tuple(item.cycle for item in self.cycle_summaries) != self.train_cycles:
            raise SenateJointValidationError("cycle_summaries 周期必须精确等于 train_cycles")
        for index, item in enumerate(self.cycle_summaries):
            _midterm_cycle(item.cycle, f"cycle_summaries[{index}].cycle")
            residual_mean = _finite(
                item.residual_mean, f"cycle_summaries[{index}].residual_mean"
            )
            residual_square = _nonnegative(
                item.residual_mean_square,
                f"cycle_summaries[{index}].residual_mean_square",
            )
            if not math.isclose(
                residual_square,
                residual_mean * residual_mean,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise SenateJointValidationError(
                    "cycle summary 的 residual_mean_square 必须等于 residual_mean²"
                )
            if (
                isinstance(item.n_margin, bool)
                or not isinstance(item.n_margin, int)
                or item.n_margin <= 0
            ):
                raise SenateJointValidationError("cycle summary 的 n_margin 必须为正整数")
        if self.n_train_margin != sum(item.n_margin for item in self.cycle_summaries):
            raise SenateJointValidationError(
                "n_train_margin 必须等于各 cycle summary 分母之和"
            )
        summary_raw = _mean(
            [item.residual_mean_square for item in self.cycle_summaries]
        )
        if not math.isclose(raw, summary_raw, rel_tol=1e-12, abs_tol=1e-12):
            raise SenateJointValidationError(
                "shared_variance_raw 必须等于周期等权 residual_mean_square"
            )

    @property
    def marginal_variance(self) -> float:
        """相关结构下仍与父 M0 完全相同的单席边际方差。"""

        return self.parent_total_sd * self.parent_total_sd

    @property
    def variance_identity_error(self) -> float:
        return (
            self.shared_sd * self.shared_sd
            + self.local_sd * self.local_sd
            - self.marginal_variance
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "clipped": self.clipped,
            "component_id": self.component_id,
            "cycle_summaries": [item.as_dict() for item in self.cycle_summaries],
            "estimator": "zero_mean_cycle_equal_mean_residual_square",
            "local_sd": self.local_sd,
            "marginal_variance": self.marginal_variance,
            "n_train_cycles": len(self.train_cycles),
            "n_train_margin": self.n_train_margin,
            "parent_total_sd": self.parent_total_sd,
            "shared_mean": 0.0,
            "shared_sd": self.shared_sd,
            "shared_variance_raw": self.shared_variance_raw,
            "shared_variance_used": self.shared_variance_used,
            "train_cycles": list(self.train_cycles),
            "variance_identity_error": self.variance_identity_error,
        }


def fit_shared_residual_scale(
    train_rows: Sequence[Mapping[str, Any]],
    parent_total_sd: float,
    test_cycle: int,
    min_train_cycles: int = 2,
) -> SharedResidualScale:
    """拟合周期等权、零均值的共享残差矩尺度。

    ``train_rows`` 是预测已经冻结后形成的训练配对行，至少包含
    ``race_id/cycle/office/two_party_margin/predicted_margin``。测试结果不应被
    传入本函数；``test_cycle`` 硬闸保证每个来源周期都严格更早。
    """

    total_sd = _positive(parent_total_sd, "parent_total_sd")
    held_out_cycle = _midterm_cycle(test_cycle, "test_cycle")
    if isinstance(min_train_cycles, bool) or not isinstance(min_train_cycles, int):
        raise SenateJointValidationError("min_train_cycles 必须是至少 2 的整数")
    if min_train_cycles < 2:
        raise SenateJointValidationError("min_train_cycles 必须至少为 2")
    if not train_rows:
        raise SenateJointValidationError("共享残差尺度需要非空训练配对行")

    residuals_by_cycle: dict[int, list[float]] = {}
    seen_races: set[str] = set()
    for index, row in enumerate(train_rows):
        if not isinstance(row, Mapping):
            raise SenateJointValidationError(f"train_rows[{index}] 必须是对象")
        missing = [
            field
            for field in ("race_id", "cycle", "office", "two_party_margin", "predicted_margin")
            if field not in row
        ]
        if missing:
            raise SenateJointValidationError(
                f"train_rows[{index}] 缺少字段：{', '.join(missing)}"
            )
        if row["office"] != "SENATE":
            raise SenateJointValidationError("共享 Senate 残差训练不得混入 House")
        cycle = _midterm_cycle(row["cycle"], f"train_rows[{index}].cycle")
        if cycle >= held_out_cycle:
            raise SenateJointValidationError(
                f"训练周期 {cycle} 不严格早于测试周期 {held_out_cycle}"
            )
        race_id = row["race_id"]
        if not isinstance(race_id, str) or not race_id.startswith(f"SENATE-{cycle}-"):
            raise SenateJointValidationError(
                f"train_rows[{index}].race_id 必须编码 SENATE 与 cycle"
            )
        if race_id in seen_races:
            raise SenateJointValidationError(f"训练配对行含重复 race_id：{race_id}")
        seen_races.add(race_id)
        residuals_by_cycle.setdefault(cycle, [])

        margin = row["two_party_margin"]
        if margin is None:
            continue
        observed = _finite(margin, f"train_rows[{index}].two_party_margin")
        predicted = _finite(
            row["predicted_margin"], f"train_rows[{index}].predicted_margin"
        )
        if not -100.0 <= observed <= 100.0 or not -100.0 <= predicted <= 100.0:
            raise SenateJointValidationError("竞选边际必须位于 [-100,100]")
        if "margin_sd" not in row:
            raise SenateJointValidationError(
                f"train_rows[{index}] 缺少声明为父尺度不变量的 margin_sd"
            )
        row_sd = _positive(row["margin_sd"], f"train_rows[{index}].margin_sd")
        if row_sd != total_sd:
            raise SenateJointValidationError(
                "训练父预测 margin_sd 必须逐字等于 parent_total_sd"
            )
        residuals_by_cycle[cycle].append(observed - predicted)

    train_cycles = tuple(sorted(residuals_by_cycle))
    if len(train_cycles) < min_train_cycles:
        raise SenateJointValidationError(
            f"共享尺度至少需要 {min_train_cycles} 个独立训练中期周期"
        )
    summaries: list[SharedResidualCycleSummary] = []
    for cycle in train_cycles:
        residuals = residuals_by_cycle[cycle]
        if not residuals:
            raise SenateJointValidationError(f"训练周期 {cycle} 没有可用残差")
        residual_mean = _mean(residuals)
        summaries.append(
            SharedResidualCycleSummary(
                cycle=cycle,
                residual_mean=residual_mean,
                residual_mean_square=residual_mean * residual_mean,
                n_margin=len(residuals),
            )
        )

    raw_variance = _mean([item.residual_mean_square for item in summaries])
    total_variance = total_sd * total_sd
    used_variance = min(raw_variance, total_variance)
    local_variance = max(0.0, total_variance - used_variance)
    result = SharedResidualScale(
        parent_total_sd=total_sd,
        shared_sd=math.sqrt(used_variance),
        local_sd=math.sqrt(local_variance),
        shared_variance_raw=raw_variance,
        shared_variance_used=used_variance,
        train_cycles=train_cycles,
        n_train_margin=sum(item.n_margin for item in summaries),
        clipped=raw_variance > total_variance,
        cycle_summaries=tuple(summaries),
    )
    # 再次以独立断言锁住核心职责，避免未来 dataclass 改动绕开守门。
    if not math.isclose(
        result.shared_sd**2 + result.local_sd**2,
        result.parent_total_sd**2,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise SenateJointValidationError("父 M0 总边际方差守门失败")
    return result


def validate_pmf(
    probabilities: Sequence[float], *, tolerance: float = 1e-10
) -> tuple[float, ...]:
    """验证有限、非负、归一的 0..n 离散 PMF，不静默修补输入。"""

    if isinstance(probabilities, (str, bytes)) or not isinstance(probabilities, Sequence):
        raise SenateJointValidationError("PMF 必须是概率序列")
    if not probabilities:
        raise SenateJointValidationError("PMF 不能为空")
    tol = _positive(tolerance, "tolerance")
    values: list[float] = []
    for index, raw in enumerate(probabilities):
        value = _finite(raw, f"pmf[{index}]")
        if not 0.0 <= value <= 1.0:
            raise SenateJointValidationError(f"pmf[{index}] 必须位于 [0,1]")
        values.append(value)
    total = math.fsum(values)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=tol):
        raise SenateJointValidationError(f"PMF 未归一化：sum={total}")
    return tuple(values)


def poisson_binomial_pmf(probabilities: Sequence[float]) -> tuple[float, ...]:
    """用动态规划计算独立、非同概率 Bernoulli 和的完整 PMF。"""

    if isinstance(probabilities, (str, bytes)) or not isinstance(probabilities, Sequence):
        raise SenateJointValidationError("竞选概率必须是序列")
    if not probabilities:
        raise SenateJointValidationError("至少需要一场竞选")
    values = []
    for index, raw in enumerate(probabilities):
        probability = _finite(raw, f"probabilities[{index}]")
        if not 0.0 <= probability <= 1.0:
            raise SenateJointValidationError(
                f"probabilities[{index}] 必须位于 [0,1]"
            )
        values.append(probability)
    # 排序使等价竞选集合在输入顺序变化后仍产生相同字节。
    distribution = [1.0]
    for probability in sorted(values):
        updated = [0.0] * (len(distribution) + 1)
        for count, mass in enumerate(distribution):
            updated[count] += mass * (1.0 - probability)
            updated[count + 1] += mass * probability
        distribution = updated
    total = math.fsum(distribution)
    if not math.isfinite(total) or total <= 0.0:
        raise SenateJointValidationError("Poisson-binomial PMF 无法归一化")
    normalized = tuple(mass / total for mass in distribution)
    return validate_pmf(normalized)


def _conditional_probability(mean: float, intercept: float, local_sd: float) -> float:
    if local_sd > 0.0:
        return NORMAL.cdf((mean + intercept) / local_sd)
    value = mean + intercept
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return 0.0
    return 0.5


def normal_random_intercept_count_pmf(
    mean_margins: Sequence[float],
    parent_total_sd: float,
    shared_sd: float,
    *,
    grid_size: int = 2048,
) -> tuple[float, ...]:
    """确定性正态分位网格上的共享随机截距计数 PMF。

    每个竞选的生成边际为 ``mean + U + epsilon``，其中
    ``U~N(0,shared_sd²)``，局部尺度由父总方差扣除。``shared_sd=0`` 时
    精确调用独立 Poisson-binomial，而不是做数值近似。
    """

    if isinstance(mean_margins, (str, bytes)) or not isinstance(mean_margins, Sequence):
        raise SenateJointValidationError("mean_margins 必须是序列")
    if not mean_margins:
        raise SenateJointValidationError("至少需要一场竞选")
    means = sorted(_finite(value, f"mean_margins[{index}]") for index, value in enumerate(mean_margins))
    total_sd = _positive(parent_total_sd, "parent_total_sd")
    tau = _nonnegative(shared_sd, "shared_sd")
    tolerance = 1e-12 * max(1.0, total_sd)
    if tau > total_sd + tolerance:
        raise SenateJointValidationError("shared_sd 不得超过 parent_total_sd")
    tau = min(tau, total_sd)
    if isinstance(grid_size, bool) or not isinstance(grid_size, int) or grid_size < 2:
        raise SenateJointValidationError("grid_size 必须是至少 2 的整数")

    parent_probabilities = [NORMAL.cdf(mean / total_sd) for mean in means]
    if tau == 0.0:
        return poisson_binomial_pmf(parent_probabilities)

    local_variance = max(0.0, total_sd * total_sd - tau * tau)
    local_sd = math.sqrt(local_variance)
    accumulated = [0.0] * (len(means) + 1)
    for index in range(grid_size):
        level = (index + 0.5) / grid_size
        intercept = tau * NORMAL.inv_cdf(level)
        conditional = [
            _conditional_probability(mean, intercept, local_sd) for mean in means
        ]
        conditional_pmf = poisson_binomial_pmf(conditional)
        for count, mass in enumerate(conditional_pmf):
            accumulated[count] += mass
    distribution = tuple(mass / grid_size for mass in accumulated)
    total = math.fsum(distribution)
    normalized = tuple(mass / total for mass in distribution)
    return validate_pmf(normalized, tolerance=1e-9)


def discrete_crps(probabilities: Sequence[float], observed_count: int) -> float:
    """0..n 计数 PMF 的离散 CRPS（越小越好）。"""

    pmf = validate_pmf(probabilities)
    if isinstance(observed_count, bool) or not isinstance(observed_count, int):
        raise SenateJointValidationError("observed_count 必须是整数")
    if not 0 <= observed_count < len(pmf):
        raise SenateJointValidationError("observed_count 超出 PMF 支持集")
    cumulative = 0.0
    terms = []
    for count, mass in enumerate(pmf):
        cumulative += mass
        observed_cdf = 1.0 if count >= observed_count else 0.0
        terms.append((cumulative - observed_cdf) ** 2)
    return math.fsum(terms)


def discrete_log_score(probabilities: Sequence[float], observed_count: int) -> float:
    """实际计数的对数预测质量（越大越好，零质量返回负无穷）。"""

    pmf = validate_pmf(probabilities)
    if isinstance(observed_count, bool) or not isinstance(observed_count, int):
        raise SenateJointValidationError("observed_count 必须是整数")
    if not 0 <= observed_count < len(pmf):
        raise SenateJointValidationError("observed_count 超出 PMF 支持集")
    mass = pmf[observed_count]
    return math.log(mass) if mass > 0.0 else -math.inf


def discrete_quantile(probabilities: Sequence[float], level: float) -> int:
    """返回离散分布左连续分位数。"""

    pmf = validate_pmf(probabilities)
    q = _finite(level, "level")
    if not 0.0 <= q <= 1.0:
        raise SenateJointValidationError("level 必须位于 [0,1]")
    cumulative = 0.0
    for count, mass in enumerate(pmf):
        cumulative += mass
        if cumulative >= q:
            return count
    return len(pmf) - 1


def central_interval(
    probabilities: Sequence[float], level: float
) -> tuple[int, int]:
    """计数 PMF 的等尾中心区间。"""

    coverage = _finite(level, "level")
    if not 0.0 < coverage <= 1.0:
        raise SenateJointValidationError("level 必须位于 (0,1]")
    tail = (1.0 - coverage) / 2.0
    return (
        discrete_quantile(probabilities, tail),
        discrete_quantile(probabilities, 1.0 - tail),
    )


def pmf_mean(probabilities: Sequence[float]) -> float:
    pmf = validate_pmf(probabilities)
    return math.fsum(count * mass for count, mass in enumerate(pmf))


def pmf_variance(probabilities: Sequence[float]) -> float:
    pmf = validate_pmf(probabilities)
    expectation = pmf_mean(pmf)
    return math.fsum(
        (count - expectation) ** 2 * mass for count, mass in enumerate(pmf)
    )


def average_pairwise_covariance_from_count_pmf(
    probabilities: Sequence[float], marginal_probabilities: Sequence[float]
) -> float:
    """由总数方差扣除单席方差，诊断平均竞选对协方差。"""

    pmf = validate_pmf(probabilities)
    if len(pmf) != len(marginal_probabilities) + 1:
        raise SenateJointValidationError("PMF 支持集与单席概率数量不一致")
    if len(marginal_probabilities) < 2:
        raise SenateJointValidationError("平均协方差至少需要两场竞选")
    values = []
    for index, raw in enumerate(marginal_probabilities):
        value = _finite(raw, f"marginal_probabilities[{index}]")
        if not 0.0 <= value <= 1.0:
            raise SenateJointValidationError("单席概率必须位于 [0,1]")
        values.append(value)
    independent_variance = math.fsum(value * (1.0 - value) for value in values)
    n = len(values)
    return (pmf_variance(pmf) - independent_variance) / (n * (n - 1))


def pmf_bytes(probabilities: Sequence[float]) -> bytes:
    """稳定序列化一个已验证 PMF。"""

    pmf = validate_pmf(probabilities, tolerance=1e-9)
    return json.dumps(
        list(pmf),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def scale_bytes(scale: SharedResidualScale) -> bytes:
    """稳定序列化训练尺度及其有效周期数。"""

    if not isinstance(scale, SharedResidualScale):
        raise SenateJointValidationError("scale 必须是 SharedResidualScale")
    return json.dumps(
        scale.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
