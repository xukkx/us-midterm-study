"""竞选快照的数据合同与时间泄漏审计。

本模块只验证“在预测截点上，这一行数据是否可能被模型合法看到”。它不负责
估计模型，也不把合成数据的通过误写成现实效度。公开入口为：

``validate_snapshot(snapshot, feature_registry)``
    验证单条 House 或 Senate 竞选快照。

``audit_panel(rows, feature_registry)``
    验证完整面板，并拦截同一竞选、周期、预测时距的重复快照。

注册表既可传入已经解析的字典，也可传入 JSON 文件路径。标准形态是
``{"features": [{"id": ..., "role": ..., "dtype": ...}]}``。
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


class SnapshotValidationError(ValueError):
    """竞选快照或特征注册表违反数据合同时抛出。"""


_REQUIRED_FIELDS = (
    "race_id",
    "cycle",
    "forecast_horizon",
    "forecast_as_of",
    "office",
    "state",
    "district",
    "map",
    "feature_values",
    "predictors",
    "actual_result",
)
_OUTCOME_ROLES = {"outcome", "target", "result", "label"}
_PREDICTOR_ROLES = {"predictor", "feature", "input"}
_STATE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")


def _fail(message: str) -> None:
    raise SnapshotValidationError(message)


def _load_registry(feature_registry: Any) -> dict[str, dict[str, Any]]:
    """读取并规范化特征注册表，不允许重复或无名条目。"""

    raw = feature_registry
    if isinstance(raw, (str, Path)):
        path = Path(raw)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail(f"无法读取特征注册表 {path}：{error}")

    if isinstance(raw, Mapping) and "features" in raw:
        entries = raw["features"]
    elif isinstance(raw, list):
        entries = raw
    elif isinstance(raw, Mapping):
        # 兼容 {feature_id: spec} 的紧凑写法，便于固定样例自测。
        entries = []
        for feature_id, spec in raw.items():
            if not isinstance(spec, Mapping):
                _fail("特征注册表映射的每个值都必须是对象")
            entries.append({"id": feature_id, **dict(spec)})
    else:
        _fail("特征注册表必须是含 features 的对象、特征数组或 id→定义映射")

    if not isinstance(entries, list) or not entries:
        _fail("特征注册表 features 必须是非空数组")

    definitions: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            _fail(f"特征注册表第 {index + 1} 项必须是对象")
        spec = dict(entry)
        feature_id = spec.get("id", spec.get("name"))
        if not isinstance(feature_id, str) or not feature_id.strip():
            _fail(f"特征注册表第 {index + 1} 项缺少非空 id")
        feature_id = feature_id.strip()
        if feature_id in definitions:
            _fail(f"特征注册表存在重复 id：{feature_id}")
        definitions[feature_id] = spec
    return definitions


def _instant(value: Any, field: str, *, role: str = "available") -> datetime:
    """按字段角色把 ISO 日期/时间统一成 UTC。

    数据可用时刻的仅日期值按下一日 00:00 UTC 才可用；预测截点的仅日期值
    则取当日 00:00 UTC。两类无时区 datetime 都拒绝，避免本机时区或善意方向
    猜测悄悄改变泄漏边界。
    """

    if role not in {"available", "forecast"}:
        _fail(f"{field} 的时刻角色未知：{role}")

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        day = value + timedelta(days=1) if role == "available" else value
        parsed = datetime.combine(day, time.min, tzinfo=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            _fail(f"{field} 不是合法 ISO 8601 日期/时间：{value!r}（{error}）")
        if date_only:
            if role == "available":
                parsed = parsed + timedelta(days=1)
            parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        _fail(f"{field} 必须是非空 ISO 8601 日期/时间")

    if parsed.tzinfo is None:
        _fail(f"{field} 的 datetime 必须显式携带时区")
    return parsed.astimezone(timezone.utc)


def _minimum(spec: Mapping[str, Any]) -> Any:
    if "minimum" in spec:
        return spec["minimum"]
    if "min" in spec:
        return spec["min"]
    bounds = spec.get("allowed_range", spec.get("range"))
    if isinstance(bounds, list) and len(bounds) == 2:
        return bounds[0]
    if isinstance(bounds, Mapping):
        return bounds.get("minimum", bounds.get("min"))
    return None


def _maximum(spec: Mapping[str, Any]) -> Any:
    if "maximum" in spec:
        return spec["maximum"]
    if "max" in spec:
        return spec["max"]
    bounds = spec.get("allowed_range", spec.get("range"))
    if isinstance(bounds, list) and len(bounds) == 2:
        return bounds[1]
    if isinstance(bounds, Mapping):
        return bounds.get("maximum", bounds.get("max"))
    return None


def _check_value(feature_id: str, value: Any, spec: Mapping[str, Any]) -> None:
    """按注册表类型、枚举与上下界检查一个特征值。"""

    dtype = str(spec.get("dtype", spec.get("type", ""))).casefold()
    if dtype in {"number", "numeric", "float"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail(f"特征 {feature_id} 必须是数值")
        if not math.isfinite(float(value)):
            _fail(f"特征 {feature_id} 必须是有限数值")
    elif dtype in {"integer", "int"}:
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(f"特征 {feature_id} 必须是整数")
    elif dtype in {"boolean", "bool"}:
        if not isinstance(value, bool):
            _fail(f"特征 {feature_id} 必须是布尔值")
    elif dtype in {"string", "str", "category", "categorical"}:
        if not isinstance(value, str):
            _fail(f"特征 {feature_id} 必须是字符串")
    else:
        _fail(f"特征 {feature_id} 的 dtype 未知或缺失：{dtype!r}")

    allowed = spec.get("enum", spec.get("allowed_values"))
    if allowed is not None:
        if not isinstance(allowed, list):
            _fail(f"特征 {feature_id} 的 enum/allowed_values 必须是数组")
        if value not in allowed:
            _fail(f"特征 {feature_id} 的值 {value!r} 不在允许集合中")

    minimum = _minimum(spec)
    maximum = _maximum(spec)
    if minimum is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail(f"带 minimum 的特征 {feature_id} 必须是数值")
        if value < minimum:
            _fail(f"特征 {feature_id} 数值越界：{value} < {minimum}")
    if maximum is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail(f"带 maximum 的特征 {feature_id} 必须是数值")
        if value > maximum:
            _fail(f"特征 {feature_id} 数值越界：{value} > {maximum}")


def _vintage_required(spec: Mapping[str, Any]) -> bool:
    marker = spec.get("requires_vintage", spec.get("vintage_required", False))
    if isinstance(marker, str):
        return marker.casefold() in {"required", "true", "yes"}
    return marker is True


def _validate_snapshot(
    snapshot: Mapping[str, Any], definitions: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping):
        _fail("snapshot 必须是对象")
    missing = [field for field in _REQUIRED_FIELDS if field not in snapshot]
    if missing:
        _fail("snapshot 缺少必填字段：" + ", ".join(missing))

    race_id = snapshot["race_id"]
    if not isinstance(race_id, str) or not race_id.strip():
        _fail("race_id 必须是非空字符串")
    cycle = snapshot["cycle"]
    if isinstance(cycle, bool) or not isinstance(cycle, int) or not 1900 <= cycle <= 2200:
        _fail("cycle 必须是 1900..2200 的整数")
    horizon = snapshot["forecast_horizon"]
    if not isinstance(horizon, str) or not horizon.strip():
        _fail("forecast_horizon 必须是非空字符串")

    as_of = _instant(snapshot["forecast_as_of"], "forecast_as_of", role="forecast")
    office = str(snapshot["office"]).upper()
    if office not in {"HOUSE", "SENATE"}:
        _fail("office 只能是 HOUSE 或 SENATE")
    state = snapshot["state"]
    if not isinstance(state, str) or not _STATE_PATTERN.fullmatch(state):
        _fail("state 必须是 2–3 位大写辖区代码")
    district = snapshot["district"]
    if office == "HOUSE":
        valid_integer = isinstance(district, int) and not isinstance(district, bool) and district >= 0
        valid_code = isinstance(district, str) and bool(district.strip())
        if not (valid_integer or valid_code):
            _fail("House 快照的 district 必须是非空选区代码或不小于 0 的整数")
    elif district is not None:
        _fail("Senate 快照的 district 必须为 null")
    if office == "SENATE":
        senate_class = snapshot.get("senate_class")
        if isinstance(senate_class, bool) or not isinstance(senate_class, int) or senate_class not in {1, 2, 3}:
            _fail("Senate 快照必须含 senate_class=1/2/3")
        is_special = snapshot.get("is_special_election")
        if not isinstance(is_special, bool):
            _fail("Senate 快照必须含布尔 is_special_election")
        stage = snapshot.get("election_stage")
        allowed_stages = {"general", "runoff", "ranked_choice_final", "special_general", "special_runoff"}
        if stage not in allowed_stages:
            _fail("Senate 快照必须含合法 election_stage")

    map_data = snapshot["map"]
    if not isinstance(map_data, Mapping):
        _fail("map 必须是对象")
    for field in ("map_id", "known_at", "effective_from"):
        if field not in map_data:
            _fail(f"map 缺少字段：{field}")
    if not isinstance(map_data["map_id"], str) or not map_data["map_id"].strip():
        _fail("map.map_id 必须是非空字符串")
    known_at = _instant(map_data["known_at"], "map.known_at")
    effective_from = _instant(map_data["effective_from"], "map.effective_from")
    if known_at > as_of:
        _fail("地图 known_at 晚于 forecast_as_of，构成未来地图泄漏")
    if effective_from > as_of:
        _fail("地图 effective_from 晚于 forecast_as_of，构成未来地图泄漏")

    feature_values = snapshot["feature_values"]
    if not isinstance(feature_values, Mapping):
        _fail("feature_values 必须是 feature_id→观测对象的映射")
    unknown_values = sorted(set(feature_values) - set(definitions))
    if unknown_values:
        _fail("出现未登记的未知特征：" + ", ".join(unknown_values))

    for feature_id, observation in feature_values.items():
        if not isinstance(observation, Mapping):
            _fail(f"特征 {feature_id} 的观测必须是含 value/available_at 的对象")
        if "value" not in observation or "available_at" not in observation:
            _fail(f"特征 {feature_id} 的观测缺少 value 或 available_at")
        available_at = _instant(observation["available_at"], f"{feature_id}.available_at")
        if available_at > as_of:
            _fail(f"特征 {feature_id} 的 available_at 晚于 forecast_as_of，构成时间泄漏")
        spec = definitions[feature_id]
        offices = spec.get("offices")
        if offices is not None:
            if not isinstance(offices, list) or office not in offices:
                _fail(f"特征 {feature_id} 不允许用于 {office} 轨道")
        if _vintage_required(spec):
            # 历史数据源常称作 vintage，确定性夹具则显式称 vintage_id；
            # 二者语义相同，但必须至少有一个非空值，不能靠最终修订值回填。
            vintage = observation.get("vintage", observation.get("vintage_id"))
            if vintage is None or (isinstance(vintage, str) and not vintage.strip()):
                _fail(f"特征 {feature_id} 需要修订 vintage，但观测未提供")
        _check_value(feature_id, observation["value"], spec)

    predictors = snapshot["predictors"]
    if not isinstance(predictors, list) or not all(isinstance(item, str) for item in predictors):
        _fail("predictors 必须是特征 id 字符串数组")
    if len(predictors) != len(set(predictors)):
        _fail("predictors 不得含重复特征")
    unknown_predictors = sorted(set(predictors) - set(definitions))
    if unknown_predictors:
        _fail("predictors 含未登记的未知特征：" + ", ".join(unknown_predictors))

    actual_result = snapshot["actual_result"]
    if not isinstance(actual_result, Mapping):
        _fail("actual_result 必须是对象")
    expected_actual_keys = {
        "democratic_margin",
        "democratic_win",
        "available_at",
        "source_id",
    }
    actual_key_strings = set(actual_result)
    if actual_key_strings != expected_actual_keys:
        missing_actual = sorted(expected_actual_keys - actual_key_strings)
        extra_actual = sorted(actual_key_strings - expected_actual_keys)
        details = []
        if missing_actual:
            details.append("缺少 " + ", ".join(missing_actual))
        if extra_actual:
            details.append("多出 " + ", ".join(extra_actual))
        _fail("actual_result 键集不符合显式契约：" + "；".join(details))
    actual_keys = {str(key).casefold() for key in actual_result}
    for feature_id in predictors:
        spec = definitions[feature_id]
        role = str(spec.get("role", "predictor")).casefold()
        forbidden = (
            role in _OUTCOME_ROLES
            or role not in _PREDICTOR_ROLES
            or feature_id.casefold() == "actual_result"
            or feature_id.casefold().startswith("actual_")
            or feature_id.casefold() in actual_keys
        )
        if forbidden:
            _fail(f"结果/非预测字段 {feature_id} 混入 predictors，构成目标泄漏")
        if spec.get("predictor_allowed") is not True:
            _fail(f"特征 {feature_id} 未获 predictor_allowed=true，不得进入 predictors")
        if spec.get("allowed_in_current_contract") is not True:
            _fail(f"特征 {feature_id} 未获 allowed_in_current_contract=true，不得在本合同启用")
        offices = spec.get("offices")
        if not isinstance(offices, list) or office not in offices:
            _fail(f"特征 {feature_id} 不允许作为 {office} predictor")
        if feature_id not in feature_values:
            _fail(f"predictor {feature_id} 在 feature_values 中没有观测")

    return snapshot


def validate_snapshot(
    snapshot: Mapping[str, Any], feature_registry: Any
) -> Mapping[str, Any]:
    """验证单条快照；成功时原样返回，失败时抛 ``SnapshotValidationError``。"""

    return _validate_snapshot(snapshot, _load_registry(feature_registry))


def audit_panel(
    rows: Iterable[Mapping[str, Any]], feature_registry: Any
) -> list[Mapping[str, Any]]:
    """验证完整面板及唯一键，成功时按输入顺序返回行列表。

    唯一键严格按合同使用 ``race_id/cycle/forecast_horizon``；即使 as-of 不同，
    同一键出现两次也必须显式改用不同 horizon，而不能静默覆盖。
    """

    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Iterable):
        _fail("rows 必须是快照对象的可迭代序列")
    definitions = _load_registry(feature_registry)
    validated: list[Mapping[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for index, row in enumerate(rows):
        try:
            _validate_snapshot(row, definitions)
        except SnapshotValidationError as error:
            raise SnapshotValidationError(f"面板第 {index + 1} 行不合规：{error}") from error
        key = (row["race_id"], row["cycle"], row["forecast_horizon"])
        if key in seen:
            _fail(
                "重复快照：同一 race_id/cycle/forecast_horizon 已出现："
                f"{key[0]}/{key[1]}/{key[2]}"
            )
        seen.add(key)
        validated.append(row)
    if not validated:
        _fail("面板不能为空")
    return validated


def validate_snapshots(
    rows: Iterable[Mapping[str, Any]], feature_registry: Any
) -> list[Mapping[str, Any]]:
    """``audit_panel`` 的复数命名入口，供基准驱动器直接调用。"""

    return audit_panel(rows, feature_registry)


# 语义明确的兼容别名：调用方若把该步骤称为 leakage audit，可直接复用。
audit_leakage = audit_panel
ValidationError = SnapshotValidationError
