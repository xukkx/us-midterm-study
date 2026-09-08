"""真实历史回测的只读训练来源校验。

这里的 lineage 不是装饰性元数据。每条记录都声明一个训练来源周期，任何
不早于测试周期的来源都会使整折失败关闭。模块只处理周期级来源，不把同号
House district 解释成跨地图延续的席位。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class LineageValidationError(ValueError):
    """训练来源违反过去信息约束时抛出。"""


def _cycle(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LineageValidationError(f"{field} 必须是整数周期")
    if not 1900 <= value <= 2200:
        raise LineageValidationError(f"{field} 必须位于 1900..2200")
    return value


def _office(value: Any, field: str = "office") -> str:
    if not isinstance(value, str):
        raise LineageValidationError(f"{field} 必须是 HOUSE 或 SENATE")
    normalized = value.upper()
    if normalized not in {"HOUSE", "SENATE"}:
        raise LineageValidationError(f"{field} 必须是 HOUSE 或 SENATE")
    return normalized


@dataclass(frozen=True, order=True)
class SourceLineage:
    """一个可序列化的周期级训练来源。"""

    office: str
    source_cycle: int
    source_id: str = "historical-targets"

    def as_dict(self) -> dict[str, Any]:
        return {
            "office": self.office,
            "source_cycle": self.source_cycle,
            "source_id": self.source_id,
        }


def _record(entry: Mapping[str, Any] | SourceLineage, index: int) -> SourceLineage:
    if isinstance(entry, SourceLineage):
        office = _office(entry.office, f"lineage[{index}].office")
        source_cycle = _cycle(entry.source_cycle, f"lineage[{index}].source_cycle")
        source_id = entry.source_id
    elif isinstance(entry, Mapping):
        if "office" not in entry or "source_cycle" not in entry:
            raise LineageValidationError(
                f"lineage[{index}] 必须包含 office 与 source_cycle"
            )
        office = _office(entry["office"], f"lineage[{index}].office")
        source_cycle = _cycle(
            entry["source_cycle"], f"lineage[{index}].source_cycle"
        )
        source_id = entry.get("source_id", "historical-targets")
    else:
        raise LineageValidationError(f"lineage[{index}] 必须是对象")
    if not isinstance(source_id, str) or not source_id.strip():
        raise LineageValidationError(f"lineage[{index}].source_id 必须是非空字符串")
    return SourceLineage(office, source_cycle, source_id.strip())


def validate_lineage(
    entries: Iterable[Mapping[str, Any] | SourceLineage],
    test_cycle: int,
    expected_office: str | None = None,
) -> tuple[SourceLineage, ...]:
    """验证并规范化过去来源，返回与输入顺序无关的确定性结果。

    每个 ``source_cycle`` 必须严格小于 ``test_cycle``。重复记录也拒绝，避免
    同一训练周期因 lineage 重复而在后续聚合中被隐式加权两次。
    """

    target = _cycle(test_cycle, "test_cycle")
    office = _office(expected_office, "expected_office") if expected_office else None
    if isinstance(entries, (str, bytes, Mapping)) or not isinstance(entries, Iterable):
        raise LineageValidationError("lineage 必须是来源对象序列")

    normalized: list[SourceLineage] = []
    seen: set[SourceLineage] = set()
    for index, entry in enumerate(entries):
        record = _record(entry, index)
        if record.source_cycle >= target:
            raise LineageValidationError(
                "过去信息泄漏："
                f"source_cycle={record.source_cycle} 不早于 test_cycle={target}"
            )
        if office is not None and record.office != office:
            raise LineageValidationError(
                f"lineage 院别 {record.office} 与预期 {office} 不一致"
            )
        if record in seen:
            raise LineageValidationError(
                "lineage 含重复来源："
                f"{record.office}/{record.source_cycle}/{record.source_id}"
            )
        seen.add(record)
        normalized.append(record)
    if not normalized:
        raise LineageValidationError("lineage 不能为空")
    return tuple(sorted(normalized))


def build_cycle_lineage(
    train_rows: Sequence[Mapping[str, Any]],
    test_cycle: int,
    office: str,
    source_id: str = "historical-targets",
) -> tuple[SourceLineage, ...]:
    """从训练行构造每周期一条的来源记录，并立即执行过去信息校验。"""

    if not train_rows:
        raise LineageValidationError("训练行不能为空")
    normalized_office = _office(office)
    cycles: set[int] = set()
    for index, row in enumerate(train_rows):
        if not isinstance(row, Mapping):
            raise LineageValidationError(f"train_rows[{index}] 必须是对象")
        if "cycle" not in row or "office" not in row:
            raise LineageValidationError(
                f"train_rows[{index}] 必须包含 cycle 与 office"
            )
        row_office = _office(row["office"], f"train_rows[{index}].office")
        if row_office != normalized_office:
            raise LineageValidationError("House 与 Senate 的训练来源不得混合")
        cycles.add(_cycle(row["cycle"], f"train_rows[{index}].cycle"))
    entries = [
        SourceLineage(normalized_office, cycle, source_id) for cycle in sorted(cycles)
    ]
    return validate_lineage(entries, test_cycle, normalized_office)


def lineage_bytes(entries: Iterable[Mapping[str, Any] | SourceLineage]) -> bytes:
    """把已规范化来源写成稳定 JSON 字节，供报告与回归测试复用。"""

    records = [_record(entry, index) for index, entry in enumerate(entries)]
    if not records:
        raise LineageValidationError("lineage 不能为空")
    if len(records) != len(set(records)):
        raise LineageValidationError("lineage 含重复来源")
    payload = [record.as_dict() for record in sorted(records)]
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


# 语义明确的别名，基准驱动器可将该步骤直接当作断言使用。
assert_past_only_lineage = validate_lineage

