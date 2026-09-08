"""总统州级结果的固定来源审计与 Senate M0 特征账本生成。

该模块只做档案重建。``available_at`` 表示历史结果事实的保守可知上界；
现代 GitHub 镜像的提交/获取时间另存，绝不冒充当年原始数据 vintage。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree as ET


class PresidentialIngestError(ValueError):
    """总统来源或特征账本违反预注册口径。"""


PRESIDENTIAL_HEADERS = (
    "year",
    "state",
    "state_po",
    "state_fips",
    "state_cen",
    "state_ic",
    "office",
    "candidate",
    "party",
    "writein",
    "candidatevotes",
    "totalvotes",
    "version",
    "notes",
)
PRESIDENTIAL_CYCLES = tuple(range(1976, 2017, 4))
SENATE_TARGET_CYCLES = tuple(range(1978, 2019, 4))
STATE_CODES = (
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD",
    "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH",
    "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
)
STATE_EQUIVALENTS = tuple(sorted((*STATE_CODES, "DC")))
DEMOCRATIC_PARTIES = {"democrat", "democratic-farmer-labor"}
REPUBLICAN_PARTIES = {"republican"}
DATASET_ID = "medsl-president-1976-2016"
TRANSFORM_ID = "prior_presidential_two_party_margin_v1"
FEATURE_ID = "partisan_baseline_margin"
CSV_VINTAGE = "MEDSL_CSV_VERSION_20171015_ARCHIVAL"
MODERN_MIRROR_PUBLISHED_AT = "2019-06-07T17:50:14Z"
DOI = "10.7910/DVN/42MVDX"
GIT_BLOB_SHA1 = "d7e8c0cce41fa00c37fc133b3c80f037255d4885"
FEC_2020_SHA256 = "5073b6d2c76c86c941508dfb1a11cc497e8529b0068c5132aceb0f385c19352e"
FEC_2020_BYTES = 6_251_110
FEC_2020_DATASET_ID = "fec-federal-elections-2020"
FEC_2020_SOURCE_PATH = "data/raw/fec/federalelections2020.xlsx"
FEC_2020_RESULTS_SHEET = "9. 2020 Pres General Results"
FEC_2020_NATIONAL_SHEET = "2. Table 1 Pres Popular Vote"
FEC_2020_STATE_SUMMARY_SHEET = "3. Table 2 Electoral & Pop Vote"
FEC_2024_SHA256 = "68acdee2924d771b92a05cd950dec850b462c633c05563207ac7e206116e7366"
FEC_2024_BYTES = 21_376
FEC_2024_DATASET_ID = "fec-official-2024-presidential-general-results"
FEC_2024_SOURCE_PATH = "data/raw/fec/2024presgeresults.xlsx"
FEC_2024_RESULTS_SHEET = "OFFICIAL 2024 PRES GE RESULTS"
FEC_2024_VINTAGE = "FEC_OFFICIAL_2024_PRES_GE_RESULTS_20250116"
FEC_2024_PUBLISHED_AT = "2025-01-17T14:16:05Z"
FEC_2024_RETRIEVED_AT = "2026-08-21T01:25:57Z"
FEC_2024_RETRIEVAL_TRANSACTION_ID = "bbccb260-c7f0-4f01-93a8-e2d7e43bbb40"
FEC_2024_CONTENT_SEAL_SHA256 = (
    "ae531019dc2028fe7153b4204e739e02935854f505b8aac488beee1c4fe31413"
)
FEC_2024_OFFICIAL_NATIONAL_TOTALS = {
    "democratic_votes": 75_017_613,
    "republican_votes": 77_302_580,
    "all_candidate_votes": 155_238_302,
}
FEC_2024_KEY_STATES = ("AZ", "GA", "MI", "NV", "NC", "PA", "WI")
FEC_2024_OFFICIAL_KEY_STATE_WINNERS = {state: "R" for state in FEC_2024_KEY_STATES}
LH068_RESULTS_PREFIX_ROWS = 612
LH068_RESULTS_PREFIX_SHA256 = (
    "e62d2ae3318de2cac56693b6b74d2fbcd4b1aff46756d892bea7fbd79f09be8e"
)
LH068_BASELINES_PREFIX_ROWS = 550
LH068_BASELINES_PREFIX_SHA256 = (
    "8ed230e9113054fe573814e81eb9a86c2417e6467df2373ce26ac6c7cb2d2c8f"
)
_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XLSX_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _integer(value: str | None, field: str, line: int) -> int:
    if value is None or re.fullmatch(r"\d+", value.strip()) is None:
        raise PresidentialIngestError(f"来源第 {line} 行 {field} 不是非负整数：{value!r}")
    return int(value)


def _boolean(value: str | None, field: str, line: int) -> bool:
    if value == "TRUE":
        return True
    if value == "FALSE":
        return False
    raise PresidentialIngestError(f"来源第 {line} 行 {field} 只能是 TRUE/FALSE：{value!r}")


def _optional_text(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def _identity(value: str) -> str:
    """仅做可复现的 Unicode/空白规范化，不做模糊人名匹配。"""

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise PresidentialIngestError(f"{field} 不是 ISO-8601 时间：{value!r}") from error


def read_presidential_csv(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """严格读取固定 CSV，保留每一物理来源行及原始候选/党派字段。"""

    source = Path(path)
    data = source.read_bytes()
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PresidentialIngestError(f"{source} 不是严格 UTF-8：{error}") from error
    if text.encode("utf-8", errors="strict") != data:
        raise PresidentialIngestError(f"{source} 的 UTF-8 往返字节不一致")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != PRESIDENTIAL_HEADERS:
        raise PresidentialIngestError(
            f"{source} 表头漂移：实际 {reader.fieldnames!r}，预期 {list(PRESIDENTIAL_HEADERS)!r}"
        )

    rows: list[dict[str, Any]] = []
    for raw in reader:
        line = reader.line_num
        if None in raw:
            raise PresidentialIngestError(f"{source} 第 {line} 行存在超出表头的字段")
        cycle = _integer(raw["year"], "year", line)
        if cycle not in PRESIDENTIAL_CYCLES:
            raise PresidentialIngestError(f"来源第 {line} 行 year 不在固定总统周期：{cycle}")
        state = (raw["state_po"] or "").strip()
        if state not in STATE_EQUIVALENTS:
            raise PresidentialIngestError(f"来源第 {line} 行 state_po 未登记：{state!r}")
        if raw["office"] != "US President":
            raise PresidentialIngestError(f"来源第 {line} 行 office 漂移：{raw['office']!r}")
        if not (raw["version"] or "").strip():
            raise PresidentialIngestError(f"来源第 {line} 行缺少 version")
        rows.append(
            {
                "source_line": line,
                "cycle": cycle,
                "state": state,
                "state_name": raw["state"],
                "state_fips": _integer(raw["state_fips"], "state_fips", line),
                "state_cen": _integer(raw["state_cen"], "state_cen", line),
                "state_ic": _integer(raw["state_ic"], "state_ic", line),
                "office": "PRESIDENT",
                "candidate": _optional_text(raw["candidate"]),
                "raw_party": _optional_text(raw["party"]),
                "writein": _boolean(raw["writein"], "writein", line),
                "candidate_votes": _integer(raw["candidatevotes"], "candidatevotes", line),
                "source_total_votes": _integer(raw["totalvotes"], "totalvotes", line),
                "version": raw["version"],
                "notes": raw["notes"],
            }
        )
    return rows, {
        "codec": "utf-8",
        "roundtrip_bytes_equal": True,
        "source_bytes": len(data),
        "source_rows": len(rows),
    }


def _named_groups(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        candidate = row["candidate"]
        if candidate is not None:
            groups[_identity(str(candidate))].append(row)
    return groups


def _candidate_record(identity: str, lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(lines, key=lambda row: int(row["source_line"]))
    return {
        "candidate_identity": identity,
        "candidate": ordered[0]["candidate"],
        "raw_candidate_names": sorted({str(row["candidate"]) for row in ordered}),
        "raw_parties": sorted(
            {str(row["raw_party"]) for row in ordered if row["raw_party"] is not None}
        ),
        "votes": sum(int(row["candidate_votes"]) for row in ordered),
        "source_lines": [int(row["source_line"]) for row in ordered],
        "line_count": len(ordered),
        "writein_any": any(bool(row["writein"]) for row in ordered),
    }


def _select_major_candidate(
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    party_labels: set[str],
    party_name: str,
) -> tuple[str, dict[str, Any]]:
    identities: list[str] = []
    for identity, lines in groups.items():
        candidate = str(lines[0]["candidate"])
        if _identity(candidate) == "other":
            continue
        if any(row["raw_party"] in party_labels for row in lines):
            identities.append(identity)
    identities.sort()
    if len(identities) != 1:
        raise PresidentialIngestError(
            f"{party_name} 候选身份必须唯一，实际 {len(identities)}：{identities}"
        )
    identity = identities[0]
    return identity, _candidate_record(identity, groups[identity])


def normalize_presidential_results(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_path: str = "data/raw/medsl-president-1976-2016/1976-2016-president.csv",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """生成 561 个州届结果，并逐州届审计每个原始 ``totalvotes``。"""

    by_state_cycle: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_state_cycle[(int(row["cycle"]), str(row["state"]))].append(row)

    results: list[dict[str, Any]] = []
    duplicate_groups = 0
    major_fusion_groups = 0
    selected_major_candidate_fusion_groups = 0
    fusion_state_cycles: set[tuple[int, str]] = set()
    total_anomalies: list[dict[str, Any]] = []

    for (cycle, state), lines in sorted(by_state_cycle.items()):
        ordered = sorted(lines, key=lambda row: int(row["source_line"]))
        groups = _named_groups(ordered)
        duplicate_groups += sum(len(group) > 1 for group in groups.values())
        # “主要党 fusion 组”的全源审计按原始党派标签计数；其中 MD 2004
        # 的 candidate=Other 带 democrat 标签，但不能据此冒充民主党候选。
        major_fusion_groups += sum(
            len(group) > 1
            and any(
                row["raw_party"] in DEMOCRATIC_PARTIES | REPUBLICAN_PARTIES
                for row in group
            )
            for group in groups.values()
        )
        democratic_identity, democratic = _select_major_candidate(
            groups, DEMOCRATIC_PARTIES, "民主党"
        )
        republican_identity, republican = _select_major_candidate(
            groups, REPUBLICAN_PARTIES, "共和党"
        )
        if democratic_identity == republican_identity:
            raise PresidentialIngestError(f"{cycle}-{state} 民主/共和候选身份冲突")
        selected = (democratic, republican)
        selected_fusion = sum(record["line_count"] > 1 for record in selected)
        selected_major_candidate_fusion_groups += selected_fusion
        if selected_fusion:
            fusion_state_cycles.add((cycle, state))

        candidate_sum = sum(int(row["candidate_votes"]) for row in ordered)
        totals = sorted({int(row["source_total_votes"]) for row in ordered})
        deltas = {str(total): candidate_sum - total for total in totals}
        conserving = len(totals) == 1 and deltas[str(totals[0])] == 0
        if not conserving:
            total_anomalies.append(
                {
                    "cycle": cycle,
                    "state": state,
                    "source_lines": [int(row["source_line"]) for row in ordered],
                    "candidate_votes_sum": candidate_sum,
                    "source_total_values": totals,
                    "delta_by_source_total": deltas,
                }
            )
        denominator = democratic["votes"] + republican["votes"]
        if denominator <= 0:
            raise PresidentialIngestError(f"{cycle}-{state} 两党票分母非正")
        margin = 100.0 * (democratic["votes"] - republican["votes"]) / denominator
        if not math.isfinite(margin):
            raise PresidentialIngestError(f"{cycle}-{state} 两党边际非有限数")

        result = {
            "schema_version": "1.0",
            "office": "PRESIDENT",
            "cycle": cycle,
            "state": state,
            "state_name": ordered[0]["state_name"],
            "state_fips": ordered[0]["state_fips"],
            "state_cen": ordered[0]["state_cen"],
            "state_ic": ordered[0]["state_ic"],
            "source_rows": [
                {
                    "source_line": int(row["source_line"]),
                    "candidate": row["candidate"],
                    "raw_party": row["raw_party"],
                    "writein": bool(row["writein"]),
                    "candidate_votes": int(row["candidate_votes"]),
                    "source_total_votes": int(row["source_total_votes"]),
                    "version": str(row["version"]),
                    "notes": str(row["notes"]),
                }
                for row in ordered
            ],
            "source_row_count": len(ordered),
            "candidate_votes_sum": candidate_sum,
            "normalized_total_votes": candidate_sum,
            "normalized_vote_conservation_delta": 0,
            "source_total_values": totals,
            "delta_by_source_total": deltas,
            "source_total_conserving": conserving,
            "source_total_values_inconsistent": len(totals) != 1,
            "named_candidate_groups": [
                _candidate_record(identity, group)
                for identity, group in sorted(
                    groups.items(), key=lambda item: min(int(row["source_line"]) for row in item[1])
                )
            ],
            "duplicate_named_group_count": sum(len(group) > 1 for group in groups.values()),
            "major_party_fusion_group_count": selected_fusion,
            "democratic_candidate": democratic,
            "republican_candidate": republican,
            "democratic_votes": democratic["votes"],
            "republican_votes": republican["votes"],
            "two_party_margin": margin,
            "archival_reconstruction": True,
            "strict_original_vintage_available": False,
            "source": {
                "dataset_id": DATASET_ID,
                "source_path": source_path,
                "source_lines": [int(row["source_line"]) for row in ordered],
                "csv_versions": sorted({str(row["version"]) for row in ordered}),
                "git_blob_sha1": GIT_BLOB_SHA1,
                "doi": DOI,
            },
        }
        results.append(result)

    cycles = []
    for cycle in PRESIDENTIAL_CYCLES:
        cycle_rows = [row for row in results if row["cycle"] == cycle]
        cycles.append(
            {
                "cycle": cycle,
                "state_cycle_count": len(cycle_rows),
                "states": sorted(row["state"] for row in cycle_rows),
                "source_row_count": sum(row["source_row_count"] for row in cycle_rows),
                "source_total_anomaly_count": sum(
                    not row["source_total_conserving"] for row in cycle_rows
                ),
            }
        )
    reconciliation = {
        "schema_version": "1.0",
        "source_row_count": len(rows),
        "state_cycle_count": len(results),
        "cycles": cycles,
        "duplicate_named_candidate_groups": duplicate_groups,
            "major_party_fusion_groups": major_fusion_groups,
        "selected_major_candidate_fusion_groups": selected_major_candidate_fusion_groups,
        "fusion_affected_state_cycle_count": len(fusion_state_cycles),
        "fusion_affected_state_cycles": [
            {"cycle": cycle, "state": state}
            for cycle, state in sorted(fusion_state_cycles)
        ],
        "source_total_conserving_state_cycles": sum(
            row["source_total_conserving"] for row in results
        ),
        "source_total_anomaly_count": len(total_anomalies),
        "source_total_anomalies": total_anomalies,
        "all_major_party_candidates_unique": True,
        "all_two_party_margins_finite": all(
            math.isfinite(row["two_party_margin"]) for row in results
        ),
        "dc_preserved": any(row["state"] == "DC" for row in results),
        "archival_reconstruction": True,
        "strict_original_vintage_available": False,
        "contains_2026_probability": False,
    }
    return results, reconciliation


def build_senate_state_baselines(
    results: Sequence[Mapping[str, Any]],
    *,
    modern_mirror_retrieved_at: str,
) -> list[dict[str, Any]]:
    """从 t-2 总统结果生成 11×50 州的 Senate 结构基线。"""

    _parse_timestamp(modern_mirror_retrieved_at, "modern_mirror_retrieved_at")
    by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    for row in results:
        key = (int(row["cycle"]), str(row["state"]))
        if key in by_key:
            raise PresidentialIngestError(f"总统 state-cycle 重复：{key}")
        by_key[key] = row

    baselines: list[dict[str, Any]] = []
    for target_cycle in SENATE_TARGET_CYCLES:
        source_cycle = target_cycle - 2
        forecast_as_of = f"{target_cycle}-10-01T23:59:59Z"
        available_at = f"{source_cycle + 1}-12-31T23:59:59Z"
        if _parse_timestamp(available_at, "available_at") > _parse_timestamp(
            forecast_as_of, "forecast_as_of"
        ):
            raise PresidentialIngestError(f"{target_cycle} 的事实可知时间晚于预测截点")
        for state in STATE_CODES:
            source = by_key.get((source_cycle, state))
            if source is None:
                raise PresidentialIngestError(f"缺少总统来源：{source_cycle}-{state}")
            margin = float(source["two_party_margin"])
            if not math.isfinite(margin):
                raise PresidentialIngestError(f"{source_cycle}-{state} 总统边际非有限数")
            baselines.append(
                {
                    "schema_version": "1.0",
                    "feature_id": FEATURE_ID,
                    "transform_id": TRANSFORM_ID,
                    "office": "SENATE",
                    "target_cycle": target_cycle,
                    "state": state,
                    "partisan_baseline_margin": margin,
                    "presidential_source_cycle": source_cycle,
                    "forecast_as_of": forecast_as_of,
                    "available_at": available_at,
                    "fact_available_at": available_at,
                    "fact_availability_basis": (
                        "conservative_upper_bound_end_of_year_after_presidential_election"
                    ),
                    "vintage": CSV_VINTAGE,
                    "archival_reconstruction": True,
                    "strict_original_vintage_available": False,
                    "modern_mirror_published_at": MODERN_MIRROR_PUBLISHED_AT,
                    "modern_mirror_retrieved_at": modern_mirror_retrieved_at,
                    "democratic_candidate": source["democratic_candidate"],
                    "republican_candidate": source["republican_candidate"],
                    "source": {
                        "dataset_id": DATASET_ID,
                        "source_path": source["source"]["source_path"],
                        "source_lines": source["source"]["source_lines"],
                        "git_blob_sha1": GIT_BLOB_SHA1,
                        "csv_versions": source["source"]["csv_versions"],
                        "doi": DOI,
                    },
                }
            )
    return baselines


def assert_presidential_reconciliation_ready(reconciliation: Mapping[str, Any]) -> None:
    """对合同中的固定全源计数执行硬闸。"""

    expected = {
        "source_row_count": 3740,
        "state_cycle_count": 561,
        "duplicate_named_candidate_groups": 42,
        "major_party_fusion_groups": 24,
        "fusion_affected_state_cycle_count": 12,
        "source_total_conserving_state_cycles": 560,
        "source_total_anomaly_count": 1,
    }
    for field, value in expected.items():
        if reconciliation.get(field) != value:
            raise PresidentialIngestError(
                f"总统对账 {field} 漂移：{reconciliation.get(field)!r} != {value}"
            )
    cycles = reconciliation.get("cycles")
    if not isinstance(cycles, list) or [row.get("cycle") for row in cycles] != list(
        PRESIDENTIAL_CYCLES
    ):
        raise PresidentialIngestError("总统周期集合漂移")
    for cycle in cycles:
        if cycle.get("state_cycle_count") != 51 or cycle.get("states") != list(
            STATE_EQUIVALENTS
        ):
            raise PresidentialIngestError(f"{cycle.get('cycle')} 未覆盖 50 州加 DC")
    anomalies = reconciliation.get("source_total_anomalies")
    if not isinstance(anomalies, list) or len(anomalies) != 1:
        raise PresidentialIngestError("总统 total 异常清单必须且只能包含 NE 2000")
    anomaly = anomalies[0]
    if (
        anomaly.get("cycle") != 2000
        or anomaly.get("state") != "NE"
        or anomaly.get("source_total_values") != [697019, 967019]
        or anomaly.get("candidate_votes_sum") != 697019
        or anomaly.get("delta_by_source_total") != {"697019": 0, "967019": -270000}
    ):
        raise PresidentialIngestError("NE 2000 total 异常细节漂移")
    for field in (
        "all_major_party_candidates_unique",
        "all_two_party_margins_finite",
        "dc_preserved",
        "archival_reconstruction",
    ):
        if reconciliation.get(field) is not True:
            raise PresidentialIngestError(f"总统对账硬闸未通过：{field}")
    if reconciliation.get("strict_original_vintage_available") is not False:
        raise PresidentialIngestError("不得声称保存了原始历史 vintage")


def assert_senate_baselines_ready(rows: Sequence[Mapping[str, Any]]) -> None:
    """验证 550 行特征账本的唯一性、时距与时点可用性。"""

    if len(rows) != 550:
        raise PresidentialIngestError(f"Senate 州基线必须为 550 行，实际 {len(rows)}")
    seen: set[tuple[int, str]] = set()
    counts: Counter[int] = Counter()
    for row in rows:
        if row.get("office") != "SENATE":
            raise PresidentialIngestError("Senate 基线混入非 Senate 行")
        target_cycle = int(row["target_cycle"])
        state = str(row["state"])
        key = (target_cycle, state)
        if key in seen:
            raise PresidentialIngestError(f"Senate 州基线重复：{key}")
        seen.add(key)
        counts[target_cycle] += 1
        if target_cycle not in SENATE_TARGET_CYCLES or state not in STATE_CODES:
            raise PresidentialIngestError(f"Senate 州基线周期/州未登记：{key}")
        if int(row["presidential_source_cycle"]) != target_cycle - 2:
            raise PresidentialIngestError(f"{key} 总统 source_cycle 不是 t-2")
        if row.get("feature_id") != FEATURE_ID or row.get("transform_id") != TRANSFORM_ID:
            raise PresidentialIngestError(f"{key} 特征或变换标识漂移")
        margin = float(row["partisan_baseline_margin"])
        if not math.isfinite(margin) or not -100.0 <= margin <= 100.0:
            raise PresidentialIngestError(f"{key} 基线边际非法")
        if not str(row.get("vintage", "")).strip():
            raise PresidentialIngestError(f"{key} 缺少 vintage")
        if _parse_timestamp(str(row["available_at"]), "available_at") > _parse_timestamp(
            str(row["forecast_as_of"]), "forecast_as_of"
        ):
            raise PresidentialIngestError(f"{key} available_at 晚于 forecast_as_of")
        if row.get("fact_available_at") != row.get("available_at"):
            raise PresidentialIngestError(f"{key} fact_available_at 与 available_at 不一致")
        if row.get("archival_reconstruction") is not True:
            raise PresidentialIngestError(f"{key} 未标档案重建")
        if row.get("strict_original_vintage_available") is not False:
            raise PresidentialIngestError(f"{key} 错误声称原始 vintage 可用")
        source = row.get("source")
        if not isinstance(source, Mapping) or not source.get("source_lines"):
            raise PresidentialIngestError(f"{key} 缺少来源行 lineage")
    if set(counts) != set(SENATE_TARGET_CYCLES) or set(counts.values()) != {50}:
        raise PresidentialIngestError(f"Senate 州基线逐届覆盖漂移：{dict(counts)}")


def build_all(
    csv_path: str | Path,
    *,
    modern_mirror_retrieved_at: str,
    source_path: str = "data/raw/medsl-president-1976-2016/1976-2016-president.csv",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_rows, encoding = read_presidential_csv(csv_path)
    results, reconciliation = normalize_presidential_results(source_rows, source_path=source_path)
    assert_presidential_reconciliation_ready(reconciliation)
    baselines = build_senate_state_baselines(
        results, modern_mirror_retrieved_at=modern_mirror_retrieved_at
    )
    assert_senate_baselines_ready(baselines)
    reconciliation = dict(reconciliation)
    reconciliation["source_encoding_audit"] = encoding
    reconciliation["senate_baselines"] = {
        "row_count": len(baselines),
        "target_cycles": list(SENATE_TARGET_CYCLES),
        "states_per_cycle": 50,
        "dc_excluded_from_senate_mapping": True,
        "transform_id": TRANSFORM_ID,
        "formula": "100 * (democratic_votes - republican_votes) / (democratic_votes + republican_votes)",
        "fact_time_separate_from_modern_mirror_time": True,
    }
    return results, baselines, reconciliation


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) for row in rows)


def write_processed(
    results: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
    *,
    results_path: str | Path,
    baselines_path: str | Path,
    reconciliation_path: str | Path,
) -> None:
    outputs = (
        (Path(results_path), jsonl_bytes(results)),
        (Path(baselines_path), jsonl_bytes(baselines)),
        (Path(reconciliation_path), _json_bytes(reconciliation)),
    )
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise PresidentialIngestError(f"{path} 第 {line_number} 行 JSON 非法") from error
        if not isinstance(value, dict):
            raise PresidentialIngestError(f"{path} 第 {line_number} 行必须是对象")
        rows.append(value)
    return rows


def _xlsx_column(address: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[0-9]+", address.upper())
    if match is None:
        raise PresidentialIngestError(f"OOXML 单元格地址非法：{address!r}")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except (KeyError, ET.ParseError) as error:
        raise PresidentialIngestError("FEC 2020 工作簿缺少合法 sharedStrings.xml") from error
    return tuple(
        "".join(node.text or "" for node in item.iter(f"{{{_XLSX_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_XLSX_MAIN_NS}}}si")
    )


def _xlsx_sheet_targets(archive: zipfile.ZipFile) -> tuple[dict[str, str], tuple[str, ...]]:
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError) as error:
        raise PresidentialIngestError("FEC 2020 工作簿关系结构非法") from error
    relation_map = {
        item.attrib.get("Id", ""): item.attrib.get("Target", "") for item in relations
    }
    targets: dict[str, str] = {}
    names: list[str] = []
    sheets = workbook.find(f"{{{_XLSX_MAIN_NS}}}sheets")
    for sheet in sheets if sheets is not None else ():
        name = sheet.attrib.get("name", "")
        names.append(name)
        relation_id = sheet.attrib.get(f"{{{_XLSX_REL_NS}}}id", "")
        target = relation_map.get(relation_id, "").lstrip("/")
        if target and not target.startswith("xl/"):
            target = "xl/" + target
        targets[name] = target
    required = {
        FEC_2020_RESULTS_SHEET,
        FEC_2020_NATIONAL_SHEET,
        FEC_2020_STATE_SUMMARY_SHEET,
    }
    if any(not targets.get(name) for name in required):
        raise PresidentialIngestError(
            f"FEC 2020 工作簿缺少总统解析 sheet：{sorted(required - set(targets))}"
        )
    return targets, tuple(names)


def _xlsx_all_sheet_targets(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, str], tuple[str, ...]]:
    """读取通用 OOXML sheet 目录，不植入任何年份的列位置假设。"""

    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError) as error:
        raise PresidentialIngestError("FEC 工作簿关系结构非法") from error
    relation_map = {
        item.attrib.get("Id", ""): item.attrib.get("Target", "") for item in relations
    }
    targets: dict[str, str] = {}
    names: list[str] = []
    sheets = workbook.find(f"{{{_XLSX_MAIN_NS}}}sheets")
    for sheet in sheets if sheets is not None else ():
        name = sheet.attrib.get("name", "")
        relation_id = sheet.attrib.get(f"{{{_XLSX_REL_NS}}}id", "")
        target = relation_map.get(relation_id, "").lstrip("/")
        if target and not target.startswith("xl/"):
            target = "xl/" + target
        if not name or not target or name in targets:
            raise PresidentialIngestError("FEC 工作簿 sheet 目录缺失或重复")
        names.append(name)
        targets[name] = target
    if not names:
        raise PresidentialIngestError("FEC 工作簿 sheet 清单为空")
    return targets, tuple(names)


def _xlsx_rows(
    archive: zipfile.ZipFile,
    target: str,
    shared_strings: Sequence[str],
) -> tuple[tuple[int, dict[int, str]], ...]:
    try:
        root = ET.fromstring(archive.read(target))
    except (KeyError, ET.ParseError) as error:
        raise PresidentialIngestError(f"FEC 2020 sheet XML 非法：{target}") from error
    sheet_data = root.find(f"{{{_XLSX_MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise PresidentialIngestError(f"FEC 2020 sheet 缺少 sheetData：{target}")
    output: list[tuple[int, dict[int, str]]] = []
    seen_rows: set[int] = set()
    for row in sheet_data.findall(f"{{{_XLSX_MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r", "0"))
        if row_number <= 0 or row_number in seen_rows:
            raise PresidentialIngestError(f"FEC 2020 sheet 行号重复或非法：{row_number}")
        seen_rows.add(row_number)
        values: dict[int, str] = {}
        for cell in row.findall(f"{{{_XLSX_MAIN_NS}}}c"):
            column = _xlsx_column(cell.attrib.get("r", ""))
            if column in values:
                raise PresidentialIngestError(f"FEC 2020 sheet 单元格重复：{row_number}/{column}")
            cell_type = cell.attrib.get("t")
            value = cell.find(f"{{{_XLSX_MAIN_NS}}}v")
            if cell_type == "inlineStr":
                inline = cell.find(f"{{{_XLSX_MAIN_NS}}}is")
                text = "" if inline is None else "".join(
                    node.text or "" for node in inline.iter(f"{{{_XLSX_MAIN_NS}}}t")
                )
            elif value is None or value.text is None:
                text = ""
            elif cell_type == "s":
                try:
                    text = shared_strings[int(value.text)]
                except (ValueError, IndexError) as error:
                    raise PresidentialIngestError("FEC 2020 sharedStrings 索引非法") from error
            else:
                text = value.text
            values[column] = text
        output.append((row_number, values))
    return tuple(output)


def _xlsx_integer(value: str, field: str) -> int:
    text = value.strip()
    if re.fullmatch(r"[0-9]+", text) is None:
        raise PresidentialIngestError(f"{field} 不是非负整数：{value!r}")
    return int(text)


def _xlsx_column_name(column: int) -> str:
    if column <= 0:
        raise PresidentialIngestError(f"OOXML 列号非法：{column}")
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _xlsx_italic_cells(
    archive: zipfile.ZipFile,
    target: str,
) -> frozenset[tuple[int, int]]:
    """读取单元格字体斜体标记；2024 表注释将其定义为 write-in。"""

    try:
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        sheet = ET.fromstring(archive.read(target))
    except (KeyError, ET.ParseError) as error:
        raise PresidentialIngestError("FEC 2024 样式或 sheet XML 非法") from error
    fonts = styles.find(f"{{{_XLSX_MAIN_NS}}}fonts")
    cell_xfs = styles.find(f"{{{_XLSX_MAIN_NS}}}cellXfs")
    if fonts is None or cell_xfs is None:
        raise PresidentialIngestError("FEC 2024 工作簿缺少字体或单元格样式")
    italic_fonts = {
        index
        for index, font in enumerate(fonts)
        if font.find(f"{{{_XLSX_MAIN_NS}}}i") is not None
    }
    italic_styles = {
        index
        for index, style in enumerate(cell_xfs)
        if int(style.attrib.get("fontId", "0")) in italic_fonts
    }
    output: set[tuple[int, int]] = set()
    for row in sheet.findall(f".//{{{_XLSX_MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r", "0"))
        for cell in row.findall(f"{{{_XLSX_MAIN_NS}}}c"):
            if int(cell.attrib.get("s", "0")) in italic_styles:
                output.add((row_number, _xlsx_column(cell.attrib.get("r", ""))))
    return frozenset(output)


def _fec_candidate_record(identity: str, lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(lines, key=lambda row: int(row["source_line"]))
    return {
        "candidate_identity": identity,
        "candidate": str(ordered[0]["candidate"]),
        "raw_candidate_names": sorted({str(row["candidate"]) for row in ordered}),
        "raw_parties": sorted({str(row["raw_party"]) for row in ordered}),
        "votes": sum(int(row["candidate_votes"]) for row in ordered),
        "source_lines": [int(row["source_line"]) for row in ordered],
        "line_count": len(ordered),
        "writein_any": any(bool(row["writein"]) for row in ordered),
    }


def _fec_state_metadata(existing_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = [row for row in existing_results if int(row.get("cycle", -1)) == 2016]
    if len(latest) != 51 or {str(row.get("state")) for row in latest} != set(STATE_EQUIVALENTS):
        raise PresidentialIngestError("追加 2020 前，2016 州元数据必须精确覆盖 50 州加 DC")
    return {
        str(row["state"]): {
            "state_name": str(row["state_name"]),
            "state_fips": int(row["state_fips"]),
            "state_cen": int(row["state_cen"]),
            "state_ic": int(row["state_ic"]),
        }
        for row in latest
    }


def parse_fec_presidential_2020(
    workbook_bytes: bytes,
    existing_results: Sequence[Mapping[str, Any]],
    *,
    source_path: str = FEC_2020_SOURCE_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """从封存 FEC 工作簿解析 2020 总统州级结果并执行全部资格闸。"""

    if not isinstance(workbook_bytes, bytes):
        raise PresidentialIngestError("FEC 2020 工作簿必须以 bytes 输入")
    digest = hashlib.sha256(workbook_bytes).hexdigest()
    if len(workbook_bytes) != FEC_2020_BYTES or digest != FEC_2020_SHA256:
        raise PresidentialIngestError("FEC 2020 工作簿字节数或 SHA-256 漂移")
    state_metadata = _fec_state_metadata(existing_results)
    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_bytes))
    except zipfile.BadZipFile as error:
        raise PresidentialIngestError("FEC 2020 工作簿不是合法 OOXML ZIP") from error
    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise PresidentialIngestError(f"FEC 2020 工作簿 CRC 失败：{bad_member}")
        shared_strings = _xlsx_shared_strings(archive)
        targets, sheet_names = _xlsx_sheet_targets(archive)
        result_rows = _xlsx_rows(archive, targets[FEC_2020_RESULTS_SHEET], shared_strings)
        national_rows = _xlsx_rows(archive, targets[FEC_2020_NATIONAL_SHEET], shared_strings)
        summary_rows = _xlsx_rows(
            archive, targets[FEC_2020_STATE_SUMMARY_SHEET], shared_strings
        )

    header = dict(result_rows).get(1, {})
    expected_header = {
        2: "FEC ID",
        3: "STATE",
        4: "STATE ABBREVIATION",
        8: "LAST NAME,  FIRST",
        9: "TOTAL VOTES",
        10: "PARTY",
        11: "GENERAL RESULTS",
        13: "TOTAL VOTES #",
        16: "WINNER INDICATOR",
    }
    if any(header.get(column) != text for column, text in expected_header.items()):
        raise PresidentialIngestError("FEC 2020 总统结果表头漂移")

    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    state_totals: dict[str, tuple[int, int]] = {}
    all_states_total: int | None = None
    for row_number, cells in result_rows[1:]:
        state = cells.get(4, "").strip()
        if state == "All States" and cells.get(9, "").strip() == "Total All States:":
            all_states_total = _xlsx_integer(cells.get(13, ""), "FEC 总州票")
            continue
        if state not in STATE_EQUIVALENTS:
            continue
        if cells.get(9, "").strip() == "Total State Votes:":
            if state in state_totals:
                raise PresidentialIngestError(f"2020-{state} 州总票行重复")
            state_totals[state] = (
                row_number,
                _xlsx_integer(cells.get(13, ""), f"2020-{state} 州总票"),
            )
            continue
        votes_text = cells.get(11, "").strip()
        candidate = " ".join(cells.get(8, "").split())
        if not votes_text:
            continue
        if not candidate:
            raise PresidentialIngestError(f"2020-{state} 第 {row_number} 行有票数但无候选人")
        party = " ".join(cells.get(10, "").split()).upper()
        if not party:
            if state == "NV" and _identity(candidate) == "none of these candidates":
                party = "NONE_OF_THESE"
            else:
                raise PresidentialIngestError(f"2020-{state} 第 {row_number} 行缺党籍标签")
        grouped_rows[state].append(
            {
                "candidate": candidate,
                "candidate_votes": _xlsx_integer(votes_text, f"2020-{state}/{candidate} 票数"),
                "fec_id": cells.get(2, "").strip(),
                "raw_party": party,
                "source_line": row_number,
                "winner_indicator": cells.get(16, "").strip(),
                "writein": party == "W" or _identity(candidate) == "scattered",
            }
        )

    if set(grouped_rows) != set(STATE_EQUIVALENTS) or set(state_totals) != set(
        STATE_EQUIVALENTS
    ):
        raise PresidentialIngestError("FEC 2020 总统结果未精确覆盖 50 州加 DC")
    if all_states_total is None:
        raise PresidentialIngestError("FEC 2020 总统结果缺少 Total All States")

    summary_by_state: dict[str, dict[str, int]] = {}
    for row_number, cells in summary_rows:
        raw_state = cells.get(1, "").strip()
        state = raw_state[:-1] if raw_state in {"ME*", "NE*"} else raw_state
        if state not in STATE_EQUIVALENTS:
            continue
        summary_by_state[state] = {
            "democratic_votes": _xlsx_integer(cells.get(4, ""), f"summary {state} D"),
            "republican_votes": _xlsx_integer(cells.get(5, ""), f"summary {state} R"),
            "other_votes": _xlsx_integer(cells.get(6, ""), f"summary {state} other"),
            "total_votes": _xlsx_integer(cells.get(7, ""), f"summary {state} total"),
            "source_line": row_number,
        }
    if set(summary_by_state) != set(STATE_EQUIVALENTS):
        raise PresidentialIngestError("FEC 2020 内部州汇总表未精确覆盖 50 州加 DC")

    national_candidate_totals: dict[str, int] = {}
    for _, cells in national_rows:
        label = cells.get(1, "").strip()
        if label.startswith("Joseph R. Biden"):
            national_candidate_totals["DEMOCRATIC"] = _xlsx_integer(
                cells.get(2, ""), "全国 Biden 票数"
            )
        elif label.startswith("Donald J. Trump"):
            national_candidate_totals["REPUBLICAN"] = _xlsx_integer(
                cells.get(2, ""), "全国 Trump 票数"
            )
    if set(national_candidate_totals) != {"DEMOCRATIC", "REPUBLICAN"}:
        raise PresidentialIngestError("FEC 2020 全国候选人汇总缺少 D/R")

    results: list[dict[str, Any]] = []
    excluded_worksheet_rows: list[dict[str, Any]] = []
    split_electoral_winner_indicators: list[dict[str, Any]] = []
    for state in STATE_EQUIVALENTS:
        raw_lines = sorted(grouped_rows[state], key=lambda row: int(row["source_line"]))
        total_row, state_total = state_totals[state]
        included = list(raw_lines)
        raw_sum = sum(int(row["candidate_votes"]) for row in included)
        if raw_sum != state_total:
            removable = [
                row
                for row in included
                if _identity(str(row["candidate"])) == "scattered"
                and raw_sum - int(row["candidate_votes"]) == state_total
            ]
            if len(removable) != 1:
                raise PresidentialIngestError(
                    f"2020-{state} 候选人票和无法与州总票唯一对齐：{raw_sum} != {state_total}"
                )
            excluded = removable[0]
            included.remove(excluded)
            excluded_worksheet_rows.append(
                {
                    "candidate": excluded["candidate"],
                    "party": excluded["raw_party"],
                    "reason": "worksheet_duplicate_scattered_row_outside_reported_state_total",
                    "source_line": excluded["source_line"],
                    "state": state,
                    "votes": excluded["candidate_votes"],
                }
            )
        candidate_sum = sum(int(row["candidate_votes"]) for row in included)
        if candidate_sum != state_total:
            raise PresidentialIngestError(f"2020-{state} 候选人票数不守恒")

        by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in included:
            by_identity[_identity(str(line["candidate"]))].append(line)
        records = {
            identity: _fec_candidate_record(identity, lines)
            for identity, lines in by_identity.items()
        }
        democratic_ids = sorted(
            identity
            for identity, lines in by_identity.items()
            if any(str(line["raw_party"]) in {"D", "DFL", "DNL"} for line in lines)
        )
        republican_ids = sorted(
            identity
            for identity, lines in by_identity.items()
            if any(str(line["raw_party"]) == "R" for line in lines)
        )
        if len(democratic_ids) != 1 or len(republican_ids) != 1:
            raise PresidentialIngestError(f"2020-{state} D/R 候选身份不唯一")
        winner_ids = {
            identity
            for identity, lines in by_identity.items()
            if any(str(line["winner_indicator"]).startswith("W") for line in lines)
        }
        maximum_votes = max(record["votes"] for record in records.values())
        maximum_ids = {
            identity for identity, record in records.items() if record["votes"] == maximum_votes
        }
        if len(maximum_ids) != 1:
            raise PresidentialIngestError(f"2020-{state} 州级普选最高票不唯一")
        if winner_ids != maximum_ids:
            raise PresidentialIngestError(f"2020-{state} 唯一胜者标记与票数不一致")
        if state in {"ME", "NE"}:
            split_electoral_winner_indicators.append(
                {
                    "popular_vote_winner": next(iter(maximum_ids)),
                    "state": state,
                    "summary_state_label": f"{state}*",
                    "worksheet_winner_indicator_candidates": sorted(winner_ids),
                }
            )
        democratic = records[democratic_ids[0]]
        republican = records[republican_ids[0]]
        denominator = democratic["votes"] + republican["votes"]
        if denominator <= 0:
            raise PresidentialIngestError(f"2020-{state} 两党票分母非正")
        margin = 100.0 * (democratic["votes"] - republican["votes"]) / denominator

        summary = summary_by_state[state]
        if (
            summary["democratic_votes"] != democratic["votes"]
            or summary["republican_votes"] != republican["votes"]
            or summary["total_votes"] != state_total
            or summary["other_votes"] != state_total - democratic["votes"] - republican["votes"]
        ):
            raise PresidentialIngestError(f"2020-{state} 与工作簿内部州汇总表不一致")
        metadata = state_metadata[state]
        source_rows = [
            {
                "candidate": line["candidate"],
                "candidate_votes": line["candidate_votes"],
                "notes": f"{FEC_2020_RESULTS_SHEET} row {line['source_line']}",
                "raw_party": line["raw_party"],
                "source_line": line["source_line"],
                "source_total_votes": state_total,
                "version": "FEC_FEDERAL_ELECTIONS_2020_FINAL",
                "writein": line["writein"],
            }
            for line in included
        ]
        results.append(
            {
                "archival_reconstruction": True,
                "candidate_votes_sum": candidate_sum,
                "cycle": 2020,
                "delta_by_source_total": {str(state_total): 0},
                "democratic_candidate": democratic,
                "democratic_votes": democratic["votes"],
                "duplicate_named_group_count": sum(
                    len(lines) > 1 for lines in by_identity.values()
                ),
                "major_party_fusion_group_count": sum(
                    records[identity]["line_count"] > 1
                    for identity in (democratic_ids[0], republican_ids[0])
                ),
                "named_candidate_groups": [
                    records[identity]
                    for identity in sorted(
                        records,
                        key=lambda value: min(
                            int(row["source_line"]) for row in by_identity[value]
                        ),
                    )
                ],
                "normalized_total_votes": state_total,
                "normalized_vote_conservation_delta": 0,
                "office": "PRESIDENT",
                "republican_candidate": republican,
                "republican_votes": republican["votes"],
                "schema_version": "1.0",
                "source": {
                    "dataset_id": FEC_2020_DATASET_ID,
                    "source_path": source_path,
                    "source_lines": [int(row["source_line"]) for row in included],
                    "worksheet": FEC_2020_RESULTS_SHEET,
                    "workbook_bytes": len(workbook_bytes),
                    "workbook_sha256": digest,
                    "state_summary_line": summary["source_line"],
                    "state_total_line": total_row,
                    "worksheet_excluded_rows": [
                        row for row in excluded_worksheet_rows if row["state"] == state
                    ],
                },
                "source_row_count": len(source_rows),
                "source_rows": source_rows,
                "source_total_conserving": True,
                "source_total_values": [state_total],
                "source_total_values_inconsistent": False,
                "state": state,
                "state_cen": metadata["state_cen"],
                "state_fips": metadata["state_fips"],
                "state_ic": metadata["state_ic"],
                "state_name": metadata["state_name"],
                "strict_original_vintage_available": False,
                "two_party_margin": margin,
            }
        )

    results.sort(key=lambda row: str(row["state"]))
    democratic_total = sum(int(row["democratic_votes"]) for row in results)
    republican_total = sum(int(row["republican_votes"]) for row in results)
    total_votes = sum(int(row["candidate_votes_sum"]) for row in results)
    if democratic_total != national_candidate_totals["DEMOCRATIC"]:
        raise PresidentialIngestError("FEC 2020 D 州合计与全国候选人汇总不一致")
    if republican_total != national_candidate_totals["REPUBLICAN"]:
        raise PresidentialIngestError("FEC 2020 R 州合计与全国候选人汇总不一致")
    if total_votes != all_states_total:
        raise PresidentialIngestError("FEC 2020 州总票合计与 Total All States 不一致")

    qualifications = {
        "jurisdictions_50_states_plus_dc": len(results) == 51,
        "unique_state_winner": True,
        "candidate_vote_conservation": all(
            row["candidate_votes_sum"] == row["normalized_total_votes"] for row in results
        ),
        "party_labels_present": all(
            source["raw_party"]
            for row in results
            for source in row["source_rows"]
        ),
        "state_summary_reconciled": True,
        "national_candidate_summary_reconciled": True,
        "national_total_reconciled": True,
    }
    if not all(qualifications.values()):
        raise PresidentialIngestError("FEC 2020 总统解析资格闸未全部通过")
    reconciliation = {
        "schema_version": "1.0",
        "contract_id": "LH-061",
        "cycle": 2020,
        "source": {
            "path": source_path,
            "bytes": len(workbook_bytes),
            "sha256": digest,
            "sheet_names": list(sheet_names),
            "results_sheet": FEC_2020_RESULTS_SHEET,
            "state_summary_sheet": FEC_2020_STATE_SUMMARY_SHEET,
            "national_summary_sheet": FEC_2020_NATIONAL_SHEET,
        },
        "state_cycle_count": len(results),
        "states": [str(row["state"]) for row in results],
        "candidate_source_row_count": sum(int(row["source_row_count"]) for row in results),
        "worksheet_excluded_rows": excluded_worksheet_rows,
        "worksheet_excluded_row_count": len(excluded_worksheet_rows),
        "explicit_party_annotation_rules": [
            {
                "annotation": "NONE_OF_THESE",
                "candidate": "None of These Candidates",
                "reason": "Nevada 非候选选择项；工作簿 PARTY 单元格为空",
                "source_line": 407,
                "state": "NV",
            }
        ],
        "split_electoral_winner_indicators": split_electoral_winner_indicators,
        "national_totals": {
            "democratic_votes": democratic_total,
            "republican_votes": republican_total,
            "all_candidate_votes": total_votes,
        },
        "qualification_checks": qualifications,
        "all_qualification_checks_passed": all(qualifications.values()),
        "contains_2026_probability": False,
    }
    return results, reconciliation


def _fec_state_metadata_at_cycle(
    existing_results: Sequence[Mapping[str, Any]],
    cycle: int,
) -> dict[str, dict[str, Any]]:
    selected = [row for row in existing_results if int(row.get("cycle", -1)) == cycle]
    if len(selected) != 51 or {str(row.get("state")) for row in selected} != set(
        STATE_EQUIVALENTS
    ):
        raise PresidentialIngestError(
            f"追加 2024 前，{cycle} 州元数据必须精确覆盖 50 州加 DC"
        )
    return {
        str(row["state"]): {
            "state_name": str(row["state_name"]),
            "state_fips": int(row["state_fips"]),
            "state_cen": int(row["state_cen"]),
            "state_ic": int(row["state_ic"]),
        }
        for row in selected
    }


def _identify_fec_2024_layout(header: Mapping[int, str]) -> dict[str, Any]:
    """只按实际表头文字识别列；列号变化不会改变解析语义。"""

    normalized: dict[str, int] = {}
    for column, value in header.items():
        label = " ".join(str(value).upper().split())
        if not label:
            continue
        if label in normalized:
            raise PresidentialIngestError(f"FEC 2024 表头重复：{label}")
        normalized[label] = int(column)
    required = {
        "STATE",
        "ELECTORAL VOTES",
        "ELECTORAL VOTE: TRUMP (R)",
        "ELECTORAL VOTE: HARRIS (D)",
        "HARRIS",
        "TRUMP",
        "TOTAL VOTES",
    }
    missing = sorted(required - set(normalized))
    if missing:
        raise PresidentialIngestError(f"FEC 2024 表头缺少语义列：{missing}")
    non_candidate = {
        "STATE",
        "ELECTORAL VOTES",
        "ELECTORAL VOTE: TRUMP (R)",
        "ELECTORAL VOTE: HARRIS (D)",
        "TOTAL VOTES",
    }
    candidate_columns = tuple(
        (column, label)
        for label, column in sorted(normalized.items(), key=lambda item: item[1])
        if label not in non_candidate
    )
    if len(candidate_columns) < 2:
        raise PresidentialIngestError("FEC 2024 候选人列不足")
    if {label for _, label in candidate_columns}.issuperset({"HARRIS", "TRUMP"}) is False:
        raise PresidentialIngestError("FEC 2024 候选人列未包含 Harris/Trump")
    return {
        "state_column": normalized["STATE"],
        "total_votes_column": normalized["TOTAL VOTES"],
        "candidate_columns": candidate_columns,
        "democratic_column": normalized["HARRIS"],
        "republican_column": normalized["TRUMP"],
        "header_columns": len(normalized),
    }


def _fec_2024_party_label(candidate: str, *, writein: bool) -> str:
    if candidate == "HARRIS":
        return "D"
    if candidate == "TRUMP":
        return "R"
    if candidate == "NONE OF THESE CANDIDATES":
        return "NONE_OF_THESE"
    if writein or candidate == "WRITE-INS (SCATTERED)":
        return "W"
    return "OTHER_OR_INDEPENDENT"


def parse_fec_presidential_2024(
    workbook_bytes: bytes,
    existing_results: Sequence[Mapping[str, Any]],
    *,
    source_path: str = FEC_2024_SOURCE_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """解析 FEC 2024 单表并执行州、候选列、全国合计和官方事实资格闸。"""

    if not isinstance(workbook_bytes, bytes):
        raise PresidentialIngestError("FEC 2024 工作簿必须以 bytes 输入")
    digest = hashlib.sha256(workbook_bytes).hexdigest()
    if len(workbook_bytes) != FEC_2024_BYTES or digest != FEC_2024_SHA256:
        raise PresidentialIngestError("FEC 2024 工作簿字节数或 SHA-256 漂移")
    state_metadata = _fec_state_metadata_at_cycle(existing_results, 2020)
    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_bytes))
    except zipfile.BadZipFile as error:
        raise PresidentialIngestError("FEC 2024 工作簿不是合法 OOXML ZIP") from error
    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise PresidentialIngestError(f"FEC 2024 工作簿 CRC 失败：{bad_member}")
        shared_strings = _xlsx_shared_strings(archive)
        targets, sheet_names = _xlsx_all_sheet_targets(archive)
        if sheet_names != (FEC_2024_RESULTS_SHEET,):
            raise PresidentialIngestError(
                f"FEC 2024 工作簿必须只有官方结果单表：{list(sheet_names)}"
            )
        target = targets[FEC_2024_RESULTS_SHEET]
        worksheet_rows = _xlsx_rows(archive, target, shared_strings)
        italic_cells = _xlsx_italic_cells(archive, target)

    header_matches = [
        (row_number, cells)
        for row_number, cells in worksheet_rows
        if "STATE" in {" ".join(value.upper().split()) for value in cells.values()}
        and "TOTAL VOTES" in {" ".join(value.upper().split()) for value in cells.values()}
    ]
    if len(header_matches) != 1:
        raise PresidentialIngestError("FEC 2024 表头行必须唯一")
    header_line, header = header_matches[0]
    layout = _identify_fec_2024_layout(header)
    state_column = int(layout["state_column"])
    total_column = int(layout["total_votes_column"])
    candidate_columns = tuple(layout["candidate_columns"])

    state_rows: dict[str, tuple[int, dict[int, str]]] = {}
    national_rows: list[tuple[int, dict[int, str]]] = []
    for row_number, cells in worksheet_rows:
        label = " ".join(cells.get(state_column, "").upper().split())
        if label in STATE_EQUIVALENTS:
            if label in state_rows:
                raise PresidentialIngestError(f"FEC 2024 州行重复：{label}")
            state_rows[label] = (row_number, cells)
        elif label.rstrip(":") == "TOTAL":
            national_rows.append((row_number, cells))
    if set(state_rows) != set(STATE_EQUIVALENTS) or len(state_rows) != 51:
        raise PresidentialIngestError("FEC 2024 未精确覆盖 50 州加 DC")
    if len(national_rows) != 1:
        raise PresidentialIngestError("FEC 2024 全国合计行必须唯一")
    national_line, national_cells = national_rows[0]

    workbook_candidate_totals = {
        candidate: _xlsx_integer(
            national_cells.get(column, ""), f"2024 全国合计/{candidate}"
        )
        for column, candidate in candidate_columns
    }
    workbook_all_candidate_total = _xlsx_integer(
        national_cells.get(total_column, ""), "2024 全国总票"
    )

    results: list[dict[str, Any]] = []
    winners: dict[str, dict[str, Any]] = {}
    computed_candidate_totals: Counter[str] = Counter()
    for state in STATE_EQUIVALENTS:
        row_number, cells = state_rows[state]
        state_total = _xlsx_integer(cells.get(total_column, ""), f"2024-{state} 总票")
        source_lines: list[dict[str, Any]] = []
        for column, candidate in candidate_columns:
            raw_votes = cells.get(column, "").strip()
            if not raw_votes:
                continue
            votes = _xlsx_integer(raw_votes, f"2024-{state}/{candidate} 票数")
            if votes == 0:
                continue
            writein = (row_number, column) in italic_cells or candidate == "WRITE-INS (SCATTERED)"
            party = _fec_2024_party_label(candidate, writein=writein)
            source_lines.append(
                {
                    "candidate": candidate,
                    "candidate_votes": votes,
                    "notes": (
                        f"{FEC_2024_RESULTS_SHEET} cell "
                        f"{_xlsx_column_name(column)}{row_number}"
                    ),
                    "raw_party": party,
                    "source_line": row_number,
                    "source_total_votes": state_total,
                    "version": FEC_2024_VINTAGE,
                    "writein": writein,
                }
            )
            computed_candidate_totals[candidate] += votes
        candidate_sum = sum(int(line["candidate_votes"]) for line in source_lines)
        if candidate_sum != state_total:
            raise PresidentialIngestError(
                f"2024-{state} 候选人票数不守恒：{candidate_sum} != {state_total}"
            )
        by_identity = {
            _identity(str(line["candidate"])): [line] for line in source_lines
        }
        records = {
            identity: _fec_candidate_record(identity, lines)
            for identity, lines in by_identity.items()
        }
        democratic_ids = [
            identity
            for identity, lines in by_identity.items()
            if lines[0]["raw_party"] == "D"
        ]
        republican_ids = [
            identity
            for identity, lines in by_identity.items()
            if lines[0]["raw_party"] == "R"
        ]
        if len(democratic_ids) != 1 or len(republican_ids) != 1:
            raise PresidentialIngestError(f"2024-{state} D/R 候选身份不唯一")
        maximum_votes = max(record["votes"] for record in records.values())
        maximum_ids = [
            identity for identity, record in records.items() if record["votes"] == maximum_votes
        ]
        if len(maximum_ids) != 1:
            raise PresidentialIngestError(f"2024-{state} 州级普选最高票不唯一")
        winner = records[maximum_ids[0]]
        winner_party = next(
            line["raw_party"]
            for line in source_lines
            if _identity(str(line["candidate"])) == maximum_ids[0]
        )
        winners[state] = {
            "state": state,
            "winner_candidate": winner["candidate"],
            "winner_party": winner_party,
            "winner_votes": winner["votes"],
            "democratic_votes": records[democratic_ids[0]]["votes"],
            "republican_votes": records[republican_ids[0]]["votes"],
            "source_line": row_number,
        }
        democratic = records[democratic_ids[0]]
        republican = records[republican_ids[0]]
        denominator = democratic["votes"] + republican["votes"]
        if denominator <= 0:
            raise PresidentialIngestError(f"2024-{state} 两党票分母非正")
        margin = 100.0 * (democratic["votes"] - republican["votes"]) / denominator
        metadata = state_metadata[state]
        results.append(
            {
                "archival_reconstruction": True,
                "candidate_votes_sum": candidate_sum,
                "cycle": 2024,
                "delta_by_source_total": {str(state_total): 0},
                "democratic_candidate": democratic,
                "democratic_votes": democratic["votes"],
                "duplicate_named_group_count": 0,
                "major_party_fusion_group_count": 0,
                "named_candidate_groups": [
                    records[_identity(str(line["candidate"]))] for line in source_lines
                ],
                "normalized_total_votes": state_total,
                "normalized_vote_conservation_delta": 0,
                "office": "PRESIDENT",
                "republican_candidate": republican,
                "republican_votes": republican["votes"],
                "schema_version": "1.0",
                "source": {
                    "dataset_id": FEC_2024_DATASET_ID,
                    "source_path": source_path,
                    "source_lines": [row_number],
                    "worksheet": FEC_2024_RESULTS_SHEET,
                    "workbook_bytes": len(workbook_bytes),
                    "workbook_sha256": digest,
                    "state_summary_line": row_number,
                    "state_total_line": row_number,
                    "worksheet_excluded_rows": [],
                    "header_line": header_line,
                    "national_total_line": national_line,
                    "retrieval_contract_id": "LH-067",
                    "retrieval_transaction_id": FEC_2024_RETRIEVAL_TRANSACTION_ID,
                    "content_seal_artifact_sha256": FEC_2024_CONTENT_SEAL_SHA256,
                },
                "source_row_count": len(source_lines),
                "source_rows": source_lines,
                "source_total_conserving": True,
                "source_total_values": [state_total],
                "source_total_values_inconsistent": False,
                "state": state,
                "state_cen": metadata["state_cen"],
                "state_fips": metadata["state_fips"],
                "state_ic": metadata["state_ic"],
                "state_name": metadata["state_name"],
                "strict_original_vintage_available": False,
                "two_party_margin": margin,
            }
        )

    results.sort(key=lambda row: str(row["state"]))
    candidate_columns_reconciled = dict(computed_candidate_totals) == workbook_candidate_totals
    democratic_total = sum(int(row["democratic_votes"]) for row in results)
    republican_total = sum(int(row["republican_votes"]) for row in results)
    all_candidate_total = sum(int(row["candidate_votes_sum"]) for row in results)
    national_totals = {
        "democratic_votes": democratic_total,
        "republican_votes": republican_total,
        "all_candidate_votes": all_candidate_total,
    }
    key_state_winners = [winners[state] for state in FEC_2024_KEY_STATES]
    key_state_parties = {
        row["state"]: row["winner_party"] for row in key_state_winners
    }
    qualifications = {
        "jurisdictions_50_states_plus_dc": len(results) == 51,
        "unique_state_winner": len(winners) == 51,
        "candidate_vote_conservation": all(
            row["candidate_votes_sum"] == row["normalized_total_votes"] for row in results
        ),
        "party_labels_present": all(
            source["raw_party"] for row in results for source in row["source_rows"]
        ),
        "candidate_column_totals_reconciled": candidate_columns_reconciled,
        "national_two_party_totals_reconciled": (
            democratic_total == workbook_candidate_totals["HARRIS"]
            and republican_total == workbook_candidate_totals["TRUMP"]
        ),
        "national_total_reconciled": all_candidate_total == workbook_all_candidate_total,
        "known_official_national_totals_match": (
            national_totals == FEC_2024_OFFICIAL_NATIONAL_TOTALS
        ),
        "known_official_key_state_winners_match": (
            key_state_parties == FEC_2024_OFFICIAL_KEY_STATE_WINNERS
        ),
    }
    if not all(qualifications.values()):
        failed = sorted(name for name, passed in qualifications.items() if not passed)
        raise PresidentialIngestError(f"FEC 2024 总统解析资格闸未全部通过：{failed}")
    report = {
        "schema_version": "1.0",
        "contract_id": "LH-068",
        "cycle": 2024,
        "source": {
            "path": source_path,
            "bytes": len(workbook_bytes),
            "sha256": digest,
            "sheet_names": list(sheet_names),
            "results_sheet": FEC_2024_RESULTS_SHEET,
            "header_line": header_line,
            "national_total_line": national_line,
            "published_at": FEC_2024_PUBLISHED_AT,
            "retrieved_at": FEC_2024_RETRIEVED_AT,
            "retrieval_contract_id": "LH-067",
            "retrieval_transaction_id": FEC_2024_RETRIEVAL_TRANSACTION_ID,
            "content_seal_artifact_sha256": FEC_2024_CONTENT_SEAL_SHA256,
        },
        "column_layout": {
            "identification": "normalized_header_text",
            "state_column": _xlsx_column_name(state_column),
            "total_votes_column": _xlsx_column_name(total_column),
            "democratic_candidate_column": _xlsx_column_name(
                int(layout["democratic_column"])
            ),
            "republican_candidate_column": _xlsx_column_name(
                int(layout["republican_column"])
            ),
            "candidate_columns": [
                {"column": _xlsx_column_name(column), "candidate": candidate}
                for column, candidate in candidate_columns
            ],
        },
        "party_annotation_rules": [
            {
                "label": "D/R",
                "basis": "同一工作簿表头的 ELECTORAL VOTE: HARRIS (D)/TRUMP (R)",
            },
            {
                "label": "W",
                "basis": "工作簿注释定义的斜体 write-in 单元格或 WRITE-INS (SCATTERED) 列",
            },
            {
                "label": "NONE_OF_THESE",
                "basis": "工作簿 NONE OF THESE CANDIDATES 列",
            },
            {
                "label": "OTHER_OR_INDEPENDENT",
                "basis": "工作簿未提供其余候选人的精确党籍，不离线臆造",
            },
        ],
        "state_cycle_count": len(results),
        "states": [str(row["state"]) for row in results],
        "candidate_source_cell_count": sum(int(row["source_row_count"]) for row in results),
        "workbook_candidate_totals": workbook_candidate_totals,
        "national_totals": national_totals,
        "workbook_all_candidate_total": workbook_all_candidate_total,
        "key_state_winners": key_state_winners,
        "qualification_checks": qualifications,
        "all_qualification_checks_passed": all(qualifications.values()),
        "contains_2026_probability": False,
    }
    return results, report


def build_lh068_senate_baselines(
    results_2024: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """从 2024 官方总统结果派生 2026 的 50 州结构基线，不含 DC。"""

    by_state = {str(row["state"]): row for row in results_2024}
    if len(results_2024) != 51 or set(by_state) != set(STATE_EQUIVALENTS):
        raise PresidentialIngestError("LH-068 总统追加段必须精确覆盖 50 州加 DC")
    baselines: list[dict[str, Any]] = []
    for state in STATE_CODES:
        source = by_state[state]
        margin = float(source["two_party_margin"])
        if not math.isfinite(margin) or not -100.0 <= margin <= 100.0:
            raise PresidentialIngestError(f"2024-{state} 总统边际非法")
        baselines.append(
            {
                "schema_version": "1.0",
                "feature_id": FEATURE_ID,
                "transform_id": TRANSFORM_ID,
                "office": "SENATE",
                "target_cycle": 2026,
                "state": state,
                "partisan_baseline_margin": margin,
                "presidential_source_cycle": 2024,
                "forecast_as_of": "2026-10-01T23:59:59Z",
                "available_at": "2025-12-31T23:59:59Z",
                "fact_available_at": "2025-12-31T23:59:59Z",
                "fact_availability_basis": (
                    "conservative_upper_bound_end_of_year_after_presidential_election"
                ),
                "vintage": FEC_2024_VINTAGE,
                "archival_reconstruction": True,
                "strict_original_vintage_available": False,
                "modern_mirror_published_at": FEC_2024_PUBLISHED_AT,
                "modern_mirror_retrieved_at": FEC_2024_RETRIEVED_AT,
                "democratic_candidate": source["democratic_candidate"],
                "republican_candidate": source["republican_candidate"],
                "source": {
                    "dataset_id": FEC_2024_DATASET_ID,
                    "source_path": source["source"]["source_path"],
                    "source_lines": source["source"]["source_lines"],
                    "worksheet": FEC_2024_RESULTS_SHEET,
                    "workbook_sha256": FEC_2024_SHA256,
                    "workbook_bytes": FEC_2024_BYTES,
                    "retrieval_contract_id": "LH-067",
                    "retrieval_transaction_id": FEC_2024_RETRIEVAL_TRANSACTION_ID,
                    "content_seal_artifact_sha256": FEC_2024_CONTENT_SEAL_SHA256,
                    "derivation_contract_id": "LH-068",
                    "derivation": (
                        "100 * (democratic_votes - republican_votes) / "
                        "(democratic_votes + republican_votes)"
                    ),
                },
            }
        )
    assert_lh068_senate_baseline_append_ready(baselines)
    return baselines


def assert_lh068_senate_baseline_append_ready(
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if len(rows) != 50:
        raise PresidentialIngestError(f"LH-068 基线追加段必须为 50 行，实际 {len(rows)}")
    if {str(row.get("state")) for row in rows} != set(STATE_CODES):
        raise PresidentialIngestError("LH-068 基线追加段未精确覆盖 50 州")
    seen: set[str] = set()
    for row in rows:
        state = str(row.get("state"))
        if state in seen:
            raise PresidentialIngestError(f"LH-068 基线州重复：{state}")
        seen.add(state)
        if row.get("target_cycle") != 2026 or row.get("presidential_source_cycle") != 2024:
            raise PresidentialIngestError(f"LH-068 {state} 基线不是 2024 -> 2026")
        if row.get("office") != "SENATE" or row.get("feature_id") != FEATURE_ID:
            raise PresidentialIngestError(f"LH-068 {state} 基线 schema 漂移")
        if row.get("available_at") != row.get("fact_available_at"):
            raise PresidentialIngestError(f"LH-068 {state} 事实可用时间不一致")
        if _parse_timestamp(str(row["available_at"]), "available_at") > _parse_timestamp(
            str(row["forecast_as_of"]), "forecast_as_of"
        ):
            raise PresidentialIngestError(f"LH-068 {state} 事实晚于预测截点")
        source = row.get("source")
        if not isinstance(source, Mapping) or source.get("derivation_contract_id") != "LH-068":
            raise PresidentialIngestError(f"LH-068 {state} 缺少派生 lineage")


def _line_count(payload: bytes) -> int:
    if payload and not payload.endswith(b"\n"):
        raise PresidentialIngestError("JSONL 前缀末尾缺少换行")
    return len(payload.splitlines())


def _verify_append_prefix(
    path: Path,
    *,
    expected_rows: int,
    expected_sha256: str,
) -> bytes:
    payload = path.read_bytes()
    if _line_count(payload) != expected_rows:
        raise PresidentialIngestError(
            f"{path} 追加前行数漂移：{_line_count(payload)} != {expected_rows}"
        )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise PresidentialIngestError(f"{path} 追加前 SHA-256 漂移")
    return payload


def _append_segment_once(path: Path, payload: bytes) -> None:
    if not payload or not payload.endswith(b"\n"):
        raise PresidentialIngestError(f"{path} 追加段为空或末尾无换行")
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(path, flags)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise PresidentialIngestError(
                f"{path} 追加段未一次写完：{written} != {len(payload)}"
            )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PresidentialIngestError(f"拒绝覆盖既有 LH-068 artifact：{path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def publish_lh068_append(
    results_2024: Sequence[Mapping[str, Any]],
    baselines_2026: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
    *,
    results_path: str | Path,
    baselines_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    """先验全检后，以单次 O_APPEND 写调用发布两个只追加段。"""

    if len(results_2024) != 51 or {row.get("cycle") for row in results_2024} != {2024}:
        raise PresidentialIngestError("LH-068 总统追加段必须恰为 51 行 2024")
    if not report.get("all_qualification_checks_passed"):
        raise PresidentialIngestError("LH-068 对账报告资格闸未全过")
    assert_lh068_senate_baseline_append_ready(baselines_2026)
    result_target = Path(results_path)
    baseline_target = Path(baselines_path)
    result_prefix = _verify_append_prefix(
        result_target,
        expected_rows=LH068_RESULTS_PREFIX_ROWS,
        expected_sha256=LH068_RESULTS_PREFIX_SHA256,
    )
    baseline_prefix = _verify_append_prefix(
        baseline_target,
        expected_rows=LH068_BASELINES_PREFIX_ROWS,
        expected_sha256=LH068_BASELINES_PREFIX_SHA256,
    )
    result_append = jsonl_bytes(results_2024)
    baseline_append = jsonl_bytes(baselines_2026)
    report_payload = _json_bytes(report)
    json.loads(report_payload)
    for payload in (result_append, baseline_append):
        for line in payload.splitlines():
            json.loads(line)

    _atomic_write_new(Path(report_path), report_payload)
    _append_segment_once(result_target, result_append)
    _append_segment_once(baseline_target, baseline_append)
    final_results = result_target.read_bytes()
    final_baselines = baseline_target.read_bytes()
    if final_results[: len(result_prefix)] != result_prefix or _line_count(final_results) != 663:
        raise PresidentialIngestError("LH-068 总统账本发布后前缀或行数漂移")
    if final_baselines[: len(baseline_prefix)] != baseline_prefix or _line_count(final_baselines) != 600:
        raise PresidentialIngestError("LH-068 基线账本发布后前缀或行数漂移")
    return {
        "presidential_rows_appended": 51,
        "presidential_final_rows": 663,
        "presidential_prefix_sha256": hashlib.sha256(result_prefix).hexdigest(),
        "baseline_rows_appended": 50,
        "baseline_final_rows": 600,
        "baseline_prefix_sha256": hashlib.sha256(baseline_prefix).hexdigest(),
        "report_sha256": hashlib.sha256(report_payload).hexdigest(),
    }
