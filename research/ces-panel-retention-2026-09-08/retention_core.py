"""LH-261 留存构成计数核心，仅纯统计，无输入输出。"""
# 基线字段固定顺序，用于连接核验
_BASELINE_FIELDS = ("pid7", "race", "hispanic", "employ", "ownhome", "CC20_410", "CC20_327a")
# 缺失标记集合，仅接受空、NA、None 系，对应规范要求
_MISSING_TOKENS = {"NA"}
# 分组与分层固定顺序，禁止事后增删
_GROUPS = ("all", "Latino_employed_2020", "R_renter_2020")
_DIMS = {"overall": ("all",), "pid": ("D", "I", "R", "unknown"), "employment": ("full_time", "part_time", "other", "unknown"), "tenure": ("rent", "own", "other", "unknown")}
# 各字段合法编码范围，超出即非法
_PID_OK = {"1", "2", "3", "4", "5", "6", "7", "8"}
_RACE_OK = {"1", "2", "3", "4", "5", "6", "7", "8"}
_HISP_OK = {"1", "2"}
_EMP_OK = {"1", "2", "3", "4", "5", "6", "7", "8", "9"}
_OWN_OK = {"1", "2", "3"}

def _norm(v):
    # 规范单个原始值，缺失统一为 None，数值字符串归一
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    if s.upper() in _MISSING_TOKENS:
        return None
    # 数值字符串如 1.0 归一为 1，整数值统一形态
    try:
        f = float(s)
        if f.is_integer() and abs(f) < 1000000:
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s

def _pid_cat(v):
    # pid7 合并为 D/I/R/未知
    if v is None:
        return "unknown"
    if v in ("1", "2", "3"):
        return "D"
    if v == "4":
        return "I"
    if v in ("5", "6", "7"):
        return "R"
    return "unknown"

def _emp_cat(v):
    # 就业合并为全职兼职其他未知
    if v is None:
        return "unknown"
    if v == "1":
        return "full_time"
    if v == "2":
        return "part_time"
    return "other"

def _ten_cat(v):
    # 住房合并为租房自有其他未知
    if v is None:
        return "unknown"
    if v == "2":
        return "rent"
    if v == "1":
        return "own"
    return "other"

def _check_baseline_value(field, v):
    # 检查基线非法类别，缺失合法，非缺失须在范围内
    if v is None:
        return
    if field == "pid7" and v not in _PID_OK:
        raise ValueError("非法pid7:" + v)
    if field == "race" and v not in _RACE_OK:
        raise ValueError("非法race:" + v)
    if field == "hispanic" and v not in _HISP_OK:
        raise ValueError("非法hispanic:" + v)
    if field == "employ" and v not in _EMP_OK:
        raise ValueError("非法employ:" + v)
    if field == "ownhome" and v not in _OWN_OK:
        raise ValueError("非法ownhome:" + v)
    # 两个 CC 字段非缺失即合法，不做范围限制

def _canon_map(rows, label):
    # 两边独立检查缺 ID 与重复 ID，返回 ID 到规范七字段映射
    seen = set()
    out = {}
    n = 0
    for r in rows:
        n += 1
        if not isinstance(r, dict) or not {"id", *_BASELINE_FIELDS} <= set(r):
            raise ValueError(label + "缺少id或必要基线字段")
        raw_id = r.get("id")
        if raw_id is None or str(raw_id).strip().upper() in ("", "NA"):
            raise ValueError(label + "存在缺ID")
        sid = str(raw_id).strip()
        if sid in seen:
            raise ValueError(label + "存在重复ID")
        seen.add(sid)
        canon = {}
        for f in _BASELINE_FIELDS:
            canon[f] = _norm(r.get(f))
            if label == "baseline":
                _check_baseline_value(f, canon[f])
        out[sid] = canon
    return out

def _in_latino_employed(c):
    # 拉美裔在业者判定，缺失不填零不归入
    latino = (c["race"] == "3" or c["hispanic"] == "1")
    return bool(latino and c["employ"] in ("1", "2"))

def _in_r_renter(c):
    # 共和党租房者判定
    return bool(c["pid7"] in ("5", "6", "7") and c["ownhome"] == "2")

def build_counts(baseline_rows, selected_rows, source_label):
    # 主函数，只做未加权计数，不算比率不做抑制
    base = _canon_map(baseline_rows, "baseline")
    sel = _canon_map(selected_rows, "selected")
    # 入选 ID 必须在基线中，否则报错
    for sid in sel:
        if sid not in base:
            raise ValueError("selected存在基线外ID")
    # 逐人七字段一致性核验，不一致即停
    for sid, c in sel.items():
        b = base[sid]
        for f in _BASELINE_FIELDS:
            if c[f] != b[f]:
                raise ValueError("基线字段不一致:" + f)
    sel_set = set(sel.keys())
    # 初始化全部固定组合，含零人数
    agg = {}
    for g in _GROUPS:
        for dim, cats in _DIMS.items():
            for cat in cats:
                agg[(g, dim, cat)] = [0, 0]
    # 逐人归组归层并累加
    for sid, b in base.items():
        is_sel = sid in sel_set
        gs = ["all"]
        if _in_latino_employed(b):
            gs.append("Latino_employed_2020")
        if _in_r_renter(b):
            gs.append("R_renter_2020")
        cats = {"overall": "all", "pid": _pid_cat(b["pid7"]), "employment": _emp_cat(b["employ"]), "tenure": _ten_cat(b["ownhome"])}
        for g in gs:
            for dim, cat in cats.items():
                k = (g, dim, cat)
                agg[k][0] += 1
                if is_sel:
                    agg[k][1] += 1
    # 组装行列表，顺序固定
    rows = []
    for g in _GROUPS:
        for dim in ("overall", "pid", "employment", "tenure"):
            for cat in _DIMS[dim]:
                bn, sn = agg[(g, dim, cat)]
                rows.append({"group": g, "dimension": dim, "category": cat, "baseline_n": bn, "selected_n": sn, "not_selected_n": bn - sn})
    baseline_n = len(base)
    selected_n = len(sel)
    totals = {"baseline_n": baseline_n, "selected_n": selected_n, "not_selected_n": baseline_n - selected_n, "matched_selected_n": selected_n, "unmatched_selected_n": 0, "baseline_field_mismatches": 0}
    return {"schema_version": 1, "source_label": source_label, "totals": totals, "rows": rows}
