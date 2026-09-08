"""联合席位模拟：每次抽样共享全国误差，再抽竞选局部误差。"""

from __future__ import annotations

import hashlib
import random
from typing import Sequence


def _race_seed(seed: int, race_id: str) -> int:
    """从主种子与竞选身份派生稳定子流；不使用进程随机化的 ``hash()``。"""

    payload = f"midterms-per-race-v1\0{seed}\0{race_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def simulate_race_outcomes(
    mean_margins: Sequence[float],
    national_sd: float,
    race_sd: float,
    draws: int,
    seed: int,
    *,
    correlated: bool = True,
    per_race_substreams: bool = False,
    race_ids: Sequence[str] | None = None,
) -> list[list[int]]:
    if not mean_margins:
        raise ValueError("至少需要一场竞选")
    if national_sd < 0 or race_sd < 0:
        raise ValueError("误差标准差不能为负")
    if draws < 1:
        raise ValueError("抽样次数至少为 1")
    if per_race_substreams:
        if race_ids is None or len(race_ids) != len(mean_margins):
            raise ValueError("启用 per-race 子流时 race_ids 必须与竞选边际一一对应")
        if any(not isinstance(race_id, str) or not race_id for race_id in race_ids):
            raise ValueError("race_ids 必须是非空字符串")
        if len(set(race_ids)) != len(race_ids):
            raise ValueError("race_ids 不得重复")
    elif race_ids is not None:
        raise ValueError("race_ids 仅在 per_race_substreams=true 时使用")

    # 默认分支故意完整保留既有单 RNG 调用次序，冻结输出字节不变。
    if not per_race_substreams:
        rng = random.Random(seed)
        outcomes: list[list[int]] = []
        for _ in range(draws):
            shared = rng.gauss(0.0, national_sd) if correlated else 0.0
            row = []
            for margin in mean_margins:
                # 独立版本保持相同单席边际方差，只移除跨竞选协方差。
                if correlated:
                    noise = shared + rng.gauss(0.0, race_sd)
                else:
                    total_sd = (national_sd * national_sd + race_sd * race_sd) ** 0.5
                    noise = rng.gauss(0.0, total_sd)
                row.append(int(float(margin) + noise > 0.0))
            outcomes.append(row)
        return outcomes

    assert race_ids is not None  # 已由上方合同验证；帮助类型检查器收窄。
    shared_rng = random.Random(_race_seed(seed, "__shared__"))
    race_rngs = [random.Random(_race_seed(seed, race_id)) for race_id in race_ids]
    total_sd = (national_sd * national_sd + race_sd * race_sd) ** 0.5
    outcomes = []
    for _ in range(draws):
        shared = shared_rng.gauss(0.0, national_sd) if correlated else 0.0
        row = []
        for margin, race_rng in zip(mean_margins, race_rngs, strict=True):
            local = race_rng.gauss(0.0, race_sd if correlated else total_sd)
            row.append(int(float(margin) + shared + local > 0.0))
        outcomes.append(row)
    return outcomes


def simulate_seat_counts(
    mean_margins: Sequence[float],
    national_sd: float,
    race_sd: float,
    draws: int,
    seed: int,
    *,
    democratic_holdovers: int = 0,
    correlated: bool = True,
    per_race_substreams: bool = False,
    race_ids: Sequence[str] | None = None,
) -> list[int]:
    outcomes = simulate_race_outcomes(
        mean_margins,
        national_sd,
        race_sd,
        draws,
        seed,
        correlated=correlated,
        per_race_substreams=per_race_substreams,
        race_ids=race_ids,
    )
    return [democratic_holdovers + sum(row) for row in outcomes]


def average_pair_covariance(outcomes: Sequence[Sequence[int]]) -> float:
    """诊断抽样中跨竞选同向移动；不是现实效度指标。"""
    if len(outcomes) < 2 or len(outcomes[0]) < 2:
        raise ValueError("协方差诊断至少需要两次抽样和两场竞选")
    width = len(outcomes[0])
    if any(len(row) != width for row in outcomes):
        raise ValueError("结果矩阵宽度不一致")
    means = [sum(row[index] for row in outcomes) / len(outcomes) for index in range(width)]
    covariances = []
    for left in range(width):
        for right in range(left + 1, width):
            covariance = sum(
                (row[left] - means[left]) * (row[right] - means[right]) for row in outcomes
            ) / len(outcomes)
            covariances.append(covariance)
    return sum(covariances) / len(covariances)
