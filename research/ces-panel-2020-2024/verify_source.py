"""离线核验面板输入；只输出审计汇总，不输出任何个人记录。"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MISSING = {"", "NA", "NaN", "."}


def digest(path, algorithm):
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify(raw_dir):
    manifest = json.loads((HERE / "source_manifest.json").read_bytes())
    checks = {}
    for name, meta in manifest["files"].items():
        path = raw_dir / name
        checks[name] = {
            "bytes_match": path.stat().st_size == meta["bytes"],
            "sha256_match": digest(path, "sha256") == meta["sha256"],
            "official_md5_match": digest(path, "md5") == meta["official_md5"],
        }
    if not all(all(item.values()) for item in checks.values()):
        raise ValueError("输入文件校验失败")
    ids = {f"caseid_{year}": Counter() for year in (20, 22, 24)}
    rows = 0
    with (raw_dir / "merged_recontact_2024_vv.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        reader = csv.reader(stream)
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError("存在重复字段名")
        positions = {name: header.index(name) for name in ids}
        for row in reader:
            if len(row) != len(header):
                raise ValueError("CSV行宽不一致")
            rows += 1
            for name, index in positions.items():
                ids[name][row[index]] += 1
    id_audit = {}
    for name, counts in ids.items():
        id_audit[name] = {
            "unique_nonmissing": sum(value not in MISSING for value in counts),
            "missing_n": sum(n for value, n in counts.items() if value in MISSING),
            "duplicate_rows": sum(n - 1 for value, n in counts.items()
                                  if value not in MISSING and n > 1),
        }
    if any(item["missing_n"] or item["duplicate_rows"] for item in id_audit.values()):
        raise ValueError("面板ID缺失或重复")
    header_sha = hashlib.sha256(json.dumps(
        header, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if (rows != manifest["csv"]["rows"]
            or len(header) != manifest["csv"]["columns"]
            or header_sha != manifest["csv"]["header_sha256"]):
        raise ValueError("表头或行列数改变")
    return {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "file_checks": checks, "csv_rows": rows, "csv_columns": len(header),
        "ids": id_audit,
        "identity_scope": "合并表每行的三个波次ID均唯一；跨波对应关系来自官方合并，不要求三列ID数值相等。",
        "status": "通过",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.raw_dir)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(encoded.encode("utf-8"))
    print(encoded, end="")


if __name__ == "__main__":
    main()
