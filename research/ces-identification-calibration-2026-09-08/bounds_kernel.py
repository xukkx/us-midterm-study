# bounds_kernel.py
# 仅用 Python 标准库的匿名格可行性界内核。
# 只算可行性界与见证，不算置信区间，不把权重当人数。
# 不读取真实数据，不做可行性之外的解释。
# 单次调用内口径必须一致，不得混同 resolved 与 literal。
# resolved 下 not_sure 视为 (0,1)；literal 下视为 (0,)。
# 默认目标 sum mass*(after-before)/sum mass；系数目标无分母。
# 系数可负，须按方向选端点；重叠全体与子集须联合优化。
# 见证与输入同顺序，已知端点不变；求和一律 math.fsum。

import math

__all__ = ['support', 'bound']

# 合法标签：D/I对应0，R对应1，not_sure 待定，missing 缺失。
_LABELS = ('D', 'I', 'R', 'not_sure', 'missing')
# 合法口径：resolved 消解待定，literal 保留不确定为非R。
_CONVENTIONS = ('resolved', 'literal')

def support(label, convention):
    '''单个标签在指定口径下的二值支持集，只返回 0/1 元组。'''
    '''label 限定 D/I/R/not_sure/missing，口径限定 resolved/literal。'''
    '''D/I 返回 (0,)，R 返回 (1,)，missing 返回 (0,1)。'''
    '''not_sure 在 resolved 下为 (0,1)，literal 下为 (0,)。'''
    '''非法输入一律抛 ValueError 拒绝。'''
    if convention not in _CONVENTIONS:
        raise ValueError('convention 非法，应为 resolved 或 literal')
    if label not in _LABELS:
        raise ValueError('label 非法，应为 D/I/R/not_sure/missing')
    if label == 'D' or label == 'I':
        return (0,)
    if label == 'R':
        return (1,)
    if label == 'missing':
        return (0, 1)
    # 仅剩 not_sure，按口径区分，两种口径不得混同。
    if convention == 'resolved':
        return (0, 1)
    return (0,)

def _is_finite_real(x):
    '''判断有限实数：int/float，排除 bool、无穷与 NaN。'''
    if isinstance(x, bool):
        return False
    if not isinstance(x, (int, float)):
        return False
    if not math.isfinite(float(x)):
        return False
    return True

def _extreme_diffs(sb, sa):
    '''枚举求差值 after-before 的最小值与最大值。'''
    # 支持集只含 0/1，直接枚举全部组合。
    lo = None
    hi = None
    for b in sb:
        for a in sa:
            d = a - b
            if lo is None or d < lo:
                lo = d
            if hi is None or d > hi:
                hi = d
    return (lo, hi)

def _pick_pair(sb, sa, want):
    '''按目标差值挑选 (b,a)，保证 a-b 等于 want。'''
    # 固定顺序枚举，结果确定，且已知端点自然不变。
    for b in sb:
        for a in sa:
            if a - b == want:
                return (b, a)
    raise ValueError('找不到对应差值的见证对')

