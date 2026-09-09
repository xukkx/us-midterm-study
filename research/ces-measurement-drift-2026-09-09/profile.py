"""有界可行搜索：达到的条件范围，不给全局最优或置信认证。"""
import argparse,json,random,copy,math
from common import HERE,write,encode,sha
from drift_model import *
from equivalence import point

def proposal(m,counts,delta,zero=False):
 k=len(m['Q']);q=m['Q'];u=m['U'];e0,e1,e2=m['E'];cq=[[0.]*k for _ in range(k)];cu=[[0.]*k for _ in range(k)];ce=[[[0.]*4 for _ in range(k)] for _ in range(3)]
 for (a,b,c),n in zip(SEQ,counts):
  if not n:continue
  h=[sum(u[j][l]*e2[l][c] for l in range(k)) for j in range(k)]
  x=[[q[i][j]*e0[i][a]*e1[j][b]*h[j] for j in range(k)] for i in range(k)];p=sum(map(sum,x))
  if p<=0:raise ValueError('正频数序列概率为零')
  f=[sum(q[i][j]*e0[i][a] for i in range(k))*e1[j][b] for j in range(k)];z=[[f[j]*u[j][l]*e2[l][c] for l in range(k)] for j in range(k)];scale=n/p
  for i in range(k):
   ce[0][i][a]+=scale*sum(x[i]);ce[1][i][b]+=scale*sum(z[i]);ce[2][i][c]+=scale*sum(z[j][i] for j in range(k))
   for j in range(k):cq[i][j]+=scale*x[i][j];cu[i][j]+=scale*z[i][j]
 total=sum(counts)
 if zero:
  mass=normalize([cq[i][i] for i in range(k)]);qp=diag(mass);up=eye(k)
 else:
  qp=[[v/total for v in row] for row in cq];up=[normalize(row) if sum(row) else u[i][:] for i,row in enumerate(cu)]
 raw=[[normalize(row) if sum(row) else m['E'][t][j][:] for j,row in enumerate(ce[t])] for t in range(3)]
 weights=[[sum(row) for row in mat] for mat in ce]
 # 未得到后验质量的类别不参与中心的权重；全空类别使用相同权。
 for j in range(k):
  if sum(weights[t][j] for t in range(3))==0:
   for t in range(3):weights[t][j]=1.
 ep=shrink_emissions(raw,delta,weights)
 return {'Q':qp,'U':up,'E':ep}

def fit(m,counts,delta,iterations=160,zero=False):
 m=copy.deepcopy(m);m['E']=shrink_emissions(m['E'],delta)
 if zero:m['Q']=diag(normalize(middle(m)));m['U']=eye(len(m['Q']))
 if not feasible(m,delta):raise ValueError('起点不合规')
 ll=loglik(counts,probabilities(m));history=[ll];status='iteration_limit';halvings=0
 for it in range(iterations):
  candidate=proposal(m,counts,delta,zero);accepted=None
  for power in range(16):
   step=2.**(-power);c=blend(m,candidate,step)
   if not feasible(c,delta):continue
   newll=loglik(counts,probabilities(c))
   if newll>=ll-1e-8:accepted=(c,newll);halvings+=power;break
  if accepted is None:status='no_ascent_proposal';break
  c,newll=accepted;gain=newll-ll;m=c;ll=newll;history.append(ll)
  if gain/sum(counts)<1e-8:status='small_gain';break
 return {'model':m,'loglik':ll,'iterations':it+1,'stop':status,'backtrack_halvings':halvings,'monotone':all(y>=x-1e-8 for x,y in zip(history,history[1:])),'max_delta_violation':max(0.,drift_metrics(m['E'],middle(m))['maximum']-delta),'KKT_verified':False}

def transfer(row,a,b,step):
 amount=min(step,row[a])
 if amount==0:return False
 row[a]-=amount;row[b]+=amount;return True
