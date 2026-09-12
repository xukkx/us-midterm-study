"""确定性文件与四状态编码。"""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).parent
def encode(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def write(p,x):Path(p).write_bytes(encode(x))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pid(x):
 if x in ('','NA','NaN'):return None
 n=int(x)
 if n not in range(1,9):raise ValueError('意外PID编码')
 return 0 if n<=3 else 1 if n==4 else 2 if n<=7 else 3
def groups(row):return ['all']+(['Latino_employed_2020'] if (row['race_20']=='3' or row['hispanic_20']=='1') and row['employ_20'] in ('1','2') else [])+(['R_renter_2020'] if pid(row['pid7_20'])==2 and row['ownhome_20']=='2' else [])
