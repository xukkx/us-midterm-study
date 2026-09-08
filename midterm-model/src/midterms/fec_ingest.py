"""离线解析已封印 FEC XLSX 中的 Senate 结果。

本模块只使用 Python 标准库。它在打开任何工作表 XML 前验证三个封印工作簿的
字节数和 SHA-256；随后只打开 2018/2022 Senate 结果相关 sheet。OOXML 的
sharedStrings、单元格类型、合并单元格和脚注均采用显式规则处理，遇到歧义直接
失败，不用猜测补值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET


MODEL_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = MODEL_ROOT.parent
MANIFEST_PATH = MODEL_ROOT / "config" / "lh058-fec-content-manifest.json"
INVENTORY_PATH = MODEL_ROOT / "config" / "fec-senate-contest-inventory.json"
LEDGER_PATH = MODEL_ROOT / "data" / "processed" / "fec-senate-2018-2022.jsonl"
MEDSL_PATH = MODEL_ROOT / "data" / "processed" / "historical-targets.jsonl"
RECONCILIATION_PATH = MODEL_ROOT / "data" / "processed" / "fec-medsl-2018-reconciliation.json"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": NS_MAIN, "r": NS_REL, "p": NS_PKG_REL}
FEC_HARDCODED_HASHES = {
    2018: "f2c42311862b4927df2ca5908c5f9c8f8da6221a8db88fd00434a22ec1e0e303",
    2020: "5073b6d2c76c86c941508dfb1a11cc497e8529b0068c5132aceb0f385c19352e",
    2022: "cdb258ea23803e50d752bcea19faa39b3c201eb960094bcb556c3a38c2350897",
}
SENATE_STATES = frozenset(
    "AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split()
)
EXPECTED_SHEETS = {
    2018: ("2018 US Senate Results by State",),
    2022: ("7. US Senate Results by State", "11. Special Elections 2021-2023"),
}
SOURCE_GENERAL_COLUMN = 16
SOURCE_RUNOFF_COLUMN = 18


class FecIngestError(ValueError):
    """FEC 结果解析或资格闸失败。"""


def _configure_console() -> None:
    """让 Windows 默认代码页也能稳定输出中文失败证据。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