def perturb(m,rng,step,which,delta):
 c=copy.deepcopy(m);k=len(c['Q'])
 if which==0:
  a,b=rng.sample(range(k*k),2);i,j=divmod(a,k);s,t=divmod(b,k);amount=min(step,c['Q'][i][j]);c['Q'][i][j]-=amount;c['Q'][s][t]+=amount
 elif which==1:
  i=rng.randrange(k);a,b=rng.sample(range(k),2);transfer(c['U'][i],a,b,step)
 elif which in [2,3]:
  i=rng.randrange(k);a,b=rng.sample(range(4),2)
  if which==2 or delta==0:
   amount=min(step,min(c['E'][t][i][a] for t in range(3)))
   for t in range(3):c['E'][t][i][a]-=amount;c['E'][t][i][b]+=amount
  else:transfer(c['E'][rng.randrange(3)][i],a,b,step)
 else:
  # 协同改变持续性，可同时移动首段非对角质量与后段转移。
  sign=-1 if which==4 else 1
  for i in range(k):
   j=rng.choice([j for j in range(k) if j!=i]);amount=min(step/k,c['Q'][i][j] if sign<0 else c['Q'][i][i]);c['Q'][i][j]+=sign*amount;c['Q'][i][i]-=sign*amount
   transfer(c['U'][i],j if sign<0 else i,i if sign<0 else j,step)
 return c

def extreme(start,counts,delta,threshold,target,direction,seed,settings):
 m=copy.deepcopy(start);ll=loglik(counts,probabilities(m));score=direction*gross(m)[target];rng=random.Random(seed);evaluated=0;rejected=0;accepted=0
 if not feasible(m,delta) or ll<threshold-1e-7:raise ValueError('范围搜索的起点不满足固定拟合要求')
 for step in settings['pattern_steps']:
  for sweep in range(settings['pattern_sweeps']):
   for trial in range(settings['pattern_proposals_per_sweep']):
    c=perturb(m,rng,step,trial%6,delta);evaluated+=1
    if not feasible(c,delta):rejected+=1;continue
    newscore=direction*gross(c)[target]
    if newscore<=score+1e-12:continue
    newll=loglik(counts,probabilities(c))
    if newll<threshold-1e-7:rejected+=1;continue
    m=c;ll=newll;score=newscore;accepted+=1
 return {'model':m,'loglik':ll,'targets':gross(m),'evaluated':evaluated,'rejected_constraints':rejected,'accepted_moves':accepted,'stop':'fixed_evaluation_budget','status':'locally_searched_attained_extreme','certified_global_bound':False,'stationarity_verified':False}

def zero_start(base,delta):
 k=len(base['Q']);s={'Q':diag(middle(base)),'U':eye(k),'E':copy.deepcopy(base['E'])};s['E']=shrink_emissions(s['E'],delta);return s

