"""单一强度控制历史挑战者；原整人折与预设收缩不变。"""
import argparse,itertools,json,math
from common import HERE,write,encode,sha
SEQ=list(itertools.product(range(8),repeat=3));MAP=[0,0,0,1,2,2,2,3]
def fit(raw,shrink=20.):
 parent_counts=[[0]*4 for _ in range(8)];history_counts=[[[0]*4 for _ in range(8)] for _ in range(4)]
 for (a,b,c),n in zip(SEQ,raw):parent_counts[b][MAP[c]]+=n;history_counts[MAP[a]][b][MAP[c]]+=n
 parent=[[(x+.25)/(sum(row)+1) for x in row] for row in parent_counts]
 child=[[[(history_counts[a][b][c]+shrink*parent[b][c])/(sum(history_counts[a][b])+shrink) for c in range(4)] for b in range(8)] for a in range(4)]
 return parent,child
def score(test,parent,child):
 totals=[0.,0.];brier=[0.,0.];by_path={};cal=[[[{'n':0,'predicted_sum':0.,'observed_n':0} for _ in range(10)] for _ in range(4)] for _ in range(2)]
 for (a,b,c),n in zip(SEQ,test):
  if not n:continue
  aa,bb,cc=MAP[a],MAP[b],MAP[c];p,q=parent[b],child[aa][b];values=[p,q];diff=n*(math.log(q[cc])-math.log(p[cc]));key=f'{aa}{bb}{cc}';r=by_path.setdefault(key,{'n':0,'logscore_difference_sum':0.});r['n']+=n;r['logscore_difference_sum']+=diff
  for m,pred in enumerate(values):
   totals[m]+=n*math.log(pred[cc]);brier[m]+=n*sum((v-(j==cc))**2 for j,v in enumerate(pred))
   for j,v in enumerate(pred):
    z=cal[m][j][min(9,int(v*10))];z['n']+=n;z['predicted_sum']+=n*v;z['observed_n']+=n*(j==cc)
 return {'n':sum(test),'logscore_sum':totals,'brier_sum':brier,'path_contributions':by_path,'calibration':cal}
def run():
 data=json.loads((HERE/'lh266-joint-trajectories.json').read_bytes());old=json.loads((HERE/'lh266-history-results.json').read_bytes());folds=[];allpaths={};cal=[[[{'n':0,'predicted_sum':0.,'observed_n':0} for _ in range(10)] for _ in range(4)] for _ in range(2)]
 for fold,test in enumerate(data['raw8_fold_counts']):
  train=[sum(data['raw8_fold_counts'][j][i] for j in range(5) if j!=fold) for i in range(512)];parent,child=fit(train);r=score(test,parent,child);assert abs(r['logscore_sum'][0]-old['folds'][fold]['logscore_sum']['first_order_raw8_predict_PID4'])<1e-9
  folds.append({'fold':fold,'train_n':sum(train),'test_n':r['n'],'parent':parent,'child':child,'logscore_sum':r['logscore_sum'],'brier_sum':r['brier_sum'],'paired_mean_difference':(r['logscore_sum'][1]-r['logscore_sum'][0])/r['n']})
  for key,x in r['path_contributions'].items():
   z=allpaths.setdefault(key,{'n':0,'logscore_difference_sum':0.});z['n']+=x['n'];z['logscore_difference_sum']+=x['logscore_difference_sum']
  for m,j,k in itertools.product(range(2),range(4),range(10)):
   for field in cal[m][j][k]:cal[m][j][k][field]+=r['calibration'][m][j][k][field]
 for m,j,k in itertools.product(range(2),range(4),range(10)):
  z=cal[m][j][k];z['bin_lower']=k/10;z['bin_upper']=(k+1)/10;z['mean_predicted']=z['predicted_sum']/z['n'] if z['n'] else None;z['observed_rate']=z['observed_n']/z['n'] if z['n'] else None
 pathrows=[];groups={g:{'n':0,'logscore_difference_sum':0.} for g in ['stable','return','nonreturn_change']}
 for y in itertools.product(range(4),repeat=3):
  key=''.join(map(str,y));z=allpaths.get(key,{'n':0,'logscore_difference_sum':0.});g='stable' if y[0]==y[1]==y[2] else 'return' if y[0]==y[2] else 'nonreturn_change';pathrows.append({'PID4_path':list(y),**z,'paired_mean_difference':z['logscore_difference_sum']/z['n'] if z['n'] else None,'contribution_to_cohort_mean':z['logscore_difference_sum']/6175})
  for field in groups[g]:groups[g][field]+=z[field]
 for z in groups.values():z.update(paired_mean_difference=z['logscore_difference_sum']/z['n'],contribution_to_cohort_mean=z['logscore_difference_sum']/6175)
 means=[sum(f['logscore_sum'][m] for f in folds)/6175 for m in range(2)];gain=means[1]-means[0]
 return {'n':6175,'methods':['raw8_parent','raw8_plus_PID20_4_shrink20'],'folds':folds,'mean_logscore':means,'paired_mean_improvement_nats':gain,'geometric_mean_probability_ratio':math.exp(gain),'multiclass_brier':[sum(f['brier_sum'][m] for f in folds)/6175 for m in range(2)],'classwise_ECE':[[sum(abs(z['observed_n']-z['predicted_sum']) for z in cal[m][j])/6175 for j in range(4)] for m in range(2)],'calibration':cal,'path_contributions':pathrows,'group_contributions':groups,'plan_sha256':sha(HERE/'analysis-plan.json'),'source_sha256':sha(HERE/'lh266-joint-trajectories.json'),'uncertainty':'不报告完整算法置信区间；五折不是独立重复；本轮没有逐人重采样并重拟合。校准箱和ECE为有限队列描述。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'history-nested.json').read_bytes()==encode(r)
 else:write(HERE/'history-nested.json',r)
 print(json.dumps({k:r[k] for k in ['mean_logscore','paired_mean_improvement_nats','geometric_mean_probability_ratio','multiclass_brier','group_contributions']}))