_configure_console()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _column_number(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    if not letters:
        raise FecIngestError(f"非法单元格地址：{cell_ref!r}")
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _split_range(ref: str) -> tuple[tuple[int, int], tuple[int, int]]:
    parts = ref.split(":")
    if len(parts) != 2:
        raise FecIngestError(f"合并单元格范围非法：{ref!r}")
    def one(value: str) -> tuple[int, int]:
        match = re.fullmatch(r"([A-Z]+)([0-9]+)", value.upper())
        if not match:
            raise FecIngestError(f"单元格范围端点非法：{value!r}")
        return _column_number(match.group(1)), int(match.group(2))
    start, end = one(parts[0]), one(parts[1])
    if end[0] < start[0] or end[1] < start[1]:
        raise FecIngestError(f"合并单元格范围倒置：{ref!r}")
    return start, end


def _cell_text(cell: ET.Element, shared_strings: Sequence[str]) -> str:
    value = cell.find(f"{{{NS_MAIN}}}v")
    inline = cell.find(f"{{{NS_MAIN}}}is")
    cell_type = cell.attrib.get("t")
    if value is None or value.text is None:
        if cell_type == "inlineStr" and inline is not None:
            return "".join(text.text or "" for text in inline.iter(f"{{{NS_MAIN}}}t"))
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            index = int(raw)
        except ValueError as error:
            raise FecIngestError(f"sharedStrings 索引不是整数：{raw!r}") from error
        if index < 0 or index >= len(shared_strings):
            raise FecIngestError(f"sharedStrings 索引越界：{index}")
        return shared_strings[index]
    if cell_type == "b":
        if raw not in {"0", "1"}:
            raise FecIngestError(f"布尔单元格值非法：{raw!r}")
        return "TRUE" if raw == "1" else "FALSE"
    if cell_type in {"e", "str"}:
        return raw
    return raw


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError as error:
        raise FecIngestError("工作簿缺少 sharedStrings.xml") from error
    values = []
    for item in root.findall(f"{{{NS_MAIN}}}si"):
        values.append("".join(text.text or "" for text in item.iter(f"{{{NS_MAIN}}}t")))
    return tuple(values)


class _SheetRows:
    """读取一个已获授权 sheet，并在返回前完成合并单元格歧义检查。"""

    def __init__(self, archive: zipfile.ZipFile, target: str, sheet_name: str):
        self.archive = archive
        self.target = target.lstrip("/")
        if not self.target.startswith("xl/"):
            self.target = "xl/" + self.target
        self.sheet_name = sheet_name
        try:
            self.root = ET.fromstring(archive.read(self.target))
        except KeyError as error:
            raise FecIngestError(f"sheet XML 缺失：{sheet_name}/{self.target}") from error
        self.shared_strings = _shared_strings(archive)
        self.merges = self._read_merges()

    def _read_merges(self) -> dict[tuple[int, int], tuple[int, int]]:
        output: dict[tuple[int, int], tuple[int, int]] = {}
        container = self.root.find(f"{{{NS_MAIN}}}mergeCells")
        if container is None:
            return output
        for item in container.findall(f"{{{NS_MAIN}}}mergeCell"):
            start, end = _split_range(item.attrib.get("ref", ""))
            for row in range(start[1], end[1] + 1):
                for column in range(start[0], end[0] + 1):
                    key = (row, column)
                    if key in output:
                        raise FecIngestError(f"合并单元格范围重叠：{item.attrib.get('ref')}")
                    output[key] = start
        return output

    def rows(self) -> Iterable[tuple[int, dict[int, str]]]:
        sheet_data = self.root.find(f"{{{NS_MAIN}}}sheetData")
        if sheet_data is None:
            raise FecIngestError(f"sheet 缺少 sheetData：{self.sheet_name}")
        explicit: dict[tuple[int, int], str] = {}
        row_numbers: set[int] = set()
        for row in sheet_data.findall(f"{{{NS_MAIN}}}row"):
            row_number = int(row.attrib.get("r", "0"))
            if row_number <= 0 or row_number in row_numbers:
                raise FecIngestError(f"sheet 行号重复或非法：{self.sheet_name}/{row_number}")
            row_numbers.add(row_number)
            for cell in row.findall(f"{{{NS_MAIN}}}c"):
                address = cell.attrib.get("r", "")
                column = _column_number(address)
                key = (row_number, column)
                if key in explicit:
                    raise FecIngestError(f"重复单元格：{self.sheet_name}/{address}")
                explicit[key] = _cell_text(cell, self.shared_strings)
        for key, value in explicit.items():
            top_left = self.merges.get(key)
            if top_left is not None and key != top_left and value != "":
                raise FecIngestError(
                    f"合并单元格歧义：{self.sheet_name}/{key} 含非空值而非左上角"
                )
        all_rows = sorted(row_numbers | {row for row, _ in self.merges})
        for row_number in all_rows:
            values: dict[int, str] = {}
            for column in range(1, max([col for r, col in self.merges if r == row_number] + [0]) + 1):
                top_left = self.merges.get((row_number, column))
                if top_left is not None:
                    values[column] = explicit.get(top_left, "")
            for (row, column), value in explicit.items():
                if row == row_number:
                    values[column] = value
            yield row_number, values


def _normal_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _identity(value: str) -> str:
    return _normal_text(value).casefold()


def _integer(value: str, field: str, *, allow_blank: bool = False) -> int | None:
    text = _normal_text(value)
    if text == "":
        if allow_blank:
            return None
        raise FecIngestError(f"{field} 不能为空")
    if not re.fullmatch(r"[0-9]+", text):
        raise FecIngestError(f"{field} 不是非负整数：{value!r}")
    return int(text)


def _party(value: str, candidate: str, *, special_nonpartisan: bool = False) -> str:
    raw = _normal_text(value).upper()
    if special_nonpartisan:
        normalized = _identity(candidate)
        if normalized.startswith("cindy hyde-smith") or normalized.startswith("hyde-smith, cindy"):
            return "REPUBLICAN"
        if normalized.startswith("mike espy") or normalized.startswith("espy, mike"):
            return "DEMOCRATIC"
        if normalized.startswith("mcdaniel, chris") or normalized.startswith("chris mcdaniel"):
            return "REPUBLICAN"
        if normalized.startswith("bartee, tobey") or normalized.startswith("tobey bartee"):
            return "DEMOCRATIC"
        raise FecIngestError(f"非党派特别选举候选人缺少冻结党标规则：{candidate!r}")
    if raw in {"D", "DFL", "DNL", "DEM", "D/IP"} or raw.startswith("D/"):
        return "DEMOCRATIC"
    if raw in {"R", "R*", "R/CON"} or raw.startswith("R/"):
        return "REPUBLICAN"
    return "OTHER"


def _is_writein(candidate: str, party: str, fec_id: str) -> bool:
    normalized = _identity(candidate)
    return (
        not normalized
        or normalized in {"scattered", "all others", "none of these candidates"}
        or party == "W"
        or party.startswith("W(")
        or fec_id.strip().lower() == "n/a" and not normalized
    )


def _selected_sheets(
    archive: zipfile.ZipFile, year: int
) -> tuple[dict[str, str], tuple[str, ...]]:
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError) as error:
        raise FecIngestError(f"{year} 工作簿结构非法") from error
    relmap = {
        relation.attrib.get("Id", ""): relation.attrib.get("Target", "")
        for relation in rels
    }
    names = []
    mapping: dict[str, str] = {}
    sheets = workbook.find(f"{{{NS_MAIN}}}sheets")
    for sheet in sheets if sheets is not None else ():
        name = sheet.attrib.get("name", "")
        names.append(name)
        if name in EXPECTED_SHEETS.get(year, ()):
            rel_id = sheet.attrib.get(f"{{{NS_REL}}}id", "")
            target = relmap.get(rel_id, "")
            if not target:
                raise FecIngestError(f"sheet 缺少关系：{year}/{name}")
            mapping[name] = target
    missing = [name for name in EXPECTED_SHEETS.get(year, ()) if name not in mapping]
    if missing:
        raise FecIngestError(f"授权 Senate sheet 缺失：{year}/{missing}")
    return mapping, tuple(names)


