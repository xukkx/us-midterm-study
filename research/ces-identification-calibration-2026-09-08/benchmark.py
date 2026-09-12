"""训练只接收遮蔽文件；不导入、读取或以评分真值调参。"""
import argparse,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from common import *
import glm
from summary_core import summarize

FEATURE_NAMES=['intercept','pid_I','pid_R','housing_rent','housing_other_missing','Latino_employed','age40_64','age65plus','age_missing','college','education_missing','pid_I_x_rent','pid_R_x_rent','pid_I_x_Latino_employed','pid_R_x_Latino_employed']
def features(r):
    I=int(r['y0']==1);R=int(r['y0']==2);rent=int(r['housing']==1);L=r['latino_employed']
    return [1,I,R,rent,int(r['housing']==2),L,int(r['age']==1),int(r['age']==2),int(r['age']==3),int(r['education']==1),int(r['education']==2),I*rent,R*rent,I*L,R*L]
def stratum(r):return (r['y0'],int(r['housing']==1))
def aggregate(rows,feature_fn,K,response=False):
    table={}
    for r in rows:
        if not response and not r['s']:continue
        x=tuple(feature_fn(r));v=table.setdefault(x,[0]*K);y=r['s'] if response else r['y']
        if y is None:raise ValueError('尝试使用遮蔽结果')
        v[y]+=1
    if not table:raise ValueError('训练样本没有观察结果')
    return list(table),list(table.values())

def train(rows,feature_fn=features):
    if not rows or any((not r['s'] and r['y'] is not None) or (r['s'] and r['y'] not in (0,1,2)) for r in rows):raise ValueError('遮蔽合同不符')
    if len({r['key'] for r in rows})!=len(rows):raise ValueError('受访者键重复')
    if not any(r['s'] for r in rows):raise ValueError('全部结局被遮蔽，无法拟合')
    complete=all(r['s'] for r in rows)
    table=defaultdict(lambda:[0,0,0]);totals=defaultdict(int)
    for r in rows:
        h=stratum(r);totals[h]+=1
        if r['s']:table[h][r['y']]+=1
    if any(sum(table[h])==0 for h in totals):raise ValueError('基线标准化存在无观察的目标格')
    predictions=[None]*len(rows);models=[]
    if complete:
        for i,r in enumerate(rows):
            one=[int(r['y']==k) for k in range(3)]
            predictions[i]=dict(r,m=one,e=1.0,e_raw=1.0,phi=one,std=one,std_phi=one)
        return predictions,{'complete_data_exact':True,'models':[],'feature_names':FEATURE_NAMES}
    for fold in sorted({r['fold'] for r in rows}):
        training=[r for r in rows if r['fold']!=fold];test_ix=[i for i,r in enumerate(rows) if r['fold']==fold]
        X,c=aggregate(training,feature_fn,2,True);response=glm.fit(X,c)
        X,c=aggregate(training,feature_fn,3);outcome=glm.fit(X,c)
        if not response['converged'] or not outcome['converged']:raise ValueError('nuisance优化未收敛，拒绝交付估计')
        testX=[feature_fn(rows[i]) for i in test_ix]
        probabilities=glm.predict(outcome,testX);e_all=glm.predict(response,testX)
        for i,m,ep in zip(test_ix,probabilities,e_all):
            r=rows[i];eraw=ep[1];e=max(.02,min(.98,eraw))
            phi=[m[k]+(int(r['y']==k)-m[k])/e if r['s'] else m[k] for k in range(3)]
            h=stratum(r);obs=sum(table[h]);st=[v/obs for v in table[h]];es=obs/totals[h]
            stphi=[st[k]+(int(r['y']==k)-st[k])/es if r['s'] else st[k] for k in range(3)]
            predictions[i]=dict(r,m=m,e=e,e_raw=eraw,phi=phi,std=st,std_phi=stphi)
        models.append({'fold':fold,'train_n':len(training),'outcome_train_n':sum(r['s'] for r in training),'test_n':len(test_ix),'response':response,'outcome':outcome})
    return predictions,{'complete_data_exact':False,'feature_names':FEATURE_NAMES,'models':models,'fit_scope':'全体训练，子组只用于评估；超参数固定无调参'}

