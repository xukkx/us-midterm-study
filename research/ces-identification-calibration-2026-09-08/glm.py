"""多项 logistic(softmax)数值核心，仅标准库，无文件网络。\n参考类固定为 K-1，系数恒为 0，只估计前 K-1 个类别。\n"""
import math

# 内部常量：高斯消元奇异判定阈值
_SING_TOL = 1e-14
# Armijo 准则参数
_ARMIJO_C = 1e-4
_ARMIJO_RHO = 0.5

def _is_bool(v):
    # 布尔在 Python 中是 int 子类，必须单独拒绝
    return isinstance(v, bool)

def _是有穷实数(v):
    # 检查 X 元素：只允许非布尔 int/float 且有穷
    if _is_bool(v):
        return False
    if not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(float(v))
    except Exception:
        return False

def _检查正数(v):
    # 检查 ridge 类超参数：有穷正实数，非布尔
    if _is_bool(v):
        return False
    if not isinstance(v, (int, float)):
        return False
    try:
        f = float(v)
    except Exception:
        return False
    return math.isfinite(f) and f > 0.0

def _校验X(X, p_期望=None):
    # 校验设计矩阵：n 行 p 列，第一列恒为 1
    if not isinstance(X, (list, tuple)) or len(X) == 0:
        raise ValueError("X 须为非空行列表")
    n = len(X)
    p = None
    for i, 行 in enumerate(X):
        if not isinstance(行, (list, tuple)):
            raise ValueError("X 每行须为列表")
        if p is None:
            p = len(行)
            if p < 1:
                raise ValueError("X 列数 p 须 >=1")
            if p_期望 is not None and p != p_期望:
                raise ValueError("预测时 X 列数与模型 p 不一致")
        elif len(行) != p:
            raise ValueError("X 各行列数须一致")
        for j, v in enumerate(行):
            if not _是有穷实数(v):
                raise ValueError("X 须为有限实数且非布尔")
        # 第一列恒为截距 1，不接受偏离
        if float(行[0]) != 1.0:
            raise ValueError("X 第一列须恒为 1")
    return n, p

def _校验counts(counts, n_期望=None):
    # 校验计数矩阵：n 行 K 列，非负真实整数，可为零
    if not isinstance(counts, (list, tuple)) or len(counts) == 0:
        raise ValueError("counts 须为非空行列表")
    n = len(counts)
    if n_期望 is not None and n != n_期望:
        raise ValueError("X 与 counts 行数须一致")
    K = None
    总和 = 0
    for i, 行 in enumerate(counts):
        if not isinstance(行, (list, tuple)):
            raise ValueError("counts 每行须为列表")
        if K is None:
            K = len(行)
            if K < 2:
                raise ValueError("K 须 >=2")
        elif len(行) != K:
            raise ValueError("counts 各行列数须一致")
        for v in 行:
            if _is_bool(v):
                raise ValueError("counts 不接受布尔")
            if isinstance(v, int):
                iv = v
            else:
                raise ValueError("counts须为int人数；不自动将浮点权重转换为频数")
            if iv < 0:
                raise ValueError("counts 不接受负数")
            总和 += iv
    if 总和 <= 0:
        raise ValueError("全零数据拒绝拟合")
    return n, K

def _校验beta(beta, K, p):
    # 校验系数形状为 [K-1][p] 且元素有穷
    if not isinstance(beta, (list, tuple)):
        raise ValueError("beta 须为列表")
    if len(beta) != K - 1:
        raise ValueError("beta 行数须为 K-1")
    for k in range(K - 1):
        行 = beta[k]
        if not isinstance(行, (list, tuple)) or len(行) != p:
            raise ValueError("beta 每行长度须为 p")
        for v in 行:
            if not _是有穷实数(v):
                raise ValueError("beta 须有穷")

def _稳定概率(对数向量):
    # 稳定 softmax：减最大值再指数归一，保证严格正且和为 1
    m = max(对数向量)
    指数 = [math.exp(v - m) for v in 对数向量]
    if any(v == 0 or not math.isfinite(v) for v in 指数):
        raise ValueError("softmax超出机器可表示范围，不返回伪称严格正的零概率")
    s = math.fsum(指数)
    return [v / s for v in 指数]

def _行概率(beta, x行, K, p):
    # 单行 K 个类别概率，参考类对数为 0
    对数 = []
    for k in range(K - 1):
        s = 0.0
        bk = beta[k]
        for j in range(p):
            xv = float(x行[j])
            # 跳过零特征以节省 Hessian/梯度时间
            if xv != 0.0:
                s += float(bk[j]) * xv
        对数.append(s)
    对数.append(0.0)
    return _稳定概率(对数)

