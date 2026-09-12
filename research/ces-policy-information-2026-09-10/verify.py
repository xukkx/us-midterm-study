"""LH269 勘误后的逐格匿名复算；只依赖包内 JSON 和标准库。"""
import argparse, hashlib, json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP = (0, 0, 0, 1, 2, 2, 2, 3)
N = 6175

def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

def valid(q):
    if not isinstance(q, list) or len(q) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in q):
        raise ValueError("概率维数或有限性失败")
    if any(x < 0 or x > 1 for x in q) or abs(math.fsum(q) - 1) > 1e-12:
        raise ValueError("概率边界失败")
    return q

def score(q, y, b):
    valid(q)
    if y not in range(4) or b not in range(4) or q[y] <= 0:
        raise ValueError("目标或零支持失败")
    changed = int(y != b); s = 1 - q[b] if changed else q[b]
    if s <= 0: raise ValueError("事件零支持失败")
    event = math.log(s); dest = math.log(q[y] / s) if changed else 0.0
    full = math.log(q[y]); assert abs(event + dest - full) < 1e-12
    return full, event, dest, ((1-q[b])-changed)**2, math.fsum((q[k]-int(k==y))**2 for k in range(4))

def independent():
    data, hist, decomp = load("joint-counts.json"), load("history-nested.json"), load("decomposition.json")
    raw = data["raw8_fold_counts"]
    if data.get("n") != N or len(raw) != 5 or any(len(x) != 512 for x in raw): raise ValueError("raw8 折计数不完整")
    totals = [0.0] * 5; n = changed = early = early_same_changed = early_diff_return = early_diff_keep = early_diff_third = 0
    max_err = 0.0
    for f, counts in enumerate(raw):
        parent, child = hist["folds"][f]["parent"], hist["folds"][f]["child"]
        for idx, count in enumerate(counts):
            if not count: continue
            a0, b0, y0 = idx//64, (idx//8)%8, idx%8; a,b,y = MAP[a0],MAP[b0],MAP[y0]
            old = score(parent[b0], y, b); new = score(child[a][b0], y, b)
            for k in range(5): totals[k] += count * (new[k] - old[k])
            n += count; changed += count * int(y != b)
            if a == b and y != b:
                early_same_changed += count
            elif a != b:
                early += count
                if y == b: early_diff_keep += count
                elif y == a: early_diff_return += count
                else: early_diff_third += count
            max_err = max(max_err, abs(old[1]+old[2]-old[0]), abs(new[1]+new[2]-new[0]))
    # 上述循环按互斥路径逐格累计，保持 early_diff_keep 与 changed414 分离。
    if (n, changed, early, early_same_changed, early_diff_return, early_diff_keep, early_diff_third) != (6175,414,590,237,137,413,40):
        raise ValueError("路径计数或 changed414 勘误闭合失败")
    ref = decomp["score_components"]["all6175"]
    keys = ("delta_full_log_mean","delta_event_log_mean","delta_dest_log_mean","delta_binary_brier_mean","delta_multiclass_brier_mean")
    vals = (totals[0]/n, totals[1]/n, totals[2]/n, totals[3]/n, totals[4]/n)
    for k,v in zip(keys,vals):
        if abs(v-ref[k]) > 1e-10: raise ValueError("逐格评分与冻结摘要不一致: "+k)
    protected = {}
    for name in ("joint-counts.json", "history-nested.json", "decomposition.json", "challenger.json", "comparison.json", "support-audit.json", "matched-test.json"):
        protected[name] = hashlib.sha256((HERE/name).read_bytes()).hexdigest()
    return {"passed":True,"n":n,"changed":changed,"early_changed":early,"changed_components":{"early_same_changed":early_same_changed,"early_diff_return":early_diff_return,"early_diff_third":early_diff_third},"excluded_early_diff_keep":early_diff_keep,"max_log_closure_error":max_err,"deltas":dict(zip(keys,vals)),"mapping_erratum":"changed414=237+137+40; early_diff_keep=413 excluded","protected_input_sha256":protected}

from independent_audit import audit as audit_artifacts

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--check",action="store_true"); args=ap.parse_args(); out=independent(); p=HERE/"verification.json"
    audit = audit_artifacts()
    out["producer_audit"] = audit
    if args.check:
        if not p.is_file() or json.loads(p.read_text(encoding="utf-8")) != out: raise SystemExit("verification.json 与逐格复算不一致（输入或结果已改变）")
    else: p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,sort_keys=True))
if __name__ == "__main__": main()
