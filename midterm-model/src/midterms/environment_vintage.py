"""LH-074 generic ballot 历史 topline 的点时摄取。

本模块只做忠实转录、资格闸和点时账本化。它不选择 subgroup，不计算评分，
也不生成平滑序列。来源中的无时区 timestamp 按最不利（最晚可用）方向解释
为 UTC-12 本地时刻，再统一转换为 UTC。
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping


EXPECTED_COLUMNS = (
    "subgroup",
    "modeldate",
    "dem_estimate",
    "dem_hi",
    "dem_lo",
    "rep_estimate",
    "rep_hi",
    "rep_lo",
    "timestamp",
)
NUMERIC_COLUMNS = (
    "dem_estimate",
    "dem_hi",
    "dem_lo",
    "rep_estimate",
    "rep_hi",
    "rep_lo",
)

SCHEMA_COLUMNS_MISMATCH = "SCHEMA_COLUMNS_MISMATCH"
DATE_PARSE_INVALID = "DATE_PARSE_INVALID"
NUMERIC_PARSE_INVALID = "NUMERIC_PARSE_INVALID"
ESTIMATE_OUT_OF_RANGE = "ESTIMATE_OUT_OF_RANGE"
INTERVAL_ORDER_INVALID = "INTERVAL_ORDER_INVALID"
DUPLICATE_SUBGROUP_MODEDATE = "DUPLICATE_SUBGROUP_MODEDATE"
ROW_CONSERVATION_MISMATCH = "ROW_CONSERVATION_MISMATCH"

_SOURCE_TIMESTAMP = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})  "
    r"(?P<day>\d{1,2}) (?P<month>[A-Za-z]{3}) (?P<year>\d{4})$"
)
_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_LATEST_PLAUSIBLE_ZONE = timezone(timedelta(hours=-12))


class EnvironmentVintageError(ValueError):
    """输入结构使摄取无法继续时抛出，并携带稳定失败码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}：{message}")
        self.code = code


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_modeldate(value: str) -> date:
    """严格解析来源的月/日/年日期。"""

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value.strip())
    if not match:
        raise EnvironmentVintageError(DATE_PARSE_INVALID, f"modeldate 无法解析：{value!r}")
    try:
        return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    except ValueError as error:
        raise EnvironmentVintageError(DATE_PARSE_INVALID, f"modeldate 无法解析：{value!r}") from error


def parse_available_at(value: str) -> tuple[datetime, str, str]:
    """按 M2 的 available 角色把 timestamp 变成 tz-aware UTC。

    返回 ``(UTC 时刻, 输入形态, 解析选择)``。仅日期值在该日结束后可用；
    显式 offset 的时刻直接归一化；无 offset 的时刻按 UTC-12 解释，以得到
    全球民用时区范围内最晚的 UTC 可用时刻。
    """

    text = value.strip()
    source_match = _SOURCE_TIMESTAMP.fullmatch(text)
    if source_match:
        month = _MONTHS.get(source_match.group("month").title())
        if month is None:
            raise EnvironmentVintageError(DATE_PARSE_INVALID, f"timestamp 月份无法解析：{value!r}")
        try:
            parsed = datetime(
                int(source_match.group("year")),
                month,
                int(source_match.group("day")),
                int(source_match.group("hour")),
                int(source_match.group("minute")),
                int(source_match.group("second")),
                tzinfo=_LATEST_PLAUSIBLE_ZONE,
            )
        except ValueError as error:
            raise EnvironmentVintageError(DATE_PARSE_INVALID, f"timestamp 无法解析：{value!r}") from error
        return (
            parsed.astimezone(timezone.utc),
            "source_naive_english",
            "naive_assumed_utc_minus_12_latest_possible",
        )

    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed_iso = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise EnvironmentVintageError(DATE_PARSE_INVALID, f"timestamp 无法解析：{value!r}") from error

    if date_only:
        available = datetime.combine(parsed_iso.date() + timedelta(days=1), time.min, timezone.utc)
        return available, "iso_date_only", "date_only_available_after_day"
    if parsed_iso.tzinfo is None:
        return (
            parsed_iso.replace(tzinfo=_LATEST_PLAUSIBLE_ZONE).astimezone(timezone.utc),
            "iso_naive_datetime",
            "naive_assumed_utc_minus_12_latest_possible",
        )
    return parsed_iso.astimezone(timezone.utc), "iso_aware_datetime", "explicit_offset_to_utc"


