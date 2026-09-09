"""先运行精确分布门和有限样本恢复，再允许实证拟合。"""
import argparse,itertools,json,math,random,statistics
from common import HERE,encode,write,sha
from models import initial,norm,tensor,tensor3,static_map,static_tensor,sample,fit_hmm,latent_summary
from algebra import recover_hmm,maxerr,rank
def align_error(truth,fit):
 k=len(truth['pi']);best=None
 for p in itertools.permutations(range(k)):
  e=maxerr(truth['E'],[fit['E'][j] for j in p])
  t=max(maxerr(truth[key],[[fit[key][i][j] for j in p] for i in p]) for key in ['T01','T12'])
  pi=max(abs(truth['pi'][i]-fit['pi'][p[i]]) for i in range(k))
  val={'E_max_error':e,'T_max_error':t,'pi_max_error':pi,'max_error':max(e,t,pi),'permutation':p}
  if best is None or val['max_error']<best['max_error']:best=val
 return best
def exact():
 ledger=[]
 for k in [3,4]:
  for rep in range(25):
   model=initial(k,random.Random(265000+k*100+rep));p=tensor(model);fit=recover_hmm(tensor3(p),k);err=align_error(model,fit)
   mapped=static_tensor(static_map(model));err['static_reconstruction_error']=max(abs(x-y) for x,y in zip(p,mapped));err['k']=k;err['rep']=rep
   assert err['max_error']<1e-7 and err['static_reconstruction_error']<1e-12
   ledger.append(err)
 bad={'pi':[.5,.5],'T01':[[.5,.5],[.5,.5]],'T12':[[.5,.5],[.5,.5]],'E':[[.4,.3,.2,.1]]*2}
 try:recover_hmm(tensor3(tensor(bad)),2)
 except ValueError:rejected=True
 else:raise AssertionError('秩不足应拒绝')
 return {'cases':ledger,'maximum_parameter_error':max(x['max_error'] for x in ledger),'maximum_static_error':max(x['static_reconstruction_error'] for x in ledger),'degenerate_rejected':rejected,'passed':True}
def dgp(k,quality):
 pi=norm([.43,.15,.40,.02][:k]);stay=.92
 t=[[stay if i==j else (1-stay)/(k-1) for j in range(k)] for i in range(k)]
 u=[[.88 if i==j else .12/(k-1) for j in range(k)] for i in range(k)]
 accuracy=.95 if quality=='strong' else .58
 e=[[accuracy if j==i else (1-accuracy)/3 for j in range(4)] for i in range(k)]
 return {'pi':pi,'T01':t,'T12':u,'E':e}
def recovery():
 ledger=[]
 plan=json.loads((HERE/'analysis-plan.json').read_bytes())['recovery']
 for k,quality,n in itertools.product(plan['K'],plan['measurement'],plan['n']):
  truth=dgp(k,quality);p=tensor(truth);target=latent_summary(truth)
  for rep in range(plan['replications_per_cell']):
   seed=plan['seed']+k*100000+n*100+rep+(10000 if quality=='weak' else 0)
   counts=sample(p,n,random.Random(seed));fit=fit_hmm(counts,k,seed,starts=plan['starts'],iterations=plan['iterations']);err=align_error(truth,fit['model']);s=latent_summary(fit['model'])
   ledger.append({'k':k,'quality':quality,'n':n,'rep':rep,'converged':fit['converged'],'iterations':fit['iterations'],'loglik':fit['loglik'],'errors':err,'gross01_error':s['gross01']-target['gross01'],'gross12_error':s['gross12']-target['gross12'],'observable_TV':sum(abs(a-b) for a,b in zip(tensor(fit['model']),p))/2})
  print(json.dumps({'simulation_done':[k,quality,n],'replications':plan['replications_per_cell']}),flush=True)
 rows=[]
 for k,quality,n in itertools.product(plan['K'],plan['measurement'],plan['n']):
  group=[x for x in ledger if (x['k'],x['quality'],x['n'])==(k,quality,n)];r=len(group);errors=[x['gross01_error'] for x in group];rate=sum(x['converged'] for x in group)/r
  rows.append({'k':k,'quality':quality,'n':n,'replications':r,'convergence_fraction':rate,'convergence_MCSE':math.sqrt(rate*(1-rate)/r),'gross01_bias':statistics.mean(errors),'gross01_RMSE':math.sqrt(statistics.mean(x*x for x in errors)),'gross01_bias_MCSE':statistics.stdev(errors)/math.sqrt(r),'median_E_max_error':statistics.median(x['errors']['E_max_error'] for x in group),'median_T_max_error':statistics.median(x['errors']['T_max_error'] for x in group),'median_observable_TV':statistics.median(x['observable_TV'] for x in group)})
 return {'replications':len(ledger),'summary':rows,'ledger':ledger,'inference':'保留所有未收敛结果；12次/格只供诊断，有MC误差；没有人口置信区间覆盖声明。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--exact-only',action='store_true');ap.add_argument('--check',action='store_true');a=ap.parse_args();results={'exact-results.json':exact()}
 if not a.exact_only:results['recovery-results.json']=recovery()
 for name,r in results.items():
  if a.check:assert (HERE/name).read_bytes()==encode(r),name
  else:write(HERE/name,r)
 print(json.dumps({'exact_cases':50,'passed':True,'recovery':not a.exact_only}))
