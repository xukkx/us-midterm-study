"""LH268 结果对照汇总。

只读取本目录 decomposition/challenger 和冻结 LH266 policy-calibration 结果；
不重训、不进行 Monte Carlo。``--check`` 重新生成并逐字节比较 comparison.json。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "ces-policy-calibration-2026-09-09"
DECOMP = HERE / "decomposition.json"
CHALLENGER = HERE / "challenger.json"
OLD_POLICY = HERE / "policy-calibration.json" if (HERE / "policy-calibration.json").exists() else OLD / "policy-calibration.json"
OUT = HERE / "comparison.json"
N = 6175
METRICS = ("full_log", "event_log", "dest_log", "binary_brier", "multiclass_brier")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def zeros():
    return {key: 0.0 for key in METRICS}


def add_score(total, score, factor=1.0):
    for key in METRICS:
        total[key] += factor * score["score"][key] if "score" in score else factor * score[key]


def decomp_totals(obj, prefix="new_"):
    return {key: obj[prefix + key + "_total"] for key in METRICS}


def challenger_totals(obj):
    return {key: obj["score"][key] for key in METRICS}


def means_and_deltas(n, baseline, challenger):
    if n <= 0:
        raise ValueError("分母必须为正")
    out = {}
    for key in METRICS:
        base_mean = baseline[key] / n
        new_mean = challenger[key] / n
        delta = new_mean - base_mean
        out[key] = {
            "baseline_mean": base_mean,
            "new_mean": new_mean,
            "delta_mean": delta,
            "baseline_sum": baseline[key],
            "new_sum": challenger[key],
            "delta_sum": challenger[key] - baseline[key],
            "delta_cohort_contribution": (challenger[key] - baseline[key]) / N,
        }
    return {"n": n, "metrics": out}


def sum_challenge_groups(challenger, names):
    total = zeros()
    for name in names:
        add_score(total, challenger["early_five_group_scores"][name])
    return total


def r1_summary(old, new):
    old_items = {}
    for item, value in old["items"].items():
        r = value["R1"]
        mi = r["statistics"]["MI"]
        tv = r["statistics"]["TV"]
        old_items[item] = {
            "n": r["complete_n"], "layer_count": len(r["strata"]),
            "MI": {"observed": mi["observed"], "null_mean": mi["null"]["mean"], "p_plus_one": mi["p_plus_one"],
                   "Holm_primary_six": mi.get("Holm_primary_six"), "Holm_three_diagnostic": mi.get("Holm_three_diagnostic")},
            "TV": {"observed": tv["observed"], "null_mean": tv["null"]["mean"], "p_plus_one": tv["p_plus_one"]},
        }
    layers = []
    for row in new["layers"]:
        layers.append({"PID20raw": row["PID20raw"], "policy20": row["policy20"], "n": row["n"],
                       "row_margins": row["row_margins"], "W_margins": row["W_margins"],
                       "zero_rows": row["zero_rows"], "zero_W_cells": row["zero_W_cells"], "table": row["table"]})
    sizes = [row["n"] for row in layers]
    return {
        "old_all_items": old_items,
        "old_primary_item": "conditional_legalization",
        "old_primary": old_items["conditional_legalization"],
        "new_raw8": {
            "n": new["complete_n"], "layer_count": new["layer_n"], "MI": {
                "observed": new["statistics"]["MI"]["observed"], "null_mean": new["statistics"]["MI"]["null"]["mean"],
                "p_plus_one": new["statistics"]["MI"]["p_plus_one"], "MC_se": new["statistics"]["MI"]["MC_se"],
            }, "TV": {
                "observed": new["statistics"]["TV"]["observed"], "null_mean": new["statistics"]["TV"]["null"]["mean"],
                "p_plus_one": new["statistics"]["TV"]["p_plus_one"], "MC_se": new["statistics"]["TV"]["MC_se"],
            }, "draws": new["draws"], "seed": new["seed"],
            "sparse": new["diagnostics"], "layer_size_range": [min(sizes), max(sizes)], "layers": layers,
        },
        "interpretation": "旧为三题中的 conditional_legalization 主条目；新为本轮单一 raw8 敏感性。旧总层数不得把三题相加；新实际层数由非空H层确定。",
    }


def build():
    decomp = read(DECOMP); challenger = read(CHALLENGER); old = read(OLD_POLICY)
    if decomp["n"] != N or challenger["n"] != N:
        raise ValueError("当前结果人数不符")
    baseline_all = decomp_totals(decomp["score_components"]["all6175"])
    new_all = {key: challenger["mean_scores"][key] * N for key in METRICS}
    cohorts = {"all6175": means_and_deltas(N, baseline_all, new_all)}
    mappings = {
        "known_early_same": ("early_same", ("early_same_stable", "early_same_changed")),
        "known_early_diff": ("early_diff", ("early_diff_return", "early_diff_keep", "early_diff_third")),
        "changed414": ("changed414", ("early_same_changed", "early_diff_return", "early_diff_keep", "early_diff_third")),
    }
    for name, (base_key, challenge_keys) in mappings.items():
        base_obj = decomp["known_history"].get(base_key, decomp["score_components"].get(base_key))
        if base_obj is None: raise ValueError("缺少基线分组: " + base_key)
        n = base_obj["n"]
        cohorts[name] = means_and_deltas(n, decomp_totals(base_obj), sum_challenge_groups(challenger, challenge_keys))
    future = {}
    for name, base_obj in decomp["future_paths"].items():
        future[name] = means_and_deltas(base_obj["n"], decomp_totals(base_obj), challenger_totals(challenger["early_five_group_scores"][name]))
    if sum(value["n"] for value in future.values()) != N:
        raise ValueError("五类未来路径人数不闭合")
    if cohorts["known_early_same"]["n"] + cohorts["known_early_diff"]["n"] != N:
        raise ValueError("known 两组人数不闭合")
    if cohorts["changed414"]["n"] != 414 or cohorts["known_early_diff"]["n"] != 590:
        raise ValueError("414/590 人数合同不符")
    changed = cohorts["changed414"]
    conditional_dest = {"n": changed["n"], "baseline_mean": decomp["score_components"]["changed414"]["new_dest_log_mean"],
                        "new_mean": challenger["conditional_changed_means"]["dest_log"]}
    conditional_dest["delta_mean"] = conditional_dest["new_mean"] - conditional_dest["baseline_mean"]
    early = decomp["early_changed_threeway"]
    t = challenger["early_changed_threeway"]
    new_third_sum = t["third_internal_log_mean"] * t["third_n"]
    new_full590 = t["full_log_mean"] * t["n"]
    new_brier590 = t["brier_mean"] * t["n"]
    old_full590, old_brier590 = early["early_diff590"]["new_full_log_total"], early["early_diff590"]["new_brier_total"]
    old_third590 = early["early_diff590"]["new_third_internal_log_total"]
    def simple3(n, base_full, new_full, base_third, new_third, base_brier=None, new_brier=None):
        value = {"n": n, "full_log": {"baseline_sum": base_full, "new_sum": new_full, "delta_sum": new_full - base_full,
              "baseline_mean": base_full / n, "new_mean": new_full / n, "delta_mean": (new_full - base_full) / n, "delta_cohort_contribution": (new_full - base_full) / N},
              "coarse_log": {"baseline_sum": base_full - base_third, "new_sum": new_full - new_third, "delta_sum": (new_full - new_third) - (base_full - base_third),
              "baseline_mean": (base_full - base_third) / n, "new_mean": (new_full - new_third) / n, "delta_mean": ((new_full - new_third) - (base_full - base_third)) / n, "delta_cohort_contribution": ((new_full - new_third) - (base_full - base_third)) / N},
              "third_internal_log": {"baseline_sum": base_third, "new_sum": new_third, "delta_sum": new_third - base_third,
              "baseline_mean": base_third / n, "new_mean": new_third / n, "delta_mean": (new_third - base_third) / n, "delta_cohort_contribution": (new_third - base_third) / N}}
        if base_brier is not None: value["threeway_brier"] = {"baseline_sum": base_brier, "new_sum": new_brier, "delta_sum": new_brier - base_brier, "baseline_mean": base_brier / n, "new_mean": new_brier / n, "delta_mean": (new_brier - base_brier) / n, "delta_cohort_contribution": (new_brier - base_brier) / N}
        return value
    # third40 full log来自挑战者五路径中的 early_diff_third；第三类内部仍用590摘要中40人的条件和。
    new_full40 = challenger["early_five_group_scores"]["early_diff_third"]["score"]["full_log"]
    early_three = {"early_diff590": simple3(590, old_full590, new_full590, old_third590, new_third_sum, early["early_diff590"]["new_brier_total"], new_brier590),
                   "third40": simple3(40, early["third40"]["new_full_log_total"], new_full40, early["third40"]["new_third_internal_log_total"], new_third_sum)}
    if early_three["early_diff590"]["third_internal_log"]["new_sum"] != early_three["third40"]["third_internal_log"]["new_sum"]:
        raise ValueError("590/third40 内部条件和不闭合")
    return {
        "schema": "LH268-comparison-v1", "research": "LH268", "contract": "LH-302", "run": 319,
        "sources": {"decomposition_sha256": sha(DECOMP), "challenger_sha256": sha(CHALLENGER), "old_policy_calibration_sha256": sha(OLD_POLICY)},
        "r1": r1_summary(old, read(HERE / "r1-sensitivity.json")),
        "challenge_vs_frozen_child": {"baseline": "decomposition new_* totals (冻结LH267 child)", "cohorts": cohorts, "future_five": future, "changed414_conditional_destination": conditional_dest, "early_changed_threeway": early_three},
        "closure": {"cohort_n": {key: value["n"] for key, value in cohorts.items()}, "future_five_n": {key: value["n"] for key, value in future.items()}, "early_changed_n": 590, "third_n": 40, "changed_n": 414},
        "method": "纯JSON汇总；未重拟合、未新增置换；每项 delta=new-baseline，cohort contribution=delta_sum/6175。",
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); args = ap.parse_args()
    value = build(); encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.check:
        if not OUT.is_file() or OUT.read_bytes() != encoded: raise SystemExit("comparison.json 与纯汇总重算不一致")
    else:
        OUT.write_bytes(encoded)
    print(json.dumps({"schema": value["schema"], "cohorts": len(value["challenge_vs_frozen_child"]["cohorts"]), "future_five": len(value["challenge_vs_frozen_child"]["future_five"])}, ensure_ascii=False))


if __name__ == "__main__": main()
