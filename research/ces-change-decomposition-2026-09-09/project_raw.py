"""从本地 CES 原件投影 LH268 的匿名 raw8×政策联合格。

默认动作只读取受控本地原件，输出不含 caseid 或任何逐人字段。
``--check`` 只读取已经生成的匿名 joint-counts.json，便于公开复算，
不会打开私有 CSV。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / "midterm-model/data/raw/ces/panel-2020-2024/merged_recontact_2024_vv.csv"
RAW_SHA256 = "e9921d391159cf8fcb68a0b69aa76c94a5bf73436f516606bf3fb310125ba5ac"
PID_MAP = {1: 0, 2: 0, 3: 0, 4: 1, 5: 2, 6: 2, 7: 2, 8: 3}
POLICY_FIELDS = ("CC20_331a", "CC22_331a", "CC24_331a")
POLICY_CODES = {"unknown": 0, "oppose": 1, "support": 2}
FIELDS = (
    "caseid_20", "pid7_20", "pid7_22", "pid7_24",
    "CC20_331a", "CC22_331a", "CC24_331a",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def policy_code(value: str) -> int:
    """把 1=support、2=oppose、空/NA/NaN=unknown 编成 2/1/0。"""
    value = (value or "").strip().lower()
    if value in ("", "na", "nan", "null", "none", "__na__"):
        return 0
    if value == "1":
        return 2
    if value == "2":
        return 1
    raise ValueError("政策字段出现未声明编码: " + repr(value))


def pid_code(value: str) -> int:
    try:
        code = int(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError("PID7 出现非整数编码: " + repr(value)) from exc
    if code not in PID_MAP:
        raise ValueError("PID7 出现未声明编码: " + repr(value))
    return code


def fold_for(caseid_20: str) -> int:
    digest = hashlib.sha256(("LH265|" + caseid_20).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 5


def _new_cell() -> dict:
    return {"n": 0, "fold_counts": [0, 0, 0, 0, 0]}


def project(raw: Path = RAW) -> dict:
    if sha256(raw) != RAW_SHA256:
        raise AssertionError("原件 SHA256 不符合合同封印")
    cells: dict[tuple[int, int, int, int, int, int], dict] = defaultdict(_new_cell)
    raw8 = [0] * 512
    raw8_fold = [[0] * 512 for _ in range(5)]
    policy_margins = [[0] * 3 for _ in range(3)]
    pid4_policy = [[[0] * 3 for _ in range(4)] for _ in range(3)]
    n = 0
    unknown_policy = 0
    with raw.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("原件表头重复或缺失")
        missing = set(FIELDS) - set(reader.fieldnames)
        if missing:
            raise ValueError("原件缺失字段: " + repr(sorted(missing)))
        ids = set()
        for row in reader:
            if not row or any(k not in row for k in FIELDS):
                raise ValueError("原件存在短行或字段缺失")
            caseid = row["caseid_20"].strip()
            if not caseid or caseid in ids:
                raise ValueError("caseid_20 为空或重复")
            ids.add(caseid)
            pids = tuple(pid_code(row[f"pid7_{wave}"]) for wave in ("20", "22", "24"))
            policies = tuple(policy_code(row[field]) for field in POLICY_FIELDS)
            fold = fold_for(caseid)
            key = pids + policies
            cell = cells[key]
            cell["n"] += 1
            cell["fold_counts"][fold] += 1
            raw_index = 64 * (pids[0] - 1) + 8 * (pids[1] - 1) + (pids[2] - 1)
            raw8[raw_index] += 1
            raw8_fold[fold][raw_index] += 1
            for wave, policy in enumerate(policies):
                policy_margins[wave][policy] += 1
                pid4_policy[wave][PID_MAP[pids[wave]]][policy] += 1
            unknown_policy += int(0 in policies)
            n += 1
    if n != 6175 or len(ids) != 6175:
        raise AssertionError(f"目标唯一人数应为6175，实际 {n}/{len(ids)}")
    if sum(policy_margins[0][1:]) != 6169 or sum(policy_margins[1][1:]) != 6174:
        raise AssertionError("20/22政策完整人数未得到6169/6174")
    if unknown_policy != 7:
        raise AssertionError(f"三波政策联合未知人数应为7，实际 {unknown_policy}")
    rows = []
    for key in sorted(cells):
        p20, p22, p24, q20, q22, q24 = key
        cell = cells[key]
        rows.append({
            "PID20raw": p20, "PID22raw": p22, "PID24raw": p24,
            "policy20": q20, "policy22": q22, "policy24": q24,
            "n": cell["n"], "fold_counts": cell["fold_counts"],
        })
    assert sum(x["n"] for x in rows) == n
    assert all(sum(x["fold_counts"]) == x["n"] for x in rows)
    return {
        "schema": "LH268-joint-counts-v1",
        "n": n,
        "unknown_policy_n": unknown_policy,
        "complete_policy_n": n - unknown_policy,
        "pid_map_1_to_8": [PID_MAP[i] for i in range(1, 9)],
        "policy_codes": POLICY_CODES,
        "fold_rule": "int(SHA256(UTF8('LH265|'+caseid_20))[:16],16)%5",
        "rows": rows,
        "raw8_counts": raw8,
        "raw8_fold_counts": raw8_fold,
        "policy_margins": policy_margins,
        "pid4_policy_counts": pid4_policy,
        "source": {
            "path_role": "本地 CES 原件；只保存哈希，不外发原始行",
            "sha256": RAW_SHA256,
            "unique_caseid_20": len(ids),
            "fields": list(FIELDS[1:]),
        },
    }


def check_anonymous(data: dict) -> dict:
    """公开入口：只对匿名格做结构、和式及独立边际检查。"""
    if data.get("schema") != "LH268-joint-counts-v1":
        raise AssertionError("匿名格 schema 不符")
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise AssertionError("匿名格 rows 为空")
    fields = ("PID20raw", "PID22raw", "PID24raw", "policy20", "policy22", "policy24")
    seen = set()
    raw8 = [0] * 512
    raw8_fold = [[0] * 512 for _ in range(5)]
    pm = [[0] * 3 for _ in range(3)]
    p4 = [[[0] * 3 for _ in range(4)] for _ in range(3)]
    total = 0
    for row in rows:
        if set(row) != set(fields) | {"n", "fold_counts"}:
            raise AssertionError("匿名格字段集合不符")
        key = tuple(row[x] for x in fields)
        if key in seen or any(not isinstance(x, int) for x in key):
            raise AssertionError("匿名格键重复或非整数")
        if not (1 <= key[0] <= 8 and 1 <= key[1] <= 8 and 1 <= key[2] <= 8):
            raise AssertionError("raw PID 超出 1..8")
        if any(not 0 <= key[i] < 3 for i in range(3, 6)):
            raise AssertionError("政策编码超出 0..2")
        n = row["n"]
        fc = row["fold_counts"]
        if not isinstance(n, int) or n < 1 or not isinstance(fc, list) or len(fc) != 5:
            raise AssertionError("匿名格计数非法")
        if any(not isinstance(x, int) or x < 0 for x in fc) or sum(fc) != n:
            raise AssertionError("fold_counts 与 n 不闭合")
        seen.add(key)
        raw_index = 64 * (key[0] - 1) + 8 * (key[1] - 1) + (key[2] - 1)
        raw8[raw_index] += n
        for f in range(5): raw8_fold[f][raw_index] += fc[f]
        for wave, policy in enumerate(key[3:]):
            pm[wave][policy] += n
            p4[wave][PID_MAP[key[wave]]][policy] += n
        total += n
    if total != data.get("n") or total != 6175:
        raise AssertionError("匿名格总人数错误")
    if raw8 != data.get("raw8_counts") or raw8_fold != data.get("raw8_fold_counts"):
        raise AssertionError("匿名格与 raw8 边际不一致")
    if pm != data.get("policy_margins") or p4 != data.get("pid4_policy_counts"):
        raise AssertionError("匿名格与政策/PID4 边际不一致")
    if data.get("complete_policy_n") != 6168 or data.get("unknown_policy_n") != 7:
        raise AssertionError("完整/未知政策人数错误")
    if data.get("source", {}).get("sha256") != RAW_SHA256 or data.get("source", {}).get("unique_caseid_20") != 6175:
        raise AssertionError("匿名包原件封印元数据不符")
    return {"rows": len(rows), "n": total, "raw8_nonzero": sum(x > 0 for x in raw8)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只验证匿名 joint-counts.json，不读原件")
    ap.add_argument("--input", type=Path, default=HERE / "joint-counts.json")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    if args.check:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        print(json.dumps(check_anonymous(data), ensure_ascii=False))
        return
    data = project(args.root / "midterm-model/data/raw/ces/panel-2020-2024/merged_recontact_2024_vv.csv")
    (HERE / "joint-counts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": data["n"], "rows": len(data["rows"]), "complete_policy_n": data["complete_policy_n"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