def verify_sealed_workbooks(
    manifest_path: str | Path = MANIFEST_PATH,
    raw_dir: str | Path | None = None,
) -> dict[int, dict[str, Any]]:
    """在打开 ZIP 成员前逐字节验证三个封印对象。"""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = MODEL_ROOT if raw_dir is None else Path(raw_dir).resolve().parents[2]
    directory = MODEL_ROOT / "data" / "raw" / "fec" if raw_dir is None else Path(raw_dir)
    results: dict[int, dict[str, Any]] = {}
    sources = manifest.get("sources")
    if not isinstance(sources, list) or {item.get("year") for item in sources} != {2018, 2020, 2022}:
        raise FecIngestError("LH-058 manifest 必须精确覆盖 2018/2020/2022")
    for item in sorted(sources, key=lambda value: int(value["year"])):
        year = int(item["year"])
        path = directory / str(item["filename"])
        data = path.read_bytes()
        digest = sha256_bytes(data)
        expected = FEC_HARDCODED_HASHES.get(year)
        if len(data) != int(item["expected_byte_count"]) or digest != expected:
            raise FecIngestError(f"{year} 封印哈希/字节数不匹配")
        if item.get("expected_byte_count") != len(data):
            raise FecIngestError(f"{year} manifest 字节数不匹配")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise FecIngestError(f"{year} ZIP CRC 校验失败")
            selected, sheet_names = _selected_sheets(archive, year) if year in EXPECTED_SHEETS else ({}, ())
        results[year] = {
            "filename": path.name,
            "byte_count": len(data),
            "sha256": digest,
            "selected_sheets": list(selected),
            "sheet_names": list(sheet_names),
            "opened_sheet_xml": False,
        }
    return results


def _row_value(row: Mapping[int, str], column: int) -> str:
    return _normal_text(str(row.get(column, "")))


def _is_total_row(row: Mapping[int, str]) -> bool:
    fec_id = _row_value(row, 5).lower()
    candidate = _row_value(row, 9)
    label = _row_value(row, 10)
    general_total = _row_value(row, SOURCE_GENERAL_COLUMN)
    runoff_total = _row_value(row, SOURCE_RUNOFF_COLUMN)
    return (
        fec_id == "n/a"
        and candidate == ""
        and label.endswith("State Votes:")
        and not label.startswith("Party ")
        and bool(general_total or runoff_total)
    )


def _is_candidate_row(row: Mapping[int, str]) -> bool:
    candidate = _row_value(row, 9)
    if candidate in {"", "Party Votes:", "Total State Votes:", "Total Party Votes:"}:
        return False
    general = _row_value(row, SOURCE_GENERAL_COLUMN)
    runoff = _row_value(row, SOURCE_RUNOFF_COLUMN)
    return bool(general or runoff or _row_value(row, 5) not in {"", "n/a"})


