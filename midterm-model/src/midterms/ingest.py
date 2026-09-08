"""MEDSL 固定快照的零依赖读取、规范化与逐周期对账。

本模块把最终结果当作目标账本，而不是预测特征。House 的 ``district`` 只在
当届周期内有意义；代码绝不据同号选区伪造跨重划区 ``map_id`` 或席位连续性。

上游 CSV 含少量无法按 UTF-8/Windows-1252 严格解码的历史字节。这里使用
ISO-8859-1 做一字节一代码点的可逆读取，并验证往返字节完全一致；不得使用
``errors=ignore`` 或 ``errors=replace`` 吞掉候选人姓名中的原始字节。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class IngestError(ValueError):
    """来源结构或规范化不满足可审计约束。"""


EXPECTED_CYCLES = tuple(range(1976, 2020, 2))
FORMAL_TARGET_MAX_CYCLE = 2016
EXPECTED_HOUSE_SEATS = 435

HOUSE_HEADERS = (
    "year",
    "state",
    "state_po",
    "state_fips",
    "state_cen",
    "state_ic",
    "office",
    "district",
    "stage",
    "runoff",
    "special",
    "candidate",
    "party",
    "writein",
    "mode",
    "candidatevotes",
    "totalvotes",
    "unofficial",
    "version",
)
SENATE_HEADERS = tuple(field for field in HOUSE_HEADERS if field != "runoff")

_MISSING = {"", "NA"}
_DEMOCRATIC_PARTIES = {
    "democrat",
    "democratic-farmer-labor",
    "democratic-nonpartisan league",
    "democratic-npl",
    "democrat (not identified on ballot)",
}
_REPUBLICAN_PARTIES = {
    "republican",
    "independent-republican",
    "republican (not identified on ballot)",
}

# 固定 MEDSL 快照的逐周期 Senate 席位清单锚。值为（竞选数，规范 race_id
# 清单 SHA-256）；它独立于当次来源中是否“碰巧有行”，因此整州缺行也会关闭周期。
EXPECTED_SENATE_INVENTORY = {
    1976: (33, "7c2d6e5ba4439c2b82897aae27b3f51dd2c3e796d18569023a1942adc1fdea7f"),
    1978: (35, "7095921e85ac4815101b237c3c8a027b13e45efa9b948043c3ec1132c44d23c3"),
    1980: (33, "a401f36ba82933369fc912cfd2e7c09fb45f0cedc738a4a615b12b317dc11ce4"),
    1982: (33, "52ae83160cd4698663c9b2fd671ff229e88741ab2713f987cb17b002cb586b0e"),
    1984: (33, "c97d59eec12fd6f2957d5fbb485421288af64cca42388dcfd957061e18f5a8c1"),
    1986: (34, "eacedb258737102be831e6d78bd8cc2dba10257e17ba4f5c20238bd9ed76b06d"),
    1988: (33, "957f1fa8970e9ef1e6a4648914dfbac79ac5228541b2315dacc92b20319d2d39"),
    1990: (35, "b36dc04c104eadf74804a7be476b94f9d6227c5456939f1d6ffd15a70dbbc44e"),
    1992: (35, "ebc1315e0325525ce0d0381a10010d8bae71646f928f0c89a472be031545df00"),
    1994: (35, "0413994646ecc2f02219029e91cc20f7f05ab2a5fefaebd6497f3beea4c7b58b"),
    1996: (34, "4e9708f3a0e601839f144d2e725cf201c04553017aee57ac19a2da7a030544a9"),
    1998: (34, "d3c43ed3f6e98fb27d5585a3952666dc06127ca930ce115e10d2c7c6de98b93d"),
    2000: (34, "91ee8a8d4c3332b41b5f1d94508c3096151ab81427e9295965ee00b49a2b2d84"),
    2002: (34, "372b485ec94ec732fb8710f051bf3434a82e6c7ee65931d3dfc39300f0276bf2"),
    2004: (34, "66ddccdba35b25c52e5ef6c4cd6e07c41b0f4ab5471d2b39c51f9a9b47df0c07"),
    2006: (33, "30436caaa5893785044d180b1747b2e5d92ce2001df594e96f965154a06a732e"),
    2008: (35, "b03bb5cb9ac0ff3dad731c6064a2dc43ba725d99176bc55b64a8582c9b4af9f7"),
    2010: (37, "d7fa25f450cb6d6d86cb6a8e17bc43e0677659c4e5f8b762a72d3b3a0f1b53d0"),
    2012: (33, "bf05a745a44ddc294bb2da20cb2c929a3d3422338c757f1f4ae44b6d8f74181d"),
    2014: (36, "d589f9b1b776fb82b8b482fc32125bb38a067ad85122f03c72b3257385e791b0"),
    2016: (34, "147bd7ec10e7e92973d86e487ed503bd0cdb3e316cc2b616de20ae46daae0059"),
    2018: (35, "372824f3bf0a6a98e445d779f781fe6192a683a853e1695c3b648bdc7641f82c"),
}


def _senate_inventory_digest(race_ids: Iterable[str]) -> str:
    payload = "".join(f"{race_id}\n" for race_id in sorted(race_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _senate_inventory_matches(cycle: int, race_ids: Sequence[str]) -> bool:
    expected_count, expected_digest = EXPECTED_SENATE_INVENTORY[cycle]
    return len(race_ids) == expected_count and _senate_inventory_digest(race_ids) == expected_digest


def _text_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in _MISSING else value


def _integer(value: str | None, field: str, line: int) -> int:
    if value is None or not re.fullmatch(r"\d+", value.strip()):
        raise IngestError(f"来源第 {line} 行 {field} 不是非负整数：{value!r}")
    return int(value)


def _boolean(value: str | None, field: str, line: int) -> bool:
    if value == "TRUE":
        return True
    if value == "FALSE":
        return False
    raise IngestError(f"来源第 {line} 行 {field} 只能是 TRUE/FALSE：{value!r}")


def _identity(name: str) -> str:
    """只做可验证的精确规范化，不做模糊姓名匹配。"""

    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def _party_group(raw_parties: Iterable[str]) -> str:
    parties = {_identity(party) for party in raw_parties}
    is_democratic = bool(parties & _DEMOCRATIC_PARTIES)
    is_republican = bool(parties & _REPUBLICAN_PARTIES)
    if is_democratic and is_republican:
        return "CONFLICT"
    if is_democratic:
        return "DEMOCRATIC"
    if is_republican:
        return "REPUBLICAN"
    if parties:
        return "OTHER"
    return "UNKNOWN"


def read_medsl_csv(path: str | Path, office: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """严格读取一个固定 CSV，并返回逐行来源号和可逆编码审计。"""

    source_path = Path(path)
    data = source_path.read_bytes()
    text = data.decode("iso-8859-1", errors="strict")
    if text.encode("iso-8859-1", errors="strict") != data:
        raise IngestError(f"{source_path} 的 ISO-8859-1 往返字节不一致")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected = HOUSE_HEADERS if office == "HOUSE" else SENATE_HEADERS
    if tuple(reader.fieldnames or ()) != expected:
        raise IngestError(
            f"{source_path} 表头漂移：实际 {reader.fieldnames!r}，预期 {list(expected)!r}"
        )

    rows: list[dict[str, Any]] = []
    for raw in reader:
        line = reader.line_num
        if None in raw:
            raise IngestError(f"{source_path} 第 {line} 行存在超出表头的字段")
        cycle = _integer(raw["year"], "year", line)
        if cycle not in EXPECTED_CYCLES:
            raise IngestError(f"来源第 {line} 行 year 不在固定 1976–2018 偶数周期：{cycle}")
        state = (raw["state_po"] or "").strip()
        if not re.fullmatch(r"[A-Z]{2}", state):
            raise IngestError(f"来源第 {line} 行 state_po 非两位州代码：{state!r}")
        expected_office = "US House" if office == "HOUSE" else "US Senate"
        if raw["office"] != expected_office:
            raise IngestError(f"来源第 {line} 行 office 漂移：{raw['office']!r}")
        if raw["mode"] != "total":
            raise IngestError(f"来源第 {line} 行 mode 非 total：{raw['mode']!r}")

        if office == "HOUSE":
            district = _integer(raw["district"], "district", line)
            runoff_raw = raw["runoff"]
            if runoff_raw not in {"TRUE", "FALSE", "NA"}:
                raise IngestError(f"来源第 {line} 行 runoff 口径未知：{runoff_raw!r}")
            runoff = None if runoff_raw == "NA" else runoff_raw == "TRUE"
        else:
            if raw["district"] != "statewide":
                raise IngestError(f"来源第 {line} 行 Senate district 非 statewide")
            district = None
            runoff_raw = None
            runoff = None

        rows.append(
            {
                "source_line": line,
                "cycle": cycle,
                "office": office,
                "state": state,
                "state_name": raw["state"],
                "district": district,
                "source_stage": (raw["stage"] or "").strip(),
                "source_runoff_raw": runoff_raw,
                "source_runoff": runoff,
                "source_special": _boolean(raw["special"], "special", line),
                "candidate": _text_or_none(raw["candidate"]),
                "party": _text_or_none(raw["party"]),
                "writein": _boolean(raw["writein"], "writein", line),
                "candidate_votes": _integer(raw["candidatevotes"], "candidatevotes", line),
                "source_total_votes": _integer(raw["totalvotes"], "totalvotes", line),
                "unofficial": _boolean(raw["unofficial"], "unofficial", line),
                "version": (raw["version"] or "").strip(),
            }
        )

    c1 = Counter(byte for byte in data if 0x80 <= byte <= 0x9F)
    audit = {
        "codec": "iso-8859-1",
        "strategy": "逐字节可逆；禁止 ignore/replace",
        "roundtrip_bytes_equal": True,
        "source_bytes": len(data),
        "source_rows": len(rows),
        "c1_byte_count": sum(c1.values()),
        "c1_bytes_hex": {f"{byte:02x}": c1[byte] for byte in sorted(c1)},
    }
    return rows, audit


def _round_key(row: Mapping[str, Any], office: str) -> tuple[Any, ...]:
    key: tuple[Any, ...] = (
        row["source_stage"],
        row["source_special"],
    )
    if office == "HOUSE":
        key += (row["source_runoff_raw"],)
    return key


def _round_summary(rows: Sequence[Mapping[str, Any]], office: str) -> dict[str, Any]:
    totals = sorted({int(row["source_total_votes"]) for row in rows})
    return {
        "source_stage": str(rows[0]["source_stage"]),
        "source_runoff": rows[0]["source_runoff"] if office == "HOUSE" else None,
        "source_special": bool(rows[0]["source_special"]),
        "source_total_votes_values": totals,
        "source_lines": sorted(int(row["source_line"]) for row in rows),
    }


def _choose_house_round(
    rounds: Sequence[tuple[tuple[Any, ...], list[dict[str, Any]]]]
) -> tuple[list[dict[str, Any]] | None, str, list[dict[str, Any]]]:
    """选出当届 House 席位的最终决定轮，保留全部未选轮。"""

    regular = [item for item in rounds if not item[1][0]["source_special"]]
    pool = regular if regular else list(rounds)
    prefix = "regular" if regular else "source_special_only"

    runoff = [item for item in pool if item[1][0]["source_runoff"] is True]
    if len(runoff) == 1:
        selected = runoff[0]
        basis = f"{prefix}_runoff"
    elif len(runoff) > 1:
        return None, "ambiguous_multiple_runoff_rounds", []
    else:
        general = [item for item in pool if item[1][0]["source_stage"] == "gen"]
        if len(general) == 1:
            selected = general[0]
            basis = f"{prefix}_general"
        elif len(general) > 1:
            return None, "ambiguous_multiple_general_rounds", []
        elif len(pool) == 1:
            selected = pool[0]
            basis = f"{prefix}_sole_anomalous_stage"
        else:
            return None, "ambiguous_no_final_round", []

    unselected = [
        _round_summary(rows, "HOUSE")
        for key, rows in rounds
        if key != selected[0]
    ]
    return selected[1], basis, unselected


def _choose_senate_round(
    rounds: Sequence[tuple[tuple[Any, ...], list[dict[str, Any]]]]
) -> tuple[list[dict[str, Any]] | None, str, list[dict[str, Any]]]:
    general = [item for item in rounds if item[1][0]["source_stage"] == "gen"]
    if len(general) == 1:
        selected = general[0]
        basis = "source_general_final"
    elif len(general) > 1:
        return None, "ambiguous_multiple_general_rounds", []
    elif len(rounds) == 1:
        selected = rounds[0]
        basis = "sole_anomalous_stage"
    else:
        return None, "ambiguous_no_final_round", []
    unselected = [
        _round_summary(rows, "SENATE")
        for key, rows in rounds
        if key != selected[0]
    ]
    return selected[1], basis, unselected


def _round_kind(row: Mapping[str, Any]) -> str:
    if row["source_runoff"] is True:
        return "runoff"
    if row["source_stage"] == "gen":
        return "general"
    if row["source_stage"] in {"pre", "pri"}:
        return "source_labeled_preliminary_but_final_for_target"
    return "source_stage_missing_but_final_for_target"


def _race_id(
    office: str, cycle: int, state: str, district: int | None, source_special: bool
) -> str:
    if office == "HOUSE":
        # district 明示为 cycle-local，不暗示跨重划区连续性。
        return f"HOUSE-{cycle}-{state}-{district:02d}-CYCLE-SEAT"
    election_type = "SPECIAL" if source_special else "REGULAR"
    return f"SENATE-{cycle}-{state}-{election_type}"


def _aggregate_candidates(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        name = row["candidate"]
        # 匿名/NA 行没有可核对的共同身份，因此绝不跨行合票。
        key = _identity(name) if name is not None else f"__anonymous_line_{row['source_line']}"
        grouped[key].append(row)

    candidates: list[dict[str, Any]] = []
    problems: list[str] = []
    for key, lines in sorted(grouped.items(), key=lambda item: min(r["source_line"] for r in item[1])):
        raw_names = sorted({row["candidate"] for row in lines if row["candidate"] is not None})
        raw_parties = sorted({row["party"] for row in lines if row["party"] is not None})
        party = _party_group(raw_parties)
        # 跨 D/R 合票在上游确实存在；它使两党边际不可定义，但候选人身份与赢家
        # 仍可验证，不能据此删掉 House 席位。
        writeins = {bool(row["writein"]) for row in lines}
        if len(writeins) > 1:
            problems.append("candidate_writein_status_conflict")
        candidates.append(
            {
                "candidate": raw_names[0] if raw_names else None,
                "raw_candidate_names": raw_names,
                "raw_parties": raw_parties,
                "canonical_party": party,
                "votes": sum(int(row["candidate_votes"]) for row in lines),
                "writein": any(writeins),
                "source_lines": sorted(int(row["source_line"]) for row in lines),
                "fusion_line_count": len(lines),
            }
        )
    return candidates, sorted(set(problems))


def _normalize_selected_round(
    rows: Sequence[Mapping[str, Any]],
    *,
    dataset_id: str,
    source_path: str,
    selection_basis: str,
    unselected_rounds: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    first = rows[0]
    office = str(first["office"])
    candidates, problems = _aggregate_candidates(rows)
    source_totals = sorted({int(row["source_total_votes"]) for row in rows})
    # 2018 的若干州把写入行总票与具名候选行总票分开登记。保留全部原始值；
    # 规范化总票始终由候选票重算，不把来源 total 的异常误作目标不可判定。
    source_total: int | None = source_totals[0] if len(source_totals) == 1 else None

    normalized_total = sum(int(candidate["votes"]) for candidate in candidates)
    ordered = sorted(
        candidates,
        key=lambda candidate: (-int(candidate["votes"]), candidate["source_lines"][0]),
    )
    if not ordered:
        problems.append("no_candidates")
        winner = None
    else:
        top_votes = ordered[0]["votes"]
        tied = [candidate for candidate in ordered if candidate["votes"] == top_votes]
        if len(tied) != 1:
            problems.append("winner_tie")
            winner = None
        else:
            winner = dict(tied[0])
            if winner["candidate"] is None:
                problems.append("winner_identity_missing")
            if winner["canonical_party"] in {"UNKNOWN", "CONFLICT"}:
                winner["party_resolution"] = "raw_party_unknown_or_cross_major_fusion"
                winner["winner_group"] = "OTHER"
            else:
                winner["party_resolution"] = "direct_from_verified_raw_party_lines"
                winner["winner_group"] = winner["canonical_party"]

    democratic_votes = sum(
        int(candidate["votes"])
        for candidate in candidates
        if candidate["canonical_party"] == "DEMOCRATIC"
    )
    republican_votes = sum(
        int(candidate["votes"])
        for candidate in candidates
        if candidate["canonical_party"] == "REPUBLICAN"
    )
    third_party_votes = normalized_total - democratic_votes - republican_votes
    cross_major_fusion = any(
        candidate["canonical_party"] == "CONFLICT" for candidate in candidates
    )
    if cross_major_fusion:
        two_party_margin = None
        margin_reason = "fusion_cross_major_party_candidate"
    elif normalized_total == 0:
        two_party_margin = None
        margin_reason = "zero_vote_uncontested_candidate"
    elif democratic_votes == 0 and republican_votes == 0:
        two_party_margin = None
        margin_reason = "missing_both_major_parties"
    elif democratic_votes == 0:
        two_party_margin = None
        margin_reason = "missing_democratic_candidate"
    elif republican_votes == 0:
        two_party_margin = None
        margin_reason = "missing_republican_candidate"
    else:
        two_party_margin = round(
            100.0 * (democratic_votes - republican_votes) / (democratic_votes + republican_votes),
            12,
        )
        margin_reason = None

    district = first["district"]
    source_special = bool(first["source_special"])
    source_lines = sorted(int(row["source_line"]) for row in rows)
    source_delta = None if source_total is None else normalized_total - source_total
    target = {
        "schema_version": "1.0",
        "status": "accepted",
        "race_id": _race_id(
            office, int(first["cycle"]), str(first["state"]), district, source_special
        ),
        "cycle": int(first["cycle"]),
        "forecast_horizon": "final_target_backtest",
        "benchmark_eligible": int(first["cycle"]) <= FORMAL_TARGET_MAX_CYCLE,
        "office": office,
        "state": str(first["state"]),
        "district": district,
        "district_is_cycle_local": office == "HOUSE",
        "map_id": None,
        "seat_scope": "biennial_house_voting_seat" if office == "HOUSE" else "contested_senate_seat",
        "election_type": "special" if source_special else "regular",
        "source_stage": str(first["source_stage"]),
        "source_runoff": first["source_runoff"] if office == "HOUSE" else None,
        "round_kind": _round_kind(first),
        "final_deciding_round": True,
        "selection_basis": selection_basis,
        "winner": winner,
        "winner_group": winner["winner_group"] if winner is not None else None,
        "candidates": candidates,
        "source_total_votes": source_total,
        "source_total_votes_values": source_totals,
        "candidate_votes_sum": normalized_total,
        "normalized_total_votes": normalized_total,
        "normalized_vote_conservation_delta": 0,
        "source_total_vote_delta": source_delta,
        "democratic_votes": democratic_votes,
        "republican_votes": republican_votes,
        "third_party_votes": third_party_votes,
        "third_party_share": (
            round(third_party_votes / normalized_total, 12) if normalized_total > 0 else None
        ),
        "two_party_margin": two_party_margin,
        "two_party_margin_reason": margin_reason,
        "source": {
            "dataset_id": dataset_id,
            "source_path": source_path,
            "source_lines": source_lines,
            "version": sorted({str(row["version"]) for row in rows}),
            "unofficial_any": any(bool(row["unofficial"]) for row in rows),
            "source_total_values_inconsistent": len(source_totals) != 1,
            "encoding": "iso-8859-1-byte-preserving",
        },
        "unselected_source_rounds": list(unselected_rounds),
    }
    return target, sorted(set(problems))


def normalize_office(
    rows: Sequence[Mapping[str, Any]], *, dataset_id: str, source_path: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按院别选最终轮、精确候选人合票，并把不可判定竞选隔离。"""

    if not rows:
        raise IngestError("规范化输入不能为空")
    offices = {str(row["office"]) for row in rows}
    if len(offices) != 1 or next(iter(offices)) not in {"HOUSE", "SENATE"}:
        raise IngestError("normalize_office 必须一次只处理一个院别")
    office = next(iter(offices))

    seat_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if office == "HOUSE":
            key = (int(row["cycle"]), str(row["state"]), int(row["district"]))
        else:
            key = (
                int(row["cycle"]),
                str(row["state"]),
                bool(row["source_special"]),
            )
        seat_groups[key].append(dict(row))

    targets: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for seat_key, seat_rows in sorted(seat_groups.items()):
        round_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in seat_rows:
            round_groups[_round_key(row, office)].append(row)
        rounds = sorted(round_groups.items(), key=lambda item: min(r["source_line"] for r in item[1]))
        if office == "HOUSE":
            selected, selection_basis, unselected = _choose_house_round(rounds)
        else:
            selected, selection_basis, unselected = _choose_senate_round(rounds)

        if selected is None:
            first = seat_rows[0]
            quarantine.append(
                {
                    "office": office,
                    "cycle": int(first["cycle"]),
                    "state": str(first["state"]),
                    "district": first["district"],
                    "source_special": bool(first["source_special"]) if office == "SENATE" else None,
                    "source_lines": sorted(int(row["source_line"]) for row in seat_rows),
                    "reasons": [selection_basis],
                    "source_rounds": [_round_summary(group, office) for _, group in rounds],
                }
            )
            continue

        target, problems = _normalize_selected_round(
            selected,
            dataset_id=dataset_id,
            source_path=source_path,
            selection_basis=selection_basis,
            unselected_rounds=unselected,
        )
        if problems:
            quarantine.append(
                {
                    "race_id": target["race_id"],
                    "office": target["office"],
                    "cycle": target["cycle"],
                    "state": target["state"],
                    "district": target["district"],
                    "source_special": target["election_type"] == "special",
                    "source_lines": target["source"]["source_lines"],
                    "reasons": problems,
                    "candidate_votes_sum": target["candidate_votes_sum"],
                    "source_total_votes": target["source_total_votes"],
                    "source_total_vote_delta": target["source_total_vote_delta"],
                    "winner_candidate": target["winner"]["candidate"] if target["winner"] else None,
                    "winner_party": target["winner"]["canonical_party"] if target["winner"] else None,
                    "source_rounds": [_round_summary(group, office) for _, group in rounds],
                }
            )
        else:
            targets.append(target)

    targets.sort(key=lambda row: row["race_id"])
    quarantine.sort(
        key=lambda row: (
            row["cycle"],
            row["office"],
            row["state"],
            -1 if row["district"] is None else row["district"],
            str(row.get("source_special")),
        )
    )
    return targets, quarantine