def _number(value: str, field: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise EnvironmentVintageError(NUMERIC_PARSE_INVALID, f"{field} 不是数值：{value!r}") from error
    if not math.isfinite(number):
        raise EnvironmentVintageError(NUMERIC_PARSE_INVALID, f"{field} 必须是有限数值")
    return number


def _rejected_row(line_number: int, raw: list[str], failures: Iterable[str]) -> dict[str, Any]:
    return {
        "source_csv_line": line_number,
        "failure_codes": sorted(set(failures)),
        "raw_original": raw,
    }


def ingest_csv_bytes(
    content: bytes,
    *,
    source_path: str,
    source_sha256: str,
    expected_data_rows: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """摄取 CSV 字节，返回账本行与构建对账报告所需的审计事实。"""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EnvironmentVintageError(SCHEMA_COLUMNS_MISMATCH, "来源不是 UTF-8") from error

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as error:
        raise EnvironmentVintageError(SCHEMA_COLUMNS_MISMATCH, "来源缺少表头") from error
    if tuple(header) != EXPECTED_COLUMNS:
        raise EnvironmentVintageError(
            SCHEMA_COLUMNS_MISMATCH,
            f"九列表头不逐字一致：actual={header!r}",
        )

    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    gate_failures: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()
    choice_counts: Counter[str] = Counter()
    raw_row_count = 0

    for raw in reader:
        raw_row_count += 1
        line_number = reader.line_num
        failures: list[str] = []
        if len(raw) != len(EXPECTED_COLUMNS):
            failures.append(SCHEMA_COLUMNS_MISMATCH)
            gate_failures.update(failures)
            rejected.append(_rejected_row(line_number, raw, failures))
            continue

        row = dict(zip(EXPECTED_COLUMNS, raw, strict=True))
        model_day: date | None = None
        available_at: datetime | None = None
        shape = ""
        choice = ""
        try:
            model_day = parse_modeldate(row["modeldate"])
        except EnvironmentVintageError as error:
            failures.append(error.code)
        try:
            available_at, shape, choice = parse_available_at(row["timestamp"])
        except EnvironmentVintageError as error:
            failures.append(error.code)

        numbers: dict[str, float] = {}
        for field in NUMERIC_COLUMNS:
            try:
                numbers[field] = _number(row[field], field)
            except EnvironmentVintageError as error:
                failures.append(error.code)

        if all(field in numbers for field in ("dem_estimate", "rep_estimate")):
            if not 0.0 <= numbers["dem_estimate"] <= 100.0 or not 0.0 <= numbers["rep_estimate"] <= 100.0:
                failures.append(ESTIMATE_OUT_OF_RANGE)
        if all(field in numbers for field in NUMERIC_COLUMNS):
            if not (
                numbers["dem_hi"] >= numbers["dem_estimate"] >= numbers["dem_lo"]
                and numbers["rep_hi"] >= numbers["rep_estimate"] >= numbers["rep_lo"]
            ):
                failures.append(INTERVAL_ORDER_INVALID)

        key: tuple[str, str] | None = None
        if model_day is not None:
            key = (row["subgroup"], model_day.isoformat())
            if key in seen:
                failures.append(DUPLICATE_SUBGROUP_MODEDATE)

        if failures:
            gate_failures.update(set(failures))
            rejected.append(_rejected_row(line_number, raw, failures))
            continue

        assert model_day is not None and available_at is not None and key is not None
        seen.add(key)
        shape_counts[shape] += 1
        choice_counts[choice] += 1
        records.append(
            {
                "schema_version": "lh074.environment-vintage.v1",
                "subgroup": row["subgroup"],
                "modeldate": model_day.isoformat(),
                **numbers,
                "available_at": _utc_text(available_at),
                "available_at_basis": "timestamp",
                "timestamp_timezone_choice": choice,
                "lineage": {
                    "source_path": source_path,
                    "source_sha256_prefix": source_sha256[:8],
                    "source_csv_line": line_number,
                    "raw_timestamp": row["timestamp"],
                },
            }
        )

    conservation_total = len(records) + len(rejected)
    row_conservation_passed = conservation_total == expected_data_rows == raw_row_count
    if not row_conservation_passed:
        gate_failures[ROW_CONSERVATION_MISMATCH] += 1
    audit = {
        "header": header,
        "raw_data_rows": raw_row_count,
        "accepted_rows": len(records),
        "rejected_rows": rejected,
        "failure_code_counts": dict(sorted(gate_failures.items())),
        "timestamp_shape_counts": dict(sorted(shape_counts.items())),
        "timestamp_parsing_choice_counts": dict(sorted(choice_counts.items())),
        "row_conservation": {
            "ledger_rows": len(records),
            "rejected_rows": len(rejected),
            "accounted_rows": conservation_total,
            "raw_data_rows": raw_row_count,
            "expected_data_rows": expected_data_rows,
            "passed": row_conservation_passed,
            "failure_code": ROW_CONSERVATION_MISMATCH,
        },
    }
    return records, audit


def election_window_counts(
    records: Iterable[Mapping[str, Any]], election_day: date, days_before: int = 180
) -> dict[str, Any]:
    """统计选举日前 ``days_before`` 天至前一日的逐口径覆盖。"""

    start = election_day - timedelta(days=days_before)
    end = election_day - timedelta(days=1)
    materialized = list(records)
    counts: Counter[str] = Counter(
        {str(row["subgroup"]): 0 for row in materialized}
    )
    for row in materialized:
        model_day = date.fromisoformat(str(row["modeldate"]))
        if start <= model_day <= end:
            counts[str(row["subgroup"])] += 1
    return {
        "election_date": election_day.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "inclusive_days": days_before,
        "total_rows": sum(counts.values()),
        "rows_by_subgroup": dict(sorted(counts.items())),
        "coverage_is_diagnostic_not_gate": True,
    }


def build_reconciliation(
    records: list[Mapping[str, Any]],
    audit: Mapping[str, Any],
    *,
    source_path: str,
    source_sha256: str,
    source_byte_count: int,
) -> dict[str, Any]:
    """从已资格审计的行构造确定性对账报告。"""

    subgroup_counts = Counter(str(row["subgroup"]) for row in records)
    modeldates = [date.fromisoformat(str(row["modeldate"])) for row in records]
    earlier: list[dict[str, Any]] = []
    for row in records:
        available = datetime.fromisoformat(str(row["available_at"]).replace("Z", "+00:00"))
        model_midnight = datetime.combine(
            date.fromisoformat(str(row["modeldate"])), time.min, timezone.utc
        )
        if available < model_midnight:
            earlier.append(
                {
                    "source_csv_line": row["lineage"]["source_csv_line"],
                    "subgroup": row["subgroup"],
                    "modeldate": row["modeldate"],
                    "available_at": row["available_at"],
                    "interpretation": "来源事实；按合同保留",
                }
            )

    failure_counts = dict(audit["failure_code_counts"])
    return {
        "schema_version": "lh074.environment-vintage-reconciliation.v1",
        "contract_id": "LH-074",
        "source": {
            "path": source_path,
            "sha256": source_sha256,
            "sha256_prefix": source_sha256[:8],
            "byte_count": source_byte_count,
            "license": "CC-BY-4.0",
        },
        "ledger": {
            "schema_version": "lh074.environment-vintage.v1",
            "row_count": len(records),
            "selection_policy": "subgroup 全量忠实转录；不按数值表现筛选",
        },
        "qualification_gates": {
            "schema_columns_exact": {
                "passed": (
                    tuple(audit["header"]) == EXPECTED_COLUMNS
                    and SCHEMA_COLUMNS_MISMATCH not in failure_counts
                ),
                "failure_code": SCHEMA_COLUMNS_MISMATCH,
                "failed_rows": failure_counts.get(SCHEMA_COLUMNS_MISMATCH, 0),
                "expected": list(EXPECTED_COLUMNS),
                "actual": list(audit["header"]),
            },
            "dates_parseable": {
                "passed": DATE_PARSE_INVALID not in failure_counts,
                "failure_code": DATE_PARSE_INVALID,
                "failed_rows": failure_counts.get(DATE_PARSE_INVALID, 0),
            },
            "numeric_values_parseable": {
                "passed": NUMERIC_PARSE_INVALID not in failure_counts,
                "failure_code": NUMERIC_PARSE_INVALID,
                "failed_rows": failure_counts.get(NUMERIC_PARSE_INVALID, 0),
            },
            "estimates_in_range": {
                "passed": ESTIMATE_OUT_OF_RANGE not in failure_counts,
                "failure_code": ESTIMATE_OUT_OF_RANGE,
                "failed_rows": failure_counts.get(ESTIMATE_OUT_OF_RANGE, 0),
            },
            "interval_order": {
                "passed": INTERVAL_ORDER_INVALID not in failure_counts,
                "failure_code": INTERVAL_ORDER_INVALID,
                "failed_rows": failure_counts.get(INTERVAL_ORDER_INVALID, 0),
            },
            "unique_subgroup_modeldate": {
                "passed": DUPLICATE_SUBGROUP_MODEDATE not in failure_counts,
                "failure_code": DUPLICATE_SUBGROUP_MODEDATE,
                "failed_rows": failure_counts.get(DUPLICATE_SUBGROUP_MODEDATE, 0),
            },
            "row_conservation": dict(audit["row_conservation"]),
        },
        "rejected_rows": list(audit["rejected_rows"]),
        "subgroups": {
            "count": len(subgroup_counts),
            "enumeration": [
                {"subgroup": subgroup, "row_count": count}
                for subgroup, count in sorted(subgroup_counts.items())
            ],
        },
        "modeldate_coverage": {
            "first": min(modeldates).isoformat() if modeldates else None,
            "last": max(modeldates).isoformat() if modeldates else None,
        },
        "election_windows": {
            "2018": election_window_counts(records, date(2018, 11, 6)),
            "2022": election_window_counts(records, date(2022, 11, 8)),
        },
        "timestamp_semantics": {
            "source_column": "timestamp",
            "output_field": "available_at",
            "output_timezone": "UTC",
            "shape_counts": dict(audit["timestamp_shape_counts"]),
            "parsing_choice_counts": dict(audit["timestamp_parsing_choice_counts"]),
            "naive_policy": "无时区时刻按 UTC-12 本地时间解释，再转 UTC；这是全球民用时区范围内最晚可用的保守方向",
            "date_only_policy": "available 角色按该日结束后的下一日 00:00 UTC",
        },
        "leakage_direction_check": {
            "rule": "available_at >= modeldate 当日 00:00 UTC",
            "passed_without_earlier_source_facts": not earlier,
            "non_earlier_rows": len(records) - len(earlier),
            "earlier_rows_count": len(earlier),
            "earlier_rows": earlier,
            "earlier_rows_policy": "不剔除；记录并保留来源事实",
        },
        "boundaries": {
            "scores_emitted": False,
            "weights_emitted": False,
            "smoothing_emitted": False,
            "subgroup_recommendation_emitted": False,
            "future_cycle_values_emitted": False,
        },
    }
