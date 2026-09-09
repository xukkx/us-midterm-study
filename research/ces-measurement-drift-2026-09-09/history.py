"""同一整人折、同一PID4预测目标；先验在看新对照结果前固定。"""
import argparse,itertools,json,math
from common import HERE,write,encode,sha
SEQ=list(itertools.product(range(4),repeat=3));RAW=list(itertools.product(range(8),repeat=3));MAP=[0,0,0,1,2,2,2,3]
METHODS=['first_order_PID4','history_PID4_shrink20','first_order_raw8_predict_PID4']
def fit(counts,raw):
 pairs=[[0]*4 for _ in range(4)];hist=[[[0]*4 for _ in range(4)] for _ in range(4)];rawpairs=[[0]*8 for _ in range(8)]
 for (a,b,c),n in zip(SEQ,counts):pairs[b][c]+=n;hist[a][b][c]+=n
 for (a,b,c),n in zip(RAW,raw):rawpairs[b][c]+=n
 first=[[(n+.25)/(sum(row)+1) for n in row] for row in pairs]
 history=[[[(hist[a][b][c]+20*first[b][c])/(sum(hist[a][b])+20) for c in range(4)] for b in range(4)] for a in range(4)]
 prior=[.25/MAP.count(MAP[c]) for c in range(8)]
 rawpred=[[(n+prior[c])/(sum(row)+1) for c,n in enumerate(row)] for row in rawpairs]
 coarsened=[[sum(row[c] for c in range(8) if MAP[c]==g) for g in range(4)] for row in rawpred]
 return {'first':first,'history':history,'raw':coarsened}
def lumpability(rows,mapping):
 grouped=[[sum(row[j] for j in range(len(row)) if mapping[j]==g) for g in sorted(set(mapping))] for row in rows]
 return {str(g):max([sum(abs(x-y) for x,y in zip(grouped[i],grouped[j]))/2 for i in range(len(rows)) for j in range(i) if mapping[i]==mapping[j]==g] or [0.]) for g in sorted(set(mapping))}
def empirical(counts,raw):
 ab=[[0]*4 for _ in range(4)];bc=[[0]*4 for _ in range(4)]
 for (a,b,c),n in zip(SEQ,counts):ab[a][b]+=n;bc[b][c]+=n
 total=sum(counts);observed=sum(n for (a,b,c),n in zip(SEQ,counts) if a==c and a!=b)
 expected=sum(ab[a][b]*bc[b][a]/sum(bc[b]) for a in range(4) for b in range(4) if a!=b and sum(bc[b]))
 cmi=sum(n/total*math.log(n*sum(bc[b])/(ab[a][b]*bc[b][c])) for (a,b,c),n in zip(SEQ,counts) if n)
 middle=[{'baseline':a,'n':ab[a][1],'final_counts':bc_a} for a in [0,2] for bc_a in [[sum(n for (x,b,c),n in zip(SEQ,counts) if x==a and b==1 and c==j) for j in range(4)]]]
 rp=[[0]*8 for _ in range(8)]
 for (a,b,c),n in zip(RAW,raw):rp[b][c]+=n
 assert all(sum(row)>0 for row in rp)
 criterion=lumpability([[n/sum(row) for n in row] for row in rp],MAP)
 return {'observed_returns':observed,'first_order_expected_returns':expected,'return_ratio':observed/expected,'conditional_mutual_information_nats':cmi,'middle_I_by_baseline':middle,'raw8_next_wave_source_n':[sum(row) for row in rp],'empirical_lumpability_max_TV_by_PID4':criterion,'singleton_I_raw_codes':[4],'interpretation':'经验频率限制与描述性差异；不是总体检验。I只有原码4，单凭其他类别聚合无法严格解释该条件层里的早期历史差异。'}
def run():
 d=json.loads((HERE/'joint-trajectories.json').read_bytes());full=d['counts']['all'];raw=d['raw8_counts'];folds=[]
 for fold,(test,rawtest) in enumerate(zip(d['fold_counts'],d['raw8_fold_counts'])):
  train=[n-m for n,m in zip(full,test)];rawtrain=[n-m for n,m in zip(raw,rawtest)];n=sum(test);assert sum(train)+n==6175 and sum(rawtest)==n
  p=fit(train,rawtrain);scores=[sum(v*math.log(p['first'][b][c]) for (a,b,c),v in zip(SEQ,test)),sum(v*math.log(p['history'][a][b][c]) for (a,b,c),v in zip(SEQ,test)),sum(v*math.log(p['raw'][b][MAP[c]]) for (a,b,c),v in zip(RAW,rawtest))]
  folds.append({'fold':fold,'train_n':sum(train),'test_n':n,'training_counts':train,'training_raw8_counts':rawtrain,'predictions':p,'logscore_sum':dict(zip(METHODS,scores)),'mean_logscore':dict(zip(METHODS,[s/n for s in scores]))})
 totals={m:sum(f['logscore_sum'][m] for f in folds)/6175 for m in METHODS}
 differences={m:{'mean_nats_per_person':totals[m]-totals[METHODS[0]],'by_fold':[f['mean_logscore'][m]-f['mean_logscore'][METHODS[0]] for f in folds]} for m in METHODS[1:]}
 return {'n':6175,'folds':folds,'mean_logscore':totals,'paired_improvement_over_PID4_first_order':differences,'empirical':empirical(full,raw),'source_sha256':sha(HERE/'joint-trajectories.json'),'interpretation':'大分数较好；有限队列中预先固定的预测对照，未据此调先验或状态数；无因果或显著性结论；旧HMM不同正则化分数仅见lh265-source.json。'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();r=run()
 if a.check:assert (HERE/'history-results.json').read_bytes()==encode(r)
 else:write(HERE/'history-results.json',r)
 print(json.dumps({'scores':r['mean_logscore'],'empirical':r['empirical']}))
