"""LH-059 FEC 账本解析、资格闸和对账测试。"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms import fec_ingest  # noqa: E402


class FecIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.metadata = fec_ingest.parse_fec_senate()

    def test_full_cycle_counts(self):
        self.assertEqual(len(self.rows), 71)
        self.assertEqual(self.metadata["cycle_row_counts"], {"2018": 35, "2022": 36})

    def test_inventory_hashes_are_m3_canonical(self):
        config = json.loads(fec_ingest.INVENTORY_PATH.read_text(encoding="utf-8"))
        for cycle in (2018, 2022):
            ids = [row["race_id"] for row in self.rows if row["cycle"] == cycle]
            canonical, digest = fec_ingest.canonical_contest_inventory(ids)
            self.assertEqual(tuple(config["cycles"][str(cycle)]["race_ids"]), canonical)
            self.assertEqual(config["cycles"][str(cycle)]["contest_inventory_hash"], digest)
            self.assertTrue(all(row["contest_inventory_hash"] == digest for row in self.rows if row["cycle"] == cycle))

    def test_fec_seal_metadata_matches_lh058(self):
        verified = fec_ingest.verify_sealed_workbooks()
        self.assertEqual(set(verified), {2018, 2020, 2022})
        self.assertTrue(all(len(item["sha256"]) == 64 for item in verified.values()))
        self.assertEqual(verified[2018]["selected_sheets"], ["2018 US Senate Results by State"])
        self.assertEqual(verified[2022]["selected_sheets"], ["7. US Senate Results by State", "11. Special Elections 2021-2023"])
        self.assertEqual(verified[2020]["selected_sheets"], [])

    def test_only_senate_values_are_emitted(self):
        serialized = fec_ingest.jsonl_bytes(self.rows).decode("utf-8")
        self.assertNotIn("House", serialized)
        self.assertNotIn("President", serialized)
        self.assertFalse(self.metadata["house_or_president_values_emitted"])

    def test_special_races_have_uppercase_ids(self):
        special = [row for row in self.rows if row["election_type"] == "special"]
        self.assertEqual([row["race_id"] for row in special], [
            "SENATE-2018-MN-SPECIAL", "SENATE-2018-MS-SPECIAL",
            "SENATE-2022-CA-SPECIAL", "SENATE-2022-OK-SPECIAL",
        ])

    def test_writein_fusion_and_raw_total_preservation(self):
        mn = next(row for row in self.rows if row["race_id"] == "SENATE-2018-MN-REGULAR")
        self.assertTrue(any(candidate["writein"] for candidate in mn["candidates"]))
        self.assertTrue(mn["raw_total_preserved"])
        self.assertEqual(mn["raw_total_vote_delta"], 0)

    def test_qualification_allows_complete_real_ledger(self):
        for cycle in (2018, 2022):
            ids = [row["race_id"] for row in self.rows if row["cycle"] == cycle]
            result = fec_ingest.qualify_ledger(self.rows, cycle, ids)
            self.assertTrue(result["benchmark_eligible"])
            self.assertEqual(result["failure_reasons"], [])

    def test_qualification_missing_race_is_failed_closed(self):
        rows = [row for row in self.rows if row["race_id"] != "SENATE-2018-AZ-REGULAR"]
        ids = [row["race_id"] for row in self.rows if row["cycle"] == 2018]
        result = fec_ingest.qualify_ledger(rows, 2018, ids)
        self.assertFalse(result["benchmark_eligible"])
        self.assertIn("full_contest_inventory", result["failure_reasons"])

    def test_qualification_extra_race_is_failed_closed(self):
        rows = list(self.rows) + [dict(self.rows[0], race_id="SENATE-2018-ZZ-REGULAR", cycle=2018)]
        ids = [row["race_id"] for row in self.rows if row["cycle"] == 2018]
        result = fec_ingest.qualify_ledger(rows, 2018, ids)
        self.assertFalse(result["benchmark_eligible"])

    def test_qualification_vote_delta_is_failed_closed(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["raw_total_vote_delta"] = 1
        ids = [row["race_id"] for row in rows if row["cycle"] == 2018]
        result = fec_ingest.qualify_ledger(rows, 2018, ids)
        self.assertFalse(result["benchmark_eligible"])
        self.assertIn("vote_conservation", result["failure_reasons"])

    def test_qualification_bad_party_is_failed_closed(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["winner_group"] = "BAD"
        ids = [row["race_id"] for row in rows if row["cycle"] == 2018]
        result = fec_ingest.qualify_ledger(rows, 2018, ids)
        self.assertFalse(result["benchmark_eligible"])
        self.assertIn("party_tags", result["failure_reasons"])

    def test_canonical_inventory_rejects_duplicate_and_bad_id(self):
        with self.assertRaises(fec_ingest.FecIngestError):
            fec_ingest.canonical_contest_inventory(["SENATE-2018-AZ-REGULAR", "SENATE-2018-AZ-REGULAR"])
        with self.assertRaises(fec_ingest.FecIngestError):
            fec_ingest.canonical_contest_inventory(["HOUSE-2018-AZ-01"])

    def test_cell_types_and_shared_strings(self):
        shared = ("文本",)
        ns = ' xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        cases = [
            (f'<c{ns} t="s"><v>0</v></c>', "文本"),
            (f'<c{ns} t="inlineStr"><is><t>内联</t></is></c>', "内联"),
            (f'<c{ns} t="b"><v>1</v></c>', "TRUE"),
            (f'<c{ns} t="str"><v>错误</v></c>', "错误"),
            (f'<c{ns}><v>123</v></c>', "123"),
        ]
        for xml, expected in cases:
            self.assertEqual(fec_ingest._cell_text(ET.fromstring(xml), shared), expected)

    def test_invalid_boolean_cell_fails(self):
        with self.assertRaises(fec_ingest.FecIngestError):
            fec_ingest._cell_text(ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="b"><v>2</v></c>'), ())

    def test_merged_non_top_left_value_fails(self):
        sheet = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells><sheetData><row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>2</v></c></row></sheetData></worksheet>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
                archive.writestr("xl/sheet1.xml", sheet)
            with zipfile.ZipFile(path) as archive:
                reader = fec_ingest._SheetRows(archive, "xl/sheet1.xml", "fixture")
                with self.assertRaises(fec_ingest.FecIngestError):
                    list(reader.rows())

    def test_reconciliation_is_report_only_and_complete(self):
        report = fec_ingest.reconcile_medsl_2018(self.rows)
        self.assertEqual(report["fec_ledger_rows"], 35)
        self.assertEqual(report["medsl_rows"], 35)
        self.assertTrue(report["medsl_audit_only"])
        self.assertFalse(report["data_mutation"])
        self.assertTrue(all(row["reconciliation_status"] == "matched_race_id" for row in report["rows"]))

    def test_jsonl_is_byte_deterministic(self):
        self.assertEqual(fec_ingest.jsonl_bytes(self.rows), fec_ingest.jsonl_bytes(list(reversed(self.rows))))

    def test_2018_medsl_reconciliation_artifact_is_fresh(self):
        expected = fec_ingest.reconciliation_bytes(fec_ingest.reconcile_medsl_2018(self.rows))
        self.assertEqual(fec_ingest.RECONCILIATION_PATH.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
