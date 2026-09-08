"""Senate M0 总统来源、fusion 聚合和时点特征账本的聚焦测试。"""

from __future__ import annotations

import copy
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

from midterms.presidential_ingest import (
    FEC_2024_KEY_STATES,
    FEC_2024_OFFICIAL_NATIONAL_TOTALS,
    FEC_2024_SHA256,
    FEATURE_ID,
    LH068_BASELINES_PREFIX_SHA256,
    LH068_RESULTS_PREFIX_SHA256,
    PRESIDENTIAL_CYCLES,
    SENATE_TARGET_CYCLES,
    STATE_CODES,
    STATE_EQUIVALENTS,
    TRANSFORM_ID,
    PresidentialIngestError,
    assert_presidential_reconciliation_ready,
    assert_senate_baselines_ready,
    build_all,
    build_lh068_senate_baselines,
    build_senate_state_baselines,
    FEC_2020_SHA256,
    jsonl_bytes,
    load_jsonl,
    normalize_presidential_results,
    parse_fec_presidential_2020,
    parse_fec_presidential_2024,
    publish_lh068_append,
    read_presidential_csv,
    write_processed,
)


SPEC = importlib.util.spec_from_file_location(
    "lh049_fetch_senate_m0_data", MODEL_ROOT / "fetch_senate_m0_data.py"
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("无法加载 fetch_senate_m0_data.py")
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)

RAW_ROOT = MODEL_ROOT / "data" / "raw" / "medsl-president-1976-2016"
CSV_PATH = RAW_ROOT / "1976-2016-president.csv"
CODEBOOK_PATH = RAW_ROOT / "codebook-us-president-1976-2016.md"
RESULTS_PATH = MODEL_ROOT / "data" / "processed" / "presidential-state-results.jsonl"
BASELINES_PATH = MODEL_ROOT / "data" / "processed" / "senate-state-baselines.jsonl"
RECONCILIATION_PATH = MODEL_ROOT / "data" / "processed" / "senate-m0-reconciliation.json"
FEC_2024_PATH = MODEL_ROOT / "data" / "raw" / "fec" / "2024presgeresults.xlsx"
LH068_REPORT_PATH = MODEL_ROOT / "artifacts" / "lh068-presidential-2024-reconciliation.json"


class SourceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = fetch._load_manifest()

    def test_固定两文件离线三重核验通过(self) -> None:
        self.assertEqual(fetch.check_local(self.manifest), {"files": 2, "bytes": 403266})

    def test_清单区分固定分发与_doi_当前版本(self) -> None:
        self.assertEqual(self.manifest["distribution_scope"]["years"], [1976, 2016])
        self.assertEqual(self.manifest["doi_current_metadata"]["version"], "10.0")
        self.assertTrue(
            self.manifest["distribution_scope"]["current_doi_version_is_not_downloaded"]
        )
        self.assertTrue(self.manifest["archival_reconstruction"])
        self.assertFalse(self.manifest["strict_original_vintage_available"])

    def test_csv_与_codebook_版本差异明确登记(self) -> None:
        scope = self.manifest["distribution_scope"]
        self.assertEqual(scope["csv_version_column"], "20171015")
        self.assertEqual(scope["codebook_version"], "20171101")
        self.assertTrue(scope["versions_intentionally_differ"])

    def test_清单登记_blob_字节_sha256_cc0_clerk_与获取时间(self) -> None:
        for entry in self.manifest["files"]:
            self.assertEqual(len(entry["git_blob_sha1"]), 40)
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertGreater(entry["bytes"], 0)
            self.assertEqual(entry["license"]["spdx"], "CC0-1.0")
            self.assertIn("Clerk", entry["upstream_source"])
            self.assertTrue(entry["retrieved_at"])

    def test_下载白名单不能扩张(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["download_policy"]["allowed_hosts"].append("example.com")
        with self.assertRaisesRegex(fetch.SourceCheckError, "白名单"):
            fetch.validate_manifest(changed)

    def test_固定提交路径漂移确定失败(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["files"][0]["url"] = changed["files"][0]["url"].replace(
            changed["fixed_commit"], "main"
        )
        with self.assertRaisesRegex(fetch.SourceCheckError, "固定提交路径"):
            fetch.validate_manifest(changed)

    def test_任何字节漂移触发核验失败(self) -> None:
        entry = self.manifest["files"][0]
        data = CSV_PATH.read_bytes()
        with self.assertRaisesRegex(fetch.SourceCheckError, "漂移"):
            fetch.verify_bytes(entry, data[:-1] + bytes([data[-1] ^ 1]))

    def test_现代镜像时间不得冒充事实可知时间(self) -> None:
        policy = self.manifest["fact_availability_policy"]
        self.assertTrue(policy["modern_mirror_time_is_not_fact_time"])
        self.assertFalse(policy["original_publication_timestamp_preserved"])


class PresidentialReaderAndNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_rows, cls.encoding = read_presidential_csv(CSV_PATH)
        cls.results, cls.reconciliation = normalize_presidential_results(cls.source_rows)
        cls.by_key = {(row["cycle"], row["state"]): row for row in cls.results}

    def test_utf8_严格往返且原始行数固定(self) -> None:
        self.assertEqual(len(self.source_rows), 3740)
        self.assertEqual(self.encoding["codec"], "utf-8")
        self.assertTrue(self.encoding["roundtrip_bytes_equal"])
        self.assertEqual(self.encoding["source_bytes"], 400481)

    def test_十一届每届_50_州加_dc_共_561(self) -> None:
        self.assertEqual(len(self.results), 561)
        counts = Counter(row["cycle"] for row in self.results)
        self.assertEqual(set(counts), set(PRESIDENTIAL_CYCLES))
        self.assertEqual(set(counts.values()), {51})
        for cycle in PRESIDENTIAL_CYCLES:
            states = {row["state"] for row in self.results if row["cycle"] == cycle}
            self.assertEqual(states, set(STATE_EQUIVALENTS))

    def test_全部来源行逐字保留在州届账本(self) -> None:
        self.assertEqual(sum(row["source_row_count"] for row in self.results), 3740)
        observed = [
            source["source_line"]
            for result in self.results
            for source in result["source_rows"]
        ]
        self.assertEqual(len(observed), len(set(observed)))
        self.assertEqual(set(observed), {row["source_line"] for row in self.source_rows})
        first = self.by_key[(1976, "AL")]["source_rows"][0]
        self.assertEqual(
            set(first),
            {
                "source_line", "candidate", "raw_party", "writein", "candidate_votes",
                "source_total_votes", "version", "notes",
            },
        )

    def test_全源_duplicate_与_fusion_计数固定(self) -> None:
        self.assertEqual(self.reconciliation["duplicate_named_candidate_groups"], 42)
        self.assertEqual(self.reconciliation["major_party_fusion_groups"], 24)
        self.assertEqual(self.reconciliation["selected_major_candidate_fusion_groups"], 23)
        self.assertEqual(self.reconciliation["fusion_affected_state_cycle_count"], 12)

    def test_纽约_2000_主要党候选按身份跨党线合票(self) -> None:
        row = self.by_key[(2000, "NY")]
        self.assertEqual(row["democratic_candidate"]["candidate"], "Gore, Al")
        self.assertEqual(row["democratic_candidate"]["line_count"], 3)
        self.assertEqual(row["democratic_votes"], 4107697)
        self.assertEqual(row["republican_candidate"]["candidate"], "Bush, George W.")
        self.assertEqual(row["republican_candidate"]["line_count"], 2)
        self.assertEqual(row["republican_votes"], 2403374)

    def test_md_2004_other_民主标签不能冒充候选(self) -> None:
        row = self.by_key[(2004, "MD")]
        self.assertEqual(row["democratic_candidate"]["candidate"], "Kerry, John")
        self.assertEqual(row["democratic_votes"], 1334493)
        other = [source for source in row["source_rows"] if source["candidate"] == "Other"]
        self.assertEqual([(source["raw_party"], source["candidate_votes"]) for source in other], [
            ("unaffiliated", 34),
            ("democrat", 7),
        ])

    def test_mn_dfl_标签解析为民主党候选(self) -> None:
        row = self.by_key[(2012, "MN")]
        self.assertEqual(row["democratic_candidate"]["candidate"], "Obama, Barack H.")
        self.assertIn("democratic-farmer-labor", row["democratic_candidate"]["raw_parties"])

    def test_ne_2000_多值_total_原样保留(self) -> None:
        row = self.by_key[(2000, "NE")]
        self.assertEqual(row["source_total_values"], [697019, 967019])
        self.assertEqual(row["candidate_votes_sum"], 697019)
        self.assertEqual(row["normalized_total_votes"], 697019)
        self.assertEqual(row["delta_by_source_total"], {"697019": 0, "967019": -270000})
        self.assertTrue(row["source_total_values_inconsistent"])
        self.assertFalse(row["source_total_conserving"])
        self.assertEqual(self.reconciliation["source_total_conserving_state_cycles"], 560)

    def test_所有州届两党候选唯一且边际有限(self) -> None:
        self.assertTrue(self.reconciliation["all_major_party_candidates_unique"])
        self.assertTrue(self.reconciliation["all_two_party_margins_finite"])
        for row in self.results:
            self.assertGreater(row["democratic_candidate"]["votes"], 0)
            self.assertGreater(row["republican_candidate"]["votes"], 0)
            self.assertGreaterEqual(row["two_party_margin"], -100.0)
            self.assertLessEqual(row["two_party_margin"], 100.0)

    def test_第三党空名_other_writein_均未删除(self) -> None:
        sources = [source for row in self.results for source in row["source_rows"]]
        self.assertEqual(sum(source["writein"] for source in sources), 247)
        self.assertEqual(sum(source["candidate"] is None for source in sources), 266)
        self.assertEqual(sum(source["candidate"] == "Other" for source in sources), 106)
        self.assertGreater(
            sum(source["raw_party"] not in {None, "democrat", "republican"} for source in sources),
            0,
        )

    def test_dc_保留且标为总统结果(self) -> None:
        dc = [row for row in self.results if row["state"] == "DC"]
        self.assertEqual(len(dc), 11)
        self.assertTrue(all(row["office"] == "PRESIDENT" for row in dc))
        self.assertTrue(self.reconciliation["dc_preserved"])

    def test_错误表头和未来周期硬失败(self) -> None:
        source = CSV_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            bad_header = Path(directory) / "bad-header.csv"
            bad_header.write_text(source.replace('"year","state"', '"election_year","state"', 1), encoding="utf-8")
            with self.assertRaisesRegex(PresidentialIngestError, "表头漂移"):
                read_presidential_csv(bad_header)

            future = Path(directory) / "future.csv"
            future.write_text(source.replace("1976,\"Alabama\"", "2020,\"Alabama\"", 1), encoding="utf-8")
            with self.assertRaisesRegex(PresidentialIngestError, "固定总统周期"):
                read_presidential_csv(future)

    def test_对账硬闸拒绝计数漂移(self) -> None:
        changed = copy.deepcopy(self.reconciliation)
        changed["major_party_fusion_groups"] = 23
        with self.assertRaisesRegex(PresidentialIngestError, "major_party_fusion_groups"):
            assert_presidential_reconciliation_ready(changed)


class SenateBaselineLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results, cls.baselines, cls.reconciliation = build_all(
            CSV_PATH,
            modern_mirror_retrieved_at="2026-08-12T02:50:00-04:00",
        )
        cls.by_key = {(row["target_cycle"], row["state"]): row for row in cls.baselines}

    def test_十一目标届乘_50_州共_550_且无_dc(self) -> None:
        self.assertEqual(len(self.baselines), 550)
        counts = Counter(row["target_cycle"] for row in self.baselines)
        self.assertEqual(set(counts), set(SENATE_TARGET_CYCLES))
        self.assertEqual(set(counts.values()), {50})
        self.assertEqual({row["state"] for row in self.baselines}, set(STATE_CODES))
        self.assertNotIn("DC", {row["state"] for row in self.baselines})

    def test_feature_id_复用注册项且_transform_id_记录派生(self) -> None:
        self.assertEqual(FEATURE_ID, "partisan_baseline_margin")
        self.assertEqual(TRANSFORM_ID, "prior_presidential_two_party_margin_v1")
        self.assertTrue(all(row["feature_id"] == FEATURE_ID for row in self.baselines))
        self.assertTrue(all(row["transform_id"] == TRANSFORM_ID for row in self.baselines))

    def test_每条来源严格为_t_减_2_且公式精确(self) -> None:
        presidential = {(row["cycle"], row["state"]): row for row in self.results}
        for row in self.baselines:
            self.assertEqual(row["presidential_source_cycle"], row["target_cycle"] - 2)
            source = presidential[(row["presidential_source_cycle"], row["state"])]
            expected = 100.0 * (
                source["democratic_votes"] - source["republican_votes"]
            ) / (source["democratic_votes"] + source["republican_votes"])
            self.assertEqual(row["partisan_baseline_margin"], expected)

    def test_事实可知时间不晚于预测截点且与镜像时间分离(self) -> None:
        for row in self.baselines:
            self.assertLessEqual(row["available_at"], row["forecast_as_of"])
            self.assertEqual(row["fact_available_at"], row["available_at"])
            self.assertNotEqual(row["modern_mirror_published_at"], row["available_at"])
            self.assertNotEqual(row["modern_mirror_retrieved_at"], row["available_at"])
            self.assertTrue(row["vintage"])
            self.assertTrue(row["archival_reconstruction"])
            self.assertFalse(row["strict_original_vintage_available"])

    def test_来源行_blob_csv版本_doi_完整(self) -> None:
        for row in self.baselines:
            source = row["source"]
            self.assertTrue(source["source_lines"])
            self.assertEqual(source["git_blob_sha1"], "d7e8c0cce41fa00c37fc133b3c80f037255d4885")
            self.assertEqual(source["csv_versions"], ["20171015"])
            self.assertEqual(source["doi"], "10.7910/DVN/42MVDX")

    def test_缺失_重复_错误周期_晚到与混入_house_均硬失败(self) -> None:
        cases: list[tuple[list[dict], str]] = []
        cases.append((copy.deepcopy(self.baselines[:-1]), "550"))
        duplicate = copy.deepcopy(self.baselines)
        duplicate[-1] = copy.deepcopy(duplicate[0])
        cases.append((duplicate, "重复"))
        wrong_cycle = copy.deepcopy(self.baselines)
        wrong_cycle[0]["presidential_source_cycle"] += 4
        cases.append((wrong_cycle, "t-2"))
        late = copy.deepcopy(self.baselines)
        late[0]["available_at"] = "2099-12-31T23:59:59Z"
        late[0]["fact_available_at"] = late[0]["available_at"]
        cases.append((late, "晚于"))
        house = copy.deepcopy(self.baselines)
        house[0]["office"] = "HOUSE"
        cases.append((house, "非 Senate"))
        for rows, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PresidentialIngestError, message):
                    assert_senate_baselines_ready(rows)

    def test_无关未来总统行不改变基线字节(self) -> None:
        future = copy.deepcopy(self.results[0])
        future["cycle"] = 2020
        future["state"] = "ZZ"
        changed = build_senate_state_baselines(
            [*self.results, future],
            modern_mirror_retrieved_at="2026-08-12T02:50:00-04:00",
        )
        self.assertEqual(jsonl_bytes(changed), jsonl_bytes(self.baselines))

    def test_处理产物确定并可回读(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a"
            second = root / "b"
            for target in (first, second):
                write_processed(
                    self.results,
                    self.baselines,
                    self.reconciliation,
                    results_path=target / "results.jsonl",
                    baselines_path=target / "baselines.jsonl",
                    reconciliation_path=target / "reconciliation.json",
                )
            self.assertEqual((first / "results.jsonl").read_bytes(), (second / "results.jsonl").read_bytes())
            self.assertEqual((first / "baselines.jsonl").read_bytes(), (second / "baselines.jsonl").read_bytes())
            self.assertEqual((first / "reconciliation.json").read_bytes(), (second / "reconciliation.json").read_bytes())
            self.assertEqual(load_jsonl(first / "baselines.jsonl"), self.baselines)

    def test_工作区处理产物通过字节级_check(self) -> None:
        manifest = fetch._load_manifest()
        fetch.check_local(manifest)
        workspace_results = load_jsonl(RESULTS_PATH)
        self.assertEqual(len(workspace_results), 663)
        self.assertEqual(jsonl_bytes(workspace_results[:561]), jsonl_bytes(self.results))
        self.assertEqual(workspace_results[561:612], parse_fec_presidential_2020(
            (MODEL_ROOT / "data" / "raw" / "fec" / "federalelections2020.xlsx").read_bytes(),
            self.results,
        )[0])
        self.assertEqual(len(load_jsonl(BASELINES_PATH)), 600)
        reconciliation = json.loads(RECONCILIATION_PATH.read_text(encoding="utf-8"))
        self.assertFalse(reconciliation["contains_2026_probability"])


class Fec2020PresidentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.legacy = load_jsonl(RESULTS_PATH)[:561]
        cls.workbook = (
            MODEL_ROOT / "data" / "raw" / "fec" / "federalelections2020.xlsx"
        ).read_bytes()
        cls.rows, cls.report = parse_fec_presidential_2020(cls.workbook, cls.legacy)

    def test_封存工作簿哈希与五十一辖区资格闸(self) -> None:
        self.assertEqual(self.report["source"]["sha256"], FEC_2020_SHA256)
        self.assertEqual(len(self.rows), 51)
        self.assertEqual({row["state"] for row in self.rows}, set(STATE_EQUIVALENTS))
        self.assertTrue(self.report["all_qualification_checks_passed"])
        self.assertTrue(all(self.report["qualification_checks"].values()))

    def test_与州汇总和全国汇总对账(self) -> None:
        self.assertEqual(self.report["national_totals"], {
            "democratic_votes": 81283501,
            "republican_votes": 74223975,
            "all_candidate_votes": 158429631,
        })
        self.assertTrue(all(row["candidate_votes_sum"] == row["normalized_total_votes"] for row in self.rows))

    def test_德州重复_scattered_与内华达非候选标签显式留痕(self) -> None:
        self.assertEqual(self.report["worksheet_excluded_rows"], [{
            "candidate": "Scattered",
            "party": "W",
            "reason": "worksheet_duplicate_scattered_row_outside_reported_state_total",
            "source_line": 575,
            "state": "TX",
            "votes": 460,
        }])
        nv = next(row for row in self.rows if row["state"] == "NV")
        none = next(row for row in nv["source_rows"] if row["candidate"] == "None of These Candidates")
        self.assertEqual(none["raw_party"], "NONE_OF_THESE")

    def test_追加行与旧_schema_顶层兼容(self) -> None:
        expected_fields = set(self.legacy[0])
        self.assertTrue(all(set(row) == expected_fields for row in self.rows))

    def test_工作簿单字节漂移失败(self) -> None:
        changed = self.workbook[:-1] + bytes([self.workbook[-1] ^ 1])
        with self.assertRaisesRegex(PresidentialIngestError, "SHA-256"):
            parse_fec_presidential_2020(changed, self.legacy)


class Fec2024PresidentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.existing = load_jsonl(RESULTS_PATH)[:612]
        cls.workbook = FEC_2024_PATH.read_bytes()
        cls.rows, cls.report = parse_fec_presidential_2024(cls.workbook, cls.existing)
        cls.baselines = build_lh068_senate_baselines(cls.rows)

    def test_封存工作簿_51_辖区与九项资格闸全过(self) -> None:
        self.assertEqual(self.report["source"]["sha256"], FEC_2024_SHA256)
        self.assertEqual(len(self.rows), 51)
        self.assertEqual({row["state"] for row in self.rows}, set(STATE_EQUIVALENTS))
        self.assertEqual(len(self.report["qualification_checks"]), 9)
        self.assertTrue(self.report["all_qualification_checks_passed"])
        self.assertTrue(all(self.report["qualification_checks"].values()))

    def test_全国合计与七个关键州官方事实一致(self) -> None:
        self.assertEqual(self.report["national_totals"], FEC_2024_OFFICIAL_NATIONAL_TOTALS)
        self.assertEqual(
            self.report["national_totals"]["democratic_votes"],
            self.report["workbook_candidate_totals"]["HARRIS"],
        )
        self.assertEqual(
            self.report["national_totals"]["republican_votes"],
            self.report["workbook_candidate_totals"]["TRUMP"],
        )
        winners = {row["state"]: row["winner_party"] for row in self.report["key_state_winners"]}
        self.assertEqual(tuple(winners), FEC_2024_KEY_STATES)
        self.assertEqual(set(winners.values()), {"R"})

    def test_表头名称驱动列识别且追加行顶层_schema_兼容(self) -> None:
        layout = self.report["column_layout"]
        self.assertEqual(layout["identification"], "normalized_header_text")
        self.assertEqual(layout["state_column"], "A")
        self.assertEqual(layout["democratic_candidate_column"], "M")
        self.assertEqual(layout["republican_candidate_column"], "Y")
        self.assertEqual(layout["total_votes_column"], "AE")
        self.assertTrue(all(set(row) == set(self.existing[0]) for row in self.rows))
        self.assertTrue(
            all(source["raw_party"] for row in self.rows for source in row["source_rows"])
        )

    def test_州内票数守恒与唯一胜者来自真实工作簿(self) -> None:
        self.assertTrue(
            all(row["candidate_votes_sum"] == row["normalized_total_votes"] for row in self.rows)
        )
        for row in self.rows:
            votes = [candidate["votes"] for candidate in row["named_candidate_groups"]]
            self.assertEqual(votes.count(max(votes)), 1)

    def test_2026_基线恰_50_行且含派生_lineage(self) -> None:
        self.assertEqual(len(self.baselines), 50)
        self.assertEqual({row["state"] for row in self.baselines}, set(STATE_CODES))
        self.assertNotIn("DC", {row["state"] for row in self.baselines})
        for row in self.baselines:
            self.assertEqual(row["target_cycle"], 2026)
            self.assertEqual(row["presidential_source_cycle"], 2024)
            self.assertEqual(row["source"]["derivation_contract_id"], "LH-068")
            self.assertEqual(row["source"]["workbook_sha256"], FEC_2024_SHA256)

    def test_工作簿真实单字节漂移失败(self) -> None:
        changed = self.workbook[:-1] + bytes([self.workbook[-1] ^ 1])
        with self.assertRaisesRegex(PresidentialIngestError, "SHA-256"):
            parse_fec_presidential_2024(changed, self.existing)

    def test_只追加发布保持两个真实前缀逐字不变(self) -> None:
        production_results = RESULTS_PATH.read_bytes().splitlines(keepends=True)
        production_baselines = BASELINES_PATH.read_bytes().splitlines(keepends=True)
        result_prefix = b"".join(production_results[:612])
        baseline_prefix = b"".join(production_baselines[:550])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_target = root / "results.jsonl"
            baseline_target = root / "baselines.jsonl"
            report_target = root / "report.json"
            result_target.write_bytes(result_prefix)
            baseline_target.write_bytes(baseline_prefix)
            summary = publish_lh068_append(
                self.rows,
                self.baselines,
                self.report,
                results_path=result_target,
                baselines_path=baseline_target,
                report_path=report_target,
            )
            self.assertEqual(summary["presidential_prefix_sha256"], LH068_RESULTS_PREFIX_SHA256)
            self.assertEqual(summary["baseline_prefix_sha256"], LH068_BASELINES_PREFIX_SHA256)
            self.assertEqual(result_target.read_bytes()[: len(result_prefix)], result_prefix)
            self.assertEqual(baseline_target.read_bytes()[: len(baseline_prefix)], baseline_prefix)
            self.assertEqual(len(load_jsonl(result_target)), 663)
            self.assertEqual(len(load_jsonl(baseline_target)), 600)
            with self.assertRaisesRegex(PresidentialIngestError, "追加前行数"):
                publish_lh068_append(
                    self.rows,
                    self.baselines,
                    self.report,
                    results_path=result_target,
                    baselines_path=baseline_target,
                    report_path=root / "second-report.json",
                )

    def test_工作区追加产物与新鲜解析逐字一致(self) -> None:
        workspace_results = load_jsonl(RESULTS_PATH)
        workspace_baselines = load_jsonl(BASELINES_PATH)
        self.assertEqual(len(workspace_results), 663)
        self.assertEqual(len(workspace_baselines), 600)
        self.assertEqual(jsonl_bytes(workspace_results[612:]), jsonl_bytes(self.rows))
        self.assertEqual(jsonl_bytes(workspace_baselines[550:]), jsonl_bytes(self.baselines))
        self.assertEqual(
            json.loads(LH068_REPORT_PATH.read_text(encoding="utf-8")),
            self.report,
        )


if __name__ == "__main__":
    unittest.main()
