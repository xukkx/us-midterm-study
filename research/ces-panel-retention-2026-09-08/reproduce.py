"""核验新审计封印并从匿名人数逐字节重算结果。"""
import argparse,hashlib,json,sys
from pathlib import Path
from summarize import summarize
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args()
    if sys.version_info[:2]!=(3,12):raise SystemExit('本包逐字节复算使用CPython3.12')
    for name in ('plan-seal.json','fallback-seal.json','data-seal.json'):
        seal=json.loads((HERE/name).read_bytes())
        for rel,digest in seal['files'].items():
            if hashlib.sha256((HERE/rel).read_bytes()).hexdigest()!=digest:raise ValueError('封印不一致:'+rel)
    expected=(json.dumps(summarize(json.loads((HERE/'counts.json').read_bytes())),ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if expected!=(HERE/'results.json').read_bytes():raise ValueError('匿名计数到结果字节不一致')
    print('39行匿名入选构成结果逐字节一致；两波留存仍未计算')

if __name__=='__main__':main()
