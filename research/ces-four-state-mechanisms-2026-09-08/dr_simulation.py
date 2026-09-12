"""隔离双重稳健点性质与推断覆盖；合成数据从不作为经验选民。"""
import argparse,itertools,json,math,random,statistics
from common import *
from engine import train,METHODS
SCENARIOS=('response_correct_outcome_wrong','outcome_correct_response_wrong','MNAR_negative_control')
def expit(x):return 1/(1+math.exp(-x))
def probabilities(x,z,b):return expit(-1+1.2*b+.6*x+z+x*z),expit(-.4+.6*x-.9*z+.8*x*z)
def saturated(r):
    x,z,b=r['x'],r['z'],r['y0'];return [1,x,z,b,x*z,x*b,z*b,x*z*b]
def wrong(r):return [1,r['x'],r['y0']]
def truth(group):
    return math.fsum(.25*(.45 if b else .55)*(probabilities(x,z,b)[0]-b)*(2 if group=='z1' else 1) for x,z,b in itertools.product((0,1),repeat=3) if group=='all' or z==1)*100
def generate(n,rng,scenario):
    rows=[]
    for i in range(n):
        x=int(rng.random()<.5);z=int(rng.random()<.5);b=int(rng.random()<.45);m,e=probabilities(x,z,b);y=int(rng.random()<m)
        if scenario=='MNAR_negative_control':e=expit(math.log(e/(1-e))+1.2*y)
        s=int(rng.random()<e)
        rows.append({'key':str(i),'fold':i%5,'x':x,'z':z,'y0':b,'y':y if s else None,'s':s,'housing':x,'truth_y':y})
    full=[dict(r,s=1,y=r['truth_y']) for r in rows]
    masked=[{k:v for k,v in r.items() if k!='truth_y'} for r in rows]
    return masked,full
def scalar(rows,method,if_variance=False):
    if method=='unadjusted':return [r['y']-r['y0'] for r in rows if r['s']]
    name='phi' if method=='crossfit_aipw' else 'std_phi' if if_variance else 'std'
    return [r[name][1]-r['y0'] for r in rows]
def estimate_interval(rows,method,full_population):
    values=scalar(rows,method);point=100*statistics.mean(values)
    invalid=lambda why:{'estimate_pp':point,'ci95_pp':None,'state':why,'valid':False}
    if method=='baseline_standardization' and {r['key'] for r in rows}!={r['key'] for r in full_population}:return invalid('unsupported_standardization_subgroup')
    changes=[r['y']-r['y0'] for r in rows if r['s']]
    legal=([-1] if all(r['y0']==1 for r in rows) else [1] if all(r['y0']==0 for r in rows) else [-1,1])
    if any(changes.count(d)<5 for d in legal):return invalid('sparse_transitions')
    iv=scalar(rows,method,True);var=statistics.variance(iv) if len(iv)>1 else 0
    if var<=1e-20:return invalid('degenerate_variance')
    if method=='baseline_standardization' and abs(statistics.mean(iv)*100-point)>1e-9:raise ValueError('标准化完整人群中心不匹配')
    se=100*math.sqrt(var/len(iv))
    return {'estimate_pp':point,'ci95_pp':[point-1.96*se,point+1.96*se],'state':'iid_contribution_approximation_not_DR_coverage_guarantee','valid':True}
def oracle_identity():
    output=[]
    for group in ('all','z1'):
        for correct in ('response','outcome','neither'):
            bias=0.
            for x,z,b in itertools.product((0,1),repeat=3):
                if group=='z1' and z!=1:continue
                m,e=probabilities(x,z,b);ms=m if correct=='outcome' else expit(-.3+.6*x+1.2*b);es=e if correct=='response' else expit(-.2+.6*x)
                bias+=.25*(.45 if b else .55)*(2 if group=='z1' else 1)*(1-e/es)*(ms-m)
            output.append({'group':group,'correct_nuisance':correct,'exact_expected_bias_pp':100*bias})
    return output
def run(reps=120):
    rng=random.Random(26420260909);ledger=[];failures=[];summaries=[]
    for n in (600,2400):
        for scenario in SCENARIOS:
            for rep in range(reps):
                rows,full=generate(n,rng,scenario)
                try:
                    fn_m=wrong if scenario=='response_correct_outcome_wrong' else saturated
                    fn_e=wrong if scenario=='outcome_correct_response_wrong' else saturated
                    pred,_=train(rows,2,fn_m,fn_e)
                    for group in ('all','z1'):
                        sub=[r for r in pred if group=='all' or r['z']==1];ref=[r for r in full if group=='all' or r['z']==1];target=truth(group)
                        for method in METHODS:
                            estimate=estimate_interval(sub,method,pred);ci=estimate['ci95_pp'];covered=bool(estimate['valid'] and ci[0]<=target<=ci[1])
                            ledger.append({'n':n,'scenario':scenario,'replication':rep,'group':group,'method':method,**estimate,'population_truth_pp':target,'empirical_full_pp':100*statistics.mean(r['y']-r['y0'] for r in ref),'covered':covered})
                except (ValueError,ArithmeticError) as ex:failures.append({'n':n,'scenario':scenario,'replication':rep,'error':str(ex)})
            for group in ('all','z1'):
                for method in METHODS:
                    rs=[r for r in ledger if (r['n'],r['scenario'],r['group'],r['method'])==(n,scenario,group,method)];vals=[r['estimate_pp'] for r in rs];target=truth(group);valid=[r for r in rs if r['valid']];covered=sum(r['covered'] for r in rs);cov=covered/reps
                    summaries.append({'n':n,'scenario':scenario,'group':group,'method':method,'planned_replications':reps,'successful_replications':len(rs),'truth_pp':target,'bias_pp':statistics.mean(vals)-target if vals else None,'rmse_pp':math.sqrt(statistics.mean((x-target)**2 for x in vals)) if vals else None,'empirical_sd_pp':statistics.stdev(vals) if len(vals)>1 else None,'bias_MCSE_pp':statistics.stdev(vals)/math.sqrt(len(vals)) if len(vals)>1 else None,'valid_intervals':len(valid),'interval_availability':len(valid)/reps,'unconditional_coverage':cov,'coverage_MCSE':math.sqrt(cov*(1-cov)/reps),'coverage_given_available':covered/len(valid) if valid else None})
            print(json.dumps({'DR_stage':scenario,'n':n,'replications':reps,'failures':len(failures)}),flush=True)
    return {'summaries':summaries,'failures':failures,'oracle_identity':oracle_identity(),'coverage_scope':'点的双重稳健不保证本贡献方差区间；标准化子组区间未实现。'},ledger
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--replications',type=int,default=120);a=p.parse_args();v,ledger=run(a.replications)
    for name,value in [('dr-results.json',v),('dr-ledger.json',ledger)]:
        b=encode(value)
        if a.check:
            if (HERE/name).read_bytes()!=b:raise ValueError('DR模拟复算不符')
        else:(HERE/name).write_bytes(b)
