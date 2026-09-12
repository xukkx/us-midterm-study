"""预测封印后才读取已知S0结局；只输出匿名恢复诊断。"""
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from common import *
from benchmark import metrics

METHODS=('unadjusted','baseline_standardization','crossfit_aipw')
MEASURES=('R22_pp','R_change_pp','D_to_R_pp','R_to_D_pp','I_to_R_pp','R_to_I_pp','D_to_I_pp','I_to_D_pp','gross_category_change_pp','R_nonzero_change_pp')
def quantile(values,q):
    v=sorted(values);z=(len(v)-1)*q;j=int(z);return v[j]+(v[min(j+1,len(v)-1)]-v[j])*(z-j)
def shifted(p,delta):
    z=math.log(p)-math.log1p(-p)+delta
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))
def sensitivity_value(rows,delta):
    return 100*math.fsum((int(r['y']==2) if r['s'] else shifted(r['m'][2],delta))-int(r['y0']==2) for r in rows)/len(rows)
def root(rows,target=0):
    lo,hi=-12.,12.
    if sensitivity_value(rows,lo)>target or sensitivity_value(rows,hi)<target:return None
    for _ in range(70):
        mid=(lo+hi)/2
        if sensitivity_value(rows,mid)<target:lo=mid
        else:hi=mid
    return (lo+hi)/2
def fixed_influence(rows,method):
    rs=[r for r in rows if r['s']] if method=='unadjusted' else rows
    vals=[(int(r['y']==2) if method=='unadjusted' else r['std'][2] if method=='baseline_standardization' else r['phi'][2])-int(r['y0']==2) for r in rs]
    mean=math.fsum(vals)/len(vals);moves=[100*(mean-v)/(len(vals)-1) for v in vals]
    return {'conditional_on_fixed_nuisance':True,'not_refitted_LOO':True,'n':len(vals),'maximum_absolute_delete_one_shift_pp':max(map(abs,moves)),
            'delete_one_estimate_range_pp':[mean*100+min(moves),mean*100+max(moves)]}

def compute(preds,truth):
    if set(truth)!={r['key'] for r in preds}:raise ValueError('评分真值键不完整')
    for r in preds:
        if r['s'] and r['y']!=truth[r['key']]:raise ValueError('评分文件与已观察结局冲突')
    output=[];sensitivity=[];overlap=[]
    for g in GROUPS:
        rs=[r for r in preds if g in r['groups']]
        full=[dict(r,s=1,y=truth[r['key']]) for r in rs]
        reference=metrics(full,'unadjusted')
        refmatrix=reference['matrix']
        for method in METHODS:
            est=metrics(rs,method)
            output.append({'group':g,'method':method,'reference_n':len(rs),'observed_n':sum(r['s'] for r in rs),'estimate':est,'reference':reference,
                           'recovery_error_pp':{k:est[k]-reference[k] for k in MEASURES},
                           'transition_total_variation_pp':50*sum(abs(est['matrix'][a][b]-refmatrix[a][b]) for a in range(3) for b in range(3)),
                           'fixed_nuisance_influence':fixed_influence(rs,method)})
        iw=[1/r['e'] for r in rs if r['s']];W=math.fsum(iw);largest=sorted(iw,reverse=True)
        raw=[r['e_raw'] for r in rs]
        overlap.append({'group':g,'target_n':len(rs),'S1_n':len(iw),'raw_propensity_quantiles':{str(q):quantile(raw,q) for q in [0,.01,.05,.5,.95,.99,1]},
                        'propensity_clipped_n':sum(abs(r['e']-r['e_raw'])>1e-12 for r in rs),'ipw_ess':W*W/math.fsum(w*w for w in iw),
                        'max_ipw_share':max(iw)/W,'top_one_percent_ipw_share':math.fsum(largest[:max(1,math.ceil(len(iw)/100))])/W,
                        'outcome_nuisance_scope':'全体S1训练；不在子组内另拟合'})
        kept=metrics(rs,'unadjusted')['R_change_pp']
        scenarios=[{'delta':d,'completed_change_pp':sensitivity_value(rs,d),'retained_minus_completed_pp':kept-sensitivity_value(rs,d)} for d in [-2,-1,-.5,0,.5,1,2]]
        sensitivity.append({'group':g,'target_n':len(rs),'reference_complete_case_change_pp':reference['R_change_pp'],'scenarios':scenarios,
                            'net_change_zero_delta':root(rs),'selection_B_zero_delta':root(rs,kept),
                            'scope':'只为本早期完整案例参考队列的遮蔽S0赋假设概率；不是对原本不确定回答补值或校正2024。',
                            'missingness_parameter_learned_from_missing_outcomes':False})
    return {'rows':output,'overlap':overlap,'MNAR_sensitivity':sensitivity,'real_data_sampling_intervals':'不为已知经验参考值给95%区间；模型区间程序只在明示合成DGP中验覆盖。'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--private',required=True);p.add_argument('--check',action='store_true');a=p.parse_args();private=Path(a.private)
    seal=json.loads((HERE/'predictions-seal.json').read_bytes())
    assert sha(private/'predictions.jsonl')==seal['predictions_sha256'] and sha(HERE/'model-fit.json')==seal['model_sha256']
    preds=[json.loads(s) for s in (private/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(r['y'] is None for r in preds if not r['s'])
    truth_rows=[json.loads(s) for s in (private/'scoring-truth.jsonl').read_text(encoding='utf-8').splitlines()]
    truth={r['key']:r['y'] for r in truth_rows};assert len(truth)==len(truth_rows)
    v=compute(preds,truth);b=encode(v);path=HERE/'benchmark-results.json'
    if a.check:
        if path.read_bytes()!=b:raise ValueError('校准评分复算不符')
    else:
        path.write_bytes(b)
        write(HERE/'unmask-audit.json',{'unmasked_at':datetime.now(timezone.utc).isoformat(),'prediction_sealed_at':seal['sealed_at'],'prediction_sha256':seal['predictions_sha256'],'truth_sha256':sha(private/'scoring-truth.jsonl'),'scoring_only':True})
    print(json.dumps({'check':a.check,'comparison_rows':len(v['rows']),'recoveries':[{'group':x['group'],'method':x['method'],'R_change_pp':x['estimate']['R_change_pp'],'error_pp':x['recovery_error_pp']['R_change_pp']} for x in v['rows']]},ensure_ascii=False))
if __name__=='__main__':main()
