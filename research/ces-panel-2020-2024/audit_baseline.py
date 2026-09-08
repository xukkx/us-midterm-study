"""连接年度原件，仅输出面板2020字段的一致性汇总，不输出ID。"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

COLS = ["pid7", "race", "hispanic", "employ", "ownhome", "CC20_410", "CC20_327a"]


def audit(panel_path, annual_path):
    with panel_path.open(encoding="utf-8-sig", newline="") as stream:
        panel = {}
        for row in csv.DictReader(stream):
            key = row["caseid_20"]
            if key in panel or key in ("", "NA"):
                raise ValueError("面板ID重复或缺失")
            panel[key] = {c: row[c if c.startswith("CC20_") else c + "_20"] for c in COLS}
    seen = set()
    mismatch = Counter()
    mother_rows = 0
    with annual_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            mother_rows += 1
            key = row["caseid"]
            if key not in panel:
                continue
            if key in seen:
                raise ValueError("年度来源的对应ID重复")
            seen.add(key)
            for column in COLS:
                if row[column] != panel[key][column]:
                    mismatch[column] += 1
    return {"checked_at": datetime.now(timezone.utc).isoformat(),
            "annual_file": annual_path.name, "annual_sha256": hashlib.sha256(annual_path.read_bytes()).hexdigest(),
            "mother_rows": mother_rows, "panel_rows": len(panel), "matched_ids": len(seen),
            "unmatched_ids": len(panel) - len(seen), "mismatches": {c: mismatch[c] for c in COLS},
            "boundary": "仅核对来源一致性；年度母样本不等于重访邀请框，不能由此算分群流失。"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--annual", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.panel, args.annual)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(text.encode("utf-8"))
    print(text, end="")
