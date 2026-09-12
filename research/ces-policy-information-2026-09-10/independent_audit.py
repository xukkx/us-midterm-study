"""独立路径核查新分析；不调用两个生产分析器的函数。"""
import hashlib,json,math
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
MAP=(0,0,0,1,2,2,2,3)
KEYS=('full_log','event_log','dest_log','binary_brier','multiclass_brier')
def read(n):return json.loads((HERE/n).read_bytes())
def near(a,b):
    if not math.isfinite(a) or not math.isfinite(b) or abs(a-b)>1e-9:raise ValueError('独立数值不一致')
def band(x):return '0-0' if x==0 else '1-4' if x<5 else '5-19' if x<20 else '20-49' if x<50 else '50+'
def scores(q,y,b):
    if len(q)!=4 or min(q)<0 or abs(sum(q)-1)>1e-12 or q[y]<=0:raise ValueError('四维概率非法')
    changed=y!=b;p=1-q[b];full=math.log(q[y]);event=math.log(p if changed else q[b])
    return (full,event,full-event,(p-changed)**2,sum((q[k]-(k==y))**2 for k in range(4)))
def audit():
    d,h,c,s,m=(read(n) for n in ('joint-counts.json','history-nested.json','challenger.json','support-audit.json','matched-test.json'))
    folds=[defaultdict(lambda:[0,0,0,0]) for _ in range(5)];tables=defaultdict(lambda:[[0]*4 for _ in range(9)])
    for r in d['rows']:
        a,b,y=MAP[r['PID20raw']-1],r['PID22raw'],MAP[r['PID24raw']-1]
        feature=(a,b,r['policy20'],r['policy22'])
        for f,n in enumerate(r['fold_counts']):folds[f][feature][y]+=n
        tables[a,b][3*r['policy20']+r['policy22']][y]+=r['n']
    observed={(r['fold'],tuple(r['feature']),r['target']):r for r in s['rows']}
    if len(observed)!=len(s['rows']):raise ValueError('审计行重复')
    totals=[0.]*5;checked=0;counts=0;by=defaultdict(list)
    for f,features in enumerate(folds):
        for feature,ys in features.items():
            a,b,_,_=feature;train=[sum(folds[g][feature][y] for g in range(5) if g!=f) for y in range(4)]
            q0=h['folds'][f]['child'][a][b-1];cell=c['folds'][f]['training_cells']['|'.join(map(str,feature))];q1=cell['q_new']
            if train!=cell['training_target_counts'] or sum(train)!=cell['n_train']:raise ValueError('冻结训练计数错误')
            for y in range(4):near(q0[y],cell['baseline_q'][y]);near(q1[y],(train[y]+20*q0[y])/(sum(train)+20))
            for y,n in enumerate(ys):
                if not n:continue
                r=observed.get((f,feature,y));checked+=1;counts+=n
                if r is None or r['n_test']!=n or r['n_train']!=sum(train) or r['target_n']!=train[y] or r['train_counts']!=train or r['changed']!=int(y!=MAP[b-1]):raise ValueError('留出审计行计数错误')
                if r['total_band']!=band(sum(train)) or r['target_band']!=band(train[y]):raise ValueError('支持分带错误')
                near(r['shrink_weight'],sum(train)/(sum(train)+20));near(r['target_probability'],q1[y])
                before,after=scores(q0,y,MAP[b-1]),scores(q1,y,MAP[b-1]);delta=[v-u for u,v in zip(before,after)]
                for j,k in enumerate(KEYS):near(r['loss_delta'][k],delta[j]);totals[j]+=n*delta[j]
                for j in range(4):near(r['q_history'][j],q0[j]);near(r['q_new'][j],q1[j])
                for axis,bkey in (('totalcell_band','total_band'),('realized_targetcount_band','target_band')):by[axis,r[bkey]].append((r,delta))
    if checked!=544 or counts!=6175 or len(observed)!=checked:raise ValueError('审计留出覆盖错误')
    for j,k in enumerate(KEYS):near(s['totals']['loss_delta_sum'][k],totals[j]);near(s['totals']['loss_delta_mean'][k],totals[j]/6175)
    for axis in ('totalcell_band','realized_targetcount_band'):
        for b in ('0-0','1-4','5-19','20-49','50+'):
            z=s['summaries'][axis][b];rr=by[axis,b];n=sum(r['n_test'] for r,_ in rr)
            if z['n_test']!=n or z['changed_n']!=sum(r['n_test']*r['changed'] for r,_ in rr):raise ValueError('分带人数不符')
            for j,k in enumerate(KEYS):near(z['loss_delta_sum'][k],sum(r['n_test']*v[j] for r,v in rr))
            near(z['dest_positive_sum'],sum(r['n_test']*max(v[2],0) for r,v in rr));near(z['dest_negative_sum'],sum(r['n_test']*min(v[2],0) for r,v in rr))
    if (m.get('n'),m.get('layer_n'),m.get('draws'),m.get('seed'))!=(6175,31,99999,26920260910):raise ValueError('匹配检验生产目标错误')
    lookup={tuple(r['H']):r for r in m['layers']};mi=tv=0.
    def ent(v):
        n=sum(v);return math.log(n)-sum(x*math.log(x) for x in v if x)/n
    for key,t in tables.items():
        if lookup[key]['table']!=t:raise ValueError('匹配检验表不一致')
        rows=list(map(sum,t));cols=list(map(sum,zip(*t)));n=sum(rows)
        if lookup[key]['W_margins']!=rows or lookup[key]['Y_margins']!=cols:raise ValueError('匹配边际错误')
        mi+=n/6175*(ent(rows)+ent(cols)-ent([x for row in t for x in row]))
        tv+=sum(abs(t[i][j]-rows[i]*cols[j]/n) for i in range(9) for j in range(4))/2/6175
    near(m['statistics']['MI']['observed'],mi);near(m['statistics']['TV']['observed'],tv)
    corrected={k:sum(c['early_five_group_scores'][g]['score'][k] for g in ('early_same_changed','early_diff_return','early_diff_third')) for k in KEYS}
    old=read('comparison.json')['challenge_vs_frozen_child']['cohorts']['changed414']['metrics']
    for k in KEYS:near(old[k]['new_sum'],corrected[k]+c['early_five_group_scores']['early_diff_keep']['score'][k])
    return {'support_rows':checked,'n':counts,'support_means':dict(zip(KEYS,[v/6175 for v in totals])),'matched_draws':m['draws'],'matched_MI_entropy_reference':mi,'matched_TV_reference':tv,'frozen_training_cells_checked':sum(len(x) for x in folds),'changed414_correct_totals':corrected}
