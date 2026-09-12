import math
# 超几何分布概率质量函数
# N: 总体大小，K: 成功总数，n: 抽取数
# 返回支撑区间内各x的概率列表
def hypergeom_pmf(N, K, n):
    # 分母为总组合数
    d = math.comb(N, n)
    # 下界：抽样数减去失败总数与0取大
    a = max(0, n - (N - K))
    # 上界：抽样数与成功总数取小
    b = min(n, K)
    # 按公式逐点计算概率
    return [(x, math.comb(K, x) * math.comb(N - K, n - x) / d) for x in range(a, b + 1)]
# LH267_COMPLETE
