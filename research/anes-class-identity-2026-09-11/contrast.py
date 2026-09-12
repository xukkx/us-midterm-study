import math

def contrast(probabilities, weights):
    """
    计算共同固定标准化人群 S 上的加权对比度：
        sum_s w_s * (m11_s - m01_s - m10_s + m00_s)
    每行概率按 (m11, m01, m10, m00) 排列，weights 为各层权重。

    严格校验：
      - probabilities 与 weights 维度一致且非空；
      - 所有数值必须为有限数（拒绝 NaN / inf）；
      - 权重不得为负，权重总和不得为零；
      - 每个概率必须落在 [0, 1] 区间内。

    返回 float。不估计方差，不声称任何因果效应；
    真实概率由本地 survey 拟合；分包模型仅收到合成规范。
    """
    if not isinstance(probabilities, (list, tuple)) or not isinstance(weights, (list, tuple)):
        raise TypeError("probabilities 与 weights 必须为序列")
    if len(probabilities) == 0 or len(weights) == 0:
        raise ValueError("输入不能为空")
    if len(probabilities) != len(weights):
        raise ValueError("probabilities 与 weights 维度不一致")

    total = 0.0
    acc = 0.0
    for row, w in zip(probabilities, weights):
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            raise ValueError("每行必须恰好包含 4 个概率 (m11, m01, m10, m00)")
        wf = float(w)
        if not math.isfinite(wf):
            raise ValueError("权重必须为有限数")
        if wf < 0.0:
            raise ValueError("权重不得为负")
        vals = []
        for p in row:
            pf = float(p)
            if not math.isfinite(pf):
                raise ValueError("概率必须为有限数")
            if pf < 0.0 or pf > 1.0:
                raise ValueError("概率越界：必须位于 [0, 1]")
            vals.append(pf)
        m11, m01, m10, m00 = vals
        acc += wf * (m11 - m01 - m10 + m00)
        total += wf

    if total == 0.0:
        raise ValueError("权重总和为零")
    return float(acc / total)

# END