def loss_gradient_hessian(beta, X, counts, ridge, intercept_ridge):
    # 计算带 ridge 的负对数似然、梯度与完整 Hessian
    # 梯度：sum x*(n*prob-y)+lambda*beta，Hessian 类块见文档
    if not _检查正数(ridge) or not _检查正数(intercept_ridge):
        raise ValueError("ridge 与 intercept_ridge 须为正有穷数")
    n, p = _校验X(X)
    n2, K = _校验counts(counts, n)
    _校验beta(beta, K, p)
    Km = K - 1
    # 行总数 n_i，用于多项方差结构
    行总数 = []
    for i in range(n):
        行总数.append(math.fsum(float(v) for v in counts[i]))
    损失 = 0.0
    # 梯度形状 [K-1][p]，初始化为 0
    梯度 = [[0.0 for _ in range(p)] for _ in range(Km)]
    m = Km * p
    # 完整 Hessian 形状 m*m，初始化为 0
    海森 = [[0.0 for _ in range(m)] for _ in range(m)]
    for i in range(n):
        x行 = X[i]
        y行 = counts[i]
        ni = 行总数[i]
        if ni == 0:
            continue
        prob = _行概率(beta, x行, K, p)
        # 负对数似然累加：-sum y*log(prob)，prob 严格正故安全
        for k in range(K):
            y = float(y行[k])
            if y != 0.0:
                损失 += -y * math.log(prob[k])
        # 梯度累加：x*(ni*prob-y)，只处理前 K-1 类
        for k in range(Km):
            残差 = ni * prob[k] - float(y行[k])
            if 残差 == 0.0:
                continue
            gk = 梯度[k]
            for j in range(p):
                xv = float(x行[j])
                if xv != 0.0:
                    gk[j] += xv * 残差
        # Hessian 类块：ni*p_k*(I-p_l)*x_j*x_h，只遍历非零 x
        非零列 = [j for j in range(p) if float(x行[j]) != 0.0]
        for k in range(Km):
            for ll in range(Km):
                系数 = ni * prob[k] * ((1.0 if k == ll else 0.0) - prob[ll])
                if 系数 == 0.0:
                    continue
                for j in 非零列:
                    xj = float(x行[j])
                    行号 = k * p + j
                    for h in 非零列:
                        列号 = ll * p + h
                        海森[行号][列号] += 系数 * xj * float(x行[h])
    # ridge 惩罚：截距用 intercept_ridge，其余用 ridge
    惩罚 = 0.0
    for k in range(Km):
        for j in range(p):
            lam = float(intercept_ridge) if j == 0 else float(ridge)
            b = float(beta[k][j])
            惩罚 += 0.5 * lam * b * b
            梯度[k][j] += lam * b
            海森[k * p + j][k * p + j] += lam
    损失 += 惩罚
    return 损失, 梯度, 海森

def _解线性方程(A, b):
    # 纯 Python 高斯消元部分选主元解 A x = b
    n = len(b)
    # 增广矩阵深拷贝为浮点
    M = [[float(A[i][j]) for j in range(n)] + [float(b[i])] for i in range(n)]
    for 列 in range(n):
        # 部分选主元：在列中找绝对值最大行
        主元 = 列
        最大 = abs(M[列][列])
        for r in range(列 + 1, n):
            v = abs(M[r][列])
            if v > 最大:
                最大 = v
                主元 = r
        if 最大 < _SING_TOL:
            raise ValueError("奇异矩阵")
        if 主元 != 列:
            M[列], M[主元] = M[主元], M[列]
        # 归一化主元行
        除数 = M[列][列]
        for j in range(列, n + 1):
            M[列][j] /= 除数
        # 消去下方行
        for r in range(列 + 1, n):
            因子 = M[r][列]
            if 因子 != 0.0:
                for j in range(列, n + 1):
                    M[r][j] -= 因子 * M[列][j]
    # 回代求解
    x = [0.0 for _ in range(n)]
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for j in range(i + 1, n):
            s -= M[i][j] * x[j]
        x[i] = s
    return x

