"""匿名轨迹重现全部回溯模型、整人验证和轮廓似然。"""
import argparse,csv,json,math
from datetime import datetime,timezone
from common import HERE,write,encode,sha
from models import *
from algebra import rank,mm,transpose,condition_inf,maxerr
from foundation import equivalent

def evaluate(counts,p):
 n=sum(counts);marg=[sum(p[4*j:4*j+4]) for j in range(16)]
 joint_score=likelihood(counts,p)/n
 conditional=sum(c*math.log(max(q/max(marg[i//4],1e-300),1e-300)) for i,(c,q) in enumerate(zip(counts,p)) if c)/n
 return {'n':n,'joint_log_score':joint_score,'last_wave_conditional_log_score':conditional}
def fit_set(counts,seed,starts,it,tol):
 fits={'observed_markov':fit_observed(counts)}
 for k in [3,4]:
  h=fit_hmm(counts,k,seed+k,starts=starts,iterations=it,tol=tol);p=tensor(h['model']);h['probabilities']=p;h['latent']=latent_summary(h['model'])
  e=h['model']['E'];h['rank']={key:rank(h['model'][key]) for key in ['E','T01','T12']};h['gram_condition_inf']=condition_inf(mm(e,transpose(e)))
  mapped=static_map(h['model']);h['static_equivalence_max_error']=max(abs(a-b) for a,b in zip(p,static_tensor(mapped)));h['static_equivalence_witness']=mapped;fits[f'hmm{k}']=h
  s=fit_static(counts,k,seed+k,starts=starts,iterations=it,tol=tol,extra=mapped);s['probabilities']=static_tensor(s['model']);fits[f'static{k}']=s
 for f in fits.values():
  f['observed_summary']=summary(f['probabilities']);f['observed_TV']=sum(abs(n/sum(counts)-p) for n,p in zip(counts,f['probabilities']))/2
 return fits
def analyze():
 plan=json.loads((HERE/'analysis-plan.json').read_bytes());data=json.loads((HERE/'trajectories.json').read_bytes());c=data['counts']['all'];n=sum(c)
 gate=json.loads((HERE/'exact-results.json').read_bytes());sim=json.loads((HERE/'recovery-results.json').read_bytes())
 if not gate['passed'] or len(gate['cases'])!=50 or sim['replications']!=96:raise ValueError('必须先完成精确构造和96次恢复模拟')
 settings=plan['fit'];fits=fit_set(c,settings['seed'],settings['starts'],settings['iterations'],settings['tolerance_per_person']);print('全体模型已拟合',flush=True)
 cv=[]
 for fold,test in enumerate(data['fold_counts']):
  train=[a-b for a,b in zip(c,test)];f=fit_set(train,settings['seed']+10000+fold*100,settings['cv_starts'],settings['iterations'],settings['tolerance_per_person'])
  for name,fit in f.items():cv.append({'fold':fold,'model':name,**evaluate(test,fit['probabilities']),'converged':fit.get('converged',True),'fit_loglik':fit['loglik'],'starts':fit.get('starts',[]),'probabilities':fit['probabilities']})
  print(json.dumps({'cv_fold_done':fold}),flush=True)
 profile=[]
 for g in plan['profile']['grid']:
  f=fit_hmm(c,3,settings['seed']+30000,starts=plan['profile']['starts'],iterations=settings['iterations'],tol=settings['tolerance_per_person'],gross=g,extra=fits['hmm3']['model'])
  profile.append({'gross01':g,'loglik':f['loglik'],'converged':f['converged'],'iterations':f['iterations'],'constraint_error':abs(latent_summary(f['model'])['gross01']-g),'starts':f['starts']})
 print('固定网格轮廓已完成',flush=True)
 llref=max([fits['hmm3']['loglik']]+[x['loglik'] for x in profile])
 for row in profile:row['twice_loglik_loss']=2*(llref-row['loglik'])
 observed={g:dict(n=sum(counts),**summary([x/sum(counts) for x in counts])) for g,counts in data['counts'].items()}
 cv_summary={name:{key:sum(r['n']*r[key] for r in cv if r['model']==name)/n for key in ['joint_log_score','last_wave_conditional_log_score']} for name in fits}
 out={'n':n,'fit_settings':settings,'observed':observed,'fits':fits,'cv':cv,'cv_summary':cv_summary,'profile':profile,'profile_unconstrained_ll':fits['hmm3']['loglik'],'profile_better_than_unconstrained':llref>fits['hmm3']['loglik']+1e-6,'gates':{'exact_sha256':sha(HERE/'exact-results.json'),'recovery_sha256':sha(HERE/'recovery-results.json'),'plan_sha256':sha(HERE/'analysis-plan.json'),'trajectories_sha256':sha(HERE/'trajectories.json')},'interpretation':'条件于S=1的三波PID回答模型；拟合是有限多起点近似，不声称全局最优；轮廓与留出评分无人口置信解释。'}
 return out
def tables(r):
 data=json.loads((HERE/'trajectories.json').read_bytes())
 with (HERE/'trajectory-comparison.csv').open('w',encoding='utf-8',newline='') as f:
  wr=csv.writer(f);wr.writerow(['y20','y22','y24','observed_n']+list(r['fits']))
  for i,y in enumerate(SEQ):wr.writerow([*[data['states'][x] for x in y],data['counts']['all'][i],*[r['n']*v['probabilities'][i] for v in r['fits'].values()]])
 with (HERE/'profile.csv').open('w',encoding='utf-8',newline='') as f:
  wr=csv.writer(f);wr.writerow(['gross01','loglik','twice_loglik_loss','converged','constraint_error'])
  for row in r['profile']:wr.writerow([row[k] for k in ['gross01','loglik','twice_loglik_loss','converged','constraint_error']])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=analyze()
 if a.check:assert encode(r)==(HERE/'results.json').read_bytes()
 else:write(HERE/'results.json',r);tables(r)
 reference=json.loads((HERE/'two-wave-reference.json').read_bytes());p=[[x/reference['n'] for x in row] for row in reference['counts']];b=equivalent(p)
 if a.check:assert encode(b)==(HERE/'measurement-results.json').read_bytes()
 else:write(HERE/'measurement-results.json',b)
 print(json.dumps({'n':r['n'],'models':list(r['fits']),'cv':r['cv_summary']},ensure_ascii=False))
