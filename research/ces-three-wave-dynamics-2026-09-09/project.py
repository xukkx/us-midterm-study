"""本地原件到匿名64轨迹；无逐人资料进入输出。"""
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path
from common import HERE,sha,write,pid,groups
from models import SEQ
def read(path,fields):
 with path.open(encoding='utf-8-sig',newline='') as f:
  rd=csv.reader(f);h=next(rd)
  if len(h)!=len(set(h)) or not set(fields)<=set(h):raise ValueError('重复或缺失表头')
  ix={c:h.index(c) for c in fields}
  for row in rd:
   if len(row)!=len(h):raise ValueError('行宽不一致')
   yield {c:row[i].strip() for c,i in ix.items()}
def project(root):
 raw=root/'midterm-model/data/raw/ces';p2=raw/'panel-2020-2022/merged_recontact.csv';p3=raw/'panel-2020-2024/merged_recontact_2024_vv.csv'
 assert sha(p2)=='ee5ff210d535fc8e4443c98f967beee6e9e0da9995e4a502ae682a5bd2d33565'
 assert sha(p3)=='e9921d391159cf8fcb68a0b69aa76c94a5bf73436f516606bf3fb310125ba5ac'
 fields=['pid7_20','race_20','hispanic_20','employ_20','ownhome_20','CC20_410','CC20_327a','caseid_22','pid7_22']
 vm_path=root/'research/ces-panel-2020-2024/variable_map.json';vm=json.loads(vm_path.read_bytes())
 policy_cols=sorted({c for item in vm['issues'] for c in item['cols'].values()})
 rows2=list(read(p2,['caseid']+fields));base={r['caseid']:r for r in rows2};assert len(base)==len(rows2)==11009
 rows=list(read(p3,sorted(set(['caseid_20','caseid_24','pid7_24']+fields+policy_cols))))
 assert len(rows)==6175 and len({r['caseid_20'] for r in rows})==6175
 names=['all','Latino_employed_2020','R_renter_2020'];table={g:[0]*64 for g in names};folds=[[0]*64 for _ in range(5)];den={g:Counter() for g in names}
 for r in rows:
  prev=base[r['caseid_20']];assert all(r[f]==prev[f] for f in fields)
  y=tuple(pid(r[f'pid7_{t}']) for t in ('20','22','24'))
  for g in groups(r):
   den[g]['retained']+=1;den[g]['complete']+=int(None not in y);den[g]['not_sure_any']+=int(3 in y)
   if None not in y:table[g][16*y[0]+4*y[1]+y[2]]+=1
  if None not in y:
   fold=int.from_bytes(hashlib.sha256(('LH265|'+r['caseid_20']).encode()).digest()[:8],'big')%5
   folds[fold][16*y[0]+4*y[1]+y[2]]+=1
 for r in rows2:
  for g in groups(r):den[g]['two_wave']+=1
 for g in names:den[g]['missing_pid_any']=den[g]['retained']-den[g]['complete']
 policies=[]
 for item in vm['issues']:
  q=dict(item);q['timing']='2020、2022、2024面板相应年度提问，题干沿用既有变量表40、42页核验；精确施测日期与RC题块阶段本轮未另核定，进入多指标模型前必须补齐。';q['measurement_status']='候选实质态度，尚未验证与PID的条件独立或跨波测量稳定性'
  q['response_counts']={str(t):dict(Counter(r[col] for r in rows)) for t,col in item['cols'].items()};q['complete_binary_n']=sum(all(r[col] in ('1','2') for col in item['cols'].values()) for r in rows) if item['comparable_years'] else None
  policies.append(q)
 out={'states':['D','I','R','not_sure'],'sequences':[list(y) for y in SEQ],'counts':table,'fold_counts':folds,'denominators':den,'sources':{'two_wave_sha256':sha(p2),'three_wave_sha256':sha(p3),'variable_map_sha256':sha(vm_path)},'linkage_checks':{'unique_ids':6175,'baseline_and_2022_fields':fields,'all_agree':True},'fold_rule':'SHA256(UTF8("LH265|"+caseid20))前8字节大端mod5，整人同折'}
 return out,{'source_variable_map_sha256':sha(vm_path),'items':policies,'PID':'pid7_20/22/24，每波1—8映射D/I/R/不确定；三波各6175非缺失，派生PID4与PID7非独立指标。','future_gate':'逐题量表方向与构念、局部依赖、同波独立复测/外部锚需另外核定；本轮不拟合多指标模型。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--check',action='store_true');a=ap.parse_args();out,inventory=project(a.root)
 from common import encode
 for name,value in [('trajectories.json',out),('indicator-inventory.json',inventory)]:
  if a.check:assert (HERE/name).read_bytes()==encode(value)
  else:write(HERE/name,value)
 print(json.dumps({'retained':6175,'denominators':out['denominators'],'raw_verified':True},ensure_ascii=False))
