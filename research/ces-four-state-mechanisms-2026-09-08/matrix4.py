import math
# 固定4维矩阵工具
def matmul4(A, B):
    # 计算4x4矩阵积，内积用math.fsum求和
    return [[math.fsum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def inverse4(e):
    # 校验e为有限实数、非布尔且0<=e<1
    if isinstance(e, bool) or not isinstance(e, (int, float)) or not math.isfinite(e) or not 0 <= e < 1:
        raise ValueError('e须为有限实数、非布尔且0<=e<1')
    # 返回(I-e*J/4)/(1-e)，J为4x4全1矩阵
    d = (1 - e / 4) / (1 - e)
    o = (-e / 4) / (1 - e)
    return [[d if i == j else o for j in range(4)] for i in range(4)]
# LH264_MATRIX_COMPLETE