def bound(cells, convention, weighted=False, coefficient=None):
    '''匿名格可行性界：返回 lower/upper 与上下界见证。'''
    '''每格含 before/after/n/w；n 非负 int 非 bool；w 有限非负。'''
    '''n 为 0 则 w 须为 0；weighted 为真则 n>0 格 w 须大于 0。'''
    '''默认目标为加权平均差；coefficient 给定时为线性组合无分母。'''
    '''始终先验证所有格，不过滤坏输入；默认空集与零分母拒绝。'''
    if convention not in _CONVENTIONS:
        raise ValueError('convention 非法')
    if not isinstance(weighted, bool):
        raise ValueError('weighted 须为布尔量')
    if not isinstance(cells, (list, tuple)):
        raise ValueError('cells 须为 list 或 tuple')
    has_coef = coefficient is not None
    if has_coef:
        # 系数须与格数等长，每项有限实数，可为负。
        if not isinstance(coefficient, (list, tuple)):
            raise ValueError('coefficient 须为序列')
        if len(coefficient) != len(cells):
            raise ValueError('coefficient 长度须与 cells 一致')
        for c in coefficient:
            if not _is_finite_real(c):
                raise ValueError('coefficient 每项须为有限实数')
    # 第一阶段：逐格完整校验，不提前计算不过滤。
    ns = []
    ws = []
    sbs = []
    sas = []
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError('每格须为字典')
        for k in ('before', 'after', 'n', 'w'):
            if k not in cell:
                raise ValueError('每格须含 before/after/n/w')
        bl = cell['before']
        al = cell['after']
        n = cell['n']
        w = cell['w']
        if bl not in _LABELS or al not in _LABELS:
            raise ValueError('before/after 标签非法')
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError('n 须为非负 int 且非 bool')
        if not _is_finite_real(w) or float(w) < 0.0:
            raise ValueError('w 须为有限非负数')
        if n == 0 and float(w) != 0.0:
            raise ValueError('n 为 0 时 w 必须为 0')
        if weighted and n > 0 and float(w) <= 0.0:
            raise ValueError('加权模式下 n>0 格 w 须大于 0')
        ns.append(n)
        ws.append(w)
        sbs.append(support(bl, convention))
        sas.append(support(al, convention))
    k = len(cells)
    if k == 0:
        raise ValueError('cells 不得为空')
    # 质量：未加权用 n，加权用 w；系数模式同样遵循。
    if weighted:
        mass = [float(x) for x in ws]
    else:
        mass = [float(x) for x in ns]
    # 每格差值极值，先全部算好。
    los = []
    his = []
    for sb, sa in zip(sbs, sas):
        lo_d, hi_d = _extreme_diffs(sb, sa)
        los.append(lo_d)
        his.append(hi_d)
    if not has_coef:
        # 默认模式：分母固定为正，分子取极值即得上下界。
        denom = math.fsum(mass)
        if denom == 0.0:
            raise ValueError('默认模式分母为零，拒绝计算')
        lo_num = math.fsum([m * d for m, d in zip(mass, los)])
        hi_num = math.fsum([m * d for m, d in zip(mass, his)])
        lower = lo_num / denom
        upper = hi_num / denom
        lw = []
        uw = []
        for i in range(k):
            lb, la = _pick_pair(sbs[i], sas[i], los[i])
            ub, ua = _pick_pair(sbs[i], sas[i], his[i])
            lw.append({'before_value': lb, 'after_value': la, 'n': ns[i], 'w': ws[i]})
            uw.append({'before_value': ub, 'after_value': ua, 'n': ns[i], 'w': ws[i]})
        return {'lower': lower, 'upper': upper, 'lower_witness': lw, 'upper_witness': uw}
    # 系数模式：sum coef*mass*diff，无分母；按 eff 符号选端点。
    coef = [float(c) for c in coefficient]
    lo_terms = []
    hi_terms = []
    lw = []
    uw = []
    for i in range(k):
        eff = coef[i] * mass[i]
        if eff >= 0.0:
            lo_terms.append(eff * los[i])
            hi_terms.append(eff * his[i])
            lb, la = _pick_pair(sbs[i], sas[i], los[i])
            ub, ua = _pick_pair(sbs[i], sas[i], his[i])
        else:
            # 负权方向翻转，不得独立优化重叠全体与子集。
            lo_terms.append(eff * his[i])
            hi_terms.append(eff * los[i])
            lb, la = _pick_pair(sbs[i], sas[i], his[i])
            ub, ua = _pick_pair(sbs[i], sas[i], los[i])
        lw.append({'before_value': lb, 'after_value': la, 'n': ns[i], 'w': ws[i]})
        uw.append({'before_value': ub, 'after_value': ua, 'n': ns[i], 'w': ws[i]})
    lower = math.fsum(lo_terms)
    upper = math.fsum(hi_terms)
    return {'lower': lower, 'upper': upper, 'lower_witness': lw, 'upper_witness': uw}

# 示例核验（注释）：R->missing n=2 w=5；I->R n=1 w=1。
# 默认未加权 [-1/3,1/3]，加权 [-4/6,1/6]；coef=[1,-1] 未加权 [-3,-1]。
# LH263_BOUNDS_COMPLETE