def _groups_from_main_sheet(
    rows: Iterable[tuple[int, dict[int, str]]], year: int
) -> list[tuple[str, list[dict[str, Any]], dict[str, Any]]]:
    groups: list[tuple[str, list[dict[str, Any]], dict[str, Any]]] = []
    state: str | None = None
    current: list[dict[str, Any]] = []
    ordinal = 0
    for row_number, row in rows:
        raw_state = _row_value(row, 2)
        if raw_state in SENATE_STATES:
            state = raw_state
        if state is None:
            continue
        if _is_candidate_row(row):
            current.append(
                {
                    "row_number": row_number,
                    "state": state,
                    "fec_id": _row_value(row, 5),
                    "candidate": _row_value(row, 9),
                    "raw_party": _row_value(row, 11),
                    "general_votes": _row_value(row, SOURCE_GENERAL_COLUMN),
                    "runoff_votes": _row_value(row, SOURCE_RUNOFF_COLUMN),
                    "general_winner_indicator": _row_value(row, 22),
                    "special_winner_indicator": _row_value(row, 23),
                    "footnotes": _row_value(row, 24),
                }
            )
        if _is_total_row(row):
            total = {
                "row_number": row_number,
                "general_total": _integer(_row_value(row, SOURCE_GENERAL_COLUMN), f"{year}/{state}/general_total"),
                "runoff_total": _integer(_row_value(row, SOURCE_RUNOFF_COLUMN), f"{year}/{state}/runoff_total", allow_blank=True),
                "footnotes": _row_value(row, 24),
            }
            if not current:
                raise FecIngestError(f"{year}/{state} total 前没有候选行")
            ordinal += 1
            groups.append((state, current, {**total, "ordinal": ordinal}))
            current = []
    if current:
        raise FecIngestError(f"{year}/{state} sheet 末尾缺少总数行")
    return groups


def _group_signature(lines: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                str(line["fec_id"]),
                _identity(str(line["candidate"])),
                str(line["general_votes"]),
                str(line["runoff_votes"]),
            )
            for line in lines
        )
    )


def _special_group_keys(
    rows: Iterable[tuple[int, dict[int, str]]], year: int
) -> set[tuple[str, tuple[tuple[str, str, str, str], ...]]]:
    """从 2022 special sheet 提取候选签名，不依赖两个 sheet 的行号相同。"""

    if year != 2022:
        return set()
    state: str | None = None
    candidate_rows: list[tuple[str, tuple[tuple[str, str, str, str], ...]]] = []
    current: list[dict[str, Any]] = []
    for row_number, row in rows:
        raw_state = _row_value(row, 2)
        if raw_state in SENATE_STATES:
            state = raw_state
        if state is None:
            continue
        if _is_candidate_row(row) and _row_value(row, 4) == "S":
            current.append(
                {
                    "fec_id": _row_value(row, 5),
                    "candidate": _row_value(row, 9),
                    "general_votes": _row_value(row, SOURCE_GENERAL_COLUMN),
                    "runoff_votes": _row_value(row, SOURCE_RUNOFF_COLUMN),
                }
            )
        if _is_total_row(row):
            if current and state in {"CA", "OK"}:
                candidate_rows.append((state, _group_signature(current)))
            current = []
    return set(candidate_rows)


def _candidate_records(
    lines: Sequence[Mapping[str, Any]], *, cycle: int, special: bool, final_round: str
) -> tuple[list[dict[str, Any]], int, int, int]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for line in lines:
        # 即使最终采用 runoff，也必须拒绝被忽略的非数值票数，避免把坏单元格
        # 静默藏在未选中的轮次里。
        for field in ("general_votes", "runoff_votes"):
            if str(line[field]) != "":
                _integer(str(line[field]), f"候选人票数/{line['state']}/{line['candidate']}/{field}")
        name = str(line["candidate"])
        identity = "__writein__" if _is_writein(name, str(line["raw_party"]), str(line["fec_id"])) else _identity(name)
        if identity == "__writein__":
            identity += ":" + str(line["row_number"])
        grouped[identity].append(line)
    records: list[dict[str, Any]] = []
    for identity, members in sorted(grouped.items(), key=lambda item: min(int(row["row_number"]) for row in item[1])):
        ordered = sorted(members, key=lambda row: int(row["row_number"]))
        name = _normal_text(str(ordered[0]["candidate"])) or None
        votes = sum(_integer(str(row[final_round]), f"候选人票数/{ordered[0]['state']}/{name}") or 0 for row in ordered if str(row[final_round]) != "")
        raw_parties = sorted({str(row["raw_party"]) for row in ordered})
        writein = any(_is_writein(str(row["candidate"]), str(row["raw_party"]), str(row["fec_id"])) for row in ordered)
        if special and ordered[0]["state"] == "MS" and final_round == "runoff_votes":
            canonical = _party("N", name or "", special_nonpartisan=True)
        else:
            canonical_values = {_party(str(row["raw_party"]), name or "") for row in ordered}
            canonical = "DEMOCRATIC" if "DEMOCRATIC" in canonical_values else "REPUBLICAN" if "REPUBLICAN" in canonical_values else "OTHER"
        records.append(
            {
                "candidate": name,
                "canonical_party": canonical if not writein else "UNKNOWN",
                "fusion_line_count": len(ordered),
                "raw_candidate_names": sorted({str(row["candidate"]) for row in ordered if str(row["candidate"])}),
                "raw_parties": raw_parties,
                "source_rows": [int(row["row_number"]) for row in ordered],
                "votes": votes,
                "writein": writein,
            }
        )
    if not records:
        raise FecIngestError("竞选候选人为空")
    democratic = sum(int(item["votes"]) for item in records if item["canonical_party"] == "DEMOCRATIC")
    republican = sum(int(item["votes"]) for item in records if item["canonical_party"] == "REPUBLICAN")
    third = sum(int(item["votes"]) for item in records if item["canonical_party"] not in {"DEMOCRATIC", "REPUBLICAN"})
    return records, democratic, republican, third


