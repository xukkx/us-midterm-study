"""真实历史来源、规范化、合票与对账的聚焦测试。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


MODEL_ROOT = Path(__file__).resolve().parents[1]
SRC = MODEL_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from midterms.ingest import (
    EXPECTED_CYCLES,
    EXPECTED_SENATE_INVENTORY,
    IngestError,
    _cycle_reconciliation,
    _raw_round_audit,
    assert_reconciliation_ready,
    build_historical_targets,
    load_jsonl,
    normalize_office,
    read_medsl_csv,
    write_processed,
)


SPEC = importlib.util.spec_from_file_location("lh048_fetch_data", MODEL_ROOT / "fetch_data.py")
if SPEC is None or SPEC.loader is None:  # pragma: no cover - 导入器异常时给出明确失败
    raise RuntimeError("无法加载 fetch_data.py")
fetch_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_data)


RAW = MODEL_ROOT / "data" / "raw" / "medsl-1976-2018"
HOUSE = RAW / "1976-2018-house.csv"
SENATE = RAW / "1976-2018-senate.csv"
DELTA_REPORT = MODEL_ROOT / "artifacts" / "lh063-r1-ndpa-delta.json"


class SourceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = fetch_data._load_manifest()

    def test_来源清单和五个本地文件三重核验通过(self) -> None:
        self.assertEqual(fetch_data.check_local(self.manifest), {"files": 5, "bytes": 4342996})

    def test_来源清单区分固定分发与_doi_当前版本(self) -> None:
        self.assertEqual(self.manifest["distribution_scope"]["years"], [1976, 2018])
        self.assertEqual(self.manifest["doi_current_metadata"]["house"]["version"], "15.0")
        self.assertEqual(self.manifest["doi_current_metadata"]["senate"]["version"], "8.0")
        self.assertTrue(self.manifest["distribution_scope"]["current_doi_versions_are_not_downloaded"])

    def test_所有来源登记_cc0_doi_blob_字节和_sha256(self) -> None:
        for entry in self.manifest["files"]:
            self.assertEqual(entry["license"]["spdx"], "CC0-1.0")
            self.assertTrue(entry["doi"])
            self.assertEqual(len(entry["git_blob_sha1"]), 40)
            self.assertGreater(entry["bytes"], 0)
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertTrue(entry["retrieved_at"])

    def test_下载主机白名单不能扩张(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["download_policy"]["allowed_hosts"].append("example.com")
        with self.assertRaisesRegex(fetch_data.SourceCheckError, "白名单"):
            fetch_data.validate_manifest(manifest)

    def test_固定提交路径漂移会失败(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["files"][0]["url"] = manifest["files"][0]["url"].replace(
            manifest["fixed_commit"], "master"
        )
        with self.assertRaisesRegex(fetch_data.SourceCheckError, "固定提交路径"):
            fetch_data.validate_manifest(manifest)

    def test_单字节篡改同时触发字节或哈希失败(self) -> None:
        entry = self.manifest["files"][0]
        data = (MODEL_ROOT / entry["local_path"]).read_bytes()
        with self.assertRaisesRegex(fetch_data.SourceCheckError, "漂移"):
            fetch_data.verify_bytes(entry, data[:-1] + bytes([data[-1] ^ 1]))

    def test_git_blob_sha_不是普通文件_sha(self) -> None:
        entry = self.manifest["files"][1]
        data = (MODEL_ROOT / entry["local_path"]).read_bytes()
        self.assertEqual(fetch_data._git_blob_sha1(data), entry["git_blob_sha1"])
        self.assertNotEqual(entry["git_blob_sha1"], entry["sha256"][:40])


class RawReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.house_rows, cls.house_encoding = read_medsl_csv(HOUSE, "HOUSE")
        cls.senate_rows, cls.senate_encoding = read_medsl_csv(SENATE, "SENATE")

    def test_原始行数固定(self) -> None:
        self.assertEqual(len(self.house_rows), 29636)
        self.assertEqual(len(self.senate_rows), 3421)

    def test_latin1_策略逐字节可逆且记录_c1(self) -> None:
        for audit in (self.house_encoding, self.senate_encoding):
            self.assertEqual(audit["codec"], "iso-8859-1")
            self.assertTrue(audit["roundtrip_bytes_equal"])
            self.assertGreater(audit["c1_byte_count"], 0)
            self.assertIn("禁止 ignore/replace", audit["strategy"])

    def test_每条来源行保留物理行号(self) -> None:
        self.assertEqual(self.house_rows[0]["source_line"], 2)
        self.assertEqual(self.senate_rows[0]["source_line"], 2)
        self.assertGreater(self.house_rows[-1]["source_line"], self.house_rows[0]["source_line"])

    def test_错误表头确定性拒绝(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_bytes(b'"year","state"\n1976,"Alabama"\n')
            with self.assertRaisesRegex(IngestError, "表头漂移"):
                read_medsl_csv(path, "HOUSE")

    def test_非法布尔值不被_truthiness_吞掉(self) -> None:
        source = HOUSE.read_bytes()
        changed = source.replace(
            b'"gen",FALSE,FALSE,"Bill Davenport"',
            b'"gen",FALSE,MAYBE,"Bill Davenport"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-bool.csv"
            path.write_bytes(changed)
            with self.assertRaisesRegex(IngestError, "只能是 TRUE/FALSE"):
                read_medsl_csv(path, "HOUSE")


class HistoricalTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.house_rows, _ = read_medsl_csv(HOUSE, "HOUSE")
        cls.senate_rows, _ = read_medsl_csv(SENATE, "SENATE")
        cls.targets, cls.reconciliation = build_historical_targets(
            house_path=HOUSE,
            senate_path=SENATE,
        )
        cls.by_id = {row["race_id"]: row for row in cls.targets}

    def test_正式账本闸通过且_2018_保持审计关闭(self) -> None:
        assert_reconciliation_ready(self.reconciliation)
        for office in ("HOUSE", "SENATE"):
            cycles = self.reconciliation["offices"][office]["cycles"]
            self.assertEqual([row["cycle"] for row in cycles], list(EXPECTED_CYCLES))
            self.assertFalse(cycles[-1]["benchmark_eligible"])
            self.assertIn("audit_only_2018", cycles[-1]["benchmark_closed_reasons"])

    def test_两院_2018_关闭原因由审计计数支撑(self) -> None:
        audit = self.reconciliation["raw_round_audit"]
        selected = self.reconciliation["raw_total_anomalies"]
        required = {
            "raw_total_scope_anomalies",
            "unofficial_source_rows_present",
            "fixed_snapshot_superseded_by_newer_doi",
        }
        for office in ("HOUSE", "SENATE"):
            cycle = self.reconciliation["offices"][office]["cycles"][-1]
            reasons = set(cycle["benchmark_closed_reasons"])
            self.assertTrue(required <= reasons)
            self.assertEqual(
                cycle["raw_total_scope_rounds"],
                sum(
                    row["office"] == office and row["cycle"] == 2018
                    for row in audit["rounds"]
                ),
            )
            self.assertEqual(
                cycle["raw_total_scope_anomaly_rounds"],
                sum(
                    row["office"] == office and row["cycle"] == 2018
                    for row in audit["anomalies"]
                ),
            )
            self.assertEqual(
                cycle["selected_target_raw_total_anomaly_races"],
                sum(
                    row["office"] == office and row["cycle"] == 2018
                    for row in selected
                ),
            )
            self.assertGreater(cycle["raw_total_scope_anomaly_rounds"], 0)
            self.assertGreater(cycle["unofficial_source_rows"], 0)

    def test_house_1976_至_2016_每周期恰为_435(self) -> None:
        counts = Counter(
            row["cycle"]
            for row in self.targets
            if row["office"] == "HOUSE" and row["benchmark_eligible"]
        )
        self.assertEqual(set(counts), set(range(1976, 2018, 2)))
        self.assertEqual(set(counts.values()), {435})

    def test_正式目标行数和周期集合机器可读(self) -> None:
        self.assertEqual(self.reconciliation["formal_target_row_counts"]["HOUSE"], 9135)
        self.assertEqual(self.reconciliation["formal_target_row_counts"]["SENATE"], 717)
        self.assertEqual(
            self.reconciliation["formal_target_cycle_sets"]["HOUSE"], list(range(1976, 2018, 2))
        )

    def test_race_id_含院别周期且_house_不伪造地图(self) -> None:
        for row in self.targets:
            self.assertTrue(row["race_id"].startswith(f"{row['office']}-{row['cycle']}-"))
            self.assertIsNone(row["map_id"])
            if row["office"] == "HOUSE":
                self.assertTrue(row["district_is_cycle_local"])

    def test_最终轮和来源阶段逐场保留(self) -> None:
        for row in self.targets:
            self.assertTrue(row["final_deciding_round"])
            self.assertIn(row["round_kind"], {
                "general",
                "runoff",
                "source_labeled_preliminary_but_final_for_target",
                "source_stage_missing_but_final_for_target",
            })
            self.assertTrue(row["source"]["source_lines"])

    def test_路易斯安那_2002_第五区选择决胜轮且保留前轮(self) -> None:
        row = self.by_id["HOUSE-2002-LA-05-CYCLE-SEAT"]
        self.assertEqual(row["selection_basis"], "regular_runoff")
        self.assertTrue(row["source_runoff"])
        self.assertEqual(row["winner"]["candidate"], "Rodney Alexander")
        self.assertEqual(len(row["unselected_source_rounds"]), 1)
        self.assertEqual(row["unselected_source_rounds"][0]["source_runoff"], False)

    def test_texas_特殊字段异常仍保留且不改写来源口径(self) -> None:
        row = self.by_id["HOUSE-2006-TX-25-CYCLE-SEAT"]
        self.assertEqual(row["election_type"], "special")
        self.assertEqual(row["source_stage"], "")
        self.assertEqual(row["selection_basis"], "source_special_only_sole_anomalous_stage")
        self.assertEqual(row["winner"]["candidate"], "Lloyd Doggett")

    def test_跨民主共和党票线合票但连续边际为空(self) -> None:
        row = self.by_id["HOUSE-1976-NY-07-CYCLE-SEAT"]
        winner = row["winner"]
        self.assertEqual(winner["fusion_line_count"], 3)
        self.assertEqual(set(winner["raw_parties"]), {"democrat", "liberal", "republican"})
        self.assertEqual(winner["winner_group"], "OTHER")
        self.assertIsNone(row["two_party_margin"])
        self.assertEqual(row["two_party_margin_reason"], "fusion_cross_major_party_candidate")

    def test_可验证同名多党线被精确合票(self) -> None:
        fusion = next(
            row
            for row in self.targets
            if any(
                candidate["fusion_line_count"] > 1
                and candidate["canonical_party"] == "DEMOCRATIC"
                for candidate in row["candidates"]
            )
        )
        candidate = next(
            candidate
            for candidate in fusion["candidates"]
            if candidate["fusion_line_count"] > 1
            and candidate["canonical_party"] == "DEMOCRATIC"
        )
        source_votes = {
            line["source_line"]: line["candidate_votes"]
            for line in self.house_rows
            if line["source_line"] in candidate["source_lines"]
        }
        self.assertEqual(candidate["votes"], sum(source_votes.values()))

    def test_零票无人竞争仍计赢家且不插补正负一百(self) -> None:
        row = self.by_id["HOUSE-2016-FL-24-CYCLE-SEAT"]
        self.assertEqual(row["winner"]["candidate"], "Frederica S. Wilson")
        self.assertEqual(row["normalized_total_votes"], 0)
        self.assertIsNone(row["two_party_margin"])
        self.assertEqual(row["two_party_margin_reason"], "zero_vote_uncontested_candidate")
        self.assertIsNone(row["third_party_share"])

    def test_缺少_d_r_对手不伪造连续边际(self) -> None:
        missing = [
            row
            for row in self.targets
            if row["two_party_margin_reason"] in {
                "missing_democratic_candidate",
                "missing_republican_candidate",
                "missing_both_major_parties",
            }
        ]
        self.assertTrue(missing)
        self.assertTrue(all(row["two_party_margin"] is None for row in missing))

    def test_第三党候选人与份额保留(self) -> None:
        row = self.by_id["SENATE-1976-AZ-REGULAR"]
        parties = {party for candidate in row["candidates"] for party in candidate["raw_parties"]}
        self.assertIn("libertarian", parties)
        self.assertIn("independent", parties)
        self.assertGreater(row["third_party_votes"], 0)
        self.assertGreater(row["third_party_share"], 0.0)

    def test_senate_同州常规与特殊选举不会合并(self) -> None:
        regular = self.by_id["SENATE-2018-MN-REGULAR"]
        special = self.by_id["SENATE-2018-MN-SPECIAL"]
        self.assertNotEqual(regular["race_id"], special["race_id"])
        self.assertEqual(regular["election_type"], "regular")
        self.assertEqual(special["election_type"], "special")
        self.assertNotEqual(regular["winner"]["candidate"], special["winner"]["candidate"])

    def test_ndpa_三场党线均自民主党边际剥离(self) -> None:
        affected = {
            "HOUSE-1976-AL-06-CYCLE-SEAT": "national democrat",
            "HOUSE-1980-AL-06-CYCLE-SEAT": "national democratic party of alabama",
            "SENATE-1980-AL-REGULAR": "national democratic party of alabama",
        }
        for race_id, raw_party in affected.items():
            with self.subTest(race_id=race_id):
                row = self.by_id[race_id]
                ndpa = next(
                    candidate
                    for candidate in row["candidates"]
                    if raw_party in candidate["raw_parties"]
                )
                self.assertEqual(ndpa["canonical_party"], "OTHER")
                democratic = sum(
                    candidate["votes"]
                    for candidate in row["candidates"]
                    if candidate["canonical_party"] == "DEMOCRATIC"
                )
                republican = sum(
                    candidate["votes"]
                    for candidate in row["candidates"]
                    if candidate["canonical_party"] == "REPUBLICAN"
                )
                self.assertEqual(row["democratic_votes"], democratic)
                self.assertAlmostEqual(
                    row["two_party_margin"],
                    100.0 * (democratic - republican) / (democratic + republican),
                    places=11,
                )

    def test_ndpa_delta_报告与再生账本逐行对齐(self) -> None:
        report = json.loads(DELTA_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["changed_row_count"], 3)
        self.assertEqual(report["unchanged_rows"]["count"], 10319)
        self.assertTrue(report["unchanged_rows"]["before_after_bytes_equal"])
        self.assertEqual(
            {row["race_id"] for row in report["changed_rows"]},
            {
                "HOUSE-1976-AL-06-CYCLE-SEAT",
                "HOUSE-1980-AL-06-CYCLE-SEAT",
                "SENATE-1980-AL-REGULAR",
            },
        )
        ledger = MODEL_ROOT / "data" / "processed" / "historical-targets.jsonl"
        self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(), report["after"]["sha256"])
        for delta in report["changed_rows"]:
            current = self.by_id[delta["race_id"]]
            self.assertEqual(current["democratic_votes"], delta["after"]["democratic_votes"])
            self.assertEqual(current["third_party_votes"], delta["after"]["third_party_votes"])
            self.assertEqual(current["two_party_margin"], delta["after"]["two_party_margin"])
        dependent = report["dependent_reports"][0]
        dependent_path = MODEL_ROOT / dependent["path"]
        self.assertEqual(
            hashlib.sha256(dependent_path.read_bytes()).hexdigest(),
            dependent["after_sha256"],
        )

    def test_ga_1992_2008_倒置_runoff_赢家锚定(self) -> None:
        expected = {
            1992: "Paul Coverdell",
            2008: "Saxby Chambliss",
        }
        for cycle, winner in expected.items():
            row = self.by_id[f"SENATE-{cycle}-GA-REGULAR"]
            self.assertEqual(row["winner"]["candidate"], winner)
            self.assertEqual(row["source_stage"], "gen")
            self.assertEqual(row["selection_basis"], "source_general_final")
            self.assertEqual(len(row["unselected_source_rounds"]), 1)
            self.assertEqual(row["unselected_source_rounds"][0]["source_stage"], "pre")

    def test_senate_低层周期闸按固定席位清单拒绝整州缺行(self) -> None:
        targets_1976 = [
            row
            for row in self.targets
            if row["office"] == "SENATE" and row["cycle"] == 1976
        ]
        missing_one = [row for row in targets_1976 if row["state"] != "AZ"]
        report = _cycle_reconciliation(
            "SENATE", 1976, self.senate_rows, missing_one, []
        )
        self.assertFalse(report["benchmark_eligible"])
        self.assertIn("senate_cycle_inventory_mismatch", report["benchmark_closed_reasons"])

    def test_assert_reconciliation_ready_单独调用也核验_senate_清单(self) -> None:
        reconciliation = copy.deepcopy(self.reconciliation)
        rounds = reconciliation["raw_round_audit"]["rounds"]
        removed = next(
            index
            for index, row in enumerate(rounds)
            if row["office"] == "SENATE"
            and row["cycle"] == 1976
            and row["state"] == "AZ"
            and row["selection_status"] == "selected_final_round"
        )
        del rounds[removed]
        with self.assertRaisesRegex(IngestError, "SENATE 1976 席位清单漂移"):
            assert_reconciliation_ready(reconciliation)
        self.assertEqual(EXPECTED_SENATE_INVENTORY[1976][0], 33)

    def test_来源_total_异常单列而规范化票数守恒(self) -> None:
        row = self.by_id["SENATE-2018-MN-REGULAR"]
        self.assertNotEqual(row["source_total_vote_delta"], 0)
        self.assertEqual(row["candidate_votes_sum"], row["normalized_total_votes"])
        self.assertEqual(row["normalized_vote_conservation_delta"], 0)
        cycle = self.reconciliation["offices"]["SENATE"]["cycles"][-1]
        self.assertGreater(cycle["source_reported_total_delta_races"], 0)
        detail = next(
            item
            for item in self.reconciliation["raw_total_anomalies"]
            if item["race_id"] == row["race_id"]
        )
        self.assertEqual(detail["delta_by_source_total"]["5184235"], -2587356)
        self.assertEqual(detail["source_lines"], row["source"]["source_lines"])

    def test_全源每个原始轮次恰审计一次(self) -> None:
        audit = self.reconciliation["raw_round_audit"]
        raw_rows = self.house_rows + self.senate_rows
        expected_keys = {
            (
                row["office"],
                row["cycle"],
                row["state"],
                row["district"] if row["office"] == "HOUSE" else row["source_special"],
                row["source_stage"],
                row["source_special"],
                row["source_runoff_raw"] if row["office"] == "HOUSE" else None,
            )
            for row in raw_rows
        }
        audited_lines = [
            line
            for round_record in audit["rounds"]
            for line in round_record["source_lines"]
        ]
        expected_lines = [row["source_line"] for row in raw_rows]
        # House/Senate 是不同文件，物理行号可重复；按院别复合后验证一对一。
        audited_line_keys = [
            (round_record["office"], line)
            for round_record in audit["rounds"]
            for line in round_record["source_lines"]
        ]
        expected_line_keys = [(row["office"], row["source_line"]) for row in raw_rows]
        self.assertEqual(audit["round_count"], len(expected_keys))
        self.assertEqual(audit["source_row_count"], len(raw_rows))
        self.assertEqual(len(audited_lines), len(expected_lines))
        self.assertEqual(len(audited_line_keys), len(set(audited_line_keys)))
        self.assertEqual(set(audited_line_keys), set(expected_line_keys))

    def test_全源异常清单与逐轮重算完全一致(self) -> None:
        audit = self.reconciliation["raw_round_audit"]
        recomputed = [
            round_record
            for round_record in audit["rounds"]
            if len(round_record["source_total_values"]) != 1
            or any(
                round_record["candidate_votes_sum"] != source_total
                for source_total in round_record["source_total_values"]
            )
        ]
        self.assertEqual(audit["anomaly_count"], len(recomputed))
        self.assertEqual(
            [row["raw_round_id"] for row in audit["anomalies"]],
            [row["raw_round_id"] for row in recomputed],
        )
        for round_record in audit["rounds"]:
            self.assertEqual(
                round_record["delta_by_source_total"],
                {
                    str(source_total): round_record["candidate_votes_sum"] - source_total
                    for source_total in round_record["source_total_values"]
                },
            )

    def test_未选前轮异常也在全源审计中(self) -> None:
        audit = self.reconciliation["raw_round_audit"]
        louisiana = next(
            row
            for row in audit["anomalies"]
            if row["office"] == "HOUSE"
            and row["cycle"] == 2002
            and row["state"] == "LA"
            and row["district"] == 5
            and row["source_runoff"] is False
        )
        self.assertEqual(louisiana["selection_status"], "nonselected_round")
        self.assertEqual(louisiana["candidate_votes_sum"], 184657)
        self.assertEqual(louisiana["delta_by_source_total"]["357119"], -172462)

    def test_跨院同物理行号不会误标为已选(self) -> None:
        house = dict(self.house_rows[0])
        senate = dict(self.senate_rows[0])
        house["source_line"] = 2
        senate["source_line"] = 2
        audit = _raw_round_audit(
            [house, senate],
            [{"office": "HOUSE", "source": {"source_lines": [2]}}],
        )
        by_office = {row["office"]: row for row in audit["rounds"]}
        self.assertEqual(by_office["HOUSE"]["selection_status"], "selected_final_round")
        self.assertEqual(by_office["SENATE"]["selection_status"], "nonselected_round")

    def test_2018_来源_total_多值不静默选择一个(self) -> None:
        row = self.by_id["HOUSE-2018-GA-06-CYCLE-SEAT"]
        self.assertIsNone(row["source_total_votes"])
        self.assertGreater(len(row["source_total_votes_values"]), 1)
        self.assertTrue(row["source"]["source_total_values_inconsistent"])

    def test_所有接纳竞选候选票守恒且唯一赢家(self) -> None:
        for row in self.targets:
            self.assertEqual(
                sum(candidate["votes"] for candidate in row["candidates"]),
                row["normalized_total_votes"],
            )
            top = max(candidate["votes"] for candidate in row["candidates"])
            self.assertEqual(sum(candidate["votes"] == top for candidate in row["candidates"]), 1)
            self.assertEqual(row["winner"]["votes"], top)

    def test_目标只含最终结果时距且没有_2026(self) -> None:
        self.assertTrue(all(row["forecast_horizon"] == "final_target_backtest" for row in self.targets))
        self.assertNotIn(2026, {row["cycle"] for row in self.targets})
        self.assertFalse(self.reconciliation["contains_2026_probability"])

    def test_模糊多个一般轮进入_quarantine_不静默删行(self) -> None:
        base = dict(self.house_rows[0])
        base.update({"cycle": 1976, "state": "AL", "district": 1, "source_line": 2})
        first = dict(base, source_runoff=False, source_runoff_raw="FALSE")
        second = dict(base, source_line=3, source_runoff=None, source_runoff_raw="NA")
        targets, quarantine = normalize_office(
            [first, second], dataset_id="fixture", source_path="fixture.csv"
        )
        self.assertEqual(targets, [])
        self.assertEqual(len(quarantine), 1)
        self.assertIn("ambiguous_multiple_general_rounds", quarantine[0]["reasons"])
        self.assertEqual(quarantine[0]["source_lines"], [2, 3])

    def test_jsonl_写出确定且可回读(self) -> None:
        subset = self.targets[:20]
        mini_reconciliation = {"schema_version": "test", "rows": 20}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_targets = root / "a" / "targets.jsonl"
            first_recon = root / "a" / "reconciliation.json"
            second_targets = root / "b" / "targets.jsonl"
            second_recon = root / "b" / "reconciliation.json"
            write_processed(
                subset,
                mini_reconciliation,
                targets_path=first_targets,
                reconciliation_path=first_recon,
            )
            write_processed(
                subset,
                mini_reconciliation,
                targets_path=second_targets,
                reconciliation_path=second_recon,
            )
            self.assertEqual(first_targets.read_bytes(), second_targets.read_bytes())
            self.assertEqual(first_recon.read_bytes(), second_recon.read_bytes())
            self.assertEqual(load_jsonl(first_targets), subset)


if __name__ == "__main__":
    unittest.main()
