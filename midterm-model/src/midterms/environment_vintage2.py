"""LH-082 旧模型 generic ballot 的近点时摄取。

本模块只做全部单元格的忠实转录、资格闸、逐行 lineage 与点时账本化。
来源没有独立发布时间戳，故复用 ``schema._instant`` 的 available 角色：
来源 ``date`` 在次日 00:00 UTC 才视为可用。这里不评分、不加权、不平滑，
也不推荐候选口径。
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping

from . import schema as snapshot_schema


EXPECTED_COLUMNS = (
    "candidate",
    "pct_estimate",
    "lo",
    "hi",
    "date",
    "election",
    "cycle",
)
NUMERIC_COLUMNS = ("pct_estimate", "lo", "hi")

SCHEMA_COLUMNS_MISMATCH = "SCHEMA_COLUMNS_MISMATCH"
DATE_PARSE_INVALID = "DATE_PARSE_INVALID"
NUMERIC_PARSE_INVALID = "NUMERIC_PARSE_INVALID"
ESTIMATE_OUT_OF_RANGE = "ESTIMATE_OUT_OF_RANGE"
INTERVAL_ORDER_INVALID = "INTERVAL_ORDER_INVALID"
DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE = "DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE"
ROW_CONSERVATION_MISMATCH = "ROW_CONSERVATION_MISMATCH"

AVAILABLE_AT_BASIS = "date_next_day_00_00_utc_via_schema_instant_available_role"
EVIDENCE_TIER = "near_point_in_time"


class EnvironmentVintage2Error(ValueError):
    """输入结构使 LH-082 摄取无法继续时抛出，并携带稳定失败码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}：{message}")
        self.code = code


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_date(value: str, field: str) -> date:
    """严格解析来源的 ISO 日期，不接受带时刻或宽松变体。"""

    text = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise EnvironmentVintage2Error(DATE_PARSE_INVALID, f"{field} 无法解析：{value!r}")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise EnvironmentVintage2Error(DATE_PARSE_INVALID, f"{field} 无法解析：{value!r}") from error


def parse_cycle(value: str) -> int:
    """将四位周期字段转成整数；失败归入数值解析闸。"""

    text = value.strip()
    if not re.fullmatch(r"\d{4}", text):
        raise EnvironmentVintage2Error(NUMERIC_PARSE_INVALID, f"cycle 不是四位整数：{value!r}")
    return int(text)


def available_at_from_date(model_day: date) -> datetime:
    """复用 M2 ``_instant``：仅日期 available 值在次日零时才可用。"""

    return snapshot_schema._instant(model_day.isoformat(), "date", role="available")


