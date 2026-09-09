"""逐题、逐字面路径的描述性反证；不估计PID变化的因果效应。"""
import argparse,itertools,json,math
from common import HERE,write,encode,sha
from project import path_group
PID=list(itertools.product(range(4),repeat=3));POL=list(itertools.product(range(3),repeat=3));GROUPS=['stable','return','nonreturn_change']
def summarize(joint):
 rows=[];strata={}
 for group in GROUPS:
  cells=[(y,z,n) for y,row in zip(PID,joint) for z,n in zip(POL,row) if path_group(y)==group and n];total=sum(n for y,z,n in cells);complete=[(y,z,n) for y,z,n in cells if 0 not in z];nc=sum(n for y,z,n in complete)
  r={'PID_path_group':group,'retained_n':total,'policy_complete_n':nc,'missing_any_n':total-nc,'policy_stable_n':sum(n for y,z,n in complete if z[0]==z[1]==z[2]),'policy_return_n':sum(n for y,z,n in complete if z[0]==z[2] and z[0]!=z[1]),'intervals':{}}
  for t in [0,1]:
   pairs=[(y,z,n) for y,z,n in cells if z[t] and z[t+1]]
   r['intervals'][str(t)]={'triple_complete_denominator':nc,'oppose_to_support_n':sum(n for y,z,n in complete if z[t]==1 and z[t+1]==2),'support_to_oppose_n':sum(n for y,z,n in complete if z[t]==2 and z[t+1]==1),'pair_known_denominator':sum(n for y,z,n in pairs),'pair_oppose_to_support_n':sum(n for y,z,n in pairs if z[t]==1 and z[t+1]==2),'pair_support_to_oppose_n':sum(n for y,z,n in pairs if z[t]==2 and z[t+1]==1)}
  for y,z,n in complete:
   key=(y[0],z[0]);future=(z[1]-1)*2+z[2]-1;strata.setdefault(key,{g:[0]*4 for g in GROUPS})[group][future]+=n
  rows.append(r)
 N=sum(r['policy_complete_n'] for r in rows);cmi=0.;weighted_tv=0.;contrasts=[]
 for (baseline_pid,baseline_policy),groups in sorted(strata.items()):
  totals=[sum(v[i] for v in groups.values()) for i in range(4)];n=sum(totals)
  for g,v in groups.items():
   ng=sum(v)
   if not ng:continue
   weighted_tv+=ng/N*sum(abs(v[i]/ng-totals[i]/n) for i in range(4))/2
   for i,ni in enumerate(v):
    if ni:cmi+=ni/N*math.log(ni*n/(ng*totals[i]))
  v=groups['return'];s=groups['stable'];nr=sum(v);ns=sum(s);target=((2 if baseline_policy==1 else 1)-1)*2+(baseline_policy-1)
  contrasts.append({'baseline_pid':baseline_pid,'baseline_policy':baseline_policy,'return_group_n':nr,'stable_group_n':ns,'return_group_policy_returns':v[target],'stable_group_policy_returns':s[target],'difference':v[target]/nr-s[target]/ns if nr and ns else None})
 eligible=[r for r in contrasts if r['difference'] is not None];den=sum(r['return_group_n'] for r in eligible);all_returns=sum(r['return_group_n'] for r in contrasts)
 return {'path_rows':rows,'restriction_1':{'name':'给定PID20和政策20后，政策22/24联合分布与完成PID路径组条件独立','empirical_conditional_mutual_information_nats':cmi,'weighted_empirical_TV_departure':weighted_tv,'interpretation':'有限样本经验差异，插件MI有向上偏差，不是p值或一般标签噪声模型的否定'},'restriction_2':{'name':'给定基线后，PID返回者在该政策上也返回的比例不低于PID稳定者','strata':contrasts,'return_population_with_stable_comparator_n':den,'return_population_complete_n':all_returns,'standardized_difference':sum(r['return_group_n']*r['difference'] for r in eligible)/den if den else None,'weights':'PID返回组的基线PID×基线政策构成；只对有稳定组对照的层；非因果标准化'}}
def run():
 data=json.loads((HERE/'joint-trajectories.json').read_bytes());return {'n':data['n'],'items':{k:summarize(v) for k,v in data['joint_counts'].items()},'source_sha256':sha(HERE/'joint-trajectories.json'),'scope':'政策分开作观察结果；保留缺失，不拼成意识形态量表，不用政策验证自身构造的潜得分。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'policy-results.json').read_bytes()==encode(r)
 else:write(HERE/'policy-results.json',r)
 print(json.dumps({k:{g['PID_path_group']:{q:g[q] for q in ['retained_n','policy_complete_n','policy_stable_n','policy_return_n']} for g in v['path_rows']} for k,v in r['items'].items()},ensure_ascii=False))
