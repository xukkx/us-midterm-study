"""先封存四态预测再评分；匿名复算不读取受控逐人文件。"""
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from common import *
from engine import train,sufficient,summarize,METHODS
STATES=('D','I','R','not_sure')

def loadrows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s]
def fit(private):
    private=Path(private);rows=loadrows(private/'masked-input.jsonl');pred,model=train(rows)
    with (private/'predictions.jsonl').open('w',encoding='utf-8',newline='\n') as f:
        for r in pred:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    write(HERE/'model-fit.json',model)
    write(HERE/'predictions-seal.json',{'sealed_at':datetime.now(timezone.utc).isoformat(),'input_sha256':sha(private/'masked-input.jsonl'),'predictions_sha256':sha(private/'predictions.jsonl'),'model_sha256':sha(HERE/'model-fit.json'),'n':len(rows),'S0_hidden':all(r['y'] is None for r in rows if not r['s'])})
    print(json.dumps({'predictions':len(pred),'classes':4,'fit_features':18,'sealed_before_scoring':True}))
def describe(atoms):
    out=[]
    for g in GROUPS:
        for cohort in COHORTS:
            cs=[c for c in atoms if g in groups_from_flags(c['latino_employed'],c['r_renter']) and (cohort=='full' or c['s']==int(cohort=='retained'))]
            count=[[sum(c['n'] for c in cs if (c['before'],c['after'])==(a,b)) for b in STATES] for a in STATES]
            for weighted in (False,True):
                key='w' if weighted else 'n';mass=[[math.fsum(c[key] for c in cs if (c['before'],c['after'])==(a,b)) for b in STATES] for a in STATES];W=math.fsum(c[key] for c in cs);P=[[v/W for v in row] for row in mass]
                out.append({'group':g,'cohort':cohort,'weighted':weighted,'n':sum(c['n'] for c in cs),'denominator':W,'raw_counts':count,'matrix_mass':mass,'matrix':P,'R_change_pp':100*(sum(P[a][2] for a in range(4))-sum(P[2])),'not_sure_change_pp':100*(sum(P[a][3] for a in range(4))-sum(P[3])),'any_change_pp':100*(1-sum(P[a][a] for a in range(4)))})
    for g in GROUPS:
        subset=[r for r in out if r['group']==g and not r['weighted']];by={r['cohort']:r for r in subset}
        for a in range(4):
            for b in range(4):assert by['full']['raw_counts'][a][b]==by['retained']['raw_counts'][a][b]+by['omitted']['raw_counts'][a][b]
    return out
def summarize_benchmark(source):
    expected={(g,m) for g in GROUPS for m in METHODS};indexed={}
    rows=source.get('rows')
    if not isinstance(rows,list) or len(rows)!=9:raise ValueError('四态恢复必须恰有9行')
    for r in rows:
        k=(r.get('group'),r.get('method'))
        if k not in expected or k in indexed:raise ValueError('重复或未知组合')
        indexed[k]=r
    if set(indexed)!=expected:raise ValueError('恢复组合缺项')
    output=[]
    for g in GROUPS:
        for m in METHODS:
            r=indexed[(g,m)];e,ref=summarize(r['estimate']),summarize(r['reference'])
            output.append({'group':g,'method':m,'estimate':e,'reference':ref,'R_error_pp':e['R_change_pp']-ref['R_change_pp'],'NS_error_pp':e['not_sure_change_pp']-ref['not_sure_change_pp'],'any_change_error_pp':e['any_change_pp']-ref['any_change_pp'],'matrix_half_L1_pp':50*math.fsum(abs(e['matrix'][a][b]-ref['matrix'][a][b]) for a in range(4) for b in range(4)),'flow_error_pp':{k:e['flows_pp'][k]-ref['flows_pp'][k] for k in e['flows_pp']}})
    return output
def score(private):
    private=Path(private);seal=json.loads((HERE/'predictions-seal.json').read_bytes())
    if sha(private/'predictions.jsonl')!=seal['predictions_sha256'] or sha(HERE/'model-fit.json')!=seal['model_sha256']:raise ValueError('预测或模型封印失效')
    preds=loadrows(private/'predictions.jsonl');truthrows=loadrows(private/'scoring-truth.jsonl');truth={r['key']:r['y'] for r in truthrows}
    if len(truth)!=len(truthrows) or set(truth)!={r['key'] for r in preds}:raise ValueError('真值键不闭合')
    source=[];overlap=[]
    for g in GROUPS:
        rows=[r for r in preds if g in r['groups']];full=[dict(r,s=1,y=truth[r['key']]) for r in rows]
        for m in METHODS:source.append({'group':g,'method':m,'reference':sufficient(full,'unadjusted'),'estimate':sufficient(rows,m)})
        iw=[1/r['e'] for r in rows if r['s']];W=math.fsum(iw)
        overlap.append({'group':g,'n':len(rows),'observed_n':len(iw),'clipped_n':sum(abs(r['e']-r['e_raw'])>1e-12 for r in rows),'min_raw_e':min(r['e_raw'] for r in rows),'max_raw_e':max(r['e_raw'] for r in rows),'ipw_ess':W*W/math.fsum(w*w for w in iw),'largest_weight_share':max(iw)/W})
    write(HERE/'benchmark-sufficient.json',{'rows':source,'classes':list(STATES),'target':'四态全两波队列；真实匿名矩阵总和，不含逐人键/协变量'})
    write(HERE/'overlap.json',overlap)
    write(HERE/'unmask-audit.json',{'unmasked_at':datetime.now(timezone.utc).isoformat(),'prediction_sealed_at':seal['sealed_at'],'truth_sha256':sha(private/'scoring-truth.jsonl'),'n':len(truth),'training_truth_access':False})
def reproduce(check=False):
    atoms=json.loads((HERE/'pid-atoms.json').read_bytes())['atoms'];description=describe(atoms)
    benchmark=summarize_benchmark(json.loads((HERE/'benchmark-sufficient.json').read_bytes()))
    for r in benchmark:
        d=next(x for x in description if x['group']==r['group'] and x['cohort']=='full' and not x['weighted'])
        assert r['reference']['n']==d['n'] and all(abs(r['reference']['matrix'][a][b]-d['matrix'][a][b])<1e-12 for a in range(4) for b in range(4))
    for name,value in [('description.json',description),('benchmark-results.json',benchmark)]:
        b=encode(value)
        if check:
            if (HERE/name).read_bytes()!=b:raise ValueError('四态匿名复算不符')
        else:(HERE/name).write_bytes(b)
    print(json.dumps({'description_rows':len(description),'benchmark_rows':len(benchmark),'check':check,'recoveries':[{'group':r['group'],'method':r['method'],'R_error_pp':r['R_error_pp']} for r in benchmark]},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private');p.add_argument('--fit',action='store_true');p.add_argument('--score',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.fit:fit(a.private)
    elif a.score:score(a.private);reproduce()
    else:reproduce(a.check)
