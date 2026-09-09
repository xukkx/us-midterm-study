"""已指定的政策条件校准；不会把置换参考当随机处理。"""
import argparse,itertools,json,math,random
from common import HERE,write,encode,sha
from reference import FixedMargins,distribution,hg_draw,tail_result,holm,cp_interval
GROUPS=['stable','return','nonreturn_change']
def strata(joint):
 tables={}
 for y,row in zip(itertools.product(range(4),repeat=3),joint):
  group=0 if y[0]==y[1]==y[2] else 1 if y[0]==y[2] else 2
  for z,n in zip(itertools.product(range(3),repeat=3),row):
   if not all(z):continue
   key=(y[0],z[0]);tables.setdefault(key,[[0]*4 for _ in range(3)])[group][2*(z[1]-1)+z[2]-1]+=n
 return [{'baseline_PID':key[0],'baseline_policy':key[1],'table':table} for key,table in sorted(tables.items()) if sum(map(sum,table))]
def r1_calibrate(rows,B,seed):
 refs=[FixedMargins(r['table']) for r in rows];N=sum(x.n for x in refs);observed=[sum(ref.statistics_numerator(r['table'])[j] for ref,r in zip(refs,rows))/N for j in range(2)];rng=random.Random(seed);null=[[],[]];hits=[0,0]
 for _ in range(B):
  stats=[ref.statistics_numerator(ref.draw(rng)) for ref in refs]
  for j in range(2):
   value=sum(x[j] for x in stats)/N;null[j].append(value);hits[j]+=value>=observed[j]-1e-12
 return {'complete_n':N,'strata':rows,'statistics':{name:{'observed':observed[j],'null':distribution(null[j]),**tail_result(hits[j],B)} for j,name in enumerate(['MI','TV'])}}
def r2_calibrate(rows,B,seed,probability_family_size):
 cells=[];unsupported=[]
 for r in rows:
  tab=r['table'];nr=sum(tab[1]);ns=sum(tab[0]);event=2*(2-r['baseline_policy'])+r['baseline_policy']-1;ar=tab[1][event];ass=tab[0][event]
  if not nr or not ns:unsupported.append({'baseline_PID':r['baseline_PID'],'baseline_policy':r['baseline_policy'],'return_n':nr,'stable_n':ns});continue
  cr=cp_interval(ar,nr,.05/probability_family_size);cs=cp_interval(ass,ns,.05/probability_family_size)
  cells.append({'baseline_PID':r['baseline_PID'],'baseline_policy':r['baseline_policy'],'return_n':nr,'return_events':ar,'stable_n':ns,'stable_events':ass,'difference':ar/nr-ass/ns,'simultaneous_difference_interval':[cr[0]-cs[1],cr[1]-cs[0]],'return_probability_interval':cr,'stable_probability_interval':cs})
 total=sum(r['return_n'] for r in cells);obs=sum(r['return_n']/total*r['difference'] for r in cells);base=sum(r['return_n']/total*r['stable_events']/r['stable_n'] for r in cells);interval=[sum(r['return_n']/total*r['simultaneous_difference_interval'][j] for r in cells) for j in range(2)];rng=random.Random(seed);null=[];hits=0
 for _ in range(B):
  value=0.
  for r in cells:
   nr,ns=r['return_n'],r['stable_n'];events=r['return_events']+r['stable_events'];x=hg_draw(rng,nr+ns,events,nr);value+=nr/total*(x/nr-(events-x)/ns)
  null.append(value);hits+=abs(value)>=abs(obs)-1e-12
 return {'hypothesis_version':'R2_eq_average_statistic_v1','null':'每层等概率；不是只要求标准化平均为零','complete_return_n':total,'strata':cells,'unsupported_strata':unsupported,'observed_average_difference':obs,'reference_stable_return_rate':base,'materiality_epsilon':base*.5,'simultaneous_average_interval':interval,'all_supported_strata_nonnegative_lower_bound':all(r['simultaneous_difference_interval'][0]>=0 for r in cells),'any_supported_stratum_negative_upper_bound':any(r['simultaneous_difference_interval'][1]<0 for r in cells),'null_distribution':distribution(null),**tail_result(hits,B)}
def run():
 plan=json.loads((HERE/'analysis-plan.json').read_bytes());data=json.loads((HERE/'lh266-joint-trajectories.json').read_bytes());old=json.loads((HERE/'lh266-policy-results.json').read_bytes());itemrows={item:strata(data['joint_counts'][item]) for item in plan['items']};family=sum(2 for rows in itemrows.values() for r in rows if sum(r['table'][0]) and sum(r['table'][1]));assert family==36;results={}
 for i,item in enumerate(plan['items']):
  a=r1_calibrate(itemrows[item],plan['R1']['B'],plan['seed']+i*100);b=r2_calibrate(itemrows[item],plan['R2']['B'],plan['seed']+i*100+1,family);source=old['items'][item]
  assert abs(a['statistics']['MI']['observed']-source['restriction_1']['empirical_conditional_mutual_information_nats'])<1e-12
  assert abs(a['statistics']['TV']['observed']-source['restriction_1']['weighted_empirical_TV_departure'])<1e-12
  assert abs(b['observed_average_difference']-source['restriction_2']['standardized_difference'])<1e-12
  a['materiality_TV_scale']=.5*sum(r['policy_return_n'] for r in source['path_rows'])/a['complete_n'];results[item]={'R1':a,'R2':b};print(json.dumps({'item':item,'R1_MI_p':a['statistics']['MI']['p_plus_one'],'R1_TV_p':a['statistics']['TV']['p_plus_one'],'R2_p':b['p_plus_one']}),flush=True)
 tests=[(item,target,results[item]['R1']['statistics']['MI'] if target=='R1' else results[item]['R2']) for target in ['R1','R2'] for item in plan['items']];adjusted=holm([r['p_plus_one'] for _,_,r in tests]);low=holm([r['MC_Wilson95'][0] for _,_,r in tests]);high=holm([r['MC_Wilson95'][1] for _,_,r in tests])
 for (item,target,r),a,l,u in zip(tests,adjusted,low,high):r.update(Holm_primary_six=a,Holm_MC_endpoint_sensitivity=[l,u])
 for target in ['R1','R2']:
  records=[r for _,t,r in tests if t==target]
  for r,a in zip(records,holm([r['p_plus_one'] for r in records])):r['Holm_three_diagnostic']=a
 return {'items':results,'simultaneous_probability_family':family,'simultaneous_error_budget':.05,'plan_sha256':sha(HERE/'analysis-plan.json'),'source_sha256':sha(HERE/'lh266-joint-trajectories.json'),'interpretation':'条件可交换或另述Bernoulli参考，有限保留人群；并非随机处理或全国调查设计推断。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'policy-calibration.json').read_bytes()==encode(r)
 else:write(HERE/'policy-calibration.json',r)
