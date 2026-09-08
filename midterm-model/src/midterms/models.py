"""首轮只保留两个透明均值基线及训练窗内估计的误差结构。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev
from typing import Mapping, Sequence


def feature_value(row: Mapping, feature_id: str) -> float:
    feature = row["feature_values"][feature_id]
    value = feature.get("value") if isinstance(feature, Mapping) else feature
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"特征 {feature_id} 不是数值")
    return float(value)


class PartisanBaseline:
    id = "M0_partisan_baseline"
    predictors = ("partisan_baseline_margin",)

    @staticmethod
    def predict_margin(row: Mapping) -> float:
        return feature_value(row, "partisan_baseline_margin")


class UniformNationalSwing:
    id = "B1_uniform_national_swing"
    predictors = ("partisan_baseline_margin", "national_swing")

    @staticmethod
    def predict_margin(row: Mapping) -> float:
        return feature_value(row, "partisan_baseline_margin") + feature_value(row, "national_swing")


@dataclass(frozen=True)
class ErrorStructure:
    national_sd: float
    race_sd: float

    @property
    def marginal_sd(self) -> float:
        return math.hypot(self.national_sd, self.race_sd)


def actual_margin(row: Mapping) -> float:
    result = row["actual_result"]
    value = result["democratic_margin"]
    return float(value)


def fit_error_structure(model, train_rows: Sequence[Mapping], floor: float = 0.25) -> ErrorStructure:
    """只在训练窗内把残差拆成周期共同项与竞选局部项。"""
    if not train_rows:
        raise ValueError("误差结构需要非空训练集")
    grouped: dict[int, list[float]] = {}
    for row in train_rows:
        residual = actual_margin(row) - model.predict_margin(row)
        grouped.setdefault(int(row["cycle"]), []).append(residual)
    cycle_means = {cycle: sum(values) / len(values) for cycle, values in grouped.items()}
    national_sd = pstdev(cycle_means.values()) if len(cycle_means) > 1 else 0.0
    local = [
        actual_margin(row) - model.predict_margin(row) - cycle_means[int(row["cycle"])]
        for row in train_rows
    ]
    race_sd = pstdev(local) if len(local) > 1 else 0.0
    return ErrorStructure(max(floor, national_sd), max(floor, race_sd))

