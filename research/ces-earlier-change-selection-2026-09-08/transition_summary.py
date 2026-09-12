# transition_summary.py
# 公开调查转移的描述性计数：只处理已匿名汇总格。
# 输入中没有受访者或实际统计；输出仅为计数与百分点差。
# 不计算置信区间、显著性、政治主体评分或预测。
import math

__all__ = ["summarize"]

_必填键 = ("before", "after", "n", "positive_n", "w", "w2")

def _是整数人数(x):
    """检查非负整数人数，排除布尔与浮点。"""
    return isinstance(x, int) and not isinstance(x, bool)

def _是合格权重(x):
    """检查非负有限权重，拒绝 NaN/无穷/负数/布尔。"""
    if isinstance(x, bool):
        return False
    if not isinstance(x, (int, float)):
        return False
    v = float(x)
    return math.isfinite(v) and v >= 0

def _校验单格(cell):
    """校验单个汇总格，返回标准化元组，失败即抛错。"""
    if not isinstance(cell, dict):
        raise TypeError("每格必须为 dict")
    for k in _必填键:
        if k not in cell:
            raise ValueError(f"缺失键：{k}")
    before = cell["before"]
    after = cell["after"]
    n = cell["n"]
    positive_n = cell["positive_n"]
    w = cell["w"]
    w2 = cell["w2"]
    if not isinstance(before, str) or not isinstance(after, str):
        raise TypeError("before/after 必须为 str")
    if not _是整数人数(n) or n < 0:
        raise ValueError("n 必须为非负整数")
    if not _是整数人数(positive_n) or positive_n < 0:
        raise ValueError("positive_n 必须为非负整数")
    if positive_n > n:
        raise ValueError("positive_n 不能大于 n")
    if not _是合格权重(w):
        raise ValueError("w 必须为非负有限数")
    if not _是合格权重(w2):
        raise ValueError("w2 必须为非负有限数")
    wf = float(w)
    w2f = float(w2)
    # 正权重人数与权重和的一致性：无正权重者则权重为零。
    if positive_n == 0:
        if wf != 0.0 or w2f != 0.0:
            raise ValueError("positive_n 为 0 时 w/w2 必须为 0")
    else:
        if wf <= 0.0 or w2f <= 0.0:
            raise ValueError("positive_n 为正时 w/w2 必须为正")
    # 非负权重下 w 与 w2 同为零或同为正。
    if (wf == 0.0) != (w2f == 0.0):
        raise ValueError("w 与 w2 必须同为零或同为正")
    # 监督补充：非负权重的二阶矩必须满足柯西界，防止有效n大于实际人数。
    if positive_n and (wf * wf > positive_n * w2f * (1 + 1e-10) or w2f > wf * wf * (1 + 1e-10)):
        raise ValueError("权重一二阶矩与正权重人数不一致")
    return (before, after, n, positive_n, wf, w2f)

def summarize(cells, allowed):
    """汇总合格转移格，返回描述性计数字典。"""
    # 校验集合类型：允许如 ['D','R'] 或 ['D','I','R']。
    if not isinstance(cells, (list, tuple)):
        raise TypeError("cells 必须为 list/tuple")
    if not isinstance(allowed, (list, tuple, set)):
        raise TypeError("allowed 必须为 list/tuple/set")
    allowed_set = set(allowed)
    if not allowed_set or any(not isinstance(s, str) for s in allowed_set):
        raise ValueError("allowed 必须为非空字符串集合")
    # 所有验证发生在筛选之前，不合格格也要拒绝。
    已验 = [_校验单格(c) for c in cells]
    # 只选择 before 与 after 都在 allowed 中的格。
    合格 = [t for t in 已验 if t[0] in allowed_set and t[1] in allowed_set]
    # 整数人数用求和，权重用 fsum 保持数值稳定。
    n = sum(t[2] for t in 合格)
    positive_n = sum(t[3] for t in 合格)
    w = math.fsum(t[4] for t in 合格)
    w2 = math.fsum(t[5] for t in 合格)
    n_eff = (w * w / w2) if w2 > 0 else None
    forward_n = sum(t[2] for t in 合格 if t[0] != "R" and t[1] == "R")
    reverse_n = sum(t[2] for t in 合格 if t[0] == "R" and t[1] != "R")
    changed_n = sum(t[2] for t in 合格 if t[0] != t[1])
    d_to_r_n = sum(t[2] for t in 合格 if t[0] == "D" and t[1] == "R")
    r_to_d_n = sum(t[2] for t in 合格 if t[0] == "R" and t[1] == "D")
    r0_n = sum(t[2] for t in 合格 if t[0] == "R")
    r1_n = sum(t[2] for t in 合格 if t[1] == "R")
    # 未加权净变化百分点：无分母时为 None。
    unweighted_delta_pp = ((r1_n - r0_n) / n * 100) if n > 0 else None
    # 加权净变化：每格 w*(I(后=R)-I(前=R)) 求和再除以 w。
    加权分子 = math.fsum(t[4] * ((1 if t[1] == "R" else 0) - (1 if t[0] == "R" else 0)) for t in 合格)
    weighted_delta_pp = (加权分子 / w * 100) if w > 0 else None
    # 额外描述量：加权前后占比、分母为零标记、稀疏标记。
    unweighted_r0_pp = (r0_n / n * 100) if n > 0 else None
    unweighted_r1_pp = (r1_n / n * 100) if n > 0 else None
    加权r0 = math.fsum(t[4] * (1 if t[0] == "R" else 0) for t in 合格)
    加权r1 = math.fsum(t[4] * (1 if t[1] == "R" else 0) for t in 合格)
    weighted_r0_pp = (加权r0 / w * 100) if w > 0 else None
    weighted_r1_pp = (加权r1 / w * 100) if w > 0 else None
    zero_denominator = (n == 0 or w == 0)
    sparse_transitions = (changed_n < 10)
    return {"n": n, "positive_n": positive_n, "w": w, "w2": w2, "n_eff": n_eff, "forward_n": forward_n, "reverse_n": reverse_n, "changed_n": changed_n, "d_to_r_n": d_to_r_n, "r_to_d_n": r_to_d_n, "r0_n": r0_n, "r1_n": r1_n, "unweighted_delta_pp": unweighted_delta_pp, "weighted_delta_pp": weighted_delta_pp, "unweighted_r0_pp": unweighted_r0_pp, "unweighted_r1_pp": unweighted_r1_pp, "weighted_r0_pp": weighted_r0_pp, "weighted_r1_pp": weighted_r1_pp, "zero_denominator": zero_denominator, "sparse_transitions": sparse_transitions}
