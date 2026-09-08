"""LH-052 规则账本、预注册封印与读取 canary 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODEL_ROOT = Path(__file__).resolve().parents[1]
SRC = MODEL_ROOT / "src"
for search_path in (MODEL_ROOT, SRC):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

SPEC = importlib.util.spec_from_file_location(
    "lh052_senate_balancing_preregister",
    MODEL_ROOT / "senate_balancing_preregister.py",
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("无法加载 senate_balancing_preregister.py")
preregister = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preregister)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid_ledger():
    return load_json(preregister.LEDGER_PATH)


def valid_prereg():
    return load_json(preregister.PREREG_PATH)


class PartyLedgerTests(unittest.TestCase):
    def test_十届映射精确(self):
        rows = preregister.validate_party_ledger(valid_ledger())
        self.assertEqual(tuple(row["cycle"] for row in rows), preregister.LEDGER_CYCLES)
        self.assertEqual(
            {row["cycle"]: row["president_party"] for row in rows},
            preregister.EXPECTED_PARTIES,
        )

    def test_开发届_d_r_各四届(self):
        rows = preregister.validate_party_ledger(valid_ledger())
        parties = [
            row["president_party"]
            for row in rows
            if row["cycle"] in preregister.DEVELOPMENT_CYCLES
        ]
        self.assertEqual(parties.count("DEM"), 4)
        self.assertEqual(parties.count("REP"), 4)

    def test_2000与2016普选赢家陷阱不反推总统党(self):
        ledger = valid_ledger()
        rows = preregister.validate_party_ledger(ledger)
        by_cycle = {row["cycle"]: row for row in rows}
        for trap in ledger["anti_inference_fixtures"]:
            with self.subTest(trap=trap["fixture_id"]):
                self.assertNotEqual(
                    trap["popular_vote_winner_party"],
                    trap["expected_incumbent_president_party"],
                )
                self.assertEqual(
                    by_cycle[trap["following_midterm_cycle"]]["president_party"],
                    trap["expected_incumbent_president_party"],
                )

    def test_乱序输入规范化确定性(self):
        ledger = valid_ledger()
        left = preregister.validate_party_ledger(ledger)
        ledger["rows"].reverse()
        right = preregister.validate_party_ledger(ledger)
        self.assertEqual(left, right)

    def test_重复周期失败(self):
        ledger = valid_ledger()
        ledger["rows"].append(copy.deepcopy(ledger["rows"][0]))
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_缺周期失败(self):
        ledger = valid_ledger()
        ledger["rows"].pop()
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_额外周期失败(self):
        ledger = valid_ledger()
        extra = copy.deepcopy(ledger["rows"][-1])
        extra["cycle"] = 2026
        ledger["rows"].append(extra)
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_bool周期失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["cycle"] = True
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_未知总统党失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["president_party"] = "IND"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_错误总统党映射失败(self):
        ledger = valid_ledger()
        ledger["rows"][4]["president_party"] = "DEM"
        ledger["rows"][4]["president_party_sign"] = 1
        ledger["rows"][4]["balancing_direction_sign"] = -1
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_错误党符号失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["president_party_sign"] = 1
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_错误制衡符号失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["balancing_direction_sign"] = -1
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_available晚于forecast失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["available_at"] = "1987-01-01T00:00:00Z"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_effective与任期开始不一致失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["effective_at"] = "1985-01-21T00:00:00Z"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_无时区失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["available_at"] = "1985-01-21T00:00:00"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_来源状态不合格失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["source_hash_status"] = "pending"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_source_url与registry不一致失败(self):
        ledger = valid_ledger()
        ledger["rows"][0]["source_url"] = "https://example.invalid/"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)

    def test_普选陷阱被改写失败(self):
        ledger = valid_ledger()
        ledger["anti_inference_fixtures"][0]["expected_incumbent_president_party"] = "DEM"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_party_ledger(ledger)


class PreregistrationSchemaTests(unittest.TestCase):
    def test_冻结预注册通过(self):
        parsed = preregister.validate_preregistration(valid_prereg())
        self.assertEqual(
            parsed["component"]["component_id"],
            "SENATE_BALANCING_DIRECTION_PRIOR",
        )

    def test_开发周期变更失败(self):
        config = valid_prereg()
        config["development"]["development_cycles"].pop()
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_评估周期变更失败(self):
        config = valid_prereg()
        config["evaluation"]["primary_evaluation_cycles"] = [2018]
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_2022用2018训练失败(self):
        config = valid_prereg()
        config["evaluation"]["train_2022_on_2018"] = True
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_评估访问计数非零失败(self):
        config = valid_prereg()
        config["evaluation"]["evaluation_access_count"] = 1
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_family_primary_challenger多于一失败(self):
        config = valid_prereg()
        config["seal"]["primary_challenger_count"] = 2
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_占位hash被提前填写失败(self):
        config = valid_prereg()
        config["seal"]["placeholder_manifests"]["predictions"]["sha256"] = "0" * 64
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_评估父预测训练窗必须精确十届(self):
        config = valid_prereg()
        config["seal"]["placeholder_manifests"]["evaluation_parent_predictions"]["parent_train_cycles"] = list(
            preregister.DEVELOPMENT_CYCLES
        )
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_开发输入与评估父预测占位不可合并(self):
        config = valid_prereg()
        del config["seal"]["placeholder_manifests"]["development_oof_inputs"]
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_盲锁箱声明失败(self):
        config = valid_prereg()
        config["evaluation"]["secret_blind_lockbox"] = True
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_前瞻声明失败(self):
        config = valid_prereg()
        config["evaluation"]["prospective"] = True
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_artifact边界布尔值漂移失败(self):
        config = valid_prereg()
        config["artifact_claims"]["contains_2018_2022_outcomes"] = True
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test_canary路径删减失败(self):
        config = valid_prereg()
        config["read_policy"]["canary_paths"].pop()
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)

    def test公式逐字漂移失败(self):
        config = valid_prereg()
        config["formula"]["prior"] = "b_hat=mean_R-mean_D"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_preregistration(config)


class ReadAuditTests(unittest.TestCase):
    def test_raw_canary在open前失败(self):
        audit = preregister.StaticReadAudit([])
        with self.assertRaises(preregister.ProtectedOutcomeAccessError):
            audit.read_bytes(
                preregister.PROJECT_ROOT
                / "midterm-model/data/raw/CANARY-2018-SENATE-RESULTS.csv"
            )
        self.assertEqual(len(audit.blocked_attempts), 1)

    def test_processed路径即使不存在也在exists前失败(self):
        audit = preregister.StaticReadAudit([])
        path = preregister.PROJECT_ROOT / "midterm-model/data/processed/DOES-NOT-EXIST.jsonl"
        self.assertFalse(path.exists())
        with self.assertRaises(preregister.ProtectedOutcomeAccessError):
            audit.read_bytes(path)

    def test_未登记静态文件失败(self):
        audit = preregister.StaticReadAudit([])
        with self.assertRaises(preregister.PreregistrationError):
            audit.read_bytes(MODEL_ROOT / "README.md")

    def test_允许文件读取并记录(self):
        audit = preregister.StaticReadAudit([preregister.LEDGER_PATH])
        self.assertTrue(audit.read_bytes(preregister.LEDGER_PATH).startswith(b"{"))
        self.assertEqual(
            audit.allowed_reads,
            ["midterm-model/config/presidential-party-midterms.json"],
        )

    def test_四个canary全部失败关闭(self):
        contract_path = preregister._contract_path()
        audit = preregister.StaticReadAudit(preregister._allowed_paths(contract_path))
        result = preregister.run_canary_audit(audit)
        self.assertTrue(result["passed"])
        self.assertEqual(result["canary_blocked_before_open_count"], 4)
        self.assertFalse(result["directory_traversal_performed"])
        self.assertFalse(result["filter_after_read_used"])

    def test_规范json拒绝nan与inf(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(preregister.PreregistrationError):
                    preregister.canonical_bytes({"value": value})


class ConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = preregister.build_report()

    def test_合成手算全部通过(self):
        self.assertTrue(self.report["synthetic_fixtures"]["passed"])
        self.assertTrue(all(self.report["synthetic_fixtures"]["checks"].values()))

    def test_核心与driver父训练窗常量一致(self):
        self.assertEqual(
            preregister.EVALUATION_PARENT_TRAIN_CYCLES,
            preregister.senate_balancing.EVALUATION_PARENT_TRAIN_CYCLES,
        )

    def test_构造未打开outcome(self):
        audit = self.report["read_audit"]
        self.assertEqual(audit["outcome_files_opened"], 0)
        self.assertEqual(audit["canary_attempt_count"], 4)
        self.assertEqual(audit["canary_blocked_before_open_count"], 4)
        self.assertFalse(any("/data/" in path for path in audit["allowed_reads"]))

    def test_产物边界固定(self):
        self.assertEqual(self.report["activation"], "queued_preingestion")
        for key in (
            "real_historical_scores_emitted",
            "contains_2018_2022_outcomes",
            "contains_2026_probability",
            "senate_control_probability",
            "behavioral_claim",
        ):
            self.assertIs(self.report[key], False)

    def test_seal只散列静态allowlist文件(self):
        paths = [item["path"] for item in self.report["seal"]["files"]]
        self.assertEqual(len(paths), 5)
        self.assertFalse(any("/data/" in path for path in paths))
        self.assertTrue(all(len(item["sha256"]) == 64 for item in self.report["seal"]["files"]))

    def test_四个占位manifest未填充(self):
        placeholders = self.report["seal"]["placeholder_manifests"]
        self.assertEqual(len(placeholders), 4)
        self.assertTrue(
            all(item["payload_sha256"] == preregister.PENDING_HASH for item in placeholders)
        )

    def test_contract使用canonical_label而非生命周期目录(self):
        paths = [item["path"] for item in self.report["seal"]["files"]]
        self.assertIn(preregister.CONTRACT_CANONICAL_LABEL, paths)
        self.assertNotIn("contracts/active/LH-052.json", paths)
        self.assertNotIn("contracts/done/LH-052.json", paths)
        self.assertIn(
            preregister.CONTRACT_CANONICAL_LABEL,
            self.report["read_audit"]["allowed_reads"],
        )

    def test_contract_active_done归档模拟不改变seal字节(self):
        active = preregister.PROJECT_ROOT / "contracts/active/LH-052.json"
        done = preregister.PROJECT_ROOT / "contracts/done/LH-052.json"
        actual = preregister._contract_path()
        archived = done if actual == active else active

        class AliasAudit:
            def __init__(self, base, alias, payload):
                self.base = base
                self.alias = alias.resolve()
                self.payload = payload

            def read_bytes(self, path):
                if Path(path).resolve() == self.alias:
                    return self.payload
                return self.base.read_bytes(path)

        audit = preregister.StaticReadAudit(preregister._allowed_paths(actual))
        contract_bytes = audit.read_bytes(actual)
        prereg = preregister.validate_preregistration(valid_prereg())
        active_seal = preregister._build_seal(audit, actual, prereg)
        alias_audit = AliasAudit(audit, archived, contract_bytes)
        archived_seal = preregister._build_seal(alias_audit, archived, prereg)
        self.assertEqual(
            preregister.canonical_bytes(active_seal),
            preregister.canonical_bytes(archived_seal),
        )

    def test_重复构造报告字节确定(self):
        self.assertEqual(
            preregister.canonical_bytes(self.report),
            preregister.canonical_bytes(preregister.build_report()),
        )

    def test_vintage生成路径重复字节一致(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "report.json"
            md_path = Path(directory) / "report.md"
            with mock.patch.object(preregister, "JSON_REPORT", json_path), mock.patch.object(
                preregister, "MD_REPORT", md_path
            ):
                self.assertEqual(preregister.write_or_check("write"), 0)
                first_json = json_path.read_bytes()
                first_md = md_path.read_bytes()
                self.assertEqual(preregister.write_or_check("write"), 0)
                self.assertEqual(first_json, json_path.read_bytes())
                self.assertEqual(first_md, md_path.read_bytes())

    def test_check检测artifact真实单字节翻转(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "report.json"
            md_path = Path(directory) / "report.md"
            json_path.write_bytes(preregister.JSON_REPORT.read_bytes())
            md_path.write_bytes(preregister.MD_REPORT.read_bytes())
            with mock.patch.object(preregister, "JSON_REPORT", json_path), mock.patch.object(
                preregister, "MD_REPORT", md_path
            ):
                self.assertEqual(preregister.write_or_check("check"), 0)
                original = json_path.read_bytes()
                json_path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                self.assertEqual(preregister.write_or_check("check"), 1)

    def test_存量artifact_schema通过且字段漂移失败(self):
        artifact = json.loads(preregister.JSON_REPORT.read_text(encoding="utf-8"))
        preregister.validate_sealed_artifact_schema(artifact)
        artifact["schema_version"] = "2.0"
        with self.assertRaises(preregister.PreregistrationError):
            preregister.validate_sealed_artifact_schema(artifact)


class LH059EvaluationEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            preregister.EVALUATION_JSON_REPORT.read_text(encoding="utf-8")
        )

    def test_评估访问一次并锁定(self):
        self.assertEqual(self.report["evaluation_access_count"], 1)
        self.assertTrue(self.report["evaluation_access_lock"]["locked"])

    def test_缺父源失败闭合且身份受限(self):
        self.assertEqual(self.report["result_identity"], "preregistered_not_supported")
        self.assertEqual(self.report["score_track"]["status"], "aborted_failed_closed")
        self.assertIn("evaluation_parent_predictions", self.report["blockers"])

    def test_分数机制双轨存在(self):
        self.assertIn("score_track", self.report)
        self.assertIn("mechanism_track", self.report)
        self.assertIn("fold_b_hats", self.report["mechanism_track"])
        self.assertIn("party_residual_means", self.report["mechanism_track"])

    def test_禁止超范围声明(self):
        claims = self.report["claims"]
        for name in ("contains_2026_probability", "senate_control_probability", "significance_claim", "robustness_claim", "historically_supported_claim"):
            self.assertFalse(claims[name])

    def test_账本与对账产物新鲜(self):
        freshness = self.report["freshness"]
        self.assertTrue(freshness["fec_ledger_matches_fresh_generation"])
        self.assertTrue(freshness["reconciliation_matches_fresh_generation"])

    def test_medsl保持审计态(self):
        self.assertTrue(self.report["claims"]["medsl_2018_audit_only"])
        self.assertFalse(self.report["claims"]["medsl_2018_mutated"])


class LH061EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            preregister.LH061_EVALUATION_JSON_REPORT.read_text(encoding="utf-8")
        )

    def test_第二次访问只打开结果账本一次并再次锁死(self):
        self.assertEqual(self.report["evaluation_access_count"], 2)
        self.assertTrue(self.report["evaluation_access_lock"]["locked"])
        self.assertFalse(self.report["evaluation_access_lock"]["further_access_allowed"])
        audit = self.report["evaluation_stage_read_audit"]
        self.assertEqual(audit["result_file_open_count_this_access"], 1)
        self.assertEqual(audit["other_result_files_opened"], 0)

    def test_三项治理偏差完整且公式版本不变(self):
        deviations = {item["id"]: item for item in self.report["governance_deviations"]}
        self.assertEqual(set(deviations), {
            "second_evaluation_access", "m3_code_evolution", "evidence_ceiling"
        })
        m3 = deviations["m3_code_evolution"]
        self.assertTrue(m3["preregistered_sha256"].startswith("6e876173"))
        self.assertTrue(m3["current_sha256"].startswith("0a77d3c9"))
        self.assertFalse(m3["parameter_tuning"])
        self.assertEqual(m3["formula_version_before"], m3["formula_version_current"])
        self.assertEqual(
            deviations["evidence_ceiling"]["maximum_evidence_status"],
            "experimental_two_cycle_signal/queued",
        )

    def test_首次_lh059_产物哈希一字节不动(self):
        custody = self.report["governance_deviations"][0]["evidence"]
        self.assertTrue(custody["bytes_unchanged"])
        self.assertEqual(custody["json_sha256"], preregister.LEGACY_EVALUATION_JSON_SHA256)
        self.assertEqual(custody["markdown_sha256"], preregister.LEGACY_EVALUATION_MD_SHA256)

    def test_分数轨逐周期主指标与等权护栏口径(self):
        score = self.report["score_track"]
        self.assertEqual(len(score["cycles"]), 2)
        self.assertEqual(score["primary_gate"]["metric"], "cycle_brier_democratic_win_each_cycle_strictly_better")
        guard = score["guard_gate"]
        self.assertEqual(guard["metric"], "equal_cycle_mean_independent_poisson_binomial_contested_count_crps_not_worse")
        self.assertEqual(guard["count_scope"], "registered_contested_seats_only_not_senate_control")
        self.assertFalse(score["all_preregistered_gates_passed"])
        self.assertEqual(score["failed_gates"], ["cycle_brier_democratic_win_each_cycle_strictly_better"])

    def test_机制轨参数逐折党别与零值语义完整(self):
        mechanism = self.report["mechanism_track"]
        self.assertIsInstance(mechanism["b_hat"], float)
        self.assertEqual(len(mechanism["fold_b_hats"]), 8)
        self.assertEqual(set(mechanism["party_residual_means"]), {"DEM", "REP"})
        self.assertIn("b_hat=0", mechanism["b_hat_zero_semantics"])
        self.assertEqual(mechanism["truncation_formula"], "b_hat=max(0,0.5*(mean_R(r_s)-mean_D(r_s)))")

    def test_失败闭合_registry_只采用状态结果(self):
        registry = json.loads(preregister.COMPONENT_REGISTRY_PATH.read_text(encoding="utf-8"))
        component = next(
            item for item in registry["preregistered_components"]
            if item["id"] == preregister.COMPONENT_ID
        )
        self.assertEqual(component["status"], "fail_closed_evaluated")
        self.assertEqual(component["evaluation_access_count"], 2)
        self.assertIn("cycle_brier_democratic_win_each_cycle_strictly_better", component["queue_reason"])

    def test_禁止超范围声明(self):
        self.assertTrue(all(value is False for value in self.report["claims"].values()))
        self.assertNotIn("2026", preregister.LH061_EVALUATION_MD_REPORT.read_text(encoding="utf-8"))

    def test_内容式重入不再读取真实结果(self):
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve() == preregister.FEC_LEDGER_PATH.resolve():
                raise AssertionError("不得再次打开结果")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", guarded_open):
            self.assertEqual(preregister.write_lh061_evaluation(), 0)


if __name__ == "__main__":
    unittest.main()
