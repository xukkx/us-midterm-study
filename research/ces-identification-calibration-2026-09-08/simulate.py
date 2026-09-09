"""固定合成DGP的恢复、精度和区间覆盖检查；不是新调查记录。"""
import argparse,json,math,random,statistics
from pathlib import Path
from common import *
from benchmark import train,metrics,uncertainty

METHODS=('unadjusted','baseline_standardization','crossfit_aipw')
SCENARIOS=('MCAR','MAR_covariate','MNAR_outcome','sparse_MCAR')
def simulation_features(r):
    x=int(r['housing']==1);a=int(r['y0']==2)
    return [1,x,a,x*a]
def probabilities(a,x,sparse=False):
    if sparse:return [.998,.001,.001] if a==0 else [.001,.001,.998]
    return {(0,0):[.83,.10,.07],(0,1):[.62,.16,.22],(2,0):[.16,.12,.72],(2,1):[.04,.09,.87]}[a,x]
def population_truth(scenario):
    r1=sum((.55 if a==0 else .45)*.5*probabilities(a,x,scenario=='sparse_MCAR')[2] for a in (0,2) for x in (0,1))
    return 100*(r1-.45)
def categorical(rng,ps):
    v=rng.random();s=0
    for k,p in enumerate(ps):
        s+=p
        if v<s:return k
    return len(ps)-1
def generate(scenario,rng,n=600):
    masked=[];complete=[]
    for i in range(n):
        a=2 if rng.random()<.45 else 0;x=int(rng.random()<.5);y=categorical(rng,probabilities(a,x,scenario=='sparse_MCAR'))
        e=.55 if scenario in ('MCAR','sparse_MCAR') else .8 if x else .3
        if scenario=='MNAR_outcome':
            z=math.log(e/(1-e))+1.1*int(y==2);e=1/(1+math.exp(-z))
        s=int(rng.random()<e)
        r={'key':str(i),'fold':rng.randrange(5),'s':s,'y0':a,'y':y if s else None,'housing':x,'latino_employed':0,'age':1,'education':0,'groups':['all']}
        masked.append(r);complete.append(dict(r,s=1,y=y))
    return masked,complete

def run(reps=150,seed=26320260908):
    results=[];failures=[];ledger=[]
    for scindex,scenario in enumerate(SCENARIOS):
        true=population_truth(scenario);by={m:[] for m in METHODS}
        for rep in range(reps):
            rng=random.Random(seed+scindex*1_000_000+rep)
            masked,full=generate(scenario,rng);empirical=metrics(full,'unadjusted')['R_change_pp']
            try:preds,_=train(masked,simulation_features)
            except (ValueError,ArithmeticError) as ex:
                failures.append({'scenario':scenario,'replication':rep,'error':str(ex)})
                continue
            for method in METHODS:
                est=metrics(preds,method)['R_change_pp'];ci=uncertainty(preds,method)
                covered=bool(ci['valid'] and ci['ci95_pp'][0]<=true<=ci['ci95_pp'][1])
                row={'scenario':scenario,'replication':rep,'method':method,'estimate_pp':est,'population_truth_pp':true,'empirical_full_pp':empirical,
                     'valid_interval':ci['valid'],'interval_state':ci['state'],'covered':covered,'se_pp':ci['se_pp'],'ci95_pp':ci['ci95_pp']}
                by[method].append(row);ledger.append(row)
        for method,rows in by.items():
            vals=[r['estimate_pp'] for r in rows];valid=[r for r in rows if r['valid_interval']];coverage=sum(r['covered'] for r in rows)/reps
            result={'scenario':scenario,'method':method,'planned_replications':reps,'successful_replications':len(rows),'population_truth_pp':true,
                    'bias_pp':statistics.mean(vals)-true if vals else None,'empirical_sd_pp':statistics.stdev(vals) if len(vals)>1 else None,
                    'rmse_pp':math.sqrt(statistics.mean((v-true)**2 for v in vals)) if vals else None,
                    'rmse_vs_realized_full_cohort_pp':math.sqrt(statistics.mean((r['estimate_pp']-r['empirical_full_pp'])**2 for r in rows)) if rows else None,
                    'valid_intervals':len(valid),'unconditional_coverage':coverage,'conditional_coverage_valid_only':sum(r['covered'] for r in valid)/len(valid) if valid else None,
                    'coverage_MC_se':math.sqrt(coverage*(1-coverage)/reps),'mean_reported_se_pp':statistics.mean(r['se_pp'] for r in valid) if valid else None}
            results.append(result)
        # 只输出阶段进度，不将模型模拟当成真实政治证据。
        print(json.dumps({'simulation_scenario_complete':scenario,'replications':reps,'fit_failures':sum(x['scenario']==scenario for x in failures)},ensure_ascii=False),flush=True)
    return {'seed':seed,'results':results,'fit_failures':failures,'interpretation':'合成低维H用同一GLM/AIPW数值和交叉拟合代码；不等于验证真实15维模型所有误设。无效区间/拟合失败在无条件覆盖分母内。'},ledger

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replications',type=int,default=150);p.add_argument('--check',action='store_true');a=p.parse_args()
    v,ledger=run(a.replications)
    for name,value in [('simulation-results.json',v),('simulation-ledger.json',ledger)]:
        b=encode(value);path=HERE/name
        if a.check:
            if path.read_bytes()!=b:raise ValueError('模拟复算不符')
        else:path.write_bytes(b)