def fit(X, counts, ridge=1.0, intercept_ridge=0.05, max_iter=80, tol=1e-8):
    # 牛顿法拟合多项 logistic，Armijo 回溯保证损失不升高
    if not _检查正数(ridge) or not _检查正数(intercept_ridge):
        raise ValueError("ridge 与 intercept_ridge 须为正")
    if _is_bool(max_iter) or not isinstance(max_iter, int) or max_iter <= 0:
        raise ValueError("max_iter 须为正整数")
    if _is_bool(tol) or not isinstance(tol, (int, float)):
        raise ValueError("tol 须为正数")
    tol_f = float(tol)
    if not math.isfinite(tol_f) or tol_f <= 0.0:
        raise ValueError("tol 须为正有穷数")
    n, p = _校验X(X)
    n2, K = _校验counts(counts, n)
    Km = K - 1
    # 零初始化系数
    beta = [[0.0 for _ in range(p)] for _ in range(Km)]
    损失, 梯度, 海森 = loss_gradient_hessian(beta, X, counts, ridge, intercept_ridge)
    收敛 = False
    迭代 = 0
    平方容忍 = math.sqrt(tol_f)
    for 步 in range(1, max_iter + 1):
        # 当前梯度绝对最大值
        最大梯度 = 0.0
        for k in range(Km):
            for j in range(p):
                v = abs(梯度[k][j])
                if v > 最大梯度:
                    最大梯度 = v
        # 准则一：梯度足够小即收敛
        if 最大梯度 <= tol_f:
            收敛 = True
            break
        m = Km * p
        平坦梯度 = [梯度[k][j] for k in range(Km) for j in range(p)]
        try:
            # 解 H*d=-g 得牛顿方向
            负梯度 = [-v for v in 平坦梯度]
            方向 = _解线性方程(海森, 负梯度)
        except ValueError:
            # 奇异时退化为负梯度方向
            方向 = [-v for v in 平坦梯度]
        # 方向导数应为负，否则用负梯度保证下降
        方向导数 = math.fsum(平坦梯度[i] * 方向[i] for i in range(m))
        if not math.isfinite(方向导数) or 方向导数 >= 0.0:
            方向 = [-v for v in 平坦梯度]
            方向导数 = math.fsum(平坦梯度[i] * 方向[i] for i in range(m))
        # Armijo 回溯：防止损失升高
        步长 = 1.0
        找到 = False
        旧损失 = 损失
        for _ in range(30):
            试探 = [[float(beta[k][j]) + 步长 * 方向[k * p + j] for j in range(p)] for k in range(Km)]
            try:
                新损失, 新梯度, 新海森 = loss_gradient_hessian(试探, X, counts, ridge, intercept_ridge)
            except ValueError:
                步长 *= _ARMIJO_RHO
                continue
            if not math.isfinite(新损失):
                步长 *= _ARMIJO_RHO
                continue
            if 新损失 <= 旧损失 + _ARMIJO_C * 步长 * 方向导数:
                找到 = True
                break
            步长 *= _ARMIJO_RHO
            if 步长 < 1e-12:
                break
        if not 找到:
            # 无法下降则如实停止，不伪装成功
            break
        # 相对改善小且梯度较小则视为收敛
        分母 = max(1.0, abs(旧损失))
        相对改善 = abs(旧损失 - 新损失) / 分母
        新最大梯度 = 0.0
        for k in range(Km):
            for j in range(p):
                v = abs(新梯度[k][j])
                if v > 新最大梯度:
                    新最大梯度 = v
        beta = 试探
        损失, 梯度, 海森 = 新损失, 新梯度, 新海森
        迭代 = 步
        if 新最大梯度 <= tol_f:
            收敛 = True
            最大梯度 = 新最大梯度
            break
        if 相对改善 <= tol_f and 新最大梯度 <= 平方容忍:
            收敛 = True
            最大梯度 = 新最大梯度
            break
    # 收尾计算梯度最大值与损失
    最终梯度最大 = 0.0
    for k in range(Km):
        for j in range(p):
            v = abs(梯度[k][j])
            if v > 最终梯度最大:
                最终梯度最大 = v
    return {"beta": beta, "K": K, "p": p, "iterations": 迭代, "converged": bool(收敛), "loss": float(损失), "gradient_max": float(最终梯度最大)}

def predict(model, X):
    # 返回各行 K 个概率，严格正且合计为 1，不做随意裁剪
    if not isinstance(model, dict):
        raise ValueError("model 须为 fit 返回字典")
    for 键 in ("beta", "K", "p"):
        if 键 not in model:
            raise ValueError("model 缺少字段")
    K = model["K"]
    p = model["p"]
    beta = model["beta"]
    if _is_bool(K) or not isinstance(K, int) or K < 2:
        raise ValueError("model K 非法")
    if _is_bool(p) or not isinstance(p, int) or p < 1:
        raise ValueError("model p 非法")
    _校验beta(beta, K, p)
    n, p2 = _校验X(X, p)
    结果 = []
    for i in range(n):
        prob = _行概率(beta, X[i], K, p)
        # 显式重归一以抵消浮点误差，仍保持严格正
        s = math.fsum(prob)
        结果.append([v / s for v in prob])
    return 结果
# LH263_GLM_COMPLETE