def probability_vector(r,method):
    if method=='unadjusted':return [int(r['y']==k) for k in range(3)]
    return r['std'] if method=='baseline_standardization' else r['phi']

def sufficient(rows,method):
    use=[r for r in rows if r['s']] if method=='unadjusted' else rows
    if not use:raise ValueError('估计分母为零')
    matrix=[[math.fsum(probability_vector(r,method)[k] for r in use if r['y0']==a) for k in range(3)] for a in range(3)]
    return {'n':len(use),'baseline_R_n':sum(r['y0']==2 for r in use),'matrix_totals':matrix}

def metrics(rows,method):
    result=summarize(sufficient(rows,method));matrix=result['matrix']
    # 精确结构零由起点类别指标约束，即便AIPW有限样本估计可能超出概率域也不会制造不存在的起点。
    if all(r['y0']==2 for r in rows):assert all(v==0 for line in matrix[:2] for v in line)
    return result

def scalar_contributions(rows,method):
    if method=='unadjusted':return [int(r['y']==2)-int(r['y0']==2) for r in rows if r['s']]
    return [(r['std_phi'][2] if method=='baseline_standardization' else r['phi'][2])-int(r['y0']==2) for r in rows]

def uncertainty(rows,method,*,fitting_population=None):
    if method not in ('unadjusted','baseline_standardization','crossfit_aipw'):
        raise ValueError('未知估计方法')
    if method=='baseline_standardization':
        # LH263.1：完整拟合人群的残差在格内抵消；任意子组一般不成立。
        # 子组方差还需要来自组外训练者的贡献，本接口暂不提供，不能只重定中心。
        if fitting_population is None:
            return {'valid':False,'state':'fitting_population_required','ci95_pp':None,'se_pp':None}
        keys=[r['key'] for r in rows];full_keys=[r['key'] for r in fitting_population]
        if len(set(keys))!=len(keys) or len(set(full_keys))!=len(full_keys):
            raise ValueError('区间人群包含重复受访者')
        if not keys or set(keys)!=set(full_keys):
            return {'valid':False,'state':'unsupported_standardization_subgroup','ci95_pp':None,'se_pp':None}
    values=scalar_contributions(rows,method);n=len(values)
    changes=[int(r['y']==2)-int(r['y0']==2) for r in rows if r['s']]
    legal=([-1] if all(r['y0']==2 for r in rows) else [1] if all(r['y0']!=2 for r in rows) else [-1,1])
    sparse=any(changes.count(d)<5 for d in legal)
    mean=math.fsum(values)/n if n else None
    if method=='baseline_standardization' and n:
        point=math.fsum(r['std'][2]-int(r['y0']==2) for r in rows)/n
        if not math.isclose(mean,point,rel_tol=0,abs_tol=1e-12):
            raise ValueError('完整拟合人群的标准化残差未抵消，拒绝错位区间')
    var=math.fsum((v-mean)**2 for v in values)/(n-1) if n>1 else 0
    if sparse or var<=1e-20:return {'valid':False,'state':'sparse_transitions' if sparse else 'degenerate_variance','ci95_pp':None,'se_pp':None}
    se=math.sqrt(var/n)*100
    return {'valid':True,'state':'model_based_iid_approximation','ci95_pp':[mean*100-1.96*se,mean*100+1.96*se],'se_pp':se}

def fit_file(input_path,private):
    rows=[json.loads(s) for s in Path(input_path).read_text(encoding='utf-8').splitlines() if s]
    preds,models=train(rows);private=Path(private)
    path=private/'predictions.jsonl'
    with path.open('w',encoding='utf-8',newline='\n') as f:
        for row in preds:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    write(HERE/'model-fit.json',models)
    seal={'sealed_at':datetime.now(timezone.utc).isoformat(),'input_sha256':sha(input_path),'predictions_sha256':sha(path),'model_sha256':sha(HERE/'model-fit.json'),'outcome_masking':'S0始终null；本程序不接收truth路径','predictions_n':len(preds)}
    write(HERE/'predictions-seal.json',seal)
    print(json.dumps({'predictions_n':len(preds),'folds':len(models['models']),'all_converged':True,'sealed_before_unmasking':True},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--private',required=True);a=p.parse_args();fit_file(a.input,a.private)
