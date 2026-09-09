"""独立于置换/预测实现：重算效应、精确参考均值与折外评分。"""
import argparse,hashlib,itertools,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(n):return json.loads((HERE/n).read_bytes())
def run():
 checks=0
 def yes(x):
  nonlocal checks
  checks+=1;assert x,checks
 def close(x,y,t=1e-10):yes(abs(x-y)<=t)
 src=read('lh266-joint-trajectories.json');old=read('lh266-policy-results.json');cal=read('policy-calibration.json');plan=read('analysis-plan.json');review=read('reviewer-policy_review_results.json');exactmeans={}
 for item,res in cal['items'].items():
  records=res['R1']['strata'];N=res['R1']['complete_n'];mi=0.;tv=0.;emean=[0.,0.]
  for s in records:
   table=s['table'];row=[sum(x) for x in table];col=[sum(table[g][j] for g in range(3)) for j in range(4)];n=sum(row)
   for g,j in itertools.product(range(3),range(4)):
    observed=sum(v for y,line in zip(itertools.product(range(4),repeat=3),src['joint_counts'][item]) for z,v in zip(itertools.product(range(3),repeat=3),line) if y[0]==s['baseline_PID'] and z[0]==s['baseline_policy'] and all(z) and (0 if y[0]==y[1]==y[2] else 1 if y[0]==y[2] else 2)==g and 2*(z[1]-1)+z[2]-1==j)
    yes(table[g][j]==observed);e=row[g]*col[j]/n;tv+=abs(observed-e)/(2*N)
    if observed:mi+=observed/N*math.log(observed/e)
    # 单格边际的精确超几何均值，不调用Muse内核或生产采样器。
    den=math.comb(n,row[g]);pm=[]
    for x in range(max(0,row[g]-(n-col[j])),min(row[g],col[j])+1):pm.append((x,math.comb(col[j],x)*math.comb(n-col[j],row[g]-x)/den))
    close(sum(p for x,p in pm),1,1e-10);emean[0]+=sum(p*x*math.log(x/e) for x,p in pm if x)/N;emean[1]+=sum(p*abs(x-e) for x,p in pm)/(2*N)
  close(mi,res['R1']['statistics']['MI']['observed']);close(tv,res['R1']['statistics']['TV']['observed']);exactmeans[item]={}
  for i,name in enumerate(['MI','TV']):
   stat=res['R1']['statistics'][name];se=stat['null']['sd']/math.sqrt(stat['B']);yes(abs(stat['null']['mean']-emean[i])<6*se+1e-10);exactmeans[item][name]={'exact_null_mean':emean[i],'MC_mean_z':(stat['null']['mean']-emean[i])/se if se else 0.};yes(stat['p_plus_one']==(stat['hits']+1)/(stat['B']+1))
  r=res['R2'];count=sum(x['return_n'] for x in r['strata']);yes(count==r['complete_return_n']);delta=sum(x['return_n']/count*(x['return_events']/x['return_n']-x['stable_events']/x['stable_n']) for x in r['strata']);close(delta,r['observed_average_difference']);close(delta,old['items'][item]['restriction_2']['standardized_difference']);yes(r['p_plus_one']==(r['hits']+1)/(r['B']+1));var=0.
  for x,rr in zip(r['strata'],review['strata'][item]):
   yes([x[k] for k in ['baseline_PID','baseline_policy','return_n','return_events','stable_n','stable_events']]==rr);nr=x['return_n'];ns=x['stable_n'];M=nr+ns;K=x['return_events']+x['stable_events'];var+=(nr/count)**2*(1/nr+1/ns)**2*nr*K/M*(1-K/M)*(M-nr)/(M-1)
   close(x['simultaneous_difference_interval'][0],x['return_probability_interval'][0]-x['stable_probability_interval'][1]);close(x['simultaneous_difference_interval'][1],x['return_probability_interval'][1]-x['stable_probability_interval'][0]);yes(x['simultaneous_difference_interval'][0]<=x['difference']<=x['simultaneous_difference_interval'][1])
  yes(abs(r['null_distribution']['mean'])<6*math.sqrt(var/r['B']));yes(abs(r['null_distribution']['sd']-math.sqrt(var))<.01*math.sqrt(var));rr=next(x for x in review['results'] if x['item']==item);yes(abs(r['p_plus_one']-rr['permutation_two_sided_abs_p'])<6*math.hypot(r['MC_se'],rr['monte_carlo_se_approx']))
 # Holm独立按每个p以前所有较小排序门槛取最大。
 records=[cal['items'][item]['R1']['statistics']['MI'] if target=='R1' else cal['items'][item]['R2'] for target in ['R1','R2'] for item in plan['items']];sortedp=sorted(x['p_plus_one'] for x in records)
 for r in records:close(r['Holm_primary_six'],min(1.,max((6-i)*p for i,p in enumerate(sortedp) if p<=r['p_plus_one'])))
 h=read('history-nested.json');mapping=[0,0,0,1,2,2,2,3];seq=list(itertools.product(range(8),repeat=3));totals=[0.,0.];brier=[0.,0.];paths={};predbins=[[[[0,0.,0] for _ in range(10)] for _ in range(4)] for _ in range(2)]
 for f in h['folds']:
  fold=f['fold'];train=[sum(src['raw8_fold_counts'][i][j] for i in range(5) if i!=fold) for j in range(512)];test=src['raw8_fold_counts'][fold];yes(sum(train)==f['train_n']);yes(sum(test)==f['test_n']);scores=[0.,0.]
  for b in range(8):
   par=[(sum(n for (aa,bb,cc),n in zip(seq,train) if bb==b and mapping[cc]==c)+.25)/(sum(n for (aa,bb,cc),n in zip(seq,train) if bb==b)+1) for c in range(4)]
   for c in range(4):close(par[c],f['parent'][b][c])
   for a in range(4):
    den=sum(n for (aa,bb,cc),n in zip(seq,train) if mapping[aa]==a and bb==b);child=[(sum(n for (aa,bb,cc),n in zip(seq,train) if mapping[aa]==a and bb==b and mapping[cc]==c)+20*par[c])/(den+20) for c in range(4)]
    for c in range(4):close(child[c],f['child'][a][b][c])
  for (a,b,c),n in zip(seq,test):
   if not n:continue
   preds=[f['parent'][b],f['child'][mapping[a]][b]];key=(mapping[a],mapping[b],mapping[c]);diff=n*math.log(preds[1][key[2]]/preds[0][key[2]]);z=paths.setdefault(key,[0,0.]);z[0]+=n;z[1]+=diff
   for i,p in enumerate(preds):
    scores[i]+=n*math.log(p[key[2]]);brier[i]+=n*(1-2*p[key[2]]+sum(v*v for v in p))
    for j,v in enumerate(p):
     z=predbins[i][j][min(9,int(v*10))];z[0]+=n;z[1]+=n*v;z[2]+=n*(j==key[2])
  for i in range(2):close(scores[i],f['logscore_sum'][i],1e-8);totals[i]+=scores[i]
 for i in range(2):close(totals[i]/6175,h['mean_logscore'][i]);close(brier[i]/6175,h['multiclass_brier'][i])
 for r in h['path_contributions']:
  n,d=paths.get(tuple(r['PID4_path']),[0,0.]);yes(n==r['n']);close(d,r['logscore_difference_sum'],1e-8)
 for i,j,k in itertools.product(range(2),range(4),range(10)):
  z=predbins[i][j][k];r=h['calibration'][i][j][k];yes(z[0]==r['n']);close(z[1],r['predicted_sum'],1e-8);yes(z[2]==r['observed_n'])
 close(h['paired_mean_improvement_nats'],(totals[1]-totals[0])/6175);yes(hashlib.sha256((HERE/'analysis-plan.json').read_bytes()).hexdigest()==read('analysis-plan-seal.json')['sha256'])
 return {'passed':True,'checks':checks,'exact_null_mean_diagnostics':exactmeans,'scope':'匿名源分层计数、两统计量、精确超几何零分布均值/方差、评审差值与MC一致性、Holm、全部折外预测/校准/路径；独立于生产参考及预测函数。','full_algorithm_confidence_interval':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run();b=(json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
 if a.check:assert (HERE/'verification.json').read_bytes()==b
 else:(HERE/'verification.json').write_bytes(b)
 print(json.dumps(r))
