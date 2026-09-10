"""LH269 支持双轴与损失集中审计；只读取冻结 LH268 投影。"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path

HERE=Path(__file__).parent
BANDS=((0,0),(1,4),(5,19),(20,49),(50,None))
MASS=20.0
def band(n):
    for lo,hi in BANDS:
        if n>=lo and (hi is None or n<=hi): return f'{lo}+' if hi is None else f'{lo}-{hi}'
    raise ValueError('支持度不能为负')
def probs(q):
    if not isinstance(q,list) or len(q)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in q) or abs(math.fsum(q)-1)>1e-10: raise ValueError('概率向量非法')
    return [float(x) for x in q]
def score(q,y,b):
    q=probs(q); changed=int(y!=b); event=math.fsum(q[k] for k in range(4) if k!=b)
    if changed:
        if event<=0 or q[y]<=0: raise ValueError('变化结果无概率支持')
        el=math.log(event); dl=math.log(q[y]/event); bb=(event-1)**2
    else:
        if q[b]<=0: raise ValueError('未变化结果无概率支持')
        el=math.log(q[b]); dl=0.; bb=event**2
    return {'changed':changed,'full_log':math.log(q[y]),'event_log':el,'dest_log':dl,'binary_brier':bb,'multiclass_brier':math.fsum((q[k]-int(k==y))**2 for k in range(4)),'target_probability':q[y]}
def shrink(counts,prior,mass=MASS):
    if len(counts)!=4 or sum(counts)<0: raise ValueError('计数非法')
    prior=probs(prior); den=sum(counts)+mass
    return [(counts[k]+mass*prior[k])/den for k in range(4)]
def support_audit_rows(rows,challenger,map_1_to_8=(0,0,0,1,2,2,2,3),mass=MASS):
    folds=challenger.get('folds');
    if not isinstance(folds,list) or len(folds)!=5: raise ValueError('必须五折挑战者结果')
    if len(map_1_to_8)!=8: raise ValueError('映射维度错误')
    tests=[{} for _ in range(5)]
    for r in rows:
        try:
            vals=[r['PID20raw'],r['PID22raw'],r['PID24raw'],r['policy20'],r['policy22'],r['n']]
            if any(isinstance(x,bool) or not isinstance(x,int) for x in vals): raise ValueError('原码必须为整数')
            a=map_1_to_8[r['PID20raw']-1]; braw=r['PID22raw']; y=map_1_to_8[r['PID24raw']-1]; ps=[r['policy20'],r['policy22']]; fc=r['fold_counts']; n=r['n']
        except (KeyError,TypeError,ValueError,IndexError): raise ValueError('联合格行非法')
        if len(fc)!=5 or n<0 or any(x<0 for x in fc) or sum(fc)!=n: raise ValueError('人数/折计数不闭合')
        key=(a,braw,ps[0],ps[1],y)
        for f,v in enumerate(fc):
            if v: tests[f][key]=tests[f].get(key,0)+v
    out=[]
    for f,test in enumerate(tests):
        train={}
        for g,d in enumerate(tests):
            if g==f: continue
            for (a,braw,p20,p22,y),n in d.items(): train[(a,braw,p20,p22,y)]=train.get((a,braw,p20,p22,y),0)+n
        cells={}
        for a,braw,p20,p22,y in train:
            ck=(a,braw,p20,p22); cells.setdefault(ck,[0,0,0,0]); cells[ck][y]+=train[(a,braw,p20,p22,y)]
        for (a,braw,p20,p22,y),n in sorted(test.items()):
            ck=(a,braw,p20,p22); counts=cells.get(ck,[0,0,0,0]); total=sum(counts); target_n=counts[y]; w=total/(total+mass)
            sk='|'.join(map(str,ck)); saved=folds[f].get('training_cells',{}).get(sk)
            if not saved: raise ValueError('challenger缺少training_cells')
            if saved.get('training_target_counts')!=counts or saved.get('n_train')!=total: raise ValueError('training_cells计数与投影不一致')
            q0=probs(saved['baseline_q']); q1=probs(saved['q_new']); qcheck=shrink(counts,q0,mass)
            if any(abs(x-y)>1e-12 for x,y in zip(q1,qcheck)): raise ValueError('challenger q_new公式不一致')
            s0=score(q0,y,map_1_to_8[braw-1]); s1=score(q1,y,map_1_to_8[braw-1]); d={k:s1[k]-s0[k] for k in ('full_log','event_log','dest_log','binary_brier','multiclass_brier')}
            out.append({'fold':f,'feature':[a,braw,p20,p22],'target':y,'n_test':n,'n_train':total,'target_n':target_n,'train_counts':counts,'q_history':q0,'q_new':q1,'total_band':band(total),'target_band':band(target_n),'shrink_weight':w,'changed':s1['changed'],'target_probability':q1[y],'loss_delta':d})
    return out
def summarize(rows,axis):
    out={k:{'n_test':0,'changed_n':0,'target_n_sum':0,'weight_sum':0,'prob_sum':0,'loss_delta_sum':{k:0. for k in ('full_log','event_log','dest_log','binary_brier','multiclass_brier')},'dest_positive_sum':0.,'dest_negative_sum':0.,'dest_negative_n':0} for k in ('0-0','1-4','5-19','20-49','50+')}
    for r in rows:
        key=r[axis]; z=out.setdefault(key,{'n_test':0,'changed_n':0,'target_n_sum':0,'weight_sum':0,'prob_sum':0,'loss_delta_sum':{k:0. for k in ('full_log','event_log','dest_log','binary_brier','multiclass_brier')},'dest_positive_sum':0.,'dest_negative_sum':0.,'dest_negative_n':0})
        z['n_test']+=r['n_test']; z['changed_n']+=r['n_test']*r['changed']; z['target_n_sum']+=r['n_test']*r['target_n']; z['weight_sum']+=r['n_test']*r['shrink_weight']; z['prob_sum']+=r['n_test']*r['target_probability']
        for k,v in r['loss_delta'].items(): z['loss_delta_sum'][k]+=r['n_test']*v
        z['dest_positive_sum']+=r['n_test']*max(r['loss_delta']['dest_log'],0); z['dest_negative_sum']+=r['n_test']*min(r['loss_delta']['dest_log'],0)
        if r['loss_delta']['dest_log']<0: z['dest_negative_n']+=r['n_test']
    for z in out.values():
        n=z['n_test']; z['target_n_mean']=z.pop('target_n_sum')/n if n else None; z['weight_mean']=z.pop('weight_sum')/n if n else None; z['prob_mean']=z.pop('prob_sum')/n if n else None; z['loss_delta_mean']={k:(v/n if n else None) for k,v in z['loss_delta_sum'].items()}
    return out
def build_result():
    d=json.loads((HERE/'joint-counts.json').read_text(encoding='utf8')); c=json.loads((HERE/'challenger.json').read_text(encoding='utf8')); h=json.loads((HERE/'history-nested.json').read_text(encoding='utf8')); p=json.loads((HERE/'analysis-plan.json').read_text(encoding='utf8'))
    for fn in ('joint-counts.json','challenger.json','history-nested.json'):
        if hashlib.sha256((HERE/fn).read_bytes()).hexdigest()!=p['input_sha256'][fn]: raise ValueError('冻结输入hash不符')
    for f,fold in enumerate(c['folds']):
        for key,v in fold['training_cells'].items():
            a,b,*_=map(int,key.split('|'))
            if any(abs(x-y)>1e-15 for x,y in zip(v['baseline_q'],h['folds'][f]['child'][a][b-1])): raise ValueError('q_history不一致')
    rows=support_audit_rows(d['rows'],c,d['pid_map_1_to_8'],MASS)
    n=sum(x['n_test'] for x in rows); agg={k:sum(x['n_test']*x['loss_delta'][k] for x in rows) for k in ('full_log','event_log','dest_log','binary_brier','multiclass_brier')}
    dest_positive=sum(x['n_test']*max(x['loss_delta']['dest_log'],0) for x in rows); dest_negative=sum(x['n_test']*min(x['loss_delta']['dest_log'],0) for x in rows); dest_negative_n=sum(x['n_test'] for x in rows if x['loss_delta']['dest_log']<0)
    result={'schema':'LH269-support-audit-v1','contract':'LH-303','n':n,'rows':rows,'summaries':{'totalcell_band':summarize(rows,'total_band'),'realized_targetcount_band':summarize(rows,'target_band')},'totals':{'loss_delta_sum':agg,'loss_delta_mean':{k:v/n for k,v in agg.items()},'dest_log_positive_contribution':dest_positive,'dest_log_negative_contribution':dest_negative,'dest_log_negative_people':dest_negative_n},'bands':[list(x) for x in BANDS],'weight':'n_train/(n_train+20) 仅描述；所有评分和人数使用n_test','future_labels_diagnostic_only':True,'realized_target_count_diagnostic_only':True,'inputs':{x:hashlib.sha256((HERE/x).read_bytes()).hexdigest() for x in ('joint-counts.json','challenger.json','history-nested.json','analysis-plan.json')},'analysis_plan_sha256':hashlib.sha256((HERE/'analysis-plan.json').read_bytes()).hexdigest(),'mass':MASS}
    return result, rows, agg
def verify_result(actual,expected):
    if actual!=expected: raise AssertionError('支持审计封存结果与完整重算不一致')
    for r in actual['rows']:
        if abs(r['loss_delta']['full_log']-(r['loss_delta']['event_log']+r['loss_delta']['dest_log']))>1e-10: raise AssertionError('评分分解不闭合')
    return True
def run(check=False):
    result, rows, agg = build_result()
    outpath=HERE/'support-audit.json'
    if check:
        old=json.loads(outpath.read_text(encoding='utf8'))
        verify_result(old,result)
        # CSV 也是封存产物，逐字节重建比较。
        import io
        keys=['fold','feature','target','n_test','n_train','target_n','total_band','target_band','shrink_weight','changed','target_probability']; buf=io.StringIO(newline=''); w=csv.writer(buf); w.writerow(keys+['delta_'+k for k in agg]);
        for r in rows: w.writerow([r[k] for k in keys]+[r['loss_delta'][k] for k in agg])
        if (HERE/'support-audit.csv').read_text(encoding='utf8').replace('\r\n','\n')!=buf.getvalue().replace('\r\n','\n'): raise AssertionError('CSV封存结果与完整重算不一致')
        sb=io.StringIO(newline=''); sw=csv.writer(sb); sw.writerow(['axis','band','n_test','changed_n','target_n_mean','shrink_weight_mean','prob_mean','full_log_sum','event_log_sum','dest_log_sum','binary_brier_sum','multiclass_brier_sum','dest_positive_sum','dest_negative_sum','dest_negative_n'])
        for axis,vals in result['summaries'].items():
            for b,z in vals.items(): sw.writerow([axis,b,z['n_test'],z['changed_n'],z['target_n_mean'],z['weight_mean'],z['prob_mean']]+[z['loss_delta_sum'][k] for k in agg]+[z['dest_positive_sum'],z['dest_negative_sum'],z['dest_negative_n']])
        if (HERE/'support-summary.csv').read_text(encoding='utf8').replace('\r\n','\n')!=sb.getvalue().replace('\r\n','\n'): raise AssertionError('summary CSV封存结果与完整重算不一致')
        print(json.dumps({'check':'passed','n':result['n'],'cells':len(rows)},ensure_ascii=False)); return
    outpath.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    keys=['fold','feature','target','n_test','n_train','target_n','total_band','target_band','shrink_weight','changed','target_probability']
    with (HERE/'support-audit.csv').open('w',newline='',encoding='utf8') as fp:
        w=csv.writer(fp); w.writerow(keys+['delta_'+k for k in agg]);
        for r in rows: w.writerow([r[k] for k in keys]+[r['loss_delta'][k] for k in agg])
    with (HERE/'support-summary.csv').open('w',newline='',encoding='utf8') as fp:
        w=csv.writer(fp); w.writerow(['axis','band','n_test','changed_n','target_n_mean','shrink_weight_mean','prob_mean','full_log_sum','event_log_sum','dest_log_sum','binary_brier_sum','multiclass_brier_sum','dest_positive_sum','dest_negative_sum','dest_negative_n'])
        for axis,vals in result['summaries'].items():
            for b,z in vals.items(): w.writerow([axis,b,z['n_test'],z['changed_n'],z['target_n_mean'],z['weight_mean'],z['prob_mean']]+[z['loss_delta_sum'][k] for k in agg]+[z['dest_positive_sum'],z['dest_negative_sum'],z['dest_negative_n']])
    print(json.dumps({'n':result['n'],'cells':len(rows),'totals':agg},ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--run',action='store_true'); ap.add_argument('--check',action='store_true'); a=ap.parse_args(); run(a.check)