def _normalize_group(
    state: str,
    lines: Sequence[Mapping[str, Any]],
    total: Mapping[str, Any],
    *,
    cycle: int,
    special: bool,
    source_workbook: str,
    source_sha256: str,
    source_sheet: str,
) -> dict[str, Any]:
    has_runoff = any(str(line["runoff_votes"]) for line in lines)
    final_round = "runoff_votes" if has_runoff else "general_votes"
    final_total = total.get("runoff_total") if has_runoff else total.get("general_total")
    if final_total is None:
        raise FecIngestError(f"{cycle}/{state} final 总数缺失")
    candidates, democratic, republican, third = _candidate_records(
        lines, cycle=cycle, special=special, final_round=final_round
    )
    candidate_sum = sum(int(item["votes"]) for item in candidates)
    raw_total = int(final_total)
    delta = candidate_sum - raw_total
    final_sorted = sorted(candidates, key=lambda item: (-int(item["votes"]), str(item["candidate"] or "")))
    if not final_sorted:
        raise FecIngestError(f"{cycle}/{state} 没有候选人")
    if len(final_sorted) > 1 and int(final_sorted[0]["votes"]) == int(final_sorted[1]["votes"]):
        raise FecIngestError(f"{cycle}/{state} 多赢家：最高票并列")
    winner = final_sorted[0]
    denominator = democratic + republican
    if democratic and republican:
        margin = 100.0 * (democratic - republican) / denominator
        margin_reason = None
    else:
        margin = None
        margin_reason = "no_democratic_and_republican_pair"
    election_type = "special" if special else "regular"
    race_id = f"SENATE-{cycle}-{state}-{election_type.upper()}"
    return {
        "schema_version": "1.0",
        "office": "SENATE",
        "cycle": cycle,
        "state": state,
        "race_id": race_id,
        "election_type": election_type,
        "round_kind": "general_runoff" if has_runoff else "general",
        "candidates": candidates,
        "democratic_votes": democratic if democratic else None,
        "republican_votes": republican if republican else None,
        "third_party_votes": third,
        "two_party_margin": margin,
        "two_party_margin_reason": margin_reason,
        "winner": winner,
        "winner_group": winner["canonical_party"],
        "candidate_votes_sum": candidate_sum,
        "normalized_total_votes": candidate_sum,
        "raw_total_votes": raw_total,
        "raw_total_vote_delta": delta,
        "raw_round_totals": {
            "general": total.get("general_total"),
            "general_runoff": total.get("runoff_total"),
        },
        "raw_total_preserved": True,
        "benchmark_eligible": delta == 0,
        "source": {
            "workbook": source_workbook,
            "sha256": source_sha256,
            "sheet": source_sheet,
            "candidate_rows": sorted(int(line["row_number"]) for line in lines),
            "total_row": int(total["row_number"]),
            "footnotes": sorted({str(line["footnotes"]) for line in lines if str(line["footnotes"])} | ({str(total["footnotes"])} if str(total.get("footnotes")) else set())),
        },
        "special_rule": "FEC nonpartisan MS runoff candidate crosswalk" if cycle == 2018 and state == "MS" and special else None,
    }


def canonical_contest_inventory(race_ids: Iterable[str]) -> tuple[tuple[str, ...], str]:
    values = tuple(sorted(str(value) for value in race_ids))
    if not values or len(values) != len(set(values)):
        raise FecIngestError("竞选清单必须非空且 race_id 唯一")
    expected = []
    for race_id in values:
        if not re.fullmatch(r"SENATE-(2018|2022)-[A-Z]{2}-(REGULAR|SPECIAL)", race_id):
            raise FecIngestError(f"race_id 编码非法：{race_id}")
        expected.append(race_id)
    return values, sha256_bytes(canonical_json_bytes(list(expected)))