def _number(value: str, field: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise EnvironmentVintage2Error(NUMERIC_PARSE_INVALID, f"{field} 不是数值：{value!r}") from error
    if not math.isfinite(number):
        raise EnvironmentVintage2Error(NUMERIC_PARSE_INVALID, f"{field} 必须是有限数值")
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
    """摄取 CSV 全部单元格，返回账本行与确定性审计事实。"""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EnvironmentVintage2Error(SCHEMA_COLUMNS_MISMATCH, "来源不是 UTF-8") from error

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as error:
        raise EnvironmentVintage2Error(SCHEMA_COLUMNS_MISMATCH, "来源缺少表头") from error
    if tuple(header) != EXPECTED_COLUMNS:
        raise EnvironmentVintage2Error(
            SCHEMA_COLUMNS_MISMATCH,
            f"七列表头不逐字一致：actual={header!r}",
        )

    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    gate_failures: Counter[str] = Counter()
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
        election_day: date | None = None
        cycle: int | None = None
        try:
            model_day = parse_iso_date(row["date"], "date")
        except EnvironmentVintage2Error as error:
            failures.append(error.code)
        try:
            election_day = parse_iso_date(row["election"], "election")
        except EnvironmentVintage2Error as error:
            failures.append(error.code)
        try:
            cycle = parse_cycle(row["cycle"])
        except EnvironmentVintage2Error as error:
            failures.append(error.code)

        numbers: dict[str, float] = {}
        for field in NUMERIC_COLUMNS:
            try:
                numbers[field] = _number(row[field], field)
            except EnvironmentVintage2Error as error:
                failures.append(error.code)

        if "pct_estimate" in numbers and not 0.0 <= numbers["pct_estimate"] <= 100.0:
            failures.append(ESTIMATE_OUT_OF_RANGE)
        if all(field in numbers for field in NUMERIC_COLUMNS):
            if not numbers["hi"] >= numbers["pct_estimate"] >= numbers["lo"]:
                failures.append(INTERVAL_ORDER_INVALID)

        key: tuple[str, str, str, int] | None = None
        if model_day is not None and election_day is not None and cycle is not None:
            key = (row["candidate"], model_day.isoformat(), election_day.isoformat(), cycle)
            if key in seen:
                failures.append(DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE)

        if failures:
            gate_failures.update(set(failures))
            rejected.append(_rejected_row(line_number, raw, failures))
            continue

        assert model_day is not None and election_day is not None and cycle is not None and key is not None
        available = available_at_from_date(model_day)
        seen.add(key)
        records.append(
            {
                "schema_version": "lh082.environment-oldmodel-vintage.v1",
                "candidate": row["candidate"],
                "pct_estimate": numbers["pct_estimate"],
                "lo": numbers["lo"],
                "hi": numbers["hi"],
                "date": model_day.isoformat(),
                "election": election_day.isoformat(),
                "cycle": cycle,
                "available_at": _utc_text(available),
                "available_at_basis": AVAILABLE_AT_BASIS,
                "evidence_tier": EVIDENCE_TIER,
                "lineage": {
                    "source_path": source_path,
                    "source_sha256": source_sha256,
                    "source_sha256_prefix": source_sha256[:8],
                    "source_csv_line": line_number,
                    "raw_fields": dict(row),
                },
            }
        )

    conservation_total = len(records) + len(rejected)
    conservation_passed = conservation_total == expected_data_rows == raw_row_count
    if not conservation_passed:
        gate_failures[ROW_CONSERVATION_MISMATCH] += 1
    audit = {
        "header": header,
        "raw_data_rows": raw_row_count,
        "accepted_rows": len(records),
        "rejected_rows": rejected,
        "failure_code_counts": dict(sorted(gate_failures.items())),
        "row_conservation": {
            "ledger_rows": len(records),
            "rejected_rows": len(rejected),
            "accounted_rows": conservation_total,
            "raw_data_rows": raw_row_count,
            "expected_data_rows": expected_data_rows,
            "passed": conservation_passed,
            "failure_code": ROW_CONSERVATION_MISMATCH,
        },
    }
    return records, audit


def election_window_counts(
    records: Iterable[Mapping[str, Any]], election_day: date, days_before: int = 180
) -> dict[str, Any]:
    """统计同一 election 在选举日前指定窗口的逐候选口径覆盖。"""

    start = election_day - timedelta(days=days_before)
    end = election_day - timedelta(days=1)
    materialized = list(records)
    candidates = sorted({str(row["candidate"]) for row in materialized})
    counts: Counter[str] = Counter({candidate: 0 for candidate in candidates})
    for row in materialized:
        model_day = date.fromisoformat(str(row["date"]))
        if str(row["election"]) == election_day.isoformat() and start <= model_day <= end:
            counts[str(row["candidate"])] += 1
    return {
        "election_date": election_day.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "inclusive_days": days_before,
        "election_match_required": True,
        "total_rows": sum(counts.values()),
        "rows_by_candidate": dict(sorted(counts.items())),
        "coverage_is_diagnostic_not_gate": True,
    }


def _coverage(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    days = [date.fromisoformat(str(row["date"])) for row in records]
    by_candidate: list[dict[str, Any]] = []
    for candidate in sorted({str(row["candidate"]) for row in records}):
        selected = [date.fromisoformat(str(row["date"])) for row in records if row["candidate"] == candidate]
        by_candidate.append(
            {
                "candidate": candidate,
                "first": min(selected).isoformat(),
                "last": max(selected).isoformat(),
                "row_count": len(selected),
            }
        )
    by_series: list[dict[str, Any]] = []
    series_keys = sorted({(str(row["candidate"]), str(row["election"]), int(row["cycle"])) for row in records})
    for candidate, election, cycle in series_keys:
        selected = [
            date.fromisoformat(str(row["date"]))
            for row in records
            if row["candidate"] == candidate and row["election"] == election and row["cycle"] == cycle
        ]
        by_series.append(
            {
                "candidate": candidate,
                "election": election,
                "cycle": cycle,
                "first": min(selected).isoformat(),
                "last": max(selected).isoformat(),
                "row_count": len(selected),
            }
        )
    return {
        "first": min(days).isoformat() if days else None,
        "last": max(days).isoformat() if days else None,
        "by_candidate": by_candidate,
        "by_candidate_election_cycle": by_series,
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

    candidate_counts = Counter(str(row["candidate"]) for row in records)
    series_counts = Counter(
        (str(row["candidate"]), str(row["election"]), int(row["cycle"])) for row in records
    )
    earlier: list[dict[str, Any]] = []
    next_day_mismatches: list[dict[str, Any]] = []
    for row in records:
        available = datetime.fromisoformat(str(row["available_at"]).replace("Z", "+00:00"))
        model_day = date.fromisoformat(str(row["date"]))
        model_midnight = datetime.combine(model_day, time.min, timezone.utc)
        expected = model_midnight + timedelta(days=1)
        if available < model_midnight:
            earlier.append({"source_csv_line": row["lineage"]["source_csv_line"], "available_at": row["available_at"]})
        if available != expected:
            next_day_mismatches.append(
                {"source_csv_line": row["lineage"]["source_csv_line"], "available_at": row["available_at"]}
            )

    failures = dict(audit["failure_code_counts"])
    return {
        "schema_version": "lh082.environment-oldmodel-vintage-reconciliation.v1",
        "contract_id": "LH-082",
        "source": {
            "path": source_path,
            "sha256": source_sha256,
            "sha256_prefix": source_sha256[:8],
            "byte_count": source_byte_count,
            "license": "CC-BY-4.0",
        },
        "ledger": {
            "schema_version": "lh082.environment-oldmodel-vintage.v1",
            "row_count": len(records),
            "selection_policy": "全部 candidate/election/cycle 口径忠实转录；不按数值表现筛选",
            "schema_documentation": "docs/environment-oldmodel-vintage-schema.md",
        },
        "qualification_gates": {
            "schema_columns_exact": {
                "passed": tuple(audit["header"]) == EXPECTED_COLUMNS and SCHEMA_COLUMNS_MISMATCH not in failures,
                "failure_code": SCHEMA_COLUMNS_MISMATCH,
                "failed_rows": failures.get(SCHEMA_COLUMNS_MISMATCH, 0),
                "expected": list(EXPECTED_COLUMNS),
                "actual": list(audit["header"]),
            },
            "dates_parseable": {
                "passed": DATE_PARSE_INVALID not in failures,
                "failure_code": DATE_PARSE_INVALID,
                "failed_rows": failures.get(DATE_PARSE_INVALID, 0),
            },
            "numeric_values_parseable": {
                "passed": NUMERIC_PARSE_INVALID not in failures,
                "failure_code": NUMERIC_PARSE_INVALID,
                "failed_rows": failures.get(NUMERIC_PARSE_INVALID, 0),
            },
            "estimates_in_range": {
                "passed": ESTIMATE_OUT_OF_RANGE not in failures,
                "failure_code": ESTIMATE_OUT_OF_RANGE,
                "failed_rows": failures.get(ESTIMATE_OUT_OF_RANGE, 0),
            },
            "interval_order": {
                "passed": INTERVAL_ORDER_INVALID not in failures,
                "failure_code": INTERVAL_ORDER_INVALID,
                "failed_rows": failures.get(INTERVAL_ORDER_INVALID, 0),
            },
            "unique_candidate_date_election_cycle": {
                "passed": DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE not in failures,
                "failure_code": DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE,
                "failed_rows": failures.get(DUPLICATE_CANDIDATE_DATE_ELECTION_CYCLE, 0),
            },
            "row_conservation": dict(audit["row_conservation"]),
        },
        "rejected_rows": list(audit["rejected_rows"]),
        "candidate_scopes": {
            "count": len(candidate_counts),
            "enumeration": [
                {"candidate": candidate, "row_count": count}
                for candidate, count in sorted(candidate_counts.items())
            ],
        },
        "series_scopes": {
            "count": len(series_counts),
            "key": ["candidate", "election", "cycle"],
            "enumeration": [
                {"candidate": key[0], "election": key[1], "cycle": key[2], "row_count": count}
                for key, count in sorted(series_counts.items())
            ],
        },
        "date_coverage": _coverage(records),
        "election_windows": {
            "2018": election_window_counts(records, date(2018, 11, 6)),
            "2022": election_window_counts(records, date(2022, 11, 8)),
        },
        "point_in_time_semantics": {
            "source_time_column": "date",
            "independent_publication_timestamp_present": False,
            "output_field": "available_at",
            "output_timezone": "UTC",
            "available_at_basis": AVAILABLE_AT_BASIS,
            "choice": "来源只有 modeldate 类 date；按合同取次日 00:00 UTC，保守地不把建模日当天视为已发布",
            "evidence_tier": EVIDENCE_TIER,
            "tier_basis": "2018—2023 当年逐日模型输出由 FiveThirtyEight 仓库归档冻结；不是逐次发布传输时间戳",
            "ledger_grade_comparison": [
                {
                    "ledger": "data/processed/environment-generic-ballot-vintage.jsonl",
                    "contract": "LH-074",
                    "evidence_tier": "retrospective_reconstruction",
                    "basis": "来源 timestamp 全部落在 2020-09，历史 modeldate 为事后统一发布",
                },
                {
                    "ledger": "data/processed/environment-generic-ballot-oldmodel-vintage.jsonl",
                    "contract": "LH-082",
                    "evidence_tier": EVIDENCE_TIER,
                    "basis": "当年逐日生成并由仓库归档冻结；date 次日可用是缺少发布时刻时的保守近似",
                },
            ],
        },
        "leakage_direction_check": {
            "rule": "available_at 等于 date 次日 00:00 UTC，且不早于 date 当日 00:00 UTC",
            "passed": not earlier and not next_day_mismatches,
            "non_earlier_rows": len(records) - len(earlier),
            "earlier_rows_count": len(earlier),
            "earlier_rows": earlier,
            "next_day_mismatch_count": len(next_day_mismatches),
            "next_day_mismatches": next_day_mismatches,
        },
        "boundaries": {
            "scores_emitted": False,
            "weights_emitted": False,
            "smoothing_emitted": False,
            "candidate_recommendation_emitted": False,
            "future_cycle_values_emitted": False,
        },
    }
