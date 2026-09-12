"""确定性文件与基线编码工具。"""
import hashlib,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
GROUPS=('all','Latino_employed_2020','R_renter_2020')
COHORTS=('full','retained','omitted')
MISS={'','NA','N/A','NAN','NULL','.'}
def encode(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
def write(p,v):Path(p).write_bytes(encode(v))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def num(s):
    if str(s).strip().upper() in MISS:return None
    try:x=float(s)
    except (TypeError,ValueError):raise ValueError('数值编码非法') from None
    if not math.isfinite(x):raise ValueError('数值非有限')
    return x
def category(s,allowed):
    x=num(s)
    if x is None:return None
    if not x.is_integer() or int(x) not in allowed:raise ValueError('类别编码未核定')
    return int(x)
def pid(s):
    p=category(s,range(1,9))
    return 'missing' if p is None else 'D' if p<=3 else 'I' if p==4 else 'R' if p<=7 else 'not_sure'
def groups_from_flags(l,r):return ['all']+(['Latino_employed_2020'] if l else [])+(['R_renter_2020'] if r else [])
