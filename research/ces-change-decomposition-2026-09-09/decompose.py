"""LH268 第一阶段：冻结 raw8 折外评分分解与三张 CSV 表。"""
import csv
import hashlib
import itertools
import json
import math
import tempfile
from pathlib import Path

from scoring import score_pair


HERE = Path(__file__).parent
OLD = HERE.parent / "ces-policy-calibration-2026-09-09"
FROZEN = HERE if (HERE / "history-nested.json").exists() else OLD
SEQ = list(itertools.product(range(8), repeat=3))
MAP = [0, 0, 0, 1, 2, 2, 2, 3]
N = 6175
GROUP_ORDER = ["early_same_stable", "early_same_changed", "early_diff_return", "early_diff_keep", "early_diff_third"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(x):
    return x is None or (isinstance(x, (int, float)) and math.isfinite(x))


def add(d, key, n, value):
    z = d.setdefault(key, {"n": 0, "total": 0.0})
    z["n"] += n
    z["total"] += n * value


def group(a, b, c):
    if a == b == c:
        return "early_same_stable"
    if a == b:
        return "early_same_changed"
    if a == c:
        return "early_diff_return"
    if b == c:
        return "early_diff_keep"
    return "early_diff_third"


def load_frozen():
    src = json.loads((FROZEN / "lh266-joint-trajectories.json").read_bytes())
    hist = json.loads((FROZEN / "history-nested.json").read_bytes())
    if src["n"] != N or len(src["raw8_fold_counts"]) != 5 or any(len(x) != 512 for x in src["raw8_fold_counts"]):
        raise ValueError("raw8折外输入维度不符")
    if hist["n"] != N or len(hist["folds"]) != 5:
        raise ValueError("冻结history-nested维度不符")
    return src, hist


def row_metrics(acc):
    out = {"n": acc["n"]}
    for k, v in acc.items():
        if k == "n":
            continue
        out[k + "_total"] = v
        out[k + "_mean"] = v / acc["n"] if acc["n"] else None
    return out


def build():
    src, hist = load_frozen()
    known = {"early_same": {"n": 0}, "early_diff": {"n": 0}}
    comps = {"all6175": {"n": 0}, "changed414": {"n": 0}}
    groups = {g: {"n": 0} for g in GROUP_ORDER}
    early3 = {"early_diff590": {"n": 0}, "third40": {"n": 0}}
    values = ("full_log", "event_log", "dest_log", "multiclass_brier", "binary_brier")
    for k in values:
        for d in (known["early_same"], known["early_diff"], comps["all6175"], comps["changed414"]):
            d.setdefault("old_" + k, 0.0); d.setdefault("new_" + k, 0.0); d.setdefault("delta_" + k, 0.0)
        for d in groups.values():
            d.setdefault("old_" + k, 0.0); d.setdefault("new_" + k, 0.0); d.setdefault("delta_" + k, 0.0)
    for d in early3.values():
        for k in ("full_log", "coarse_log", "brier", "third_internal_log"):
            d.setdefault("old_" + k, 0.0); d.setdefault("new_" + k, 0.0); d.setdefault("delta_" + k, 0.0)
    for fold, test in enumerate(src["raw8_fold_counts"]):
        f = hist["folds"][fold]
        parent, child = f["parent"], f["child"]
        if len(parent) != 8 or len(child) != 4 or any(len(row) != 4 for row in parent):
            raise ValueError("冻结概率维度不符")
        for (ar, br, cr), n in zip(SEQ, test):
            if not n:
                continue
            a, b, c = MAP[ar], MAP[br], MAP[cr]
            r = score_pair(parent[br], child[a][br], c, b, a)
            key = "early_same" if a == b else "early_diff"
            g = group(a, b, c)
            known[key]["n"] += n; groups[g]["n"] += n; comps["all6175"]["n"] += n
            if c != b:
                comps["changed414"]["n"] += n
            for metric in values:
                for prefix, obj in (("old_", r["old"]), ("new_", r["new"]), ("delta_", r["delta"])):
                    known[key][prefix + metric] += n * obj[metric]
                    groups[g][prefix + metric] += n * obj[metric]
                    comps["all6175"][prefix + metric] += n * obj[metric]
                    if c != b:
                        comps["changed414"][prefix + metric] += n * obj[metric]
            if a != b:
                early3["early_diff590"]["n"] += n
                for label, objkey in (("old_", "old_threeway"), ("new_", "new_threeway")):
                    obj = r[objkey]
                    early3["early_diff590"][label + "full_log"] += n * obj["full_log"]
                    early3["early_diff590"][label + "coarse_log"] += n * obj["coarse_log"]
                    early3["early_diff590"][label + "brier"] += n * obj["brier"]
                    early3["early_diff590"][label + "third_internal_log"] += n * (obj["third_internal_log"] or 0.0)
                for metric in ("full_log", "coarse_log", "brier", "third_internal_log"):
                    oldv = r["old_threeway"][metric] or 0.0; newv = r["new_threeway"][metric] or 0.0
                    early3["early_diff590"]["delta_" + metric] += n * (newv - oldv)
                    if c not in (a, b):
                        early3["third40"]["old_" + metric] += n * oldv
                        early3["third40"]["new_" + metric] += n * newv
                        early3["third40"]["delta_" + metric] += n * (newv - oldv)
                if c not in (a, b):
                    early3["third40"]["n"] += n
    if sum(x["n"] for x in groups.values()) != N or known["early_same"]["n"] != 5585 or known["early_diff"]["n"] != 590:
        raise ValueError("人数验收失败")
    if comps["changed414"]["n"] != 414:
        raise ValueError("changed414人数验收失败")
    expected = {"early_same_stable": 5348, "early_same_changed": 237, "early_diff_return": 137, "early_diff_keep": 413, "early_diff_third": 40}
    if {k: v["n"] for k, v in groups.items()} != expected:
        raise ValueError("五组人数验收失败")
    return src, hist, known, comps, groups, early3


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def emit(outdir=HERE):
    src, hist, known, comps, groups, early3 = build()
    known_rows = []
    for key in ("early_same", "early_diff"):
        d = known[key]; row = {"early_history": key, "n": d["n"]}
        for metric in ("full_log", "event_log", "dest_log", "multiclass_brier", "binary_brier"):
            for prefix in ("old_", "new_", "delta_"):
                row[prefix + metric + "_total"] = d[prefix + metric]
                row[prefix + metric + "_mean"] = d[prefix + metric] / d["n"]
        known_rows.append(row)
    kfields = list(known_rows[0].keys())
    outdir.mkdir(parents=True, exist_ok=True)
    write_csv(outdir / "known-history.csv", known_rows, kfields)
    comp_rows = []
    for name in ("all6175", "changed414"):
        d = comps[name]; row = {"subset": name, "n": d["n"]}
        for metric in ("event_log", "dest_log", "full_log", "binary_brier", "multiclass_brier"):
            for prefix in ("old_", "new_", "delta_"):
                row[prefix + metric + "_total"] = d[prefix + metric]
                row[prefix + metric + "_mean"] = d[prefix + metric] / d["n"]
        comp_rows.append(row)
    write_csv(outdir / "score-components.csv", comp_rows, list(comp_rows[0].keys()))
    path_rows = []
    for name in GROUP_ORDER:
        d = groups[name]; row = {"future_group": name, "n": d["n"]}
        for metric in ("full_log", "event_log", "dest_log", "binary_brier", "multiclass_brier"):
            for prefix in ("old_", "new_", "delta_"):
                row[prefix + metric + "_total"] = d[prefix + metric]
                row[prefix + metric + "_mean"] = d[prefix + metric] / d["n"]
                row[prefix + metric + "_cohort_contribution"] = d[prefix + metric] / N
        path_rows.append(row)
    write_csv(outdir / "future-paths.csv", path_rows, list(path_rows[0].keys()))
    decomposition = {
        "research": "LH268", "contract": "LH-302", "run": 319, "n": N,
        "score_direction": {"log": "越高越好", "brier": "越低越好", "delta": "新-旧"},
        "component_rules": {"log": "event_log+dest_log=full_log；三类third为coarse_log+third_internal_log=full_log",
                            "brier": "binary_brier与multiclass_brier分别报告，不宣称可加闭合",
                            "third_internal_absent": "非third目标条件项记0总贡献；逐格接口返回None"},
        "map_raw8_to_pid4": MAP, "sequence": "itertools.product(range(8),repeat=3)",
        "known_history": {k: row_metrics(v) for k, v in known.items()},
        "score_components": {k: row_metrics(v) for k, v in comps.items()},
        "future_paths": {k: row_metrics(v) for k, v in groups.items()},
        "early_changed_threeway": {k: row_metrics(v) for k, v in early3.items()},
        "checks": {"old_full_mean": sum(hist["folds"][i]["logscore_sum"][0] for i in range(5)) / N,
                   "expected_old_full_mean": -0.24906643271519427,
                   "expected_full_delta_mean": 0.008199913491846539},
        "probability_inputs": {"history_nested": sha(FROZEN / "history-nested.json"), "raw8_fold_counts_source": sha(FROZEN / "lh266-joint-trajectories.json")},
        "plan_sha256": sha(HERE / "analysis-plan.json"),
    }
    (outdir / "decomposition.json").write_text(json.dumps(decomposition, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return decomposition


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--write", action="store_true"); p.add_argument("--check", action="store_true"); a = p.parse_args()
    if a.write:
        d = emit()
    elif a.check:
        with tempfile.TemporaryDirectory(prefix="lh268-score-check-") as temp:
            emit(Path(temp))
            names = ("known-history.csv", "score-components.csv", "future-paths.csv", "decomposition.json")
            for name in names:
                expected = (Path(temp) / name).read_bytes()
                actual_path = HERE / name
                if not actual_path.exists() or actual_path.read_bytes() != expected:
                    raise SystemExit("输出字节不匹配: " + name)
        d = build()
    else:
        d = build()
    print(json.dumps({"n": N, "known": {k: v["n"] for k, v in d[2].items()} if isinstance(d, tuple) else d["n"]}, ensure_ascii=False))
