def recode(row):
    """
    依据投票参与状态与实际选票对受访者进行重编码分类。

    参数 row: dict，字段值均为 int 或 None。涉及字段：
      V242095x  投票参与：0=未投票，1=已投票
      V242096x  实际选票：1=民主党(D)，2=共和党(R)，3..6=其他实际票
      V241451   自报家庭财务恶化(E)
      V242536   国家身份重要性(I)
      V241201   民主党候选人关心程度评价
      V241206   共和党候选人关心程度评价

    分类规则：
      turnout=0 且选票有效(1..6) -> conflict
      turnout=0 其他情况         -> nonvoter
      turnout=1 时按选票：1->D，2->R，3..6->other，否则 unknown
      其他 turnout 取值          -> unknown
    缺失(None)或负码一律不能补零推断。

    E: V241451 取 4/5 记 1，1/2/3 记 0，其他 None。
    I: V242536 取 1/2 记 1，3/4/5 记 0，其他 None。
    C: V241201(D评分) 与 V241206(R评分) 均在 1..5 内有效且数值越小越强：
       R 评分较小 -> R_higher；D 评分较小 -> D_higher；相等 -> tie；
       任一无效 -> None。
    禁止以非投票偏好替代实际票；POST 身份仅作事后关联，不参与本分类。

    返回 dict: state, E, I, C, reasons。
    reasons 为输入中负码与 None 字段的字典（字段名 -> 原值）。
    """
    fields = ("V242095x", "V242096x", "V241451", "V242536", "V241201", "V241206")
    reasons = {f: row.get(f) for f in fields
               if row.get(f) is None or (isinstance(row.get(f), int) and row.get(f) < 0)}

    turnout = row.get("V242095x")
    ballot = row.get("V242096x")
    ballot_valid = isinstance(ballot, int) and 1 <= ballot <= 6

    if turnout == 0:
        state = "conflict" if ballot_valid else "nonvoter"
    elif turnout == 1:
        if ballot == 1:
            state = "D"
        elif ballot == 2:
            state = "R"
        elif ballot_valid:
            state = "other"
        else:
            state = "unknown"
    else:
        state = "unknown"

    e = row.get("V241451")
    E = 1 if e in (4, 5) else (0 if e in (1, 2, 3) else None)

    i = row.get("V242536")
    I = 1 if i in (1, 2) else (0 if i in (3, 4, 5) else None)

    d_score = row.get("V241201")
    r_score = row.get("V241206")
    if isinstance(d_score, int) and 1 <= d_score <= 5 and isinstance(r_score, int) and 1 <= r_score <= 5:
        if r_score < d_score:
            C = "R_higher"
        elif d_score < r_score:
            C = "D_higher"
        else:
            C = "tie"
    else:
        C = None

    return {"state": state, "E": E, "I": I, "C": C, "reasons": reasons}
# END