def qualify_ledger(
    rows: Sequence[Mapping[str, Any]],
    cycle: int,
    expected_race_ids: Sequence[str],
) -> dict[str, Any]:
    """执行完整竞赛清单、赢家、守恒和党派标签闸；失败只会关闭该届。"""

    subset = [row for row in rows if int(row.get("cycle", -1)) == cycle]
    expected = tuple(sorted(str(value) for value in expected_race_ids))
    actual = tuple(sorted(str(row.get("race_id", "")) for row in subset))
    unique_race_ids = len(actual) == len(set(actual))
    inventory_complete = actual == expected and unique_race_ids
    winner_unique = True
    vote_conservation = True
    party_tags = True
    allowed_parties = {"DEMOCRATIC", "REPUBLICAN", "OTHER", "UNKNOWN"}
    for row in subset:
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            winner_unique = False
            continue
        vote_values = [item.get("votes") for item in candidates if isinstance(item, Mapping)]
        if (
            len(vote_values) != len(candidates)
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in vote_values)
            or len(vote_values) < 1
            or sum(value == max(vote_values) for value in vote_values) != 1
        ):
            winner_unique = False
        if int(row.get("raw_total_vote_delta", 1)) != 0:
            vote_conservation = False
        if int(row.get("candidate_votes_sum", -1)) != sum(vote_values):
            vote_conservation = False
        if row.get("winner_group") not in allowed_parties:
            party_tags = False
        if any(not isinstance(item, Mapping) or item.get("canonical_party") not in allowed_parties for item in candidates):
            party_tags = False
        winner = row.get("winner")
        if not isinstance(winner, Mapping) or winner.get("votes") != max(vote_values):
            winner_unique = False
        elif winner.get("canonical_party") != row.get("winner_group"):
            party_tags = False
    checks = {
        "full_contest_inventory": inventory_complete,
        "unique_race_id": unique_race_ids,
        "unique_winner": winner_unique,
        "vote_conservation": vote_conservation,
        "party_tags": party_tags,
    }
    return {
        "cycle": cycle,
        "expected_race_count": len(expected),
        "actual_race_count": len(actual),
        "expected_race_ids": list(expected),
        "actual_race_ids": list(actual),
        "checks": checks,
        "benchmark_eligible": all(checks.values()),
        "failure_reasons": [name for name, passed in checks.items() if not passed],
    }


def _inventory_from_config(path: str | Path = INVENTORY_PATH) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != "1.0":
        raise FecIngestError("竞选清单 config 非法")
    for cycle, expected in ((2018, 35), (2022, 36)):
        ids = raw.get("cycles", {}).get(str(cycle), {}).get("race_ids")
        if not isinstance(ids, list):
            raise FecIngestError(f"竞选清单缺少 {cycle}")
        canonical, digest = canonical_contest_inventory(ids)
        entry = raw["cycles"][str(cycle)]
        if tuple(ids) != canonical or entry.get("contest_inventory_hash") != digest or len(ids) != expected:
            raise FecIngestError(f"竞选清单 {cycle} 非规范或数量漂移")
    return raw


def _classify_groups(
    groups: Sequence[tuple[str, list[dict[str, Any]], dict[str, Any]]],
    *,
    year: int,
    special_rows: set[tuple[str, tuple[tuple[str, str, str, str], ...]]],
) -> list[tuple[str, list[dict[str, Any]], dict[str, Any], bool]]:
    by_state: dict[str, list[tuple[str, list[dict[str, Any]], dict[str, Any]]]] = defaultdict(list)
    for group in groups:
        by_state[group[0]].append(group)
    classified = []
    for state, state_groups in sorted(by_state.items()):
        state_groups = sorted(state_groups, key=lambda item: int(item[2]["ordinal"]))
        if year == 2018:
            special_count = 2 if state in {"MN", "MS"} else 0
            expected_count = 2 if special_count else 1
            if len(state_groups) != expected_count:
                raise FecIngestError(f"{year}/{state} regular/special 分组数异常")
            for index, group in enumerate(state_groups):
                classified.append((*group, bool(index == 1 and special_count)))
        else:
            special = [group for group in state_groups if (state, _group_signature(group[1])) in special_rows]
            if state in {"CA", "OK"}:
                if len(state_groups) != 2 or len(special) != 1:
                    raise FecIngestError(f"2022/{state} special 分组无法唯一绑定")
                for group in state_groups:
                    classified.append((*group, group in special))
            else:
                if len(state_groups) != 1 or special:
                    raise FecIngestError(f"2022/{state} regular 分组异常")
                classified.append((*state_groups[0], False))
    return classified


