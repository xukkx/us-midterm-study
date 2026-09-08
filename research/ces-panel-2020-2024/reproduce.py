"""从公开匿名充分统计复算；持有官方CSV时还可核验完整提取。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from analyze_panel import main as analyze_main
from panel_core import build

HERE = Path(__file__).resolve().parent


def check_seal(name):
    seal = json.loads((HERE / name).read_bytes())
    for relative, expected in seal["files"].items():
        path = (HERE / relative).resolve()
        if not path.is_relative_to(HERE):
            raise ValueError("封印包含目录外路径")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("封印不一致: " + relative)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--raw-csv", type=Path)
    args = parser.parse_args()
    if not args.check:
        parser.error("本入口只核验，请提供--check")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("逐字节复算需CPython 3.12，与本公开包既有运行时一致")
    check_seal("analysis-plan-seal.json")
    check_seal("data-seal.json")
    if args.raw_csv:
        meta = json.loads((HERE / "source_manifest.json").read_bytes())
        digest = hashlib.sha256()
        with args.raw_csv.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != meta["files"]["merged_recontact_2024_vv.csv"]["sha256"]:
            raise ValueError("原始CSV不是已核定官方版本")
        cells = build(args.raw_csv)
        encoded = (json.dumps(cells, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if encoded != (HERE / "cells.json").read_bytes():
            raise ValueError("原始CSV到充分统计的复算不一致")
        print("官方CSV到匿名充分统计：逐字节一致")
    return analyze_main(["--cells", str(HERE / "cells.json"), "--output", str(HERE / "results.json"), "--check"])


if __name__ == "__main__":
    raise SystemExit(main())
