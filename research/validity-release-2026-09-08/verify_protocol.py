"""验证协议封存、可达上限和时点/评分的独立反例；不读取旧封存结果。"""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent
def admissible(source,cutoff):
    required={'available_at','observed_for','sha256','office','is_outcome'}
    if set(source)!=required:raise ValueError('来源字段不完整或混入未知字段')
    if source['is_outcome']:raise ValueError('结果不可用作预测输入')
    if datetime.fromisoformat(source['available_at'])>datetime.fromisoformat(cutoff):raise ValueError('输入晚于截止')
    if source['office'] not in {'house','senate'}:raise ValueError('院别错误')
    if len(source['sha256'])!=64 or any(c not in '0123456789abcdef' for c in source['sha256']):raise ValueError('缺少内容哈希')
    return True

def loss(predicted,actual):
    if not predicted or len(predicted)!=len(actual):raise ValueError('目标数不一致')
    if not all(math.isfinite(x) and -100<=x<=100 for x in [*predicted,*actual]):raise ValueError('票差非法')
    errors=[p-y for p,y in zip(predicted,actual)]
    return sum(abs(e) for e in errors)/len(errors),math.sqrt(sum(e*e for e in errors)/len(errors))

def main():
    p=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    seal=json.loads((HERE/'protocol-seal.json').read_text(encoding='utf-8'))
    for name,want in seal['files'].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==want,name
    historical_max=len(p['training_candidate_cycles'])-p['minimum_prior_training_cycles']
    assert historical_max==6 and p['future_cycles_available']==1
    assert p['maximum_evidence_status']=='experimental'
    assert p['candidate_features_max']==1 and p['cycle_weighting']=='equal'
    assert p['requires_new_post_election_approval'] and not p['legacy_seals_read']
    good={'available_at':'2026-10-05T04:00:00+00:00','observed_for':'2026-10-03','sha256':'a'*64,'office':'house','is_outcome':False}
    assert admissible(good,p['forecast_as_of'])
    rejected=0
    for mutation in ({'available_at':'2026-10-06T04:00:01+00:00'},{'is_outcome':True},{'office':'president'},{'sha256':''},{'unregistered_parameter':1}):
        try:admissible(good|mutation,p['forecast_as_of'])
        except ValueError:rejected+=1
    assert rejected==5
    mae,rmse=loss([0,4],[2,0]);assert mae==3 and math.isclose(rmse,math.sqrt(10))
    ready=json.loads((HERE/'readiness.json').read_text(encoding='utf-8'))
    assert ready['prediction_sha256'] is None
    print(json.dumps({'ok':True,'rules_sealed':True,'historical_holdout_upper_bound':historical_max,'future_cycles':1,'negative_checks_rejected':rejected,'forecast_ready':False}))

if __name__=='__main__':main()