def parse_fec_senate(
    *,
    manifest_path: str | Path = MANIFEST_PATH,
    raw_dir: str | Path | None = None,
    inventory_path: str | Path = INVENTORY_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    verified = verify_sealed_workbooks(manifest_path, raw_dir)
    _inventory_from_config(inventory_path)
    raw_directory = MODEL_ROOT / "data" / "raw" / "fec" if raw_dir is None else Path(raw_dir)
    output: list[dict[str, Any]] = []
    selected_metadata: dict[str, Any] = {}
    for year in (2018, 2022):
        path = raw_directory / verified[year]["filename"]
        with zipfile.ZipFile(path) as archive:
            mapping, sheet_names = _selected_sheets(archive, year)
            selected_metadata[str(year)] = {
                "selected_sheets": list(mapping),
                "sheet_names": list(sheet_names),
                "source_sha256": verified[year]["sha256"],
            }
            main_name = EXPECTED_SHEETS[year][0]
            main_rows = _SheetRows(archive, mapping[main_name], main_name).rows()
            groups = _groups_from_main_sheet(main_rows, year)
            special_rows: set[tuple[str, tuple[tuple[str, str, str, str], ...]]] = set()
            if year == 2022:
                special_rows = _special_group_keys(_SheetRows(archive, mapping[EXPECTED_SHEETS[year][1]], EXPECTED_SHEETS[year][1]).rows(), year)
            for state, lines, total, special in _classify_groups(groups, year=year, special_rows=special_rows):
                output.append(
                    _normalize_group(
                        state, lines, total, cycle=year, special=special,
                        source_workbook=verified[year]["filename"], source_sha256=verified[year]["sha256"], source_sheet=main_name,
                    )
                )
    output.sort(key=lambda row: (int(row["cycle"]), str(row["race_id"])))
    inventory = _inventory_from_config(inventory_path)
    expected_ids = {cycle: tuple(inventory["cycles"][str(cycle)]["race_ids"]) for cycle in (2018, 2022)}
    actual_ids = {cycle: tuple(row["race_id"] for row in output if int(row["cycle"]) == cycle) for cycle in (2018, 2022)}
    if actual_ids != expected_ids:
        raise FecIngestError(f"解析竞选清单与冻结 config 不一致：actual={actual_ids} expected={expected_ids}")
    qualifications = {}
    for cycle in (2018, 2022):
        qualification = qualify_ledger(output, cycle, expected_ids[cycle])
        qualifications[str(cycle)] = qualification
        canonical, digest = canonical_contest_inventory(actual_ids[cycle])
        for row in output:
            if int(row["cycle"]) == cycle:
                row["contest_inventory_hash"] = digest
                row["period_benchmark_eligible"] = qualification["benchmark_eligible"]
    metadata = {
        "schema_version": "1.0",
        "contract_id": "LH-059",
        "source_verification": verified,
        "selected_sheet_audit": selected_metadata,
        "ledger_row_count": len(output),
        "cycle_row_counts": {str(cycle): sum(int(row["cycle"]) == cycle for row in output) for cycle in (2018, 2022)},
        "contest_inventory_hashes": {str(cycle): output[next(index for index, row in enumerate(output) if int(row["cycle"]) == cycle)]["contest_inventory_hash"] for cycle in (2018, 2022)},
        "qualification": qualifications,
        "house_or_president_values_emitted": False,
        "deterministic_sort": "cycle then race_id",
    }
    return output, metadata


def jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    ordered = sorted((dict(row) for row in rows), key=lambda row: (int(row.get("cycle", -1)), str(row.get("race_id", ""))))
    return b"".join(canonical_json_bytes(row) + b"\n" for row in ordered)


def reconcile_medsl_2018(
    fec_rows: Sequence[Mapping[str, Any]],
    medsl_path: str | Path = MEDSL_PATH,
) -> dict[str, Any]:
    """生成完整 2018 FEC×MEDSL 对账表；只读 MEDSL，不回写或修正其行。"""

    medsl_rows = []
    raw_bytes = Path(medsl_path).read_bytes()
    for line_number, line in enumerate(raw_bytes.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("cycle") == 2018 and item.get("office") == "SENATE":
            medsl_rows.append(item)
    medsl_by_race = {str(row["race_id"]): row for row in medsl_rows}
    fec_by_race = {str(row["race_id"]): row for row in fec_rows if int(row.get("cycle", -1)) == 2018}
    if len(fec_by_race) != 35 or len(medsl_by_race) != 35:
        raise FecIngestError(f"2018 FEC×MEDSL 对账必须是 35×35：fec={len(fec_by_race)} medsl={len(medsl_by_race)}")
    rows = []
    for race_id in sorted(fec_by_race):
        fec = fec_by_race[race_id]
        medsl = medsl_by_race.get(race_id)
        if medsl is None:
            raise FecIngestError(f"MEDSL 缺少 race_id：{race_id}")
        fec_margin = fec.get("two_party_margin")
        medsl_margin = medsl.get("two_party_margin")
        rows.append({
            "race_id": race_id,
            "cycle": 2018,
            "state": fec.get("state"),
            "election_type": fec.get("election_type"),
            "fec": {
                "two_party_margin": fec_margin,
                "winner_group": fec.get("winner_group"),
                "raw_total_votes": fec.get("raw_total_votes"),
                "raw_total_vote_delta": fec.get("raw_total_vote_delta"),
                "benchmark_eligible": fec.get("benchmark_eligible"),
                "period_benchmark_eligible": fec.get("period_benchmark_eligible"),
            },
            "medsl": {
                "two_party_margin": medsl_margin,
                "winner_group": medsl.get("winner_group"),
                "source_total_vote_delta": medsl.get("source_total_vote_delta"),
                "benchmark_eligible": medsl.get("benchmark_eligible"),
                "status": medsl.get("status"),
                "audit_only": True,
            },
            "margin_delta_fec_minus_medsl": None if fec_margin is None or medsl_margin is None else fec_margin - medsl_margin,
            "reconciliation_status": "matched_race_id",
        })
    return {
        "schema_version": "1.0",
        "contract_id": "LH-059",
        "reconciliation_id": "FEC_MEDSL_SENATE_2018_REPORT_ONLY",
        "fec_ledger_rows": len(fec_by_race),
        "medsl_rows": len(medsl_by_race),
        "medsl_audit_only": True,
        "medsl_source_sha256": sha256_bytes(raw_bytes),
        "data_mutation": False,
        "rows": rows,
    }


def reconciliation_bytes(report: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(report) + b"\n"


def write_or_check(mode: str, output_path: str | Path = LEDGER_PATH) -> int:
    rows, _metadata = parse_fec_senate()
    payload = jsonl_bytes(rows)
    path = Path(output_path)
    if mode == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        print(f"写入 {path} ({len(payload)} bytes; {len(rows)} rows)")
        return 0
    if not path.is_file() or path.read_bytes() != payload:
        print(f"账本字节不一致或缺失：{path}", file=sys.stderr)
        return 1
    print(f"FEC Senate ledger 字节校验通过（{len(rows)} rows）")
    return 0


def write_or_check_reconciliation(mode: str, output_path: str | Path = RECONCILIATION_PATH) -> int:
    rows, _metadata = parse_fec_senate()
    payload = reconciliation_bytes(reconcile_medsl_2018(rows))
    path = Path(output_path)
    if mode == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        print(f"写入 {path} ({len(payload)} bytes; 35 rows)")
        return 0
    if not path.is_file() or path.read_bytes() != payload:
        print(f"对账报告字节不一致或缺失：{path}", file=sys.stderr)
        return 1
    print("FEC×MEDSL 2018 对账报告字节校验通过（35 rows）")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--write-reconciliation", action="store_true")
    group.add_argument("--check-reconciliation", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write_reconciliation or args.check_reconciliation:
            return write_or_check_reconciliation("write" if args.write_reconciliation else "check")
        return write_or_check("write" if args.write else "check")
    except (FecIngestError, OSError, UnicodeError, zipfile.BadZipFile, ET.ParseError, json.JSONDecodeError) as error:
        print(f"FEC 解析失败关闭：{error}", file=sys.stderr)
        return 2


__all__ = [
    "EXPECTED_SHEETS", "FEC_HARDCODED_HASHES", "FecIngestError", "INVENTORY_PATH", "LEDGER_PATH",
    "canonical_contest_inventory", "canonical_json_bytes", "jsonl_bytes", "parse_fec_senate",
    "reconcile_medsl_2018", "reconciliation_bytes", "verify_sealed_workbooks", "write_or_check",
    "write_or_check_reconciliation",
]


if __name__ == "__main__":
    raise SystemExit(main())
