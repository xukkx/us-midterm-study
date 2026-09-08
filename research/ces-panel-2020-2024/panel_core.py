# panel_core.py 流式CSV匿名群体三波状态账本(标准库)
# 只做充分统计,不算比率/区间,不输出个人行
import argparse
import csv
import hashlib
import json
import math
SCHEMA_VERSION = "1.0.0"
WEIGHTS = [("population", "commonweight_24"), ("post", "commonpostweight_24"), ("registered22", "vvweight_22"), ("registered22_post", "vvweight_post_22")]
PID_YEARS = [2020, 2022, 2024]
PRES_YEARS = [2020, 2024]
ISSUE_COLS = {"medicare": {2020: "CC20_327a", 2022: "CC22_327a", 2024: "RC24_327a"}, "drug_price": {2020: "CC20_327b", 2022: "CC22_327b", 2024: "RC24_327b"}, "immigration": {2020: "CC20_331a", 2022: "CC22_331a", 2024: "CC24_331a"}}
MISS_TXT = {"", "na", "n/a", "nan", "null", "none", "."}
def _str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s
def _miss(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in MISS_TXT
def _int(v):
    s = _str(v)
    if s is None or _miss(s):
        return None
    try:
        if s in ("Active", "-1"):
            return s
        f = float(s)
        if not math.isfinite(f) or int(f) != f:
            raise ValueError("非法编码:" + s)
        return int(f)
    except ValueError:
        raise ValueError("非法编码:" + s)
def weight_number(value):
    if _miss(value):
        return None
    try:
        f = float(str(value).strip())
    except Exception:
        raise ValueError("非法权重")
    if not math.isfinite(f):
        raise ValueError("权重非有限")
    if f < 0:
        raise ValueError("权重为负")
    return f
def pid(value):
    c = _int(value)
    if c is None:
        return "unknown"
    if c in (1, 2, 3):
        return "D"
    if c == 4:
        return "I"
    if c in (5, 6, 7):
        return "R"
    if c == 8:
        return "unknown"
    raise ValueError("非法pid:" + str(value))
def groups(row):
    for col, allowed in (("pid7_20", range(1, 9)), ("ownhome_20", range(1, 4)),
                         ("race_20", range(1, 9)), ("hispanic_20", (1, 2)),
                         ("employ_20", range(1, 10))):
        value = _int(row.get(col))
        if value is not None and value not in allowed:
            raise ValueError("基线群体字段非法:" + col)
    out = ["all"]
    p = _int(row.get("pid7_20"))
    o = _int(row.get("ownhome_20"))
    if p in (5, 6, 7) and o == 2:
        out.append("R_renter_2020")
    r = _int(row.get("race_20"))
    h = _int(row.get("hispanic_20"))
    e = _int(row.get("employ_20"))
    if (r == 3 or h == 1) and e in (1, 2):
        out.append("Latino_employed_2020")
    return out
def turnout(row, year):
    if year == 2020:
        s = _int(row.get("CL_voter_status_20"))
        v = _int(row.get("CL_2020gvm"))
        if s is None and v is None:
            return "unmatched"
        if s is not None and v is not None:
            if s in (1, 2, 3, 4, 5) and v in (1, 2, 3, 4, 5):
                return "voted"
            raise ValueError("2020档案矛盾/非法")
        if s in (1, 2, 3, 4, 5) and v is None:
            return "matched_no_record"
        raise ValueError("2020档案矛盾/非法")
    if year == 2022:
        s = _str(row.get("TS_voterstatus_22"))
        v = _int(row.get("TS_g2022"))
        if s == "Active":
            if v in (1, 2, 3, 4, 5, 6):
                return "voted"
            if v == 7:
                return "matched_no_record"
            raise ValueError("2022档案矛盾/非法")
        if s == "-1":
            if v is None:
                return "unmatched"
            raise ValueError("2022档案矛盾")
        raise ValueError("2022状态非法")
    if year == 2024:
        s = _int(row.get("TS_voterstatus_24"))
        v = _int(row.get("TS_g2024"))
        if s == 1:
            if v in (1, 2, 3, 4, 5, 6):
                return "voted"
            if v == 7:
                return "matched_no_record"
            raise ValueError("2024档案矛盾/非法")
        if s is None:
            if v is None:
                return "unmatched"
            raise ValueError("2024档案矛盾")
        raise ValueError("2024状态非法")
    raise ValueError("非法年份")
def _took(row, year):
    yy = str(year)[2:]
    c = _int(row.get("tookpost_" + yy))
    if c is None:
        return "unknown_post"
    if c == 1:
        return "not_post"
    if c == 2:
        return None
    raise ValueError("tookpost非法")
def _party(row, year, num):
    if year == 2020:
        col = "HouseCand9Party" if num == 9 else "HouseCand" + str(num) + "Party_20"
    elif year == 2022:
        col = "HouseCand" + str(num) + "Party_22"
    else:
        col = "HouseCand" + str(num) + "Party_24"
    if col not in row:
        return "unknown_party"
    v = row.get(col)
    if _miss(v):
        return "unknown_party"
    s = str(v).strip()
    if s == "Democratic":
        return "D"
    if s == "Republican":
        return "R"
    allowed = {"Libertarian", "Independent", "Conservative", "Green", "Working Families",
               "Socialist Workers", "Liberty", "Working Class", "Constitution",
               "Independent American", "United Utah", "Alliance", "Moderate", "Unity",
               "Center", "No Party Preference"}
    if s not in allowed:
        raise ValueError("候选人党派编码未核定")
    return "other"
def vote(row, year, office):
    if office not in ("president", "house"):
        raise ValueError("非法office")
    if year not in (2020, 2022, 2024):
        raise ValueError("非法年份")
    if office == "president" and year == 2022:
        raise ValueError("2022无总统票")
    t = _took(row, year)
    if t is not None:
        return t
    if office == "president":
        col = "CC20_410" if year == 2020 else "CC24_410"
        c = _int(row.get(col))
        if c is None:
            return "missing_item"
        if year == 2020:
            if c == 1:
                return "D"
            if c == 2:
                return "R"
            if c == 4:
                return "other"
            if c == 5:
                return "not_race"
            if c == 6:
                return "not_vote"
            if c == 7:
                return "unknown"
            raise ValueError("2020总统票非法")
        if c == 1:
            return "D"
        if c == 2:
            return "R"
        if c in (3, 4, 5, 6, 8):
            return "other"
        if c == 9:
            return "not_race"
        raise ValueError("2024总统票非法")
    col = {2020: "CC20_412", 2022: "CC22_412", 2024: "CC24_412"}[year]
    c = _int(row.get(col))
    if c is None:
        return "missing_item"
    if c in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        ok = (year == 2020 and 1 <= c <= 9) or (year == 2022 and 1 <= c <= 8) or (year == 2024 and 1 <= c <= 5)
        if not ok:
            raise ValueError("众院序号越界")
        return _party(row, year, c)
    if c == 10:
        return "other"
    if c == 11:
        return "not_race"
    if c == 12:
        return "not_vote"
    if c == 13:
        return "unknown"
    raise ValueError("众院票非法")
def issue(row, year, name):
    if name not in ISSUE_COLS or year not in (2020, 2022, 2024):
        raise ValueError("非法议题/年份")
    c = _int(row.get(ISSUE_COLS[name][year]))
    if c is None:
        return "unknown"
    if c == 1:
        return "support"
    if c == 2:
        return "oppose"
    raise ValueError("议题非法码")
def _states(row, measure):
    if measure == "pid":
        return [pid(row.get("pid7_20")), pid(row.get("pid7_22")), pid(row.get("pid7_24"))], PID_YEARS
    if measure == "turnout":
        return [turnout(row, 2020), turnout(row, 2022), turnout(row, 2024)], PID_YEARS
    if measure == "house":
        return [vote(row, 2020, "house"), vote(row, 2022, "house"), vote(row, 2024, "house")], PID_YEARS
    if measure == "president":
        return [vote(row, 2020, "president"), vote(row, 2024, "president")], PRES_YEARS
    return [issue(row, 2020, measure), issue(row, 2022, measure), issue(row, 2024, measure)], PID_YEARS
def build(csv_path):
    digest = hashlib.sha256()
    with open(csv_path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    sha = digest.hexdigest()
    agg = {}
    gcount = {"all": 0, "R_renter_2020": 0, "Latino_employed_2020": 0}
    ids = {"caseid_20": set(), "caseid_22": set(), "caseid_24": set()}
    n = 0
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        head = rdr.fieldnames or []
        w0 = len(head)
        if len(set(head)) != w0:
            raise ValueError("重复字段名")
        required = set(ids) | {wc for _, wc in WEIGHTS}
        required |= {"ownhome_20", "race_20", "hispanic_20", "employ_20", "CL_voter_status_20",
                     "CL_2020gvm", "TS_voterstatus_22", "TS_g2022", "TS_voterstatus_24", "TS_g2024",
                     "CC20_410", "CC24_410", "CC20_412", "CC22_412", "CC24_412"}
        required |= {stem + str(y)[2:] for stem in ("pid7_", "tookpost_") for y in PID_YEARS}
        required |= {col for years in ISSUE_COLS.values() for col in years.values()}
        for need in required:
            if need not in head:
                raise ValueError("缺必要列:" + need)
        for row in rdr:
            if len(row) != w0 or None in row or any(v is None for v in row.values()):
                raise ValueError("行宽不一致")
            n += 1
            for k in ids:
                v = _str(row.get(k))
                if v is None or _miss(v):
                    raise ValueError(k + "缺失")
                if v in ids[k]:
                    raise ValueError(k + "重复")
                ids[k].add(v)
            gs = groups(row)
            for g in gs:
                gcount[g] = gcount.get(g, 0) + 1
            wvals = {}
            for wn, wc in WEIGHTS:
                wvals[wn] = weight_number(row.get(wc))
            for m in ("pid", "turnout", "house", "president", "medicare", "drug_price", "immigration"):
                st, yrs = _states(row, m)
                for wn, _ in WEIGHTS:
                    for g in gs:
                        k2 = (g, m, tuple(st), wn)
                        c = agg.get(k2)
                        if c is None:
                            c = [yrs, 0, 0, 0.0, 0.0]
                            agg[k2] = c
                        c[1] += 1
                        wv = wvals[wn]
                        if wv is not None and wv > 0:
                            c[2] += 1
                            c[3] += wv
                            c[4] += wv * wv
    cells = []
    for (g, m, st, wn), (yrs, cn, pn, w, w2) in sorted(agg.items()):
        cells.append({"group": g, "measure": m, "years": list(yrs), "states": list(st), "weight": wn, "n": cn, "positive_n": pn, "w": w, "w2": w2})
    notes = ["组固定2020,不重筛", "matched_no_record仅为档案状态", "总统仅同期票2020/2024", "众院序号逐行查党派", "vv权重仅登记选民敏感性", "权重不能证明流失可忽略"]
    return {"schema_version": SCHEMA_VERSION, "source_sha256": sha, "source_rows": n, "groups": {k: gcount.get(k, 0) for k in ("all", "R_renter_2020", "Latino_employed_2020")}, "cells": cells, "notes": notes}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    out = build(a.csv)
    with open(a.output, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print("source_rows:" + str(out["source_rows"]))
    for k, v in out["groups"].items():
        print(k + ":" + str(v))
    print("cells:" + str(len(out["cells"])))
if __name__ == "__main__":
    main()
