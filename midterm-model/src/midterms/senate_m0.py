"""Senate 州党派 M0：上届总统州边际原样入模，只拟合过去残差尺度。

本模块把三个边界写进接口：预测身份与测试结果分离；总统特征拥有独立的
``PredictorLineage``；M0 的竞选均值逐字等于 ``t-2`` 州总统两党边际。
模型不拟合截距、斜率、全国偏移、州效应或概率校准。
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from statistics import NormalDist
from typing import Any


NORMAL = NormalDist()
FEATURE_ID = "partisan_baseline_margin"
TRANSFORM_ID = "prior_presidential_two_party_margin_v1"
MODEL_ID = "M0_SENATE_prior_presidential_state_baseline"
VALID_STATES = frozenset(
    "AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN "
    "MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT "
    "WA WI WV WY".split()
)
_STATE_RE = re.compile(r"^[A-Z]{2}$")


class SenateM0ValidationError(ValueError):
    """M0 数据、lineage、覆盖或分布违反合同时抛出。"""


def _cycle(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SenateM0ValidationError(f"{field} 必须是整数周期")
    if not 1900 <= value <= 2200:
        raise SenateM0ValidationError(f"{field} 必须位于 1900..2200")
    return value


def _midterm_cycle(value: Any, field: str) -> int:
    cycle = _cycle(value, field)
    if cycle % 4 != 2:
        raise SenateM0ValidationError(f"{field} 必须是中期周期（cycle % 4 == 2）")
    return cycle


def _state(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _STATE_RE.fullmatch(value):
        raise SenateM0ValidationError(f"{field} 必须是两位大写州代码")
    if value not in VALID_STATES:
        if value == "DC":
            raise SenateM0ValidationError(f"{field} 的 DC 不得映射为 Senate 竞选州")
        raise SenateM0ValidationError(f"{field} 不是获准的 Senate 州代码：{value}")
    return value


def _finite(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SenateM0ValidationError(f"{field} 必须是有限数值")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise SenateM0ValidationError(
            f"{field} 必须是 [{minimum}, {maximum}] 内的有限数值"
        )
    return number


def _instant(value: Any, field: str) -> datetime:
    """解析 ISO 时刻；日期精度按该日结束后才可用。"""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value + timedelta(days=1), time.min, tzinfo=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise SenateM0ValidationError(f"{field} 不是合法 ISO 日期/时间") from error
        if date_only:
            parsed += timedelta(days=1)
    else:
        raise SenateM0ValidationError(f"{field} 必须是非空 ISO 日期/时间")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise SenateM0ValidationError("不能对空序列求均值")
    return math.fsum(sorted(values)) / len(values)


@dataclass(frozen=True, order=True)
class PredictorLineage:
    """一个州基线的预测来源；与 Senate 结果训练 lineage 分离。"""

    target_cycle: int
    state: str
    presidential_source_cycle: int
    feature_id: str
    transform_id: str
    vintage: str
    available_at: str
    forecast_as_of: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "available_at": self.available_at,
            "feature_id": self.feature_id,
            "forecast_as_of": self.forecast_as_of,
            "presidential_source_cycle": self.presidential_source_cycle,
            "state": self.state,
            "target_cycle": self.target_cycle,
            "transform_id": self.transform_id,
            "vintage": self.vintage,
        }


@dataclass(frozen=True, order=True)
class SenateRaceIdentity:
    """预测器唯一可见的测试竞选字段。"""

    race_id: str
    cycle: int
    office: str
    state: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "office": self.office,
            "race_id": self.race_id,
            "state": self.state,
        }


@dataclass(frozen=True)
class ResidualCycleSummary:
    cycle: int
    residual_mse: float
    n_margin: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "n_margin": self.n_margin,
            "residual_mse": self.residual_mse,
        }


@dataclass(frozen=True)
class SenateM0Model:
    """一折 M0 的训练期尺度；竞选均值在预测时由州基线逐行给出。"""

    test_cycle: int
    margin_sd: float
    train_cycles: tuple[int, ...]
    n_train_margin: int
    residual_cycle_summaries: tuple[ResidualCycleSummary, ...]
    lineage: tuple[PredictorLineage, ...]
    office: str = "SENATE"
    model_id: str = MODEL_ID

    def as_dict(self) -> dict[str, Any]:
        return {
            "lineage": [item.as_dict() for item in self.lineage],
            "margin_mean_formula": "partisan_baseline_margin_exact_no_fitted_offset",
            "margin_sd": self.margin_sd,
            "model_id": self.model_id,
            "n_train_margin": self.n_train_margin,
            "office": self.office,
            "probability_formula": "Phi(partisan_baseline_margin / margin_sd)",
            "residual_cycle_summaries": [
                item.as_dict() for item in self.residual_cycle_summaries
            ],
            "test_cycle": self.test_cycle,
            "train_cycles": list(self.train_cycles),
        }


def _lineage(row: Mapping[str, Any]) -> PredictorLineage:
    return PredictorLineage(
        target_cycle=int(row["target_cycle"]),
        state=str(row["state"]),
        presidential_source_cycle=int(row["presidential_source_cycle"]),
        feature_id=str(row["feature_id"]),
        transform_id=str(row["transform_id"]),
        vintage=str(row["vintage"]),
        available_at=str(row["available_at"]),
        forecast_as_of=str(row["forecast_as_of"]),
    )


def validate_feature_ledger(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """校验总统州基线并返回按 ``target_cycle/state`` 排序的副本。

    该函数不要求小型测试夹具包含全美 50 州；完整折覆盖由拟合和预测接口按
    实际 Senate race identity 严格检查。
    """

    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Iterable):
        raise SenateM0ValidationError("feature ledger 必须是对象序列")
    validated: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise SenateM0ValidationError(f"features[{index}] 必须是对象")
        required = (
            "feature_id",
            "transform_id",
            "office",
            "target_cycle",
            "state",
            "partisan_baseline_margin",
            "presidential_source_cycle",
            "forecast_as_of",
            "available_at",
            "fact_available_at",
            "vintage",
            "archival_reconstruction",
            "strict_original_vintage_available",
        )
        missing = [field for field in required if field not in raw]
        if missing:
            raise SenateM0ValidationError(
                f"features[{index}] 缺少字段：{', '.join(missing)}"
            )
        if raw["feature_id"] != FEATURE_ID:
            raise SenateM0ValidationError(f"features[{index}] feature_id 漂移")
        if raw["transform_id"] != TRANSFORM_ID:
            raise SenateM0ValidationError(f"features[{index}] transform_id 漂移")
        if raw["office"] != "SENATE":
            raise SenateM0ValidationError("州总统基线只能映射到 SENATE，拒绝 House")
        target_cycle = _midterm_cycle(raw["target_cycle"], f"features[{index}].target_cycle")
        state = _state(raw["state"], f"features[{index}].state")
        key = (target_cycle, state)
        if key in seen:
            raise SenateM0ValidationError(
                f"feature ledger 含重复州基线：{target_cycle}/{state}"
            )
        seen.add(key)
        source_cycle = _cycle(
            raw["presidential_source_cycle"],
            f"features[{index}].presidential_source_cycle",
        )
        if source_cycle != target_cycle - 2:
            raise SenateM0ValidationError(
                f"{target_cycle}/{state} 必须使用 t-2 总统来源，实际 {source_cycle}"
            )
        _finite(
            raw["partisan_baseline_margin"],
            f"features[{index}].partisan_baseline_margin",
            minimum=-100.0,
            maximum=100.0,
        )
        forecast_text = raw["forecast_as_of"]
        if not isinstance(forecast_text, str) or not forecast_text.startswith(
            f"{target_cycle}-10-01"
        ):
            raise SenateM0ValidationError(
                f"{target_cycle}/{state} forecast_as_of 必须是目标年 10 月 1 日"
            )
        forecast = _instant(forecast_text, f"features[{index}].forecast_as_of")
        available = _instant(raw["available_at"], f"features[{index}].available_at")
        if available > forecast:
            raise SenateM0ValidationError(
                f"{target_cycle}/{state} available_at 晚于 forecast_as_of"
            )
        if raw["fact_available_at"] != raw["available_at"]:
            raise SenateM0ValidationError(
                f"{target_cycle}/{state} fact_available_at 与 available_at 不一致"
            )
        vintage = raw["vintage"]
        if not isinstance(vintage, str) or not vintage.strip():
            raise SenateM0ValidationError(f"{target_cycle}/{state} vintage 不能为空")
        if raw["archival_reconstruction"] is not True:
            raise SenateM0ValidationError("州基线必须明确 archival_reconstruction=true")
        if raw["strict_original_vintage_available"] is not False:
            raise SenateM0ValidationError(
                "档案镜像不得冒充原始时点 vintage；必须明确为 false"
            )
        validated.append(dict(raw))
    if not validated:
        raise SenateM0ValidationError("feature ledger 不能为空")
    validated.sort(key=lambda row: (int(row["target_cycle"]), str(row["state"])))
    return tuple(validated)


def sanitize_senate_identities(
    rows: Sequence[Mapping[str, Any]], test_cycle: int | None = None
) -> tuple[SenateRaceIdentity, ...]:
    """从测试目标只读取竞选身份，绝不遍历或复制 actual/diagnostic。"""

    if not rows:
        raise SenateM0ValidationError("测试竞选身份不能为空")
    expected = _midterm_cycle(test_cycle, "test_cycle") if test_cycle is not None else None
    identities: list[SenateRaceIdentity] = []
    seen: set[str] = set()
    observed_cycles: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise SenateM0ValidationError(f"test_rows[{index}] 必须是对象")
        try:
            race_id = row["race_id"]
            raw_cycle = row["cycle"]
            office = row["office"]
            raw_state = row["state"]
        except KeyError as error:
            raise SenateM0ValidationError(
                f"test_rows[{index}] 缺少身份字段 {error.args[0]}"
            ) from error
        cycle = _midterm_cycle(raw_cycle, f"test_rows[{index}].cycle")
        state = _state(raw_state, f"test_rows[{index}].state")
        if office != "SENATE":
            raise SenateM0ValidationError("M0_SENATE 身份不得混入 House")
        if not isinstance(race_id, str) or not race_id.startswith(
            f"SENATE-{cycle}-{state}-"
        ):
            raise SenateM0ValidationError(
                f"test_rows[{index}].race_id 必须编码 SENATE/cycle/state"
            )
        if race_id in seen:
            raise SenateM0ValidationError(f"测试折含重复 race_id：{race_id}")
        seen.add(race_id)
        observed_cycles.add(cycle)
        identities.append(SenateRaceIdentity(race_id, cycle, "SENATE", state))
    if len(observed_cycles) != 1:
        raise SenateM0ValidationError("一个预测批次只能包含一个完整 Senate 中期周期")
    actual_cycle = next(iter(observed_cycles))
    if expected is not None and actual_cycle != expected:
        raise SenateM0ValidationError(
            f"身份周期 {actual_cycle} 与 test_cycle={expected} 不一致"
        )
    return tuple(sorted(identities))


def _feature_index(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], dict[tuple[int, str], dict[str, Any]]]:
    validated = validate_feature_ledger(rows)
    return validated, {
        (int(row["target_cycle"]), str(row["state"])): row for row in validated
    }


def _training_margin(row: Mapping[str, Any], index: int) -> float | None:
    value = row.get("two_party_margin")
    if value is None:
        return None
    return _finite(
        value,
        f"train_targets[{index}].two_party_margin",
        minimum=-100.0,
        maximum=100.0,
    )


def fit_senate_m0(
    train_targets: Sequence[Mapping[str, Any]],
    feature_ledger: Iterable[Mapping[str, Any]],
    test_cycle: int,
    margin_sd_floor: float = 0.25,
    min_train_cycles: int = 2,
) -> SenateM0Model:
    """以严格过去中期届的零均值残差拟合周期等权 RMS。"""

    target_cycle = _midterm_cycle(test_cycle, "test_cycle")
    floor = _finite(
        margin_sd_floor,
        "margin_sd_floor",
        minimum=math.nextafter(0.0, 1.0),
        maximum=1000.0,
    )
    if isinstance(min_train_cycles, bool) or not isinstance(min_train_cycles, int):
        raise SenateM0ValidationError("min_train_cycles 必须是至少 2 的整数")
    if min_train_cycles < 2:
        raise SenateM0ValidationError("min_train_cycles 必须至少为 2")
    if not train_targets:
        raise SenateM0ValidationError("M0_SENATE 需要非空训练目标")
    _, feature_by_key = _feature_index(feature_ledger)

    seen_races: set[str] = set()
    residuals_by_cycle: dict[int, list[float]] = {}
    used_feature_keys: set[tuple[int, str]] = set()
    train_cycles_seen: set[int] = set()
    for index, row in enumerate(train_targets):
        if not isinstance(row, Mapping):
            raise SenateM0ValidationError(f"train_targets[{index}] 必须是对象")
        try:
            race_id = row["race_id"]
            raw_cycle = row["cycle"]
            office = row["office"]
            raw_state = row["state"]
        except KeyError as error:
            raise SenateM0ValidationError(
                f"train_targets[{index}] 缺少字段 {error.args[0]}"
            ) from error
        cycle = _midterm_cycle(raw_cycle, f"train_targets[{index}].cycle")
        if cycle >= target_cycle:
            raise SenateM0ValidationError(
                f"训练中期周期 {cycle} 不严格早于测试周期 {target_cycle}"
            )
        if office != "SENATE":
            raise SenateM0ValidationError("M0_SENATE 训练不得混入 House")
        state = _state(raw_state, f"train_targets[{index}].state")
        if not isinstance(race_id, str) or not race_id.startswith(
            f"SENATE-{cycle}-{state}-"
        ):
            raise SenateM0ValidationError(
                f"train_targets[{index}].race_id 必须编码 SENATE/cycle/state"
            )
        if race_id in seen_races:
            raise SenateM0ValidationError(f"训练目标含重复 race_id：{race_id}")
        seen_races.add(race_id)
        train_cycles_seen.add(cycle)
        key = (cycle, state)
        feature = feature_by_key.get(key)
        if feature is None:
            raise SenateM0ValidationError(
                f"训练折缺少州基线，整折关闭：{cycle}/{state}"
            )
        used_feature_keys.add(key)
        residuals_by_cycle.setdefault(cycle, [])
        margin = _training_margin(row, index)
        if margin is not None:
            baseline = float(feature["partisan_baseline_margin"])
            residuals_by_cycle[cycle].append(margin - baseline)

    train_cycles = tuple(sorted(train_cycles_seen))
    if len(train_cycles) < min_train_cycles:
        raise SenateM0ValidationError(
            f"insufficient_calibration_cycles：至少需要 {min_train_cycles} 个过去中期届"
        )
    summaries: list[ResidualCycleSummary] = []
    for cycle in train_cycles:
        residuals = residuals_by_cycle[cycle]
        if not residuals:
            raise SenateM0ValidationError(f"训练周期 {cycle} 没有可用两党边际残差")
        mse = _mean([value * value for value in residuals])
        summaries.append(ResidualCycleSummary(cycle, mse, len(residuals)))
    margin_sd = max(floor, math.sqrt(_mean([item.residual_mse for item in summaries])))
    lineage = tuple(
        sorted(_lineage(feature_by_key[key]) for key in used_feature_keys)
    )
    return SenateM0Model(
        test_cycle=target_cycle,
        margin_sd=margin_sd,
        train_cycles=train_cycles,
        n_train_margin=sum(item.n_margin for item in summaries),
        residual_cycle_summaries=tuple(summaries),
        lineage=lineage,
    )


def predict_senate_m0(
    model: SenateM0Model,
    identities: Sequence[SenateRaceIdentity],
    feature_ledger: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """对完整 Senate 折预测；API 不接受含实际结果的原始测试行。"""

    if not isinstance(model, SenateM0Model):
        raise SenateM0ValidationError("model 必须是 SenateM0Model")
    if not identities:
        raise SenateM0ValidationError("测试竞选身份不能为空")
    _, feature_by_key = _feature_index(feature_ledger)
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, identity in enumerate(identities):
        if not isinstance(identity, SenateRaceIdentity):
            raise SenateM0ValidationError(
                "predict_senate_m0 只接受 sanitize_senate_identities 的输出"
            )
        if identity.office != "SENATE" or identity.cycle != model.test_cycle:
            raise SenateM0ValidationError(
                f"identities[{index}] 院别或周期与模型不一致"
            )
        if identity.race_id in seen:
            raise SenateM0ValidationError(f"预测身份含重复 race_id：{identity.race_id}")
        seen.add(identity.race_id)
        feature = feature_by_key.get((identity.cycle, identity.state))
        if feature is None:
            raise SenateM0ValidationError(
                f"测试折缺少州基线，整折关闭：{identity.cycle}/{identity.state}"
            )
        # 不拟合任何均值参数：该赋值是 M0 最重要的可审计不变量。
        predicted_margin = float(feature["partisan_baseline_margin"])
        probability = NORMAL.cdf(predicted_margin / model.margin_sd)
        predictions.append(
            {
                "cycle": identity.cycle,
                "democratic_win_probability": probability,
                "margin_sd": model.margin_sd,
                "office": "SENATE",
                "predicted_margin": predicted_margin,
                "race_id": identity.race_id,
                "state": identity.state,
            }
        )
    return tuple(sorted(predictions, key=lambda row: row["race_id"]))


_PREDICTION_FIELDS = {
    "cycle",
    "democratic_win_probability",
    "margin_sd",
    "office",
    "predicted_margin",
    "race_id",
    "state",
}


def prediction_bytes(predictions: Sequence[Mapping[str, Any]]) -> bytes:
    """把 M0 预测写成稳定、最小且不含实际结果的 JSON 字节。"""

    if not predictions:
        raise SenateM0ValidationError("预测不能为空")
    canonical: list[dict[str, Any]] = []
    seen: set[str] = set()
    cycles: set[int] = set()
    for index, raw in enumerate(predictions):
        if not isinstance(raw, Mapping) or set(raw) != _PREDICTION_FIELDS:
            raise SenateM0ValidationError(
                f"predictions[{index}] 必须且只能包含规范化 M0 预测字段"
            )
        race_id = raw["race_id"]
        if not isinstance(race_id, str) or not race_id.strip():
            raise SenateM0ValidationError(f"predictions[{index}].race_id 非法")
        if race_id in seen:
            raise SenateM0ValidationError(f"预测含重复 race_id：{race_id}")
        seen.add(race_id)
        cycle = _midterm_cycle(raw["cycle"], f"predictions[{index}].cycle")
        cycles.add(cycle)
        if raw["office"] != "SENATE":
            raise SenateM0ValidationError("M0_SENATE 预测不得混入 House")
        state = _state(raw["state"], f"predictions[{index}].state")
        predicted = _finite(
            raw["predicted_margin"],
            f"predictions[{index}].predicted_margin",
            minimum=-100.0,
            maximum=100.0,
        )
        sigma = _finite(
            raw["margin_sd"],
            f"predictions[{index}].margin_sd",
            minimum=math.nextafter(0.0, 1.0),
            maximum=1000.0,
        )
        probability = _finite(
            raw["democratic_win_probability"],
            f"predictions[{index}].democratic_win_probability",
            minimum=0.0,
            maximum=1.0,
        )
        canonical.append(
            {
                "cycle": cycle,
                "democratic_win_probability": probability,
                "margin_sd": sigma,
                "office": "SENATE",
                "predicted_margin": 0.0 if predicted == 0.0 else predicted,
                "race_id": race_id,
                "state": state,
            }
        )
    if len(cycles) != 1:
        raise SenateM0ValidationError("一个预测字节载荷只能包含一个中期周期")
    canonical.sort(key=lambda row: row["race_id"])
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def model_bytes(model: SenateM0Model) -> bytes:
    """稳定序列化只含训练信息的 M0 参数。"""

    if not isinstance(model, SenateM0Model):
        raise SenateM0ValidationError("model 必须是 SenateM0Model")
    return json.dumps(
        model.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
