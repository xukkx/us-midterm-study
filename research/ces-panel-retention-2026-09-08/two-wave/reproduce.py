"""离线核验事前计划与新数据封印，并从匿名人数复算。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from two_wave import summarize_counts

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true', required=True)
    p.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('本包逐字节复算使用 CPython 3.12')
    for base, name in ((HERE.parent, 'plan-seal.json'), (HERE, 'data-seal.json')):
        seal = json.loads((base / name).read_bytes())
        for rel, digest in seal['files'].items():
            if hashlib.sha256((base / rel).read_bytes()).hexdigest() != digest:
                raise ValueError('封印不一致：' + rel)
    counts = json.loads((HERE / 'counts.json').read_bytes())
    encoded = (json.dumps(summarize_counts(counts), ensure_ascii=False,
                         sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if encoded != (HERE / 'results.json').read_bytes():
        raise ValueError('匿名人数复算字节不一致')
    print('39行两波到三波留存结果逐字节一致；分母为两波发布文件，非完整邀请框')

if __name__ == '__main__':
    main()
