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

def check(source=None,result=None):
    if source is None:source=json.loads((HERE/'benchmark-sufficient.json').read_bytes())
    if result is None:result=json.loads((HERE/'benchmark-results.json').read_bytes())
    expected={(g,m) for g in GROUPS for m in METHODS}
    def indexed(value):
        if not isinstance(value,dict) or not isinstance(value.get('rows'),list) or len(value['rows'])!=9:
            raise ValueError('匿名校验必须有完整九行')
        output={}
        for row in value['rows']:
            if not isinstance(row,dict) or not isinstance(row.get('group'),str) or not isinstance(row.get('method'),str):
                raise ValueError('群体和方法必须为字符串')
            key=(row['group'],row['method'])
            if key not in expected or key in output:raise ValueError('意外或重复的群体方法组合')
            output[key]=row
        if set(output)!=expected:raise ValueError('匿名组合不完整')
        return output
    left,right=indexed(source),indexed(result);checks=0
    for key in sorted(expected):
        a,b=left[key],right[key]
        for name in ('estimate','reference'):
            actual=summarize(a[name])
            if actual!=b[name]:raise ValueError('匿名均值或矩阵复算不符')
            checks+=1
        e,r=summarize(a['estimate']),summarize(a['reference'])
        if {k:e[k]-r[k] for k in MEASURES}!=b['recovery_error_pp']:raise ValueError('恢复误差不符')
        checks+=1
        if 50*sum(abs(e['matrix'][i][j]-r['matrix'][i][j]) for i in range(3) for j in range(3))!=b['transition_total_variation_pp']:raise ValueError('转移矩阵差异不符')
        checks+=1
    if checks!=36:raise ValueError('匿名核验未完成36项检查')
    print(json.dumps({'anonymous_recovery_checks':checks,'refits_real_microdata':False},ensure_ascii=False))
    return checks
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private');a=p.parse_args()
    if a.private:export(a.private)
    check()