def run():
 plan=json.loads((HERE/'analysis-plan.json').read_bytes());settings=plan['solver'];src=json.loads((HERE/'lh265-source.json').read_bytes());path=json.loads((HERE/'equivalence-results.json').read_bytes());counts=src['counts']['all'];out={}
 for k in plan['K']:
  name=f'hmm{k}';original=src['models'][name];h=original['model'];base=from_hmm(h);ref=original['loglik'];prior_best=base;prior_zero=zero_start(point(h,1),0);prior_ext={};rows=[];archive=[]
  diverse=[(kind,random_start(k,kind,settings['seed']+k*100+idx)) for idx,kind in enumerate(settings['initializations'][1:])]
  for index,delta in enumerate(plan['delta_grid']):
   candidates=[('frozen',base),('prior_delta',prior_best)]+diverse
   candidates += [('equivalent_path',p['model']) for p in path['models'][name]['rows'] if p.get('feasible') and p['drift']['maximum']<=delta+1e-10 and (int(round(100*p['lambda']))%25==0)]
   # 在每个上限处加入一项解析lambda候选，不把101点离散化当物理边界。
   end_d=path['models'][name]['rows'][-1]['drift']['maximum'];lam=min(1.,delta/end_d) if end_d else 0.
   exact=point(h,lam)
   if feasible(exact,delta):candidates.append(('boundary_path_witness',exact))
   fits=[];pool=[]
   for label,start in candidates:
    if feasible(start,delta):pool.append(start)
    f=fit(start,counts,delta,settings['em_iterations']);pool.append(f['model']);fits.append({key:value for key,value in f.items() if key!='model'}|{'start':label})
   best=max(pool,key=lambda m:loglik(counts,probabilities(m)));prior_best=best;bestll=loglik(counts,probabilities(best))
   zfits=[]
   for label,start in [('frozen_common',zero_start(base,delta)),('exact_static_shrunk',zero_start(point(h,1),delta)),('prior_zero',prior_zero)]:
    z=fit(start,counts,delta,settings['em_iterations'],zero=True);zfits.append(z|{'start':label})
   z=max(zfits,key=lambda x:x['loglik']);prior_zero=z['model'];pool.append(z['model'])
   pool+=archive;extremes=[];current_ext={}
   for tau in plan['fit_tolerances']:
    threshold=ref-tau
    for objective in settings['extremes']:
     target,side=objective.rsplit('_',1);direction=-1 if side=='min' else 1;key=(tau,objective)
     options=[m for m in pool if feasible(m,delta) and loglik(counts,probabilities(m))>=threshold-1e-7]
     if key in prior_ext:options.append(prior_ext[key])
     options.sort(key=lambda m:direction*gross(m)[target],reverse=True);starts=options[:settings['extreme_starts']]
     if not starts:
      extremes.append({'tau':tau,'objective':objective,'status':'no_feasible_witness_found','certified_empty_set':False});continue
     attained=[extreme(m,counts,delta,threshold,target,direction,settings['seed']+k*10000+index*100+int(tau)*10+j,settings) for j,m in enumerate(starts)]
     win=max(attained,key=lambda x:direction*x['targets'][target]);model=win['model'];pool.append(model);current_ext[key]=model
     result={'tau':tau,'objective':objective,**audit(model,counts),'status':win['status'],'search':[{key:value for key,value in a.items() if key not in ('model','targets')} for a in attained],'fit_threshold':threshold,'fit_slack':win['loglik']-threshold,'nested_from_previous':key not in prior_ext or direction*gross(model)[target]>=direction*gross(prior_ext[key])[target]-1e-10}
     extremes.append(result)
   prior_ext=current_ext;archive=list(current_ext.values())
   row={'delta':delta,'best_likelihood':audit(best,counts),'likelihood_starts':fits,'zero_change_best':audit(z['model'],counts),'zero_starts':[{key:value for key,value in f.items() if key!='model'} for f in zfits],'zero_change_fit_by_tau':{str(tau):z['loglik']>=ref-tau-1e-7 for tau in plan['fit_tolerances']},'extremes':extremes,'optimization_warning':{'uncertified_global_search':True,'best_likelihood_decreased':bool(rows and bestll<rows[-1]['best_likelihood']['loglik']-1e-7),'nested_extreme_failure':any(not x.get('nested_from_previous',True) for x in extremes)}}
   rows.append(row);print(json.dumps({'profile_done':name,'delta':delta,'loglik':bestll,'zero_loglik':z['loglik']}),flush=True)
  out[name]={'fixed_reference_loglik':ref,'rows':rows,'source_same_emission_delta0_loglik_difference':rows[0]['best_likelihood']['loglik']-ref,'global_bounds_certified':False}
 return {'models':out,'plan_sha256':sha(HERE/'analysis-plan.json'),'path_sha256':sha(HERE/'equivalence-results.json'),'interpretation':'固定参考似然下的达到可行范围与有界局部搜索；拟合和漂移容差分开；没找到不是空集；无95%解释。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'profile-results.json').read_bytes()==encode(r)
 else:write(HERE/'profile-results.json',r)
 print('16个漂移上限模型比较及有界极值搜索完成')
