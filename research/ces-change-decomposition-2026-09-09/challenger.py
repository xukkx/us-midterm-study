"""LH268 唯一政策预测挑战者：固定历史母预测并收缩20。"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

from r1_sensitivity import HERE, GRID, PLAN, gate_ok, sha
from scoring import score_one, threeway
from muse_shrink_kernel import shrink_kernel
from project_raw import check_anonymous

OLD = HERE.parent / "ces-policy-calibration-2026-09-09"
BASELINE = HERE / "history-nested.json" if (HERE / "history-nested.json").exists() else OLD / "history-nested.json"
MAP = [0, 0, 0, 1, 2, 2, 2, 3]
SHRINK = 20
N = 6175
FEATURES = ("PID20_4", "PID22raw8", "policy20", "policy22")


def validate_q(q):
    if not isinstance(q, list) or len(q) != 4 or any(not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in q):
        raise ValueError("概率向量必须是四维有限非负数")
    if abs(math.fsum(q) - 1.) > 1e-12:
        raise ValueError("概率向量和不为1")
    return q


def load_baseline(path=BASELINE):
    data = json.loads(path.read_text(encoding="utf-8"))
    folds = data.get("folds")
    if data.get("n") != N or not isinstance(folds, list) or len(folds) != 5:
        raise ValueError("冻结基线人数或折数不符")
    result = []
    for fold in folds:
        child = fold.get("child")
        if not isinstance(child, list) or len(child) != 4 or any(not isinstance(row, list) or len(row) != 8 for row in child):
            raise ValueError("冻结基线 child 维度不符")
        for row in child:
            for q in row:
                validate_q(q)
        result.append(child)
    return result


def q_for(base_q, counts, cell_n):
    if cell_n != sum(counts):
        raise ValueError("cell_n与四维计数和不一致")
    q = shrink_kernel(counts, base_q, SHRINK)
    validate_q(q)
    return q


def score(q, y, b):
    result = score_one(q, y, b)
    # 使用冻结评分内核，确保未变化事件的 Brier 为 (1-q[b])²。
    result["full_log"] = math.log(q[y])
    return result


def aggregate_grid(data):
    """把匿名联合格按测试 fold 投影到 feature×target 计数。"""
    by_fold = [dict() for _ in range(5)]
    for row in data["rows"]:
        a = MAP[row["PID20raw"] - 1]
        b_raw = row["PID22raw"]
        b = MAP[b_raw - 1]
        feat = (a, b_raw, row["policy20"], row["policy22"])
        y = MAP[row["PID24raw"] - 1]
        for fold, n in enumerate(row["fold_counts"]):
            if n:
                by_fold[fold][(feat, y)] = by_fold[fold].get((feat, y), 0) + n
    return by_fold


def fit_fold(test_counts, train_counts, baseline_child, fold):
    cells = {}
    features = sorted({feat for feat, _ in test_counts} | {feat for feat, _ in train_counts})
    for feat in features:
        counts = [train_counts.get((feat, y), 0) for y in range(4)]
        cell_n = sum(counts)
        a, b_raw, _p20, _p22 = feat
        base_q = baseline_child[a][b_raw - 1]
        cells[feat] = {"n_train": cell_n, "training_target_counts": counts, "baseline_q": base_q,
                       "q_new": q_for(base_q, counts, cell_n)}
    totals = {k: 0. for k in ("full_log", "event_log", "dest_log", "multiclass_brier", "binary_brier")}
    changed_binary_total = 0.
    three_totals = {"n": 0, "full_log": 0., "brier": 0., "third_n": 0, "third_internal_log": 0.}
    n = changed_n = 0
    path = {}
    for (feat, y), count in sorted(test_counts.items()):
        a, b_raw, p20, p22 = feat
        b = MAP[b_raw - 1]
        q = cells[feat]["q_new"]
        s = score(q, y, b)
        n += count; changed_n += count * s["changed"]
        for k in totals: totals[k] += count * s[k]
        if s["changed"]:
            changed_binary_total += count * s["binary_brier"]
        if a != b:
            t = threeway(q, a, b, y)
            three_totals["n"] += count
            three_totals["full_log"] += count * t["full_log"]
            three_totals["brier"] += count * t["brier"]
            if t["third_internal_log"] is not None:
                three_totals["third_n"] += count
                three_totals["third_internal_log"] += count * t["third_internal_log"]
        path_key = (a, b, y)
        z = path.setdefault(path_key, {"n": 0, "score": {k: 0. for k in totals}})
        z["n"] += count
        for k in totals: z["score"][k] += count * s[k]
    if n != sum(test_counts.values()):
        raise AssertionError("折内评分人数不闭合")
    return {"fold": fold, "train_n": sum(train_counts.values()), "test_n": n,
            "changed_n": changed_n, "training_cells": cells, "scores": totals,
            "path_scores": path, "threeway": three_totals,
            "changed_binary_brier_sum": changed_binary_total}


def serial_fold(result):
    """将内部 tuple 键转换成可公开复算的显式字符串键。"""
    cells = {}
    for feat, value in result["training_cells"].items():
        cells["|".join(map(str, feat))] = {"feature_values": list(feat), **value}
    paths = {}
    for path, value in result["path_scores"].items():
        paths["|".join(map(str, path))] = {"PID4_path": list(path), **value}
    return {k: v for k, v in result.items() if k not in ("training_cells", "path_scores")} | {
        "training_cells": cells, "path_scores": paths}


def verify_result(result, expected):
    for key in ("schema", "n", "features", "target", "shrink_mass", "fold_rule", "folds", "mean_scores", "changed_n", "conditional_changed_means", "path_scores", "group_scores", "early_five_group_scores", "early_changed_threeway", "baseline_definition", "forbidden_inputs"):
        if result.get(key) != expected.get(key):
            raise ValueError("挑战者结果重算不一致: " + key)
    if result.get("grid_sha256") != sha(GRID):
        raise ValueError("挑战者 grid_sha256 不一致")
    if result.get("baseline_sha256") != sha(BASELINE):
        raise ValueError("挑战者 baseline_sha256 不一致")
    if result.get("plan_sha256") != sha(PLAN):
        raise ValueError("挑战者 plan_sha256 不一致")
    if result.get("shrink_kernel_sha256") != sha(HERE / "muse_shrink_kernel.py"):
        raise ValueError("挑战者 shrink kernel SHA 不一致")


def run(data, baseline):
    fold_tests = aggregate_grid(data)
    folds = []
    all_path = {}
    overall = {k: 0. for k in ("full_log", "event_log", "dest_log", "multiclass_brier", "binary_brier")}
    changed_n = 0
    changed_binary_total = 0.
    threeway_total = {"n": 0, "full_log": 0., "brier": 0., "third_n": 0, "third_internal_log": 0.}
    for f, test in enumerate(fold_tests):
        train = {}
        for g, counts in enumerate(fold_tests):
            if g == f: continue
            for key, n in counts.items(): train[key] = train.get(key, 0) + n
        result = fit_fold(test, train, baseline[f], f)
        folds.append(serial_fold(result))
        changed_n += result["changed_n"]
        changed_binary_total += result["changed_binary_brier_sum"]
        for k in overall: overall[k] += result["scores"][k]
        for k in threeway_total: threeway_total[k] += result["threeway"][k]
        for key, value in result["path_scores"].items():
            z = all_path.setdefault(key, {"n": 0, "score": {k: 0. for k in overall}})
            z["n"] += value["n"]
            for k in overall: z["score"][k] += value["score"][k]
    if sum(x["test_n"] for x in folds) != N or changed_n <= 0:
        raise AssertionError("五折总人数不闭合")
    path_rows = []
    groups = {g: {"n": 0, "score": {k: 0. for k in overall}} for g in ("stable", "return", "nonreturn_change")}
    for (a, b, c), value in sorted(all_path.items()):
        group = "stable" if a == b == c else "return" if a == c else "nonreturn_change"
        path_rows.append({"PID4_path": [a, b, c], **value})
        groups[group]["n"] += value["n"]
        for k in overall: groups[group]["score"][k] += value["score"][k]
    means = {k: overall[k] / N for k in overall}
    # 条件目的地只对实际变化者取均值；事件和 Brier 按完整队列分母报告。
    conditional_means = {"dest_log": overall["dest_log"] / changed_n,
                          "binary_brier": changed_binary_total / changed_n}
    five = {g: {"n": 0, "score": {k: 0. for k in overall}} for g in ("early_same_stable", "early_same_changed", "early_diff_return", "early_diff_keep", "early_diff_third")}
    for (a, b, c), value in all_path.items():
        g = "early_same_stable" if a == b == c else "early_same_changed" if a == b else "early_diff_return" if c == a else "early_diff_keep" if c == b else "early_diff_third"
        five[g]["n"] += value["n"]
        for k in overall: five[g]["score"][k] += value["score"][k]
    early_threeway = {
        "n": threeway_total["n"],
        "full_log_mean": threeway_total["full_log"] / threeway_total["n"],
        "brier_mean": threeway_total["brier"] / threeway_total["n"],
        "third_n": threeway_total["third_n"],
        "third_internal_log_mean": threeway_total["third_internal_log"] / threeway_total["third_n"],
        "target_classes": {"return_baseline": 137, "keep_2022": 413, "third": 40},
    }
    return {"schema": "LH268-policy-challenger-v1", "n": N, "features": list(FEATURES),
            "target": "PID24_4", "shrink_mass": SHRINK,
            "fold_rule": "匿名格已按 SHA256(LH265|caseid_20) 固定折计数",
            "folds": folds, "mean_scores": means, "changed_n": changed_n,
            "conditional_changed_means": conditional_means, "path_scores": path_rows,
            "group_scores": groups, "early_five_group_scores": five,
            "early_changed_threeway": early_threeway,
            "baseline_definition": "冻结LH267 child[PID20_4][PID22raw8][PID24_4]，每折训练外固定",
            "forbidden_inputs": ["policy24", "future_path_label", "three_wave_latent_score"],
            "uncertainty": "有限队列 OOF 描述；不报告算法或全国区间。"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = HERE / "challenger.json"
    if args.check:
        value = json.loads(out.read_text(encoding="utf-8"))
        if value.get("schema") != "LH268-policy-challenger-v1" or value.get("n") != N or value.get("shrink_mass") != SHRINK:
            raise SystemExit("挑战者结果封印不符")
        gate = gate_ok()
        if value.get("gate", {}).get("gate_sha256") != gate["gate_sha256"]:
            raise SystemExit("挑战者结果对应的 stage1-gate 已变化，需重新运行")
        if (HERE / "muse_shrink_kernel.py").exists():
            kernel_sha = sha(HERE / "muse_shrink_kernel.py")
            if value.get("shrink_kernel_sha256") != kernel_sha:
                raise SystemExit("挑战者结果对应的 Muse shrink kernel 已变化，需重新运行")
        data = json.loads(GRID.read_text(encoding="utf-8")); check_anonymous(data)
        expected = run(data, load_baseline()); verify_result(value, expected)
        print(json.dumps({"n": value["n"], "folds": len(value["folds"]), "changed_n": value["changed_n"]}, ensure_ascii=False)); return
    if not args.run:
        ap.error("需要 --run 或 --check")
    gate = gate_ok()
    data = json.loads(GRID.read_text(encoding="utf-8")); check_anonymous(data)
    baseline = load_baseline()
    result = run(data, baseline)
    result["gate"] = gate
    result["grid_sha256"] = sha(GRID)
    result["baseline_sha256"] = sha(BASELINE)
    result["shrink_kernel_sha256"] = sha(HERE / "muse_shrink_kernel.py")
    result["plan_sha256"] = sha(PLAN)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": result["n"], "folds": len(result["folds"]), "changed_n": result["changed_n"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