def _cycle_reconciliation(
    office: str,
    cycle: int,
    raw_rows: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    quarantine: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    cycle_targets = [row for row in targets if row["office"] == office and row["cycle"] == cycle]
    cycle_quarantine = [
        row for row in quarantine if row["office"] == office and row["cycle"] == cycle
    ]
    margin_missing = Counter(
        row["two_party_margin_reason"]
        for row in cycle_targets
        if row["two_party_margin"] is None
    )
    quarantine_reasons = Counter(
        reason for row in cycle_quarantine for reason in row.get("reasons", [])
    )
    unselected_round_rows = sum(
        len(summary["source_lines"])
        for row in cycle_targets
        for summary in row["unselected_source_rounds"]
    )
    selected_unofficial = sum(
        1 for row in cycle_targets if row["source"]["unofficial_any"]
    )
    expected = EXPECTED_HOUSE_SEATS if office == "HOUSE" else None
    senate_inventory_complete = True
    if office == "SENATE":
        senate_inventory_complete = _senate_inventory_matches(
            cycle, [str(row["race_id"]) for row in cycle_targets]
        )
    selected_races = len(cycle_targets) + len(cycle_quarantine)
    complete = (
        not cycle_quarantine
        and (expected is None or len(cycle_targets) == expected)
        and senate_inventory_complete
    )
    benchmark_eligible = (
        cycle <= FORMAL_TARGET_MAX_CYCLE and complete and selected_unofficial == 0
    )
    return {
        "cycle": cycle,
        "source_rows": sum(1 for row in raw_rows if row["cycle"] == cycle),
        "selected_races": selected_races,
        "accepted_races": len(cycle_targets),
        "quarantined_races": len(cycle_quarantine),
        "winner_count": sum(1 for row in cycle_targets if row["winner"] is not None),
        "expected_cycle_voting_seats": expected,
        "cycle_voting_seat_coverage": (
            round(len(cycle_targets) / expected, 12) if expected is not None else None
        ),
        "two_party_margin_available": sum(
            1 for row in cycle_targets if row["two_party_margin"] is not None
        ),
        "two_party_margin_missing_by_reason": dict(sorted(margin_missing.items())),
        "source_regular_selected": sum(
            1 for row in cycle_targets if row["election_type"] == "regular"
        ),
        "source_special_selected": sum(
            1 for row in cycle_targets if row["election_type"] == "special"
        ),
        "source_reported_total_delta_races": sum(
            1 for row in cycle_targets if row["source_total_vote_delta"] != 0
        ),
        "source_total_values_inconsistent_races": sum(
            1
            for row in cycle_targets
            if row["source"]["source_total_values_inconsistent"]
        ),
        "normalized_vote_conservation_failures": sum(
            1 for row in cycle_targets if row["normalized_vote_conservation_delta"] != 0
        ),
        "unofficial_source_rows": sum(
            1 for row in raw_rows if row["cycle"] == cycle and row["unofficial"]
        ),
        "unofficial_selected_races": selected_unofficial,
        "excluded_source_rows_by_reason": {
            "nonselected_round": unselected_round_rows,
        },
        "quarantine_by_reason": dict(sorted(quarantine_reasons.items())),
        "benchmark_eligible": benchmark_eligible,
        "benchmark_closed_reasons": sorted(
            [
                *( ["audit_only_2018"] if cycle > FORMAL_TARGET_MAX_CYCLE else [] ),
                *( ["quarantined_races_present"] if cycle_quarantine else [] ),
                *(
                    ["house_cycle_voting_seats_not_435"]
                    if expected is not None and len(cycle_targets) != expected
                    else []
                ),
                *(
                    ["senate_cycle_inventory_mismatch"]
                    if office == "SENATE" and not senate_inventory_complete
                    else []
                ),
                *( ["unofficial_selected_results"] if selected_unofficial else [] ),
            ]
        ),
    }


def _selected_target_raw_total_anomalies(
    targets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """保留既有接口：只列最终目标轮的 raw total 异常。"""

    return [
        {
            "race_id": target["race_id"],
            "office": target["office"],
            "cycle": target["cycle"],
            "source_total_votes_values": target["source_total_votes_values"],
            "candidate_votes_sum": target["candidate_votes_sum"],
            "delta_by_source_total": {
                str(source_total): target["candidate_votes_sum"] - source_total
                for source_total in target["source_total_votes_values"]
            },
            "source_total_values_inconsistent": target["source"][
                "source_total_values_inconsistent"
            ],
            "source_lines": target["source"]["source_lines"],
        }
        for target in targets
        if len(target["source_total_votes_values"]) != 1
        or any(
            target["candidate_votes_sum"] != source_total
            for source_total in target["source_total_votes_values"]
        )
    ]


def _raw_round_audit(
    raw_rows: Sequence[Mapping[str, Any]], targets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """逐个 ``_round_key`` 组审计全部来源行，前轮也不得遗漏。"""

    selected_lines = {
        (str(target["office"]), int(line))
        for target in targets
        for line in target["source"]["source_lines"]
    }
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        office = str(row["office"])
        seat = row["district"] if office == "HOUSE" else bool(row["source_special"])
        key = (
            office,
            int(row["cycle"]),
            str(row["state"]),
            seat,
            *_round_key(row, office),
        )
        groups[key].append(row)

    rounds: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items(), key=lambda item: min(r["source_line"] for r in item[1])):
        candidate_sum = sum(int(row["candidate_votes"]) for row in rows)
        source_totals = sorted({int(row["source_total_votes"]) for row in rows})
        office, cycle, state, seat, *_ = key
        source_lines = sorted(int(row["source_line"]) for row in rows)
        selected_count = sum((office, line) in selected_lines for line in source_lines)
        selection_status = (
            "selected_final_round"
            if selected_count == len(source_lines)
            else "nonselected_round"
            if selected_count == 0
            else "mixed_selection_error"
        )
        source_special = bool(rows[0]["source_special"])
        source_stage = str(rows[0]["source_stage"])
        source_runoff = rows[0]["source_runoff"] if office == "HOUSE" else None
        is_anomaly = len(source_totals) != 1 or any(
            candidate_sum != source_total for source_total in source_totals
        )
        rounds.append(
            {
                "raw_round_id": (
                    f"{office}-{cycle}-{state}-"
                    f"{seat if office == 'HOUSE' else 'STATEWIDE'}-"
                    f"{'SPECIAL' if source_special else 'REGULAR'}-"
                    f"{source_stage or 'MISSING'}-"
                    f"{rows[0]['source_runoff_raw'] or 'NA'}"
                ),
                "office": office,
                "cycle": cycle,
                "state": state,
                "district": seat if office == "HOUSE" else None,
                "source_stage": source_stage,
                "source_runoff": source_runoff,
                "source_special": source_special,
                "source_lines": source_lines,
                "source_total_values": source_totals,
                "candidate_votes_sum": candidate_sum,
                "delta_by_source_total": {
                    str(source_total): candidate_sum - source_total
                    for source_total in source_totals
                },
                "source_total_values_inconsistent": len(source_totals) != 1,
                "selection_status": selection_status,
                "is_anomaly": is_anomaly,
            }
        )

    anomalies = [row for row in rounds if row["is_anomaly"]]
    return {
        "grouping_contract": (
            "office/cycle/state/district-or-senate-special/"
            "source_stage/source_special/source_runoff"
        ),
        "source_row_count": len(raw_rows),
        "round_count": len(rounds),
        "anomaly_count": len(anomalies),
        "rounds": rounds,
        "anomalies": anomalies,
    }


def build_historical_targets(
    *,
    house_path: str | Path,
    senate_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    house_rows, house_encoding = read_medsl_csv(house_path, "HOUSE")
    senate_rows, senate_encoding = read_medsl_csv(senate_path, "SENATE")
    house_targets, house_quarantine = normalize_office(
        house_rows,
        dataset_id="medsl-house-1976-2018",
        source_path="data/raw/medsl-1976-2018/1976-2018-house.csv",
    )
    senate_targets, senate_quarantine = normalize_office(
        senate_rows,
        dataset_id="medsl-senate-1976-2018",
        source_path="data/raw/medsl-1976-2018/1976-2018-senate.csv",
    )
    targets = sorted(house_targets + senate_targets, key=lambda row: row["race_id"])
    quarantine = house_quarantine + senate_quarantine
    all_raw_rows = house_rows + senate_rows
    selected_raw_anomalies = _selected_target_raw_total_anomalies(targets)
    raw_round_audit = _raw_round_audit(all_raw_rows, targets)
    reconciliation = {
        "schema_version": "1.0",
        "audit_period": [1976, 2018],
        "formal_target_period": [1976, 2016],
        "real_historical_targets": True,
        "contains_2026_probability": False,
        "source_encoding_audit": {
            "HOUSE": house_encoding,
            "SENATE": senate_encoding,
        },
        "offices": {
            "HOUSE": {
                "cycles": [
                    _cycle_reconciliation(
                        "HOUSE", cycle, house_rows, house_targets, house_quarantine
                    )
                    for cycle in EXPECTED_CYCLES
                ]
            },
            "SENATE": {
                "cycles": [
                    _cycle_reconciliation(
                        "SENATE", cycle, senate_rows, senate_targets, senate_quarantine
                    )
                    for cycle in EXPECTED_CYCLES
                ]
            },
        },
        "quarantine": sorted(
            quarantine,
            key=lambda row: (
                row["cycle"],
                row["office"],
                row["state"],
                -1 if row["district"] is None else row["district"],
            ),
        ),
    }
    reconciliation["raw_total_anomalies"] = selected_raw_anomalies
    reconciliation["raw_round_audit"] = raw_round_audit
    for office in ("HOUSE", "SENATE"):
        for cycle_report in reconciliation["offices"][office]["cycles"]:
            cycle = int(cycle_report["cycle"])
            raw_rounds = [
                row
                for row in raw_round_audit["rounds"]
                if row["office"] == office and row["cycle"] == cycle
            ]
            raw_anomalies = [row for row in raw_rounds if row["is_anomaly"]]
            selected_anomalies = [
                row
                for row in selected_raw_anomalies
                if row["office"] == office and row["cycle"] == cycle
            ]
            cycle_report["raw_total_scope_rounds"] = len(raw_rounds)
            cycle_report["raw_total_scope_anomaly_rounds"] = len(raw_anomalies)
            cycle_report["selected_target_raw_total_anomaly_races"] = len(
                selected_anomalies
            )
            if cycle == 2018:
                reasons = set(cycle_report["benchmark_closed_reasons"])
                if raw_anomalies:
                    reasons.add("raw_total_scope_anomalies")
                if cycle_report["unofficial_source_rows"]:
                    reasons.add("unofficial_source_rows_present")
                reasons.add("fixed_snapshot_superseded_by_newer_doi")
                cycle_report["benchmark_closed_reasons"] = sorted(reasons)
    eligible_by_office_cycle = {
        (office, row["cycle"]): bool(row["benchmark_eligible"])
        for office in ("HOUSE", "SENATE")
        for row in reconciliation["offices"][office]["cycles"]
    }
    for target in targets:
        target["benchmark_eligible"] = eligible_by_office_cycle[
            (target["office"], target["cycle"])
        ]
    reconciliation["formal_target_cycle_sets"] = {
        office: [
            row["cycle"]
            for row in reconciliation["offices"][office]["cycles"]
            if row["benchmark_eligible"]
        ]
        for office in ("HOUSE", "SENATE")
    }
    reconciliation["formal_target_row_counts"] = {
        office: sum(
            1
            for target in targets
            if target["office"] == office and target["benchmark_eligible"]
        )
        for office in ("HOUSE", "SENATE")
    }
    return targets, reconciliation


def write_processed(
    targets: Sequence[Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
    *,
    targets_path: str | Path,
    reconciliation_path: str | Path,
) -> None:
    target_file = Path(targets_path)
    reconciliation_file = Path(reconciliation_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    reconciliation_file.parent.mkdir(parents=True, exist_ok=True)
    target_text = "".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in targets
    )
    reconciliation_text = (
        json.dumps(reconciliation, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    target_file.write_text(target_text, encoding="utf-8", newline="\n")
    reconciliation_file.write_text(reconciliation_text, encoding="utf-8", newline="\n")


def assert_reconciliation_ready(reconciliation: Mapping[str, Any]) -> None:
    """正式账本只要求 1976–2016；2018 必须留在审计并关闭。"""

    raw_round_audit = reconciliation.get("raw_round_audit")
    raw_rounds = raw_round_audit.get("rounds") if isinstance(raw_round_audit, Mapping) else None
    if not isinstance(raw_rounds, list):
        raise IngestError("对账缺少可独立复核的 raw_round_audit.rounds")
    senate_ids_by_cycle: dict[int, list[str]] = defaultdict(list)
    for record in raw_rounds:
        if not isinstance(record, Mapping) or record.get("office") != "SENATE":
            continue
        if record.get("selection_status") != "selected_final_round":
            continue
        cycle = int(record["cycle"])
        suffix = "SPECIAL" if record.get("source_special") is True else "REGULAR"
        senate_ids_by_cycle[cycle].append(
            f"SENATE-{cycle}-{record['state']}-{suffix}"
        )
    for cycle in EXPECTED_CYCLES:
        actual_ids = senate_ids_by_cycle.get(cycle, [])
        if not _senate_inventory_matches(cycle, actual_ids):
            expected_count, expected_digest = EXPECTED_SENATE_INVENTORY[cycle]
            raise IngestError(
                f"SENATE {cycle} 席位清单漂移：实际 {len(actual_ids)} 席/"
                f"{_senate_inventory_digest(actual_ids)}，预期 {expected_count} 席/"
                f"{expected_digest}"
            )

    for office in ("HOUSE", "SENATE"):
        cycles = reconciliation["offices"][office]["cycles"]
        if [row["cycle"] for row in cycles] != list(EXPECTED_CYCLES):
            raise IngestError(f"{office} 没有完整覆盖 1976–2018 偶数周期")
        for row in cycles:
            if row["normalized_vote_conservation_failures"]:
                raise IngestError(f"{office} {row['cycle']} 规范化票数不守恒")
            if row["cycle"] <= FORMAL_TARGET_MAX_CYCLE and not row["benchmark_eligible"]:
                raise IngestError(
                    f"{office} {row['cycle']} 未通过 1976–2016 正式目标账本闸："
                    f"{row['benchmark_closed_reasons']}"
                )
        row_2018 = next(row for row in cycles if row["cycle"] == 2018)
        if row_2018["benchmark_eligible"] or "audit_only_2018" not in row_2018["benchmark_closed_reasons"]:
            raise IngestError(f"{office} 2018 必须作为审计周期关闭正式基准")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise IngestError(f"JSONL 第 {line_number} 行无效：{error}") from error
        if not isinstance(row, dict):
            raise IngestError(f"JSONL 第 {line_number} 行不是对象")
        rows.append(row)
    return rows


def finite_margin(row: Mapping[str, Any]) -> float | None:
    """供下游读取连续边际；缺少两党对手时保持 ``None``。"""

    value = row.get("two_party_margin")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IngestError(f"竞选 {row.get('race_id')} 的 two_party_margin 非有限数值")
    return float(value)
