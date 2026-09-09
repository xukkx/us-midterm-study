"""从实际预测汇出匿名充分统计；仅靠此包能复算恢复矩阵，不能重新训练真实nuisance。"""
import argparse,json,math
from pathlib import Path
from common import *
from benchmark import sufficient
from summary_core import summarize
from evaluate import MEASURES,METHODS

def export(private):
    private=Path(private);preds=[json.loads(s) for s in (private/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    truth={x['key']:x['y'] for x in map(json.loads,(private/'scoring-truth.jsonl').read_text(encoding='utf-8').splitlines())}
    out=[]
    for g in GROUPS:
        rs=[r for r in preds if g in r['groups']];full=[dict(r,s=1,y=truth[r['key']]) for r in rs]
        for m in METHODS:out.append({'group':g,'method':m,'reference':sufficient(full,'unadjusted'),'estimate':sufficient(rs,m)})
    write(HERE/'benchmark-sufficient.json',{'rows':out,'scope':'真实预测及评分真值的匿名矩阵总和；不是合成的个人行，没有受访者键、折号、H或逐人权重。'})

def check():
    source=json.loads((HERE/'benchmark-sufficient.json').read_bytes());result=json.loads((HERE/'benchmark-results.json').read_bytes());checks=0
    for a,b in zip(source['rows'],result['rows']):
        assert (a['group'],a['method'])==(b['group'],b['method'])
        for name in ('estimate','reference'):
            actual=summarize(a[name]);assert actual==b[name];checks+=1
        e,r=summarize(a['estimate']),summarize(a['reference'])
        assert {k:e[k]-r[k] for k in MEASURES}==b['recovery_error_pp'];checks+=1
        assert 50*sum(abs(e['matrix'][i][j]-r['matrix'][i][j]) for i in range(3) for j in range(3))==b['transition_total_variation_pp'];checks+=1
    print(json.dumps({'anonymous_recovery_checks':checks,'refits_real_microdata':False},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private');a=p.parse_args()
    if a.private:export(a.private)
    check()
