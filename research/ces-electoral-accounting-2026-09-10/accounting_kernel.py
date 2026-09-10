"""有界选举状态转移核。"""

from itertools import product
import math

STATES = ("D", "R", "O", "A", "N", "U")
_SIG = {"D": -1, "R": 1, "O": 0, "A": 0, "N": 0}
_KNOWN = set(_SIG)


def _num(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise ValueError(name)


def _cell(c):
    if not isinstance(c, dict) or set(c) != {"before", "after", "n", "adult_w", "post_w", "post_n"}:
        raise ValueError("cell")
    if c["before"] not in STATES or c["after"] not in STATES:
        raise ValueError("state")
    if isinstance(c["n"], bool) or not isinstance(c["n"], int) or c["n"] < 0:
        raise ValueError("n")
    if isinstance(c["post_n"], bool) or not isinstance(c["post_n"], int) or c["post_n"] < 0 or c["post_n"] > c["n"]:
        raise ValueError("post_n")
    _num(c["adult_w"], "adult_w"); _num(c["post_w"], "post_w")
    if c["n"] == 0 and (c["adult_w"] != 0 or c["post_n"] != 0):
        raise ValueError("zero n")
    if c["post_n"] == 0 and c["post_w"] != 0:
        raise ValueError("zero post_n")


def _choices(s):
    return (s,) if s != "U" else tuple(_KNOWN)


def account(cells):
    """按完整36格状态表，返回无权重、成人权重和后期权重下的队列、已覆盖人数、已知贡献及未知边界。"""
    if not isinstance(cells, list) or len(cells) != 36:
        raise ValueError("exactly 36 cells")
    seen = set()
    for c in cells:
        _cell(c); key = (c["before"], c["after"])
        if key in seen: raise ValueError("duplicate")
        seen.add(key)
    if seen != set(product(STATES, STATES)):
        raise ValueError("missing")
    modes = {"unweighted": lambda c: (c["n"], c["n"]), "adult": lambda c: (c["adult_w"], c["n"]), "post": lambda c: (c["post_w"], c["post_n"])}
    out = {}
    for mode, get in modes.items():
        cohort = covered = weight_sum = known_n = unknown_n = known_w = unknown_w = known_delta = 0
        before_lo = before_hi = after_lo = after_hi = 0.0
        total_lo = total_hi = 0.0
        comps = {k: {"known_n": 0, "known_delta": 0, "bounds": [0.0, 0.0]} for k in ("repeat_vote_choice", "election_entry", "election_exit", "contest_entry", "contest_exit", "other_zero")}
        grid = []
        for c in cells:
            w, cov = get(c); cohort += c["n"]; covered += cov; weight_sum += w
            vals = []
            for b, a in product(_choices(c["before"]), _choices(c["after"])):
                d = _SIG[a] - _SIG[b]; vals.append((b, a, d))
            bs = [_SIG[x] for x in _choices(c["before"])]
            ass = [_SIG[x] for x in _choices(c["after"])]
            before_lo += w * min(bs); before_hi += w * max(bs)
            after_lo += w * min(ass); after_hi += w * max(ass)
            ds = [x[2] for x in vals]; total_lo += w * min(ds); total_hi += w * max(ds)
            known = c["before"] != "U" and c["after"] != "U"
            if known:
                known_n += cov; known_w += w; known_delta += w * ds[0]
            else: unknown_n += cov; unknown_w += w
            if c["before"] != "U" and c["after"] != "U":
                b, a, d = vals[0]
                if b in "DRO" and a in "DRO": cat = "repeat_vote_choice"
                elif b == "N" and a in "DRO": cat = "election_entry"
                elif b in "DRO" and a == "N": cat = "election_exit"
                elif b == "A" and a in "DRO": cat = "contest_entry"
                elif b in "DRO" and a == "A": cat = "contest_exit"
                else: cat = "other_zero"
                comps[cat]["known_n"] += cov; comps[cat]["known_delta"] += w*d; comps[cat]["bounds"][0] += w*d; comps[cat]["bounds"][1] += w*d
            else:
                # 未知端点按该类贡献规则分别取边际界限。
                cv = {k: [0.0] for k in comps}
                for b, a, d in vals:
                    if b in "DRO" and a in "DRO": cat = "repeat_vote_choice"
                    elif b == "N" and a in "DRO": cat = "election_entry"
                    elif b in "DRO" and a == "N": cat = "election_exit"
                    elif b == "A" and a in "DRO": cat = "contest_entry"
                    elif b in "DRO" and a == "A": cat = "contest_exit"
                    else: cat = "other_zero"
                    cv[cat].append(w*d)
                for cat, values in cv.items():
                    comps[cat]["bounds"][0] += min(values); comps[cat]["bounds"][1] += max(values)
            grid.append({"before": c["before"], "after": c["after"], "covered_n": cov, "weight": w, "delta_bounds": [w*min(ds), w*max(ds)], "known_delta": (w*ds[0] if known else None)})
        per = None if weight_sum == 0 else [total_lo*100/weight_sum, total_hi*100/weight_sum]
        out[mode] = {"cohort_n": cohort, "covered_n": covered, "missing_weight_n": cohort-covered, "weight_sum": weight_sum, "known_pair_n": known_n, "unknown_pair_n": unknown_n, "known_pair_weight": known_w, "unknown_pair_weight": unknown_w, "known_delta": known_delta, "delta_bounds": [total_lo, total_hi], "per100_bounds": per, "known_delta_per100": (None if weight_sum == 0 else known_delta*100/weight_sum), "before_bounds": [before_lo, before_hi], "after_bounds": [after_lo, after_hi], "components": comps, "grid": grid}
    return {"modes": out}
