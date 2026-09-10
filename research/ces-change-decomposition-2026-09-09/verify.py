"""LH268 独立数值验收。

本文件故意不导入 decompose.py、scoring.py 或生产拟合代码：它从匿名 raw8
折计数和冻结概率自行重算 log/event/destination，并单独检查三类第三类闭合。
公开 ``--check`` 只读取本目录文件；原件重算由 runs/run-319/independent_raw.py
另行完成，避免把公开包变成逐人资料容器。
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "research/ces-policy-calibration-2026-09-09"
MAP = (0, 0, 0, 1, 2, 2, 2, 3)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid(q):
    if not isinstance(q, list) or len(q) != 4:
        raise ValueError("概率维数必须为4")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in q):
        raise ValueError("概率必须是有限数")
    if any(x < 0 or x > 1 for x in q) or abs(math.fsum(q) - 1.0) > 1e-12:
        raise ValueError("概率约束失败")
    return q


def score(q, y, baseline):
    q = valid(q)
    if y not in range(4) or baseline not in range(4):
        raise ValueError("类别维数失败")
    changed = y != baseline
    mass = math.fsum(q[k] for k in range(4) if k != baseline) if changed else q[baseline]
    if mass <= 0 or (q[y] if changed else q[baseline]) <= 0:
        raise ValueError("零支持")
    event = math.log(mass)
    dest = math.log(q[y] / mass) if changed else 0.0
    full_direct = math.log(q[y])
    assert abs(event + dest - full_direct) <= 1e-12
    binary = ((1.0 - q[baseline]) - float(changed)) ** 2
    multiclass = math.fsum((q[k] - float(k == y)) ** 2 for k in range(4))
    return event, dest, full_direct, binary, multiclass


def three(q, early, baseline, y):
    q = valid(q)
    p = (q[early], q[baseline], math.fsum(q[k] for k in range(4) if k not in (early, baseline)))
    target = 0 if y == early else 1 if y == baseline else 2
    if p[target] <= 0:
        raise ValueError("三类目标零支持")
    coarse_log = math.log(p[target])
    full = coarse_log
    internal = None
    if target == 2:
        if q[y] <= 0:
            raise ValueError("第三类内部零支持")
        internal = math.log(q[y] / p[2])
        full = coarse_log + internal
        assert abs(full - math.log(q[y])) <= 1e-12
    return full, internal, coarse_log


def independent():
    data = read(HERE / "joint-counts.json")
    decomp = read(HERE / "decomposition.json")
    hist_path = HERE / "history-nested.json"
    if not hist_path.exists():
        hist_path = OLD / "history-nested.json"
    hist = read(hist_path)
    raw = data.get("raw8_fold_counts")
    assert isinstance(raw, list) and len(raw) == 5 and all(isinstance(x, list) and len(x) == 512 for x in raw)
    assert sum(sum(x) for x in raw) == data.get("n") == 6175
    total = {k: 0.0 for k in ("old_event", "new_event", "old_dest", "new_dest", "old_full", "new_full")}
    three_sum = {k: 0.0 for k in ("old_full", "new_full", "old_internal", "new_internal")}
    n = 0
    changed = 0
    early_changed = 0
    third = 0
    max_closure = 0.0
    for fold, counts in enumerate(raw):
        parent = hist["folds"][fold]["parent"]
        child = hist["folds"][fold]["child"]
        assert len(parent) == 8 and len(child) == 4 and all(len(q) == 4 for q in parent)
        assert all(len(row) == 8 and all(len(q) == 4 for q in row) for row in child)
        for q in parent:
            valid(q)
        for row in child:
            for q in row:
                valid(q)
        for index, count in enumerate(counts):
            if not count:
                continue
            a_raw, b_raw, c_raw = (index // 64 + 1, (index // 8) % 8 + 1, index % 8 + 1)
            a, b, y = MAP[a_raw - 1], MAP[b_raw - 1], MAP[c_raw - 1]
            old = score(parent[b_raw - 1], y, b)
            new = score(child[a][b_raw - 1], y, b)
            max_closure = max(max_closure, abs(old[0] + old[1] - old[2]), abs(new[0] + new[1] - new[2]))
            assert max_closure < 1e-12
            for name, value in zip(("old_event", "old_dest", "old_full"), old): total[name] += count * value
            for name, value in zip(("new_event", "new_dest", "new_full"), new): total[name] += count * value
            total.setdefault("old_binary", 0.0); total.setdefault("new_binary", 0.0); total.setdefault("old_multi", 0.0); total.setdefault("new_multi", 0.0)
            total["old_binary"] += count * old[3]; total["new_binary"] += count * new[3]
            total["old_multi"] += count * old[4]; total["new_multi"] += count * new[4]
            n += count
            changed += count * (y != b)
            if a != b:
                early_changed += count
                old3 = three(parent[b_raw - 1], a, b, y)
                new3 = three(child[a][b_raw - 1], a, b, y)
                three_sum["old_full"] += count * old3[0]; three_sum["new_full"] += count * new3[0]
                if old3[1] is not None and new3[1] is not None:
                    three_sum["old_internal"] += count * old3[1]; three_sum["new_internal"] += count * new3[1]
                third += count * (y not in (a, b))
    assert n == 6175 and changed == 414 and early_changed == 590 and third == 40
    ref = decomp["score_components"]["all6175"]
    delta = (total["new_full"] - total["old_full"]) / n
    assert abs(delta - ref["delta_full_log_mean"]) < 1e-10
    assert abs((total["new_event"] - total["old_event"]) / n - ref["delta_event_log_mean"]) < 1e-10
    assert abs((total["new_dest"] - total["old_dest"]) / n - ref["delta_dest_log_mean"]) < 1e-10
    assert abs((total["new_binary"] - total["old_binary"]) / n - ref["delta_binary_brier_mean"]) < 1e-10
    assert abs((total["new_multi"] - total["old_multi"]) / n - ref["delta_multiclass_brier_mean"]) < 1e-10
    e3 = decomp["early_changed_threeway"]["early_diff590"]
    assert abs((three_sum["new_full"] - three_sum["old_full"]) / early_changed - e3["delta_full_log_mean"]) < 1e-10
    challenger_checks = challenger_check(data, hist, read(HERE / "challenger.json")) if (HERE / "challenger.json").exists() else 0
    return {"passed": True, "checks": n + 5 * 512 + 3, "challenger_checks": challenger_checks, "n": n, "changed": changed, "early_changed": early_changed, "third": third, "max_closure_error": max_closure, "no_production_import": True}


def challenger_check(data, hist, challenger):
    """用其余四折计数重建 q_new，逐折比较挑战者的五项总分。"""
    by_fold = [dict() for _ in range(5)]
    for row in data["rows"]:
        a = MAP[row["PID20raw"] - 1]; braw = row["PID22raw"]; y = MAP[row["PID24raw"] - 1]
        feat = (a, braw, row["policy20"], row["policy22"])
        for f, count in enumerate(row["fold_counts"]):
            if count: by_fold[f][(feat, y)] = by_fold[f].get((feat, y), 0) + count
    keys = ("full_log", "event_log", "dest_log", "multiclass_brier", "binary_brier")
    checks = 0; overall = {k: 0.0 for k in keys}; total_n = 0; changed_n = 0
    paths = {}; groups = {g: {"n": 0, "score": {k: 0.0 for k in keys}} for g in ("stable", "return", "nonreturn_change")}
    for f, test in enumerate(by_fold):
        train = {}
        for g, counts in enumerate(by_fold):
            if g != f:
                for key, count in counts.items(): train[key] = train.get(key, 0) + count
        cells = {}
        for feat, _y in set(test) | set(train):
            a, braw, _p20, _p22 = feat; counts = [train.get((feat, k), 0) for k in range(4)]; cell_n = sum(counts)
            base = hist["folds"][f]["child"][a][braw - 1]
            q = [(counts[k] + 20 * base[k]) / (cell_n + 20) for k in range(4)] if cell_n else list(base)
            valid(q); cells[feat] = q
        sums = {k: 0.0 for k in keys}; n = 0
        for (feat, y), count in test.items():
            _a, braw, _p20, _p22 = feat; b = MAP[braw - 1]; s = score(cells[feat], y, b); n += count
            for k, value in zip(keys, (s[2], s[0], s[1], s[4], s[3])): sums[k] += count * value
            for k, value in zip(keys, (s[2], s[0], s[1], s[4], s[3])): overall[k] += count * value
            total_n += count; changed_n += count * int(y != b)
            pa = feat[0]; path_key = (pa, b, y); z = paths.setdefault(path_key, {"n": 0, "score": {k: 0.0 for k in keys}}); z["n"] += count
            for k, value in zip(keys, (s[2], s[0], s[1], s[4], s[3])): z["score"][k] += count * value
        result_fold = challenger["folds"][f]
        assert result_fold["test_n"] == n
        for k in keys: assert abs(result_fold["scores"][k] - sums[k]) < 1e-9, (f, k)
        checks += len(test) * len(keys)
    assert challenger.get("n") == total_n == 6175 and len(challenger.get("folds", [])) == 5
    assert challenger.get("changed_n") == changed_n == 414
    for k in keys:
        assert abs(challenger["mean_scores"][k] - overall[k] / total_n) < 1e-12
    assert abs(challenger["conditional_changed_means"]["dest_log"] - overall["dest_log"] / changed_n) < 1e-12
    reported_paths = {tuple(x["PID4_path"]): x for x in challenger["path_scores"]}
    assert set(reported_paths) == set(paths)
    for key, value in paths.items():
        row = reported_paths[key]; assert row["n"] == value["n"]
        for k in keys: assert abs(row["score"][k] - value["score"][k]) < 1e-9
        group = "stable" if key[0] == key[1] == key[2] else "return" if key[0] == key[2] else "nonreturn_change"
        groups[group]["n"] += value["n"]
        for k in keys: groups[group]["score"][k] += value["score"][k]
    for group, value in groups.items():
        row = challenger["group_scores"][group]; assert row["n"] == value["n"]
        for k in keys: assert abs(row["score"][k] - value["score"][k]) < 1e-9
    return checks


def fixtures():
    assert abs(score([0.2, 0.3, 0.4, 0.1], 2, 0)[2] - math.log(0.4)) < 1e-12
    assert abs(score([0.2, 0.3, 0.4, 0.1], 0, 0)[3] - 0.8 ** 2) < 1e-12
    assert abs(three([0.2, 0.3, 0.4, 0.1], 0, 1, 3)[0] - math.log(0.1)) < 1e-12
    for bad in ([.5, .5, 0], [1.0, 0, 0, 0]):
        try:
            score(bad, 0 if len(bad) == 3 else 1, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("错误维数/零支持反例未拒绝")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true")
    args = ap.parse_args(); fixtures(); result = independent(); print(json.dumps(result, ensure_ascii=False))
    if not args.check:
        (HERE / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
