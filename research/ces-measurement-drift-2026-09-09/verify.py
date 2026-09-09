"""不导入拟合、路径、政策或预测函数；用穷举与计数独立核验。"""
import argparse,hashlib,itertools,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(n):return json.loads((HERE/n).read_bytes())
def run():
 checks=0;models=0;maxerr=0.
 def yes(v):
  nonlocal checks
  checks+=1;assert v,checks
 def close(a,b,tol=1e-8):yes(abs(a-b)<=tol)
 src=load('lh265-source.json');counts=src['counts']['all'];seq=list(itertools.product(range(4),repeat=3))
 def audit(m,record,delta=None,threshold=None,pref=None):
  nonlocal models,maxerr
  models+=1;q,u,e=m['Q'],m['U'],m['E'];k=len(q);w=[sum(q[i][j] for i in range(k)) for j in range(k)]
  vals=[v for row in q+u+[r for et in e for r in et] for v in row];yes(all(math.isfinite(v) and v>=0 for v in vals));close(sum(map(sum,q)),1,1e-10)
  for row in u+[r for et in e for r in et]:close(sum(row),1,1e-10)
  drift=[max(sum(abs(e[t][i][c]-e[v][i][c]) for c in range(4))/2 for t,v in [(0,1),(0,2),(1,2)]) for i in range(k)]
  p=[math.fsum(q[i][j]*u[j][l]*e[0][i][a]*e[1][j][b]*e[2][l][c] for i,j,l in itertools.product(range(k),repeat=3)) for a,b,c in seq]
  close(sum(p),1,1e-10);yes(min(p)>=0);ll=math.fsum(n*math.log(v) for n,v in zip(counts,p) if n)
  close(ll,record['loglik'],1e-7);close(max(drift),record['drift']['maximum'],1e-10)
  close(sum(w[i]*drift[i] for i in range(k)),record['drift']['weighted_average'],1e-10)
  for a,b in zip(drift,record['drift']['per_state']):close(a,b,1e-10)
  g=[sum(q[i][j] for i in range(k) for j in range(k) if i!=j),sum(w[j]*u[j][l] for j in range(k) for l in range(k) if j!=l)]
  for name,value in zip(['g01','g12','sum'],[g[0],g[1],sum(g)]):close(value,record['targets'][name],1e-10)
  if delta is not None:yes(max(drift)<=delta+1e-10)
  if threshold is not None:yes(ll>=threshold-1e-7)
  if pref is not None:
   err=max(abs(x-y) for x,y in zip(p,pref));maxerr=max(maxerr,err);yes(err<1e-11)
  return g
 path=load('equivalence-results.json')
 for key,d in path['models'].items():
  yes(len(d['rows'])==101)
  for row in d['rows']:
   if row['feasible']:
    # 路径记录使用gross名称；不改变生产文件。
    rr=dict(row);rr['targets']=row.get('targets',row.get('gross'))
    g=audit(row['model'],rr,pref=src['models'][key]['probabilities'])
    if row['lambda']==1:yes(g==[0,0])
   else:
    yes(row['model'] is None);yes(row['loglik'] is None);yes(row['minimum_probability']<0)
  yes(d['feasible_n']==(101 if key=='hmm3' else 2))
 profile=load('profile-results.json')
 for key,v in profile['models'].items():
  prior={};best=-math.inf;ref=v['fixed_reference_loglik'];close(ref,src['models'][key]['loglik'])
  invariant=v['rows'][0]['best_likelihood'];yes(abs(invariant['loglik']-ref)<1e-3)
  ee=invariant['model']['E'];yes(max(abs(ee[t][i][c]-ee[0][i][c]) for t in range(3) for i in range(len(ee[0])) for c in range(4))<1e-10)
  for row in v['rows']:
   delta=row['delta'];b=row['best_likelihood'];audit(b['model'],b,delta);yes(b['loglik']>=best-1e-7);best=b['loglik']
   z=row['zero_change_best'];yes(audit(z['model'],z,delta)==[0,0]);current={}
   for x in row['extremes']:
    yes(x['status']=='locally_searched_attained_extreme' and not x['certified_global_bound']);audit(x['model'],x,delta,ref-x['tau']);target,side=x['objective'].rsplit('_',1);sign=1 if side=='max' else -1;key2=(x['tau'],x['objective']);score=sign*x['targets'][target];current[key2]=score
    if key2 in prior:yes(score>=prior[key2]-1e-10)
    if x['tau']==10:yes(score>=current[(2.,x['objective'])]-1e-10)
   prior=current
   for tau,result in row['zero_change_fit_by_tau'].items():yes(result==(z['loglik']>=ref-float(tau)-1e-7))
 data=load('joint-trajectories.json');polseq=list(itertools.product(range(3),repeat=3));pol=load('policy-results.json')
 for name,joint in data['joint_counts'].items():
  for y,row in zip(seq,joint):yes(sum(row)==counts[16*y[0]+4*y[1]+y[2]])
  for r in pol['items'][name]['path_rows']:
   g=r['PID_path_group'];cells=[(z,n) for y,row in zip(seq,joint) if ('stable' if y[0]==y[1]==y[2] else 'return' if y[0]==y[2] else 'nonreturn_change')==g for z,n in zip(polseq,row)];complete=[(z,n) for z,n in cells if all(z)]
   yes(sum(n for z,n in cells)==r['retained_n']);yes(sum(n for z,n in complete)==r['policy_complete_n']);yes(r['missing_any_n']==r['retained_n']-r['policy_complete_n'])
   yes(sum(n for z,n in complete if z[0]==z[1]==z[2])==r['policy_stable_n']);yes(sum(n for z,n in complete if z[0]==z[2]!=z[1])==r['policy_return_n'])
   for t in [0,1]:
    s=r['intervals'][str(t)];yes(s['triple_complete_denominator']==sum(n for z,n in complete));yes(s['pair_known_denominator']==sum(n for z,n in cells if z[t] and z[t+1]))
    for a,b,key2 in [(1,2,'oppose_to_support_n'),(2,1,'support_to_oppose_n')]:
     yes(s[key2]==sum(n for z,n in complete if z[t:t+2]==(a,b)));yes(s['pair_'+key2]==sum(n for z,n in cells if z[t:t+2]==(a,b)))
 rawseq=list(itertools.product(range(8),repeat=3));mapping=[0,0,0,1,2,2,2,3];h=load('history-results.json');scores={name:0. for name in h['mean_logscore']}
 for fold,f in enumerate(h['folds']):
  test=data['raw8_fold_counts'][fold];train=[sum(data['raw8_fold_counts'][i][j] for i in range(5) if i!=fold) for j in range(512)];yes(train==f['training_raw8_counts']);yes(sum(test)==f['test_n']);yes(sum(train)==f['train_n'])
  bcp=[[0]*4 for _ in range(4)];abc=[[[0]*4 for _ in range(4)] for _ in range(4)];rawbc=[[0]*8 for _ in range(8)]
  for (a,b,c),n in zip(rawseq,train):bcp[mapping[b]][mapping[c]]+=n;abc[mapping[a]][mapping[b]][mapping[c]]+=n;rawbc[b][c]+=n
  totals=[0.,0.,0.]
  for (a,b,c),n in zip(rawseq,test):
   aa,bb,cc=map(mapping.__getitem__,(a,b,c));first=(bcp[bb][cc]+.25)/(sum(bcp[bb])+1);history=(abc[aa][bb][cc]+20*first)/(sum(abc[aa][bb])+20);rawp=(sum(rawbc[b][j] for j in range(8) if mapping[j]==cc)+.25)/(sum(rawbc[b])+1)
   for i,p in enumerate([first,history,rawp]):totals[i]+=n*math.log(p)
  for name,value in zip(['first_order_PID4','history_PID4_shrink20','first_order_raw8_predict_PID4'],totals):close(value,f['logscore_sum'][name],1e-8);scores[name]+=value
 for name,value in scores.items():close(value/6175,h['mean_logscore'][name],1e-10)
 for filename in ['analysis-plan','policy-restrictions']:
  yes(hashlib.sha256((HERE/(filename+'.json')).read_bytes()).hexdigest()==load(filename+'-seal.json')['sha256'])
 timing=load('timing-audit.json');yes(timing['post_participation_by_known_response']==data['post_participation_by_known_response']);yes(not timing['limits']['exact_item_timestamps_verified'])
 return {'passed':True,'checks':checks,'model_witnesses_checked':models,'maximum_equivalence_probability_error':maxerr,'independent_of_optimizer':True,'scope':'穷举隐态重算概率、似然、漂移和转换；约束/嵌套、政策分母方向、折外评分和计划封印；原件重投影另有私人回执。','certified_global_optimum':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run();b=(json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
 if a.check:assert (HERE/'verification.json').read_bytes()==b
 else:(HERE/'verification.json').write_bytes(b)
 print(json.dumps(r,ensure_ascii=False))
