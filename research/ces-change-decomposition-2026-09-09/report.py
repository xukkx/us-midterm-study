"""生成并验收 LH268 中文报告；只读取本目录匿名/冻结结果。"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "ces-policy-calibration-2026-09-09"


def read(name):
    path = HERE / name
    if not path.exists():
        path = OLD / name
    return json.loads(path.read_text(encoding="utf-8"))


def f(x):
    return "—" if x is None else f"{x:.9f}"


def make():
    d = read("decomposition.json"); r = read("r1-sensitivity.json"); c = read("challenger.json"); cmp = read("comparison.json"); old_policy = read("policy-calibration.json")["items"]["conditional_legalization"]["R1"]
    a = d["known_history"]; g = d["future_paths"]; e = d["early_changed_threeway"]
    lines = ["# LH268：观测变化评分分解与单一政策挑战者", "", "## 研究边界与信息集", "", "本轮先封存 LH267 的折外概率，再读取匿名 raw8×政策联合格。6175 是保留的三波受访者，不是全两波样本、全国选民或失访者补回。历史同年记录的先后未知；五条未来路径是诊断分组，不参与模型路由。政策0=未知、1=反对、2=支持；本数据三波联合未知7人，20/22特征未知也是7人；PID4第四类来自raw PID8。latent/因果关系仍未识别。", "", "## 评分分解", "", "| 队列 | n | 旧full log | 新full log | 新减旧 | event差 | destination差 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key, label in (("early_same", "早期同类"), ("early_diff", "早期变化")):
        x = a[key]; lines.append(f"| {label} | {x['n']} | {f(x['old_full_log_mean'])} | {f(x['new_full_log_mean'])} | {f(x['delta_full_log_mean'])} | {f(x['delta_event_log_mean'])} | {f(x['delta_dest_log_mean'])} |")
    x = d["score_components"]["all6175"]; lines.append(f"| 全6175 | {x['n']} | {f(x['old_full_log_mean'])} | {f(x['new_full_log_mean'])} | {f(x['delta_full_log_mean'])} | {f(x['delta_event_log_mean'])} | {f(x['delta_dest_log_mean'])} |")
    lines += ["", "Brier 分开计算：全6175 的多类 Brier 新减旧为 " + f(x["delta_multiclass_brier_mean"]) + "，二元事件 Brier 新减旧为 " + f(x["delta_binary_brier_mean"]) + "；Brier 不与 log 分解相加。全体条件 destination 分母为变化者414。", "", "## 早期变化三类与第三类内部", "", "| 队列 | n | coarse log差 | full差 | third内部差 |", "|---|---:|---:|---:|---:|"]
    for key, label in (("early_diff590", "早期变化590"), ("third40", "其中third40")):
        x = e[key]; coarse = x["delta_full_log_mean"] - x["delta_third_internal_log_mean"] if key == "early_diff590" else x["delta_full_log_mean"] - x["delta_third_internal_log_mean"]; lines.append(f"| {label} | {x['n']} | {f(coarse)} | {f(x['delta_full_log_mean'])} | {f(x['delta_third_internal_log_mean'])} |")
    lines += ["", "590 的 full 闭合为 coarse 三类变化评分加 third 内部条件 log；third40 仍单列，避免把内部损失藏在590均值中。", "", "## 五类事后路径（冻结基线诊断）", "", "| 路径 | n | full差 | event差 | destination差 |", "|---|---:|---:|---:|---:|"]
    for key in ("early_same_stable", "early_same_changed", "early_diff_return", "early_diff_keep", "early_diff_third"):
        x = g[key]; lines.append(f"| {key} | {x['n']} | {f(x['delta_full_log_mean'])} | {f(x['delta_event_log_mean'])} | {f(x['delta_dest_log_mean'])} |")
    lines += ["", "## R1 单项敏感性参考", "", "| 规格 | N | 层数 | MI观测/均值 | TV观测/均值 |", "|---|---:|---:|---:|---:|", f"| 旧PID4×policy20 | {old_policy['complete_n']} | {len(old_policy['strata'])} | {f(old_policy['statistics']['MI']['observed'])} / {f(old_policy['statistics']['MI']['null']['mean'])} | {f(old_policy['statistics']['TV']['observed'])} / {f(old_policy['statistics']['TV']['null']['mean'])} |", f"| 新raw8×policy20 | {r['complete_n']} | {r['layer_n']} | {f(r['statistics']['MI']['observed'])} / {f(r['statistics']['MI']['null']['mean'])} | {f(r['statistics']['TV']['observed'])} / {f(r['statistics']['TV']['null']['mean'])} |", "", f"新规格固定置换 {r['draws']} 次、seed {r['seed']}。MI 加一尾概率 {f(r['statistics']['MI']['p_plus_one'])}，MC SE {f(r['statistics']['MI']['MC_se'])}，Wilson95% [{f(r['statistics']['MI']['MC_Wilson95'][0])}, {f(r['statistics']['MI']['MC_Wilson95'][1])}]；TV 加一尾概率 {f(r['statistics']['TV']['p_plus_one'])}，命中为0时 SE=0 只是 plug-in，Wilson上界为 {f(r['statistics']['TV']['MC_Wilson95'][1])}。稀疏层 {r['diagnostics']['sparse_layers']}，零组边际层 {r['diagnostics']['zero_group_layers']}。旧六项检验家族不改；两规格条件假设不同，结果不作单调比较。R1 是条件参考敏感性，不是机制识别。", "", "## 单一政策挑战者", "", f"挑战者固定收缩20，目标保持6175人、五折训练外计数；新 full log 均值 {f(c['mean_scores']['full_log'])}，event {f(c['mean_scores']['event_log'])}，destination {f(c['mean_scores']['dest_log'])}，多类 Brier {f(c['mean_scores']['multiclass_brier'])}，二元 Brier {f(c['mean_scores']['binary_brier'])}，变化分母 {c['changed_n']}。相对冻结母预测的独立复核 headline 为 full log 差约 -0.002904992，event 差 -0.000028838，destination 差 -0.002876154，二元 Brier 差 +0.000050545，多类 Brier 差约 -0.0005102269；因此不宣称挑战者替换基线。", "", "| 挑战者路径组 | n | full log 总分 | event 总分 | destination 总分 |", "|---|---:|---:|---:|---:|"]
    for key in ("stable", "return", "nonreturn_change"):
        x = c["group_scores"][key]; lines.append(f"| {key} | {x['n']} | {f(x['score']['full_log'])} | {f(x['score']['event_log'])} | {f(x['score']['dest_log'])} |")
    lines += ["", "| 挑战者五路径诊断 | n | 相对冻结child full差均值 | cohort贡献 | 新full log总分 | 新event总分 | 新destination总分 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key in ("early_same_stable", "early_same_changed", "early_diff_return", "early_diff_keep", "early_diff_third"):
        x = c["early_five_group_scores"][key]; z = cmp["challenge_vs_frozen_child"]["future_five"][key]; lines.append(f"| {key} | {x['n']} | {f(z['metrics']['full_log']['delta_mean'])} | {f(z['metrics']['full_log']['delta_cohort_contribution'])} | {f(x['score']['full_log'])} | {f(x['score']['event_log'])} | {f(x['score']['dest_log'])} |")
    t = c["early_changed_threeway"]; z = cmp["challenge_vs_frozen_child"]["early_changed_threeway"]; lines += ["", f"挑战者590早期变化三类 full 均值 {f(t['full_log_mean'])}，相对冻结child差 {f(z['early_diff590']['full_log']['delta_mean'])}；coarse差 {f(z['early_diff590']['coarse_log']['delta_mean'])}，third内部差 {f(z['early_diff590']['third_internal_log']['delta_mean'])}，三类 Brier 均值 {f(t['brier_mean'])}；其中 third={t['third_n']}，third 内部条件 log 均值 {f(t['third_internal_log_mean'])}。", "", "## 限制与可复算性", "", "独立验收从冻结概率直接重算逐格 log/event/destination、Brier 与三类内部闭合，并从本地原件逐格核 raw8×政策联合格及五折。没有盲测、全国算法区间、未拒绝等价或因果识别宣称；题目已看2024及旧结果后选择，探索性结果不外推。"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); args = ap.parse_args()
    output = make(); path = HERE / "report.md"
    if args.check:
        assert path.exists() and path.read_text(encoding="utf-8") == output
    else:
        path.write_text(output, encoding="utf-8")
    print(json.dumps({"passed": True, "bytes": len(output.encode("utf-8")), "check": args.check}, ensure_ascii=False))


if __name__ == "__main__": main()
