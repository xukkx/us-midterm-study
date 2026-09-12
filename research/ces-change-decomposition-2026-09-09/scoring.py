"""冻结折外概率的逐格评分与聚合接口。"""
from score_kernel import score_one, threeway


def score_pair(parent_q, child_q, y, b, a=None):
    old = score_one(parent_q, y, b)
    new = score_one(child_q, y, b)
    keys = ("event_log", "dest_log", "full_log", "binary_brier", "multiclass_brier")
    delta = {k: new[k] - old[k] for k in keys}
    result = {"old": old, "new": new, "delta": delta}
    if a is not None and a != b:
        old3 = threeway(parent_q, a, b, y)
        new3 = threeway(child_q, a, b, y)
        result["old_threeway"] = old3
        result["new_threeway"] = new3
        result["delta_threeway"] = {
            "full_log": new3["full_log"] - old3["full_log"],
            "brier": new3["brier"] - old3["brier"],
            "third_internal_log": (
                None if old3["third_internal_log"] is None or new3["third_internal_log"] is None
                else new3["third_internal_log"] - old3["third_internal_log"]
            ),
        }
    return result
