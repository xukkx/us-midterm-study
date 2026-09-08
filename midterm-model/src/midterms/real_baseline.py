"""只读过去结果的 R0 端到端哨兵基线。

R0 不读取地图、民调、当届实际全国摆动或测试结果。它只在一个院别内，以
严格早于测试周期的最终结果估计周期等权的总体均值、民主党胜率和误差尺度。
因此它只能证明真实账本与评分链路能跑通，不能被解释为可部署模型。
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .lineage import SourceLineage, build_cycle_lineage


class R0ValidationError(ValueError):
    """R0 输入不足、混轨或可能泄漏时抛出。"""


def _cycle(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise R0ValidationError(f"{field} 必须是整数周期")
    if not 1900 <= value <= 2200:
        raise R0ValidationError(f"{field} 必须位于 1900..2200")
    return value


def _office(value: Any, field: str = "office") -> str:
    if not isinstance(value, str):
        raise R0ValidationError(f"{field} 必须是 HOUSE 或 SENATE")
    normalized = value.upper()
    if normalized not in {"HOUSE", "SENATE"}:
        raise R0ValidationError(f"{field} 必须是 HOUSE 或 SENATE")
    return normalized


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise R0ValidationError(f"{field} 必须是有限数值或 null")
    number = float(value)
    if not math.isfinite(number):
        raise R0ValidationError(f"{field} 必须是有限数值或 null")
    return number


def _mean(values: Sequence[float]) -> float:
    return math.fsum(sorted(values)) / len(values)


def _clean_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


@dataclass(frozen=True)
class R0CycleSummary:
    cycle: int
    mean_margin: float
    democratic_win_rate: float
    n_margin: int
    n_winner: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "democratic_win_rate": self.democratic_win_rate,
            "mean_margin": self.mean_margin,
            "n_margin": self.n_margin,
            "n_winner": self.n_winner,
        }


@dataclass(frozen=True)
class R0Model:
    """一折 R0 参数；所有字段都可由训练行独立复算。"""

    office: str
    test_cycle: int
    mean_margin: float
    margin_sd: float
    democratic_win_probability: float
    train_cycles: tuple[int, ...]
    n_train_margin: int
    n_train_winner: int
    cycle_summaries: tuple[R0CycleSummary, ...]
    lineage: tuple[SourceLineage, ...]
    model_id: str = "R0_past_only_empirical"

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle_summaries": [item.as_dict() for item in self.cycle_summaries],
            "democratic_win_probability": self.democratic_win_probability,
            "lineage": [item.as_dict() for item in self.lineage],
            "margin_sd": self.margin_sd,
            "mean_margin": self.mean_margin,
            "model_id": self.model_id,
            "n_train_margin": self.n_train_margin,
            "n_train_winner": self.n_train_winner,
            "office": self.office,
            "test_cycle": self.test_cycle,
            "train_cycles": list(self.train_cycles),
        }


def _margin(row: Mapping[str, Any], index: int) -> float | None:
    """读取规范化目标；兼容第 0 层夹具的嵌套结果结构。"""

    if "two_party_margin" in row:
        value = row["two_party_margin"]
    else:
        actual = row.get("actual_result")
        value = actual.get("democratic_margin") if isinstance(actual, Mapping) else None
    if value is None:
        return None
    return _finite(value, f"train_rows[{index}].two_party_margin")


def _winner(row: Mapping[str, Any], index: int) -> str:
    value = row.get("winner_group")
    if value is None:
        winner = row.get("winner")
        if isinstance(winner, Mapping):
            value = winner.get("canonical_party")
    if value is None:
        actual = row.get("actual_result")
        if isinstance(actual, Mapping) and isinstance(actual.get("democratic_win"), bool):
            value = "D" if actual["democratic_win"] else "R"
    aliases = {
        "D": "D",
        "DEMOCRAT": "D",
        "DEMOCRATIC": "D",
        "R": "R",
        "REPUBLICAN": "R",
        "OTHER": "OTHER",
        # ingest 仅在唯一赢家无法可靠归入 D/R 时保留这两个原始类别；
        # 对 R0 的两党胜率分母而言，它们都属于明确排除的 OTHER。
        "UNKNOWN": "OTHER",
        "CONFLICT": "OTHER",
    }
    normalized = aliases.get(value.upper()) if isinstance(value, str) else None
    if normalized is None:
        raise R0ValidationError(
            f"train_rows[{index}] 的赢家党派必须可确定归为 D、R 或 OTHER"
        )
    return normalized


def fit_r0(
    train_rows: Sequence[Mapping[str, Any]],
    test_cycle: int,
    office: str | None = None,
    margin_sd_floor: float = 0.25,
) -> R0Model:
    """在严格过去的训练周期上拟合周期等权 R0。

    均值与胜率先在每个训练周期内计算，再让每个周期各占相同权重。误差尺度
    是各周期内相对总体 R0 均值的均方误差之周期等权平方根，因而同时保留
    周期间和竞选间变化。任一周期没有可用两党边际或 D/R 赢家时均失败关闭。
    """

    target_cycle = _cycle(test_cycle, "test_cycle")
    if isinstance(margin_sd_floor, bool) or not isinstance(
        margin_sd_floor, (int, float)
    ):
        raise R0ValidationError("margin_sd_floor 必须是正有限数")
    floor = float(margin_sd_floor)
    if not math.isfinite(floor) or floor <= 0.0:
        raise R0ValidationError("margin_sd_floor 必须是正有限数")
    if not train_rows:
        raise R0ValidationError("R0 需要非空训练集")

    inferred_offices: set[str] = set()
    grouped_margins: dict[int, list[float]] = {}
    grouped_winners: dict[int, list[str]] = {}
    for index, row in enumerate(train_rows):
        if not isinstance(row, Mapping):
            raise R0ValidationError(f"train_rows[{index}] 必须是对象")
        if "cycle" not in row or "office" not in row:
            raise R0ValidationError(
                f"train_rows[{index}] 必须包含 cycle 与 office"
            )
        row_cycle = _cycle(row["cycle"], f"train_rows[{index}].cycle")
        if row_cycle >= target_cycle:
            raise R0ValidationError(
                "过去信息泄漏："
                f"训练周期 {row_cycle} 不早于测试周期 {target_cycle}"
            )
        row_office = _office(row["office"], f"train_rows[{index}].office")
        inferred_offices.add(row_office)
        margin = _margin(row, index)
        if margin is not None:
            grouped_margins.setdefault(row_cycle, []).append(margin)
        else:
            grouped_margins.setdefault(row_cycle, [])
        grouped_winners.setdefault(row_cycle, []).append(_winner(row, index))

    if len(inferred_offices) != 1:
        raise R0ValidationError("House 与 Senate 必须分轨拟合 R0")
    inferred_office = next(iter(inferred_offices))
    requested_office = _office(office) if office is not None else inferred_office
    if requested_office != inferred_office:
        raise R0ValidationError(
            f"训练院别 {inferred_office} 与请求院别 {requested_office} 不一致"
        )

    train_cycles = tuple(sorted(grouped_winners))
    summaries: list[R0CycleSummary] = []
    for cycle in train_cycles:
        margins = grouped_margins[cycle]
        if not margins:
            raise R0ValidationError(f"训练周期 {cycle} 没有可用 two_party_margin")
        partisan_winners = [item for item in grouped_winners[cycle] if item in {"D", "R"}]
        if not partisan_winners:
            raise R0ValidationError(f"训练周期 {cycle} 没有可用于胜率的 D/R 赢家")
        summaries.append(
            R0CycleSummary(
                cycle=cycle,
                mean_margin=_clean_zero(_mean(margins)),
                democratic_win_rate=partisan_winners.count("D")
                / len(partisan_winners),
                n_margin=len(margins),
                n_winner=len(partisan_winners),
            )
        )

    if len(summaries) < 2:
        raise R0ValidationError("R0 至少需要两个独立训练周期")
    mean_margin = _clean_zero(_mean([item.mean_margin for item in summaries]))
    win_probability = _mean([item.democratic_win_rate for item in summaries])
    cycle_mse = []
    for summary in summaries:
        margins = grouped_margins[summary.cycle]
        cycle_mse.append(_mean([(value - mean_margin) ** 2 for value in margins]))
    margin_sd = max(floor, math.sqrt(_mean(cycle_mse)))

    lineage = build_cycle_lineage(
        train_rows,
        test_cycle=target_cycle,
        office=inferred_office,
    )
    return R0Model(
        office=inferred_office,
        test_cycle=target_cycle,
        mean_margin=mean_margin,
        margin_sd=margin_sd,
        democratic_win_probability=win_probability,
        train_cycles=train_cycles,
        n_train_margin=sum(item.n_margin for item in summaries),
        n_train_winner=sum(item.n_winner for item in summaries),
        cycle_summaries=tuple(summaries),
        lineage=lineage,
    )


def predict_r0(
    model: R0Model, test_rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], ...]:
    """为完整测试周期生成预测，只读取三个身份字段。

    输出不复制 ``actual_result``、``two_party_margin``、``winner_group`` 或任何
    feature/diagnostic 字段。排序键也只使用竞选身份，因此改写测试结果或当届
    realized national swing 不会改变预测字节。
    """

    if not isinstance(model, R0Model):
        raise R0ValidationError("model 必须是 R0Model")
    if not test_rows:
        raise R0ValidationError("测试周期不能为空")
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(test_rows):
        if not isinstance(row, Mapping):
            raise R0ValidationError(f"test_rows[{index}] 必须是对象")
        # 故意逐键读取：这里不能把测试行整体复制进预测产物。
        try:
            race_id = row["race_id"]
            raw_cycle = row["cycle"]
            raw_office = row["office"]
        except KeyError as error:
            raise R0ValidationError(
                f"test_rows[{index}] 缺少身份字段 {error.args[0]}"
            ) from error
        if not isinstance(race_id, str) or not race_id.strip():
            raise R0ValidationError(f"test_rows[{index}].race_id 必须是非空字符串")
        cycle = _cycle(raw_cycle, f"test_rows[{index}].cycle")
        office = _office(raw_office, f"test_rows[{index}].office")
        if cycle != model.test_cycle:
            raise R0ValidationError("一个预测批次只能包含模型指定的完整测试周期")
        if office != model.office:
            raise R0ValidationError("House 与 Senate 必须分轨预测 R0")
        if race_id in seen:
            raise R0ValidationError(f"测试周期含重复 race_id：{race_id}")
        seen.add(race_id)
        predictions.append(
            {
                "cycle": cycle,
                "democratic_win_probability": model.democratic_win_probability,
                "margin_sd": model.margin_sd,
                "office": office,
                "predicted_margin": model.mean_margin,
                "race_id": race_id,
            }
        )
    return tuple(sorted(predictions, key=lambda item: item["race_id"]))


def prediction_bytes(predictions: Sequence[Mapping[str, Any]]) -> bytes:
    """把预测规范化成字节级稳定 JSON；拒绝非有限数与重复身份。"""

    if not predictions:
        raise R0ValidationError("预测不能为空")
    canonical: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    required = {
        "cycle",
        "democratic_win_probability",
        "margin_sd",
        "office",
        "predicted_margin",
        "race_id",
    }
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, Mapping) or set(prediction) != required:
            raise R0ValidationError(
                f"predictions[{index}] 必须且只能包含规范化预测字段"
            )
        race_id = prediction["race_id"]
        if not isinstance(race_id, str) or not race_id.strip():
            raise R0ValidationError(f"predictions[{index}].race_id 必须是非空字符串")
        office = _office(prediction["office"], f"predictions[{index}].office")
        cycle = _cycle(prediction["cycle"], f"predictions[{index}].cycle")
        key = (office, cycle, race_id)
        if key in seen:
            raise R0ValidationError(f"预测含重复身份：{office}/{cycle}/{race_id}")
        seen.add(key)
        canonical.append(
            {
                "cycle": cycle,
                "democratic_win_probability": _finite(
                    prediction["democratic_win_probability"],
                    f"predictions[{index}].democratic_win_probability",
                ),
                "margin_sd": _finite(
                    prediction["margin_sd"], f"predictions[{index}].margin_sd"
                ),
                "office": office,
                "predicted_margin": _clean_zero(
                    _finite(
                        prediction["predicted_margin"],
                        f"predictions[{index}].predicted_margin",
                    )
                ),
                "race_id": race_id,
            }
        )
    canonical.sort(key=lambda item: (item["office"], item["cycle"], item["race_id"]))
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def model_bytes(model: R0Model) -> bytes:
    """稳定序列化一折训练参数与 lineage。"""

    if not isinstance(model, R0Model):
        raise R0ValidationError("model 必须是 R0Model")
    return json.dumps(
        model.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
