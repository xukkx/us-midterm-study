"""LH268 单一 raw8×政策 R1 敏感性。

R1 只使用 2020/22/24 政策完整的匿名联合格。每个
H=(PID20raw, policy20) 层固定三类 PID4 路径边际与 W=(policy22,policy24)
四类联合边际，置换仅在层内进行。99999 次和随机种子由 analysis-plan 冻结。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import random
from pathlib import Path
from project_raw import check_anonymous

HERE = Path(__file__).resolve().parent
PLAN = HERE / "analysis-plan.json"
GRID = HERE / "joint-counts.json"
GATE = HERE / "stage1-gate.json"
DRAW_COUNT = 99999
SEED = 26820260909
MAP = [0, 0, 0, 1, 2, 2, 2, 3]
GROUPS = ("stable", "return", "nonreturn_change")
W_CATEGORIES = tuple(itertools.product((1, 2), repeat=2))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def quantiles(values):
    ordered = sorted(values)
    return {str(q): ordered[int(q * (len(ordered) - 1))] for q in (0, .025, .25, .5, .75, .95, .975, .99, 1.)}


def distribution(values):
    mean = math.fsum(values) / len(values)
    sd = math.sqrt(math.fsum((x - mean) ** 2 for x in values) / (len(values) - 1))
    return {"mean": mean, "sd": sd, "quantiles": quantiles(values)}


def wilson(hits, draws):
    z = 1.959963984540054
    p = hits / draws
    den = 1 + z * z / draws
    center = (p + z * z / (2 * draws)) / den
    half = z * math.sqrt(p * (1 - p) / draws + z * z / (4 * draws * draws)) / den
    return [max(0., center - half), min(1., center + half)]


def tail(hits, draws):
    return {"hits": hits, "B": draws, "p_plus_one": (hits + 1) / (draws + 1),
            "MC_se": math.sqrt((hits / draws) * (1 - hits / draws) / draws),
            "MC_Wilson95": wilson(hits, draws)}


def margins(table):
    return [sum(row) for row in table], [sum(row[j] for row in table) for j in range(len(table[0]))]


class FixedMargins:
    def __init__(self, table):
        self.rows, self.cols = margins(table)
        self.n = sum(self.rows)
        self.order = sorted(range(len(self.rows)), key=self.rows.__getitem__)
        self.major = self.order[-1]
        self.drawn = self.n - self.rows[self.major]
        self.cuts = list(itertools.accumulate(self.cols))
        self.expected = [[r * c / self.n if self.n else 0. for c in self.cols] for r in self.rows]
        self.logn = [x * math.log(x) if x else 0. for x in range(self.n + 1)]
        self.constant = self.logn[self.n] - sum(self.logn[x] for x in self.rows + self.cols)

    def draw(self, rng):
        table = [[0] * len(self.cols) for _ in self.rows]
        sampled = rng.sample(range(self.n), self.drawn)
        start = 0
        for group in self.order[:-1]:
            end = start + self.rows[group]
            for i in sampled[start:end]:
                table[group][__import__("bisect").bisect_right(self.cuts, i)] += 1
            start = end
        for col, count in enumerate(self.cols):
            table[self.major][col] = count - sum(table[g][col] for g in self.order[:-1])
        return table

    def stats(self, table):
        mi = sum(self.logn[n] for row in table for n in row) + self.constant
        tv = sum(abs(n - e) for row, expected in zip(table, self.expected) for n, e in zip(row, expected)) / 2
        return mi, tv


def gate_ok():
    """验证 stage1-gate 的文件哈希，缺门或错门均拒绝进入实证。"""
    if not GATE.exists():
        raise RuntimeError("stage1-gate.json 尚未完成；按合同拒绝 R1 实证")
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    if gate.get("scoring_gate_passed") is not True:
        raise RuntimeError("stage1-gate 未通过")
    if gate.get("research") != "LH268" or gate.get("contract") != "LH-302" or gate.get("run") != 319:
        raise RuntimeError("stage1-gate 合同身份不符")
    if str(gate.get("plan_sha256", "")).lower() != sha(PLAN).lower():
        raise RuntimeError("stage1-gate 的 analysis-plan 哈希不符")
    expected = gate.get("artifact_sha256")
    if not isinstance(expected, dict):
        raise RuntimeError("stage1-gate 缺少前三表/分解表哈希")
    required = {"known-history.csv", "score-components.csv", "future-paths.csv", "decomposition.json"}
    if set(expected) != required:
        raise RuntimeError("stage1-gate 必须精确绑定前三表及 decomposition")
    checked = {}
    for name, expected_sha in expected.items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise RuntimeError("stage1-gate 路径越界")
        path = HERE / name
        if not path.is_file() or sha(path).lower() != str(expected_sha).lower():
            raise RuntimeError("stage1-gate 文件哈希不匹配: " + name)
        checked[name] = sha(path)
    for section, base in (("implementation_sha256", HERE), ("probability_input_sha256", HERE if (HERE / "lh266-joint-trajectories.json").exists() else HERE.parent / "ces-policy-calibration-2026-09-09")):
        declared = gate.get(section)
        if not isinstance(declared, dict):
            raise RuntimeError("stage1-gate 缺少 " + section)
        for name, expected_sha in declared.items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise RuntimeError("stage1-gate 路径越界")
            # stage1-gate 的历史基线键沿用旧登记的下划线拼写；磁盘文件名为连字符。
            disk_name = "history-nested.json" if section == "probability_input_sha256" and name == "history_nested.json" else name
            path = base / disk_name
            if not path.is_file() or sha(path).lower() != str(expected_sha).lower():
                raise RuntimeError(f"stage1-gate {section} 哈希不匹配: {name}")
            checked[f"{section}:{name}"] = sha(path)
    return {"status": gate.get("status", "passed"), "artifacts": checked, "gate_sha256": sha(GATE)}


def strata_csv_bytes(result):
    import io
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["PID20raw", "policy20", "stable", "return", "nonreturn_change", "W11", "W12", "W21", "W22", "zero_rows", "zero_W_cells"])
    for row in result["layers"]:
        writer.writerow([row["PID20raw"], row["policy20"], *[sum(row["table"][g]) for g in range(3)], *[sum(row["table"][g][j] for g in range(3)) for j in range(4)], row["zero_rows"], row["zero_W_cells"]])
    return buf.getvalue().encode("utf-8")


def verify_result(result, expected):
    """完整重算验收；结果内容或输入封印任一变化都失败。"""
    for key in ("schema", "H", "W", "groups", "complete_n", "layer_n", "layers", "draws", "seed", "statistics", "diagnostics"):
        if result.get(key) != expected.get(key):
            raise ValueError("R1结果重算不一致: " + key)
    if result.get("plan_sha256") != sha(PLAN):
        raise ValueError("R1 plan_sha256 不一致")
    if result.get("grid_sha256") != sha(GRID):
        raise ValueError("R1 grid_sha256 不一致")


def build_strata(data):
    strata = {}
    for row in data["rows"]:
        if 0 in (row["policy20"], row["policy22"], row["policy24"]):
            continue
        y = tuple(MAP[row[f"PID{wave}raw"] - 1] for wave in ("20", "22", "24"))
        group = 0 if y[0] == y[1] == y[2] else 1 if y[0] == y[2] else 2
        h = (row["PID20raw"], row["policy20"])
        w = (row["policy22"], row["policy24"])
        key = (h, w)
        if key not in strata:
            strata[key] = [[0] * 4 for _ in range(3)]
        strata[key][group][W_CATEGORIES.index(w)] += row["n"]
    rows = []
    for h in sorted({k[0] for k in strata}):
        table = [[0] * 4 for _ in range(3)]
        for (hh, _w), value in strata.items():
            if hh == h:
                for i in range(3):
                    for j in range(4):
                        table[i][j] += value[i][j]
        if sum(map(sum, table)):
            rows.append({"PID20raw": h[0], "policy20": h[1], "table": table})
    return rows


def calculate(rows, draws=DRAW_COUNT, seed=SEED):
    refs = [FixedMargins(row["table"]) for row in rows]
    total = sum(ref.n for ref in refs)
    observed_mi = sum(ref.stats(row["table"])[0] for ref, row in zip(refs, rows)) / total
    observed_tv = sum(ref.stats(row["table"])[1] for ref, row in zip(refs, rows)) / total
    rng = random.Random(seed)
    null_mi, null_tv = [], []
    hits_mi = hits_tv = 0
    for _ in range(draws):
        mi = tv = 0.
        for ref in refs:
            x, y = ref.stats(ref.draw(rng))
            mi += x; tv += y
        mi /= total; tv /= total
        null_mi.append(mi); null_tv.append(tv)
        hits_mi += mi >= observed_mi - 1e-12
        hits_tv += tv >= observed_tv - 1e-12
    layers = []
    for row, ref in zip(rows, refs):
        row = dict(row)
        row["n"] = ref.n
        row["row_margins"] = ref.rows
        row["W_margins"] = ref.cols
        row["zero_rows"] = sum(x == 0 for x in ref.rows)
        row["zero_W_cells"] = sum(x == 0 for x in ref.cols)
        layers.append(row)
    return {
        "schema": "LH268-r1-sensitivity-v1", "H": "(PID20raw,policy20)",
        "W": "(policy22,policy24)", "groups": list(GROUPS),
        "complete_n": total, "layer_n": len(layers), "layers": layers,
        "draws": draws, "seed": seed,
        "statistics": {
            "MI": {"observed": observed_mi, "null": distribution(null_mi), **tail(hits_mi, draws)},
            "TV": {"observed": observed_tv, "null": distribution(null_tv), **tail(hits_tv, draws)},
        },
        "diagnostics": {
            "sparse_layers": sum(1 for row in layers if row["zero_rows"] or row["zero_W_cells"]),
            "zero_group_layers": sum(1 for row in layers if row["zero_rows"]),
            "zero_W_margin_layers": sum(1 for row in layers if row["zero_W_cells"]),
        },
        "uncertainty_scope": "仅置换 Monte Carlo 尾计数误差，不是科学效应区间；五折不是独立全国区间。",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="门控后执行99999次置换并写出结果")
    ap.add_argument("--check", action="store_true", help="只验证已生成的匿名结果")
    args = ap.parse_args()
    out = HERE / "r1-sensitivity.json"
    if args.check:
        result = json.loads(out.read_text(encoding="utf-8"))
        if result.get("schema") != "LH268-r1-sensitivity-v1" or result.get("draws") != DRAW_COUNT or result.get("seed") != SEED:
            raise SystemExit("R1结果封印不符")
        gate = gate_ok()
        if result.get("gate", {}).get("gate_sha256") != gate["gate_sha256"]:
            raise SystemExit("R1结果对应的 stage1-gate 已变化，需重新运行")
        data = json.loads(GRID.read_text(encoding="utf-8")); check_anonymous(data)
        expected = calculate(build_strata(data)); verify_result(result, expected)
        csv_path = HERE / "r1-strata.csv"
        if not csv_path.is_file() or csv_path.read_bytes() != strata_csv_bytes(expected):
            raise SystemExit("r1-strata.csv 与重算字节不一致")
        print(json.dumps({"complete_n": result["complete_n"], "layer_n": result["layer_n"], "draws": result["draws"]}, ensure_ascii=False)); return
    if not args.run:
        ap.error("需要 --run 或 --check")
    gate = gate_ok()
    data = json.loads(GRID.read_text(encoding="utf-8")); check_anonymous(data)
    result = calculate(build_strata(data))
    result["gate"] = gate
    result["plan_sha256"] = sha(PLAN)
    result["grid_sha256"] = sha(GRID)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "r1-strata.csv").write_bytes(strata_csv_bytes(result))
    print(json.dumps({"complete_n": result["complete_n"], "layer_n": result["layer_n"], "draws": result["draws"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
