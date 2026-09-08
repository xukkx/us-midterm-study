"""LH-052 纯数学组件的合成手算与失败关闭测试。

本文件只构造内存 fixture；不读取任何真实结果或数据路径。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path
from statistics import NormalDist


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.senate_balancing import (  # noqa: E402
    COMPONENT_ID,
    DEVELOPMENT_CYCLES,
    DEVELOPMENT_PARTIES,
    EVALUATION_PARENT_TRAIN_CYCLES,
    EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES,
    FORMULA_VERSION,
    PARTY_SIGNS,
    SenateBalancingValidationError,
    apply_balancing_prior,
    canonical_contest_inventory,
    fit_balancing_prior,
    independent_count_pmf,
    poisson_binomial_pmf,
    prediction_bytes,
    prior_bytes,
    sanitize_parent_predictions,
    validate_development_inputs,
)


NORMAL = NormalDist()


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def development_rows(
    dem_residual: float = -2.0,
    rep_residual: float = 2.0,
    *,
    counts: dict[int, int] | None = None,
    residuals: dict[int, float] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    states = ("AZ", "CO", "IA", "ME", "NV")
    for cycle_index, cycle in enumerate(DEVELOPMENT_CYCLES):
        party = DEVELOPMENT_PARTIES[cycle]
        residual = (
            residuals[cycle]
            if residuals is not None
            else dem_residual if party == "DEM" else rep_residual
        )
        count = counts.get(cycle, 2) if counts is not None else 2
        for row_index in range(count):
            parent_margin = float(row_index - count // 2)
            race_id = f"SYN-DEV-{cycle}-{row_index:02d}"
            rows.append(
                {
                    "race_id": race_id,
                    "cycle": cycle,
                    "state": states[row_index % len(states)],
                    "office": "SENATE",
                    "two_party_margin": parent_margin + residual,
                    "predicted_margin": parent_margin,
                    "margin_sd": 3.0,
                    "parent_model_id": "M0_SENATE",
                    "parent_prediction_mode": "out_of_fold",
                    "parent_prediction_hash": digest(f"prediction:{race_id}"),
                    "parent_lineage_hash": digest(f"lineage:{cycle}"),
                    "parent_train_cycles": list(range(1978, cycle, 4)),
                    "president_party": party,
                }
            )
    return rows


def parent_prediction(
    cycle: int = 2018,
    *,
    suffix: str = "00",
    state: str = "AZ",
    margin: float = 1.0,
    sd: float = 2.0,
) -> dict[str, object]:
    party = {2018: "REP", 2022: "DEM"}.get(cycle, "REP")
    race_id = f"SYN-EVAL-{cycle}-{suffix}"
    return {
        "race_id": race_id,
        "cycle": cycle,
        "state": state,
        "office": "SENATE",
        "predicted_margin": margin,
        "margin_sd": sd,
        "democratic_win_probability": NORMAL.cdf(margin / sd),
        "parent_model_id": "M0_SENATE",
        "parent_prediction_mode": "out_of_fold",
        "contest_inventory_hash": digest(f"inventory:{cycle}"),
        "parent_prediction_hash": digest(f"parent:{race_id}"),
        "parent_lineage_hash": digest(f"lineage:through-2014:{cycle}"),
        "parent_train_cycles": list(EVALUATION_PARENT_TRAIN_CYCLES),
        "president_party": party,
    }


def party_rule(cycle: int = 2018) -> dict[str, object]:
    party = {2018: "REP", 2022: "DEM"}[cycle]
    sign = PARTY_SIGNS[party]
    return {
        "cycle": cycle,
        "president_name": "合成在任总统",
        "president_party": party,
        "president_party_sign": sign,
        "balancing_direction_sign": -sign,
        "term_started_at": f"{cycle - 1}-01-20T12:00:00+00:00",
        "effective_at": f"{cycle - 1}-01-20T12:00:00+00:00",
        "available_at": f"{cycle - 1}-01-20T12:00:00+00:00",
        "forecast_as_of": f"{cycle}-10-01T00:00:00+00:00",
        "source_id": "synthetic-official-rule",
        "source_url": "https://example.gov/synthetic-incumbent",
        "source_hash_status": "official_reference_url_frozen_ledger_bytes_sealed",
    }


def positive_prior():
    return fit_balancing_prior(development_rows())


def child_rows(cycle: int = 2018, count: int = 1):
    parents = [
        parent_prediction(cycle, suffix=f"{index:02d}", state=("AZ", "CO", "IA")[index % 3])
        for index in range(count)
    ]
    return parents, apply_balancing_prior(positive_prior(), party_rule(cycle), parents)


class FormulaTests(unittest.TestCase):
    def test_01_component_and_formula_identity_are_frozen(self):
        self.assertEqual(COMPONENT_ID, "SENATE_BALANCING_DIRECTION_PRIOR")
        self.assertEqual(FORMULA_VERSION, "senate_balancing_direction_prior_v1")
        self.assertEqual(
            EVALUATION_PARENT_TRAIN_CYCLES,
            (1978, 1982, 1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014),
        )

    def test_02_positive_direction_hand_calculation(self):
        prior = positive_prior()
        self.assertEqual(prior.b_hat, 2.0)

    def test_03_party_cycle_means_use_four_cycles_each(self):
        residuals = {
            1986: 1.0,
            1990: 2.0,
            1994: -1.0,
            1998: -2.0,
            2002: 3.0,
            2006: 4.0,
            2010: -3.0,
            2014: -4.0,
        }
        prior = fit_balancing_prior(development_rows(residuals=residuals))
        self.assertEqual(prior.party_cycle_means, {"DEM": -2.5, "REP": 2.5})
        self.assertEqual(prior.b_hat, 2.5)

    def test_04_cycle_summaries_are_exact_and_sorted(self):
        prior = positive_prior()
        self.assertEqual(tuple(item.cycle for item in prior.cycle_summaries), DEVELOPMENT_CYCLES)
        self.assertEqual(tuple(item.n_races for item in prior.cycle_summaries), (2,) * 8)
        self.assertEqual(
            tuple(item.residual_mean for item in prior.cycle_summaries),
            tuple(2.0 if DEVELOPMENT_PARTIES[cycle] == "REP" else -2.0 for cycle in DEVELOPMENT_CYCLES),
        )

    def test_05_cycle_equal_weighting_resists_unequal_race_counts(self):
        counts = {cycle: index + 1 for index, cycle in enumerate(DEVELOPMENT_CYCLES)}
        prior = fit_balancing_prior(development_rows(counts=counts))
        self.assertEqual(prior.b_hat, 2.0)
        self.assertEqual(tuple(item.n_races for item in prior.cycle_summaries), tuple(range(1, 9)))

    def test_06_reverse_direction_is_truncated_to_zero(self):
        prior = fit_balancing_prior(development_rows(dem_residual=1.0, rep_residual=-1.0))
        self.assertEqual(prior.b_hat, 0.0)
        self.assertEqual(math.copysign(1.0, prior.b_hat), 1.0)

    def test_07_zero_direction_is_exact_numeric_parent_identity(self):
        prior = fit_balancing_prior(development_rows(dem_residual=0.0, rep_residual=0.0))
        parent = parent_prediction(2018)
        child = apply_balancing_prior(prior, party_rule(2018), [parent])[0]
        for field in ("predicted_margin", "margin_sd", "democratic_win_probability"):
            self.assertEqual(child[field], parent[field])

    def test_08_rep_president_mirrors_shift_toward_democrats(self):
        parent = parent_prediction(2018, margin=1.0)
        child = apply_balancing_prior(positive_prior(), party_rule(2018), [parent])[0]
        self.assertEqual(child["predicted_margin"], 3.0)

    def test_09_dem_president_mirrors_shift_toward_republicans(self):
        parent = parent_prediction(2022, margin=1.0)
        child = apply_balancing_prior(positive_prior(), party_rule(2022), [parent])[0]
        self.assertEqual(child["predicted_margin"], -1.0)

    def test_10_parent_sd_and_normal_probability_are_exact(self):
        parent = parent_prediction(2018, margin=1.0, sd=2.0)
        child = apply_balancing_prior(positive_prior(), party_rule(2018), [parent])[0]
        self.assertEqual(child["margin_sd"], parent["margin_sd"])
        self.assertEqual(child["democratic_win_probability"], NORMAL.cdf(3.0 / 2.0))

    def test_11_parent_identity_inventory_and_lineage_are_preserved(self):
        parent = parent_prediction(2018)
        child = apply_balancing_prior(positive_prior(), party_rule(2018), [parent])[0]
        for field in (
            "race_id", "cycle", "state", "office", "contest_inventory_hash",
            "parent_prediction_hash", "parent_lineage_hash", "parent_model_id",
            "parent_prediction_mode", "parent_train_cycles",
        ):
            self.assertEqual(child[field], parent[field])

    def test_12_development_input_order_does_not_change_prior_bytes(self):
        rows = development_rows()
        self.assertEqual(prior_bytes(fit_balancing_prior(rows)), prior_bytes(fit_balancing_prior(list(reversed(rows)))))

    def test_13_parent_input_order_does_not_change_prediction_bytes(self):
        parents, children = child_rows(2018, 3)
        reversed_children = apply_balancing_prior(positive_prior(), party_rule(2018), list(reversed(parents)))
        self.assertEqual(prediction_bytes(children), prediction_bytes(reversed_children))

    def test_14_untrusted_test_fields_do_not_change_prediction_bytes(self):
        parent = parent_prediction(2018)
        baseline = apply_balancing_prior(positive_prior(), party_rule(2018), [parent])
        forged = dict(parent)
        forged.update({
            "test_actual": -99.0,
            "winner": "FORGED",
            "realized_swing": 999.0,
            "receipt": {"decision": "FORGED"},
            "review_context": ["FORGED"],
        })
        mutated = apply_balancing_prior(positive_prior(), party_rule(2018), [forged])
        self.assertEqual(prediction_bytes(baseline), prediction_bytes(mutated))


class DevelopmentValidationTests(unittest.TestCase):
    def test_15_exact_eight_cycle_oof_fixture_is_accepted(self):
        rows = validate_development_inputs(development_rows())
        self.assertEqual(tuple(sorted({row.cycle for row in rows})), DEVELOPMENT_CYCLES)
        self.assertEqual(len(rows), 16)

    def test_16_missing_development_cycle_fails(self):
        rows = [row for row in development_rows() if row["cycle"] != 1986]
        with self.assertRaisesRegex(SenateBalancingValidationError, "精确为冻结八届"):
            fit_balancing_prior(rows)

    def test_17_extra_development_cycle_fails(self):
        rows = development_rows()
        extra = copy.deepcopy(rows[0])
        extra.update({
            "race_id": "SYN-DEV-2018-X",
            "cycle": 2018,
            "parent_prediction_hash": digest("extra"),
            "parent_lineage_hash": digest("extra-lineage"),
        })
        rows.append(extra)
        with self.assertRaisesRegex(SenateBalancingValidationError, "allowlist"):
            fit_balancing_prior(rows)

    def test_18_non_midterm_development_cycle_fails(self):
        rows = development_rows()
        rows[0]["cycle"] = 1988
        with self.assertRaisesRegex(SenateBalancingValidationError, "中期周期"):
            fit_balancing_prior(rows)

    def test_19_duplicate_race_fails(self):
        rows = development_rows()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(SenateBalancingValidationError, "重复 race_id"):
            fit_balancing_prior(rows)

    def test_20_null_nan_and_inf_actual_margin_fail(self):
        for value in (None, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                rows = development_rows()
                rows[0]["two_party_margin"] = value
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_21_bool_actual_margin_fails(self):
        rows = development_rows()
        rows[0]["two_party_margin"] = True
        with self.assertRaisesRegex(SenateBalancingValidationError, "bool"):
            fit_balancing_prior(rows)

    def test_22_nonfinite_or_out_of_bounds_parent_margin_fails(self):
        for value in (float("nan"), float("inf"), 100.01, -100.01):
            with self.subTest(value=value):
                rows = development_rows()
                rows[0]["predicted_margin"] = value
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_23_nonpositive_nonfinite_or_bool_parent_sd_fails(self):
        for value in (0.0, -1.0, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                rows = development_rows()
                rows[0]["margin_sd"] = value
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_24_non_oof_mode_and_wrong_parent_model_fail(self):
        for field, value in (("parent_prediction_mode", "in_sample"), ("parent_model_id", "B1_SENATE")):
            with self.subTest(field=field):
                rows = development_rows()
                rows[0][field] = value
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_25_same_cycle_or_future_parent_training_fails(self):
        for value in (1986, 1990):
            with self.subTest(value=value):
                rows = development_rows()
                rows[0]["parent_train_cycles"] = [1978, 1982, value]
                with self.assertRaisesRegex(SenateBalancingValidationError, "同届或未来"):
                    fit_balancing_prior(rows)

    def test_26_unsorted_or_duplicate_parent_training_cycles_fail(self):
        for train_cycles in ([1982, 1978], [1978, 1978, 1982]):
            with self.subTest(train_cycles=train_cycles):
                rows = development_rows()
                rows[0]["parent_train_cycles"] = train_cycles
                with self.assertRaisesRegex(SenateBalancingValidationError, "严格唯一升序"):
                    fit_balancing_prior(rows)

    def test_27_duplicate_parent_prediction_hash_fails(self):
        rows = development_rows()
        rows[1]["parent_prediction_hash"] = rows[0]["parent_prediction_hash"]
        with self.assertRaisesRegex(SenateBalancingValidationError, "prediction_hash 重复"):
            fit_balancing_prior(rows)

    def test_28_within_cycle_parent_lineage_or_sd_drift_fails(self):
        for field, value in (("parent_lineage_hash", digest("drift")), ("margin_sd", 4.0)):
            with self.subTest(field=field):
                rows = development_rows()
                rows[1][field] = value
                with self.assertRaisesRegex(SenateBalancingValidationError, "漂移"):
                    fit_balancing_prior(rows)

    def test_29_unknown_or_wrong_president_party_fails(self):
        for value in ("OTHER", "DEM"):
            with self.subTest(value=value):
                rows = development_rows()
                rows[0]["president_party"] = value
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_30_missing_extra_blank_identity_bad_state_and_house_fail(self):
        mutations = (
            ("missing", lambda row: row.pop("state")),
            ("extra", lambda row: row.__setitem__("winner", "REP")),
            ("blank_race", lambda row: row.__setitem__("race_id", "")),
            ("bad_state", lambda row: row.__setitem__("state", "DC")),
            ("house", lambda row: row.__setitem__("office", "HOUSE")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                rows = development_rows()
                mutate(rows[0])
                with self.assertRaises(SenateBalancingValidationError):
                    fit_balancing_prior(rows)

    def test_50_1986_rejects_forged_earlier_parent_lineage(self):
        rows = development_rows()
        rows[0]["parent_train_cycles"] = [1974, 1978]
        with self.assertRaisesRegex(SenateBalancingValidationError, "父训练 lineage 必须精确"):
            fit_balancing_prior(rows)

    def test_51_2014_rejects_parent_lineage_with_omitted_cycle(self):
        rows = development_rows()
        target = next(row for row in rows if row["cycle"] == 2014)
        target["parent_train_cycles"] = list(range(1978, 2010, 4))
        with self.assertRaisesRegex(SenateBalancingValidationError, "父训练 lineage 必须精确"):
            fit_balancing_prior(rows)

    def test_52_expected_development_parent_lineage_mapping_is_frozen(self):
        self.assertEqual(EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES[1986], (1978, 1982))
        self.assertEqual(
            EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES[2014],
            tuple(range(1978, 2014, 4)),
        )


class ParentAndRuleValidationTests(unittest.TestCase):
    def test_31_parent_sanitizer_ignores_only_untrusted_extra_fields(self):
        parent = parent_prediction(2018)
        parent.update({"actual_margin": -9.0, "winner": "REP", "realized_swing": 42.0})
        frozen = sanitize_parent_predictions([parent])[0]
        self.assertFalse(hasattr(frozen, "actual_margin"))
        self.assertFalse(hasattr(frozen, "winner"))
        self.assertFalse(hasattr(frozen, "realized_swing"))

    def test_32_missing_parent_duty_field_fails(self):
        parent = parent_prediction(2018)
        parent.pop("contest_inventory_hash")
        with self.assertRaisesRegex(SenateBalancingValidationError, "缺父职责字段"):
            sanitize_parent_predictions([parent])

    def test_33_mixed_evaluation_cycles_in_one_batch_fail(self):
        with self.assertRaisesRegex(SenateBalancingValidationError, "一个父预测批次"):
            sanitize_parent_predictions([parent_prediction(2018), parent_prediction(2022)])

    def test_34_unregistered_or_non_midterm_prediction_cycle_fails(self):
        for cycle in (2014, 2020):
            with self.subTest(cycle=cycle):
                parent = parent_prediction(cycle)
                with self.assertRaises(SenateBalancingValidationError):
                    sanitize_parent_predictions([parent])

    def test_35_inventory_or_lineage_drift_within_cycle_fails(self):
        for field, value in (("contest_inventory_hash", digest("drift-inventory")), ("parent_lineage_hash", digest("drift-lineage"))):
            with self.subTest(field=field):
                parents = [parent_prediction(2018, suffix="A"), parent_prediction(2018, suffix="B", state="CO")]
                parents[1][field] = value
                with self.assertRaisesRegex(SenateBalancingValidationError, "inventory/lineage"):
                    sanitize_parent_predictions(parents)

    def test_36_parent_probability_must_match_normal_exactly(self):
        parent = parent_prediction(2018)
        parent["democratic_win_probability"] = float(parent["democratic_win_probability"]) + 1e-15
        with self.assertRaisesRegex(SenateBalancingValidationError, "Normal"):
            sanitize_parent_predictions([parent])

    def test_37_2022_must_not_train_on_2018(self):
        parent = parent_prediction(2022)
        parent["parent_train_cycles"] = list(EVALUATION_PARENT_TRAIN_CYCLES) + [2018]
        with self.assertRaisesRegex(SenateBalancingValidationError, "冻结十届"):
            sanitize_parent_predictions([parent])

    def test_38_parent_model_mode_party_duplicates_and_rule_signs_fail(self):
        cases = []
        wrong_model = parent_prediction(2018)
        wrong_model["parent_model_id"] = "B1_SENATE"
        cases.append(("model", lambda: sanitize_parent_predictions([wrong_model])))
        wrong_mode = parent_prediction(2018)
        wrong_mode["parent_prediction_mode"] = "in_sample"
        cases.append(("mode", lambda: sanitize_parent_predictions([wrong_mode])))
        wrong_party = parent_prediction(2018)
        wrong_party["president_party"] = "DEM"
        cases.append(("party", lambda: sanitize_parent_predictions([wrong_party])))
        duplicate = parent_prediction(2018)
        cases.append(("duplicate", lambda: sanitize_parent_predictions([duplicate, copy.deepcopy(duplicate)])))
        bad_rules = []
        wrong_cycle = party_rule(2018)
        wrong_cycle["cycle"] = 2022
        bad_rules.append(wrong_cycle)
        wrong_sign = party_rule(2018)
        wrong_sign["president_party_sign"] = 1
        bad_rules.append(wrong_sign)
        wrong_direction = party_rule(2018)
        wrong_direction["balancing_direction_sign"] = -1
        bad_rules.append(wrong_direction)
        for label, call in cases:
            with self.subTest(label=label):
                with self.assertRaises(SenateBalancingValidationError):
                    call()
        for index, rule in enumerate(bad_rules):
            with self.subTest(rule=index):
                with self.assertRaises(SenateBalancingValidationError):
                    apply_balancing_prior(positive_prior(), rule, [parent_prediction(2018)])


class SerializationTests(unittest.TestCase):
    def test_39_prediction_bytes_are_canonical_json(self):
        _, children = child_rows(2018, 2)
        payload = prediction_bytes(children)
        decoded = json.loads(payload.decode("utf-8"))
        self.assertEqual([row["race_id"] for row in decoded], sorted(row["race_id"] for row in decoded))
        self.assertNotIn(b"NaN", payload)

    def test_40_extra_field_and_duplicate_child_fail_serialization(self):
        _, children = child_rows(2018, 1)
        extra = dict(children[0], winner="REP")
        with self.assertRaisesRegex(SenateBalancingValidationError, "规范子预测字段"):
            prediction_bytes([extra])
        with self.assertRaisesRegex(SenateBalancingValidationError, "重复 race_id"):
            prediction_bytes([children[0], copy.deepcopy(children[0])])

    def test_41_empty_or_corrupted_child_probability_fails_serialization(self):
        with self.assertRaises(SenateBalancingValidationError):
            prediction_bytes([])
        _, children = child_rows(2018, 1)
        corrupt = dict(children[0])
        corrupt["democratic_win_probability"] = 0.5
        with self.assertRaisesRegex(SenateBalancingValidationError, "Normal"):
            prediction_bytes([corrupt])


class CountPmfTests(unittest.TestCase):
    def test_42_two_fair_races_match_hand_calculation(self):
        self.assertEqual(poisson_binomial_pmf([0.5, 0.5]), (0.25, 0.5, 0.25))

    def test_43_deterministic_bernoulli_races_match_hand_calculation(self):
        self.assertEqual(poisson_binomial_pmf([0.0, 1.0]), (0.0, 1.0, 0.0))

    def test_44_pmf_is_normalized_order_invariant_and_has_correct_mean(self):
        probabilities = (0.1, 0.4, 0.8)
        pmf = poisson_binomial_pmf(probabilities)
        reverse = poisson_binomial_pmf(list(reversed(probabilities)))
        self.assertEqual(pmf, reverse)
        self.assertAlmostEqual(math.fsum(pmf), 1.0)
        self.assertAlmostEqual(sum(index * mass for index, mass in enumerate(pmf)), sum(probabilities))

    def test_45_empty_missing_nan_inf_bool_and_out_of_range_probability_fail(self):
        bad_inputs = ([], [float("nan")], [float("inf")], [True], [-0.01], [1.01])
        for values in bad_inputs:
            with self.subTest(values=values):
                with self.assertRaises(SenateBalancingValidationError):
                    poisson_binomial_pmf(values)

    def test_46_prediction_pmf_accepts_same_cycle_same_inventory(self):
        _parents, children = child_rows(2018, 2)
        pmf = independent_count_pmf(children)
        self.assertEqual(len(pmf), 3)
        self.assertAlmostEqual(math.fsum(pmf), 1.0)

    def test_47_prediction_pmf_rejects_mixed_cycles(self):
        _parents_2018, children_2018 = child_rows(2018, 1)
        _parents_2022, children_2022 = child_rows(2022, 1)
        with self.assertRaisesRegex(SenateBalancingValidationError, "一个评估周期"):
            independent_count_pmf(children_2018 + children_2022)

    def test_48_prediction_pmf_rejects_inventory_drift(self):
        _parents, children = child_rows(2018, 2)
        drifted = [dict(row) for row in children]
        drifted[1]["contest_inventory_hash"] = digest("drifted-inventory")
        with self.assertRaisesRegex(SenateBalancingValidationError, "inventory hash"):
            independent_count_pmf(drifted)

    def test_49_prediction_pmf_rejects_bare_mapping_mode(self):
        with self.assertRaisesRegex(SenateBalancingValidationError, "规范子预测字段"):
            independent_count_pmf([{"democratic_win_probability": 0.5}])


class M3InventoryBindingTests(unittest.TestCase):
    def bound_parents(self):
        ids, inventory_hash = canonical_contest_inventory(
            ["SENATE-2018-AZ-REGULAR", "SENATE-2018-CO-REGULAR"]
        )
        first = parent_prediction(2018, suffix="A", state="AZ")
        second = parent_prediction(2018, suffix="B", state="CO")
        first["race_id"], second["race_id"] = ids
        first["contest_inventory_hash"] = inventory_hash
        second["contest_inventory_hash"] = inventory_hash
        return [first, second], ids, inventory_hash

    def test_50_canonical_inventory_is_sorted_sha256(self):
        ids, digest_value = canonical_contest_inventory(["SENATE-2018-CO-REGULAR", "SENATE-2018-AZ-REGULAR"])
        self.assertEqual(ids, ("SENATE-2018-AZ-REGULAR", "SENATE-2018-CO-REGULAR"))
        self.assertEqual(len(digest_value), 64)

    def test_51_missing_race_is_rejected_by_m3(self):
        parents, ids, inventory_hash = self.bound_parents()
        with self.assertRaisesRegex(SenateBalancingValidationError, "M3 contest inventory"):
            sanitize_parent_predictions(parents[:1], expected_race_ids=ids, expected_inventory_hash=inventory_hash)

    def test_52_extra_race_is_rejected_by_m3(self):
        parents, ids, inventory_hash = self.bound_parents()
        extra = dict(parents[0], race_id="SENATE-2018-IA-REGULAR", contest_inventory_hash=inventory_hash, parent_prediction_hash=digest("extra-parent"))
        with self.assertRaisesRegex(SenateBalancingValidationError, "M3 contest inventory"):
            sanitize_parent_predictions(parents + [extra], expected_race_ids=ids, expected_inventory_hash=inventory_hash)

    def test_53_hash_mismatch_is_rejected_by_m3(self):
        parents, ids, inventory_hash = self.bound_parents()
        with self.assertRaisesRegex(SenateBalancingValidationError, "M3 inventory hash"):
            sanitize_parent_predictions(parents, expected_race_ids=ids, expected_inventory_hash=digest("wrong"))

    def test_54_count_pmf_rechecks_m3_inventory(self):
        parents, ids, inventory_hash = self.bound_parents()
        children = apply_balancing_prior(positive_prior(), party_rule(2018), parents, expected_race_ids=ids, expected_inventory_hash=inventory_hash)
        self.assertAlmostEqual(sum(independent_count_pmf(children, expected_race_ids=ids, expected_inventory_hash=inventory_hash)), 1.0)
        with self.assertRaisesRegex(SenateBalancingValidationError, "M3 contest inventory"):
            independent_count_pmf(children[:1], expected_race_ids=ids, expected_inventory_hash=inventory_hash)


if __name__ == "__main__":
    unittest.main()
