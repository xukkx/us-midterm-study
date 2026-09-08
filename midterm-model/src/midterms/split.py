"""以完整选举周期为块的扩展窗口验证。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RollingFold:
    test_cycle: int
    train_cycles: tuple[int, ...]
    train: tuple[Mapping, ...]
    test: tuple[Mapping, ...]


def race_cycle_key(row: Mapping) -> tuple[str, int, str]:
    return str(row["race_id"]), int(row["cycle"]), str(row.get("forecast_horizon", ""))


def assert_fold_valid(fold: RollingFold) -> None:
    if not fold.train or not fold.test:
        raise ValueError("训练集和测试集都不能为空")
    if max(int(row["cycle"]) for row in fold.train) >= fold.test_cycle:
        raise ValueError("扩展窗口泄漏：训练周期没有严格早于测试周期")
    if any(int(row["cycle"]) != fold.test_cycle for row in fold.test):
        raise ValueError("一个测试折只能包含一个完整周期")
    overlap = {race_cycle_key(row) for row in fold.train} & {race_cycle_key(row) for row in fold.test}
    if overlap:
        raise ValueError(f"竞选-周期跨越训练/测试：{sorted(overlap)!r}")


def expanding_window_splits(rows: Sequence[Mapping], min_train_cycles: int = 3) -> list[RollingFold]:
    """返回只用过去预测未来的逐届滚动折。

    输入必须已经限定到一个 office 和一个 forecast_horizon；强制分轨能避免
    House、Senate 或不同预测时点被意外混成一个虚假的大样本。
    """
    if min_train_cycles < 1:
        raise ValueError("min_train_cycles 至少为 1")
    if not rows:
        raise ValueError("滚动切分输入不能为空")
    offices = {str(row["office"]) for row in rows}
    horizons = {str(row["forecast_horizon"]) for row in rows}
    if len(offices) != 1:
        raise ValueError("House 与 Senate 必须分轨切分")
    if len(horizons) != 1:
        raise ValueError("不同 forecast_horizon 必须分别评分")
    cycles = sorted({int(row["cycle"]) for row in rows})
    if len(cycles) <= min_train_cycles:
        raise ValueError("独立周期不足，无法建立扩展窗口测试折")
    folds: list[RollingFold] = []
    for index in range(min_train_cycles, len(cycles)):
        test_cycle = cycles[index]
        train_cycles = tuple(cycles[:index])
        train = tuple(row for row in rows if int(row["cycle"]) in train_cycles)
        test = tuple(row for row in rows if int(row["cycle"]) == test_cycle)
        fold = RollingFold(test_cycle, train_cycles, train, test)
        assert_fold_valid(fold)
        folds.append(fold)
    return folds

