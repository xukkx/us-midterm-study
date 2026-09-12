"""LH268 第一阶段冻结概率评分内核（仅 Python 标准库）。"""
import math


class ProbabilityError(ValueError):
    """概率向量不满足冻结维度或概率约束。"""


class ZeroSupportError(ProbabilityError):
    """实际结果在评分概率中没有支持。"""


def validate_probs(q, tol=1e-12):
    if not isinstance(q, (list, tuple)) or len(q) != 4:
        raise ProbabilityError("概率向量必须严格为长度4")
    vals = []
    for x in q:
        if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(float(x)):
            raise ProbabilityError("概率必须为有限数")
        x = float(x)
        if x < 0.0 or x > 1.0:
            raise ProbabilityError("概率必须在[0,1]")
        vals.append(x)
    if abs(math.fsum(vals) - 1.0) > tol:
        raise ProbabilityError("概率和必须为1")
    return vals


def score_one(q, y, b):
    """对一个未来类别 y 以 PID22 类别 b 为事件基准评分。

    log 为越高越好，Brier 为越低越好。零支持不加 floor，而是显式失败。
    """
    q = validate_probs(q)
    if y not in range(4) or b not in range(4):
        raise ProbabilityError("y和b必须属于0..3")
    changed = int(y != b)
    s = math.fsum(q[k] for k in range(4) if k != b)
    if changed:
        if s <= 0.0 or q[y] <= 0.0:
            raise ZeroSupportError("变化事件或目的地没有概率支持")
        event_log = math.log(s)
        dest_log = math.log(q[y] / s)
        binary_brier = (s - 1.0) ** 2
    else:
        if q[b] <= 0.0:
            raise ZeroSupportError("未变化结果没有概率支持")
        event_log = math.log(q[b])
        dest_log = 0.0
        binary_brier = s ** 2
    multiclass_brier = math.fsum((q[k] - int(k == y)) ** 2 for k in range(4))
    # 完整log独立计算；event+dest另作精确闭合核对。
    full_log = math.log(q[y])
    return {
        "changed": changed,
        "event_log": event_log,
        "dest_log": dest_log,
        "full_log": full_log,
        "full_log_from_components": event_log + dest_log,
        "binary_brier": binary_brier,
        "multiclass_brier": multiclass_brier,
        "event_probability": s if changed else q[b],
    }


def threeway(q, a, b, y):
    """早期 a!=b 时的 [return_baseline, keep_2022, third] 评分。"""
    q = validate_probs(q)
    if a == b or a not in range(4) or b not in range(4) or y not in range(4):
        raise ProbabilityError("三类评分要求a、b合法且a!=b")
    p = [q[a], q[b], math.fsum(q[k] for k in range(4) if k not in (a, b))]
    target = 0 if y == a else 1 if y == b else 2
    if p[target] <= 0.0:
        raise ZeroSupportError("三类评分目标没有概率支持")
    coarse_log = math.log(p[target])
    full_log = coarse_log
    third_internal_log = None
    if target == 2:
        # 保留 third 内部条件 log，并显式闭合 full。
        denom = p[2]
        if q[y] <= 0.0:
            raise ZeroSupportError("third 内部目的地没有概率支持")
        third_internal_log = math.log(q[y] / denom)
        full_log = coarse_log + third_internal_log
    brier = math.fsum((p[k] - int(k == target)) ** 2 for k in range(3))
    return {
        "target": target,
        "probabilities": p,
        "coarse_log": coarse_log,
        "full_log": full_log,
        "brier": brier,
        "third_internal_log": third_internal_log,
        "third_mass": p[2],
    }
