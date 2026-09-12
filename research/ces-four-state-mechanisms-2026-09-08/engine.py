"""任意类别数的固定标准化与交叉拟合；不接收遮蔽真值。"""
import math
from collections import defaultdict
import glm
METHODS=('unadjusted','baseline_standardization','crossfit_aipw')

def features(r):
    d=[int(r['y0']==k) for k in (1,2,3)];rent=int(r['housing']==1);L=r['latino_employed']
    return [1,*d,rent,int(r['housing']==2),L,int(r['age']==1),int(r['age']==2),int(r['age']==3),int(r['education']==1),int(r['education']==2),*[x*rent for x in d],*[x*L for x in d]]
def stratum(r):return (r['y0'],int(r['housing']==1))
def aggregate(rows,fn,K,response=False):
    table={}
    for r in rows:
        if not response and not r['s']:continue
        y=r['s'] if response else r['y'];x=tuple(fn(r));table.setdefault(x,[0]*K)[y]+=1
    if not table:raise ValueError('没有可用训练结局')
    return list(table),list(table.values())
def train(rows,K=4,outcome_features=features,response_features=features):
    if not rows or not isinstance(K,int) or K<2:raise ValueError('无数据或类别数非法')
    if len({r['key'] for r in rows})!=len(rows):raise ValueError('受访者键重复')
    for r in rows:
        if r['s'] not in (0,1) or r['y0'] not in range(K) or (r['s'] and r['y'] not in range(K)) or (not r['s'] and r['y'] is not None):raise ValueError('遮蔽或分类合同不符')
    complete=all(r['s'] for r in rows)
    if complete:
        return [dict(r,m=[int(r['y']==k) for k in range(K)],phi=[int(r['y']==k) for k in range(K)],std=[int(r['y']==k) for k in range(K)],std_phi=[int(r['y']==k) for k in range(K)],e=1.,e_raw=1.) for r in rows],{'K':K,'complete_data_exact':True,'models':[]}
    table=defaultdict(lambda:[0]*K);totals=defaultdict(int)
    for r in rows:
        h=stratum(r);totals[h]+=1
        if r['s']:table[h][r['y']]+=1
    if any(sum(table[h])==0 for h in totals):raise ValueError('标准化格无观察')
    folds=sorted({r['fold'] for r in rows})
    if len(folds)!=5:raise ValueError('必须有五个受访者折')
    result=[None]*len(rows);models=[]
    for fold in folds:
        training=[r for r in rows if r['fold']!=fold];ix=[i for i,r in enumerate(rows) if r['fold']==fold]
        X,c=aggregate(training,response_features,2,True);er=glm.fit(X,c)
        X,c=aggregate(training,outcome_features,K);om=glm.fit(X,c)
        if not er['converged'] or not om['converged']:raise ValueError('拟合未收敛')
        ps=glm.predict(om,[outcome_features(rows[i]) for i in ix]);es=glm.predict(er,[response_features(rows[i]) for i in ix])
        for i,m,ev in zip(ix,ps,es):
            r=rows[i];e=max(.02,min(.98,ev[1]));h=stratum(r);obs=sum(table[h]);st=[v/obs for v in table[h]];ec=obs/totals[h]
            phi=[m[k]+(int(r['y']==k)-m[k])/e if r['s'] else m[k] for k in range(K)]
            stphi=[st[k]+(int(r['y']==k)-st[k])/ec if r['s'] else st[k] for k in range(K)]
            result[i]=dict(r,m=m,phi=phi,std=st,std_phi=stphi,e=e,e_raw=ev[1])
        models.append({'fold':fold,'train_n':len(training),'observed_train_n':sum(r['s'] for r in training),'test_n':len(ix),'response':er,'outcome':om})
    return result,{'K':K,'complete_data_exact':False,'models':models,'method_scope':'全体训练；子组只汇总；固定惩罚与裁切'}
def vector(r,method,K):
    if method not in METHODS:raise ValueError('未知方法')
    return [int(r['y']==k) for k in range(K)] if method=='unadjusted' else r['std'] if method=='baseline_standardization' else r['phi']
def sufficient(rows,method,K=4):
    use=[r for r in rows if r['s']] if method=='unadjusted' else rows
    if not use:raise ValueError('分母零')
    return {'n':len(use),'baseline_counts':[sum(r['y0']==k for r in use) for k in range(K)],'matrix_totals':[[math.fsum(vector(r,method,K)[b] for r in use if r['y0']==a) for b in range(K)] for a in range(K)]}
def summarize(s,R=2):
    n=s['n'];M=s['matrix_totals'];K=len(M)
    if not isinstance(n,int) or n<=0 or K<2 or any(len(r)!=K for r in M) or len(s['baseline_counts'])!=K:raise ValueError('匿名充分统计尺寸非法')
    if sum(s['baseline_counts'])!=n or not math.isclose(math.fsum(v for r in M for v in r),n,abs_tol=1e-7):raise ValueError('矩阵和分母不闭合')
    for a in range(K):
        if not math.isclose(math.fsum(M[a]),s['baseline_counts'][a],abs_tol=1e-7):raise ValueError('基线行边际不闭合')
    P=[[v/n for v in r] for r in M]
    out={'n':n,'matrix':P,'R_share_pp':100*math.fsum(P[a][R] for a in range(K)),'R_change_pp':100*(math.fsum(P[a][R] for a in range(K))-s['baseline_counts'][R]/n),'any_change_pp':100*(1-math.fsum(P[a][a] for a in range(K))),'matrix_outside_probability_domain':any(v<-1e-10 or v>1+1e-10 for r in P for v in r),'flows_pp':{f'{a}_to_{b}':100*P[a][b] for a in range(K) for b in range(K) if a!=b}}
    if K==4:out['not_sure_change_pp']=100*(math.fsum(P[a][3] for a in range(K))-s['baseline_counts'][3]/n)
    return out
