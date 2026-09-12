"""封印核验和只读复算；绝不自动刷新摘要或哈希。"""
import sys
sys.dont_write_bytecode=True
import hashlib,json
from pathlib import Path
OUT=Path(__file__).parent
def validate_seal(base,entries):
    for rel,want in entries.items():
        p=(base/rel).resolve();assert p.is_relative_to(base.resolve()),rel
        assert hashlib.sha256(p.read_bytes()).hexdigest()==want,rel
def main():
    seal=json.loads((OUT/'checksums.json').read_text(encoding='utf8'));validate_seal(OUT,seal['artifacts'])
    root=OUT.parents[1];validate_seal(root,seal['local_inputs'])
    from verify import check
    from report import render
    result=check();assert (OUT/'report.md').read_text(encoding='utf8')==render()
    print(json.dumps({'passed':True,'artifacts':len(seal['artifacts']),'local_inputs':len(seal['local_inputs']),'verification':result},ensure_ascii=False))
if __name__=='__main__':main()
