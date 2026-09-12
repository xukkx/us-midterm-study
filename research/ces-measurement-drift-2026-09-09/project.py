"""原件到PID/各政策联合轨迹与原8码；只公开匿名人数。"""
import argparse,csv,hashlib,itertools,json
from collections import Counter
from pathlib import Path
from common import HERE,write,encode,sha,pid,groups
ITEMS={'medicare_single_payer':['CC20_327a','CC22_327a','RC24_327a'],'drug_price_negotiation':['CC20_327b','CC22_327b','RC24_327b'],'conditional_legalization':['CC20_331a','CC22_331a','CC24_331a']}
def read(path,fields):
 with path.open(encoding='utf-8-sig',newline='') as f:
  rd=csv.reader(f);h=next(rd)
  if len(h)!=len(set(h)) or not set(fields)<=set(h):raise ValueError('表头重复或缺字段')
  indices={c:h.index(c) for c in fields}
  for line in rd:
   if len(line)!=len(h):raise ValueError('行宽不符')
   yield {k:line[i].strip() for k,i in indices.items()}
def policy_code(x):
 if x in ('','NA','NaN'):return 0
 if x not in ('1','2'):raise ValueError('未核定政策原码')
 return 2 if x=='1' else 1
def path_group(y):return 'stable' if y[0]==y[1]==y[2] else 'return' if y[0]==y[2] else 'nonreturn_change'
def project(root):
 path=root/'midterm-model/data/raw/ces/panel-2020-2024/merged_recontact_2024_vv.csv';assert sha(path)=='e9921d391159cf8fcb68a0b69aa76c94a5bf73436f516606bf3fb310125ba5ac'
 fields=['caseid_20','caseid_22','caseid_24','pid7_20','pid7_22','pid7_24','race_20','hispanic_20','employ_20','ownhome_20','tookpost_20','tookpost_22','tookpost_24']+[c for cols in ITEMS.values() for c in cols]
 old=json.loads((HERE/'lh265-source.json').read_bytes());counts={g:[0]*64 for g in old['counts']};folds=[[0]*64 for _ in range(5)];raw=[0]*512;rawfold=[[0]*512 for _ in range(5)];joint={key:[[0]*27 for _ in range(64)] for key in ITEMS};seen=[set(),set(),set()];phase={key:{year:Counter() for year in ['20','22','24']} for key in ['PID',*ITEMS]};rawcodes={t:Counter() for t in ['20','22','24']}
 for r in read(path,fields):
  for k,col in enumerate(['caseid_20','caseid_22','caseid_24']):
   if not r[col] or r[col]=='NA' or r[col] in seen[k]:raise ValueError('连接键空或重复')
   seen[k].add(r[col])
  y=tuple(pid(r['pid7_'+t]) for t in ['20','22','24'])
  if None in y:raise ValueError('PID缺失需重新界定目标')
  idx=16*y[0]+4*y[1]+y[2];codes=[int(r['pid7_'+t])-1 for t in ['20','22','24']];idx8=64*codes[0]+8*codes[1]+codes[2];fold=int.from_bytes(hashlib.sha256(('LH265|'+r['caseid_20']).encode()).digest()[:8],'big')%5
  for g in groups(r):counts[g][idx]+=1
  folds[fold][idx]+=1;raw[idx8]+=1;rawfold[fold][idx8]+=1
  for t in ['20','22','24']:
   rawcodes[t][r['pid7_'+t]]+=1;phase['PID'][t][r['tookpost_'+t]+':known']+=1
  for key,cols in ITEMS.items():
   v=[policy_code(r[col]) for col in cols];joint[key][idx][v[0]*9+v[1]*3+v[2]]+=1
   for t,value in zip(['20','22','24'],v):
    if r['tookpost_'+t] not in ('1','2'):raise ValueError('未核定选后问卷参与码')
    phase[key][t][r['tookpost_'+t]+(':'+('known' if value else 'missing'))]+=1
 assert len(seen[0])==6175 and counts==old['counts'] and folds==old['fold_counts']
 return {'n':6175,'states':['D','I','R','not_sure'],'policy_states':['unknown','oppose','support'],'policy_fields':ITEMS,'joint_counts':joint,'counts':counts,'fold_counts':folds,'raw8_counts':raw,'raw8_fold_counts':rawfold,'raw_code_counts':rawcodes,'post_participation_by_known_response':phase,'tookpost_codes':{'1':'未参加选后问卷','2':'参加选后问卷'},'source_sha256':sha(path),'old_projection_exactly_matched':True,'no_person_records':True}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--check',action='store_true');a=ap.parse_args();r=project(a.root)
 if a.check:assert (HERE/'joint-trajectories.json').read_bytes()==encode(r)
 else:write(HERE/'joint-trajectories.json',r)
 print(json.dumps({'n':r['n'],'old_projection_exactly_matched':True,'raw8':sum(r['raw8_counts']),'policy_totals':{k:sum(map(sum,v)) for k,v in r['joint_counts'].items()}}))
