"""只从两波原件计算早期转移；三波文件只提供成员键及连接核验字段。"""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from transition_summary import summarize

HERE = Path(__file__).resolve().parent
GROUPS = ('all', 'Latino_employed_2020', 'R_renter_2020')
COHORTS = ('full', 'retained', 'omitted')
WEIGHTS = {'house': 'commonpostweight_22', 'pid': 'commonweight_22'}
BASELINE = ('pid7_20', 'race_20', 'hispanic_20', 'employ_20', 'ownhome_20', 'CC20_410', 'CC20_327a')
MISSING = {'', 'NA', 'N/A', 'NAN', 'NULL', '.'}
KNOWN = {'D', 'R', 'I', 'other', 'not_race', 'not_vote'}
EXCLUDED = {'other', 'not_race', 'not_vote'}

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def projected_rows(path, columns):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f)
        header = next(rd, [])
        if not header or len(header) != len(set(header)) or not set(columns) <= set(header):
            raise ValueError('CSV表头为空、重复或缺少必要字段')
        ix = {k: header.index(k) for k in columns}
        for row in rd:
            if len(row) != len(header): raise ValueError('CSV行宽不符')
            yield {k: row[i].strip() for k, i in ix.items()}

def code(value, allowed):
    if str(value).upper() in MISSING: return None
    try: number = float(value)
    except (TypeError, ValueError): raise ValueError('类别编码非法') from None
    if not math.isfinite(number) or not number.is_integer() or int(number) not in allowed:
        raise ValueError('类别编码未核定')
    return int(number)

def pid(value):
    c = code(value, range(1, 9))
    return 'D' if c in (1, 2, 3) else 'R' if c in (5, 6, 7) else 'I' if c == 4 else 'unknown'

def groups(row):
    p=code(row['pid7_20'], range(1,9));o=code(row['ownhome_20'], range(1,4))
    r=code(row['race_20'], range(1,9));h=code(row['hispanic_20'], (1,2));e=code(row['employ_20'], range(1,10))
    result=['all']
    if (r==3 or h==1) and e in (1,2): result.append('Latino_employed_2020')
    if p in (5,6,7) and o==2: result.append('R_renter_2020')
    return result

def party_field(year, slot, post=False):
    if year==20 and slot==9: return 'HouseCand9Party'+('_post' if post else '')
    return f'HouseCand{slot}Party'+('_post' if post else '')+f'_{year}'

def house(row, year):
    took = code(row[f'tookpost_{year}'], (1,2))
    c = code(row[f'CC{year}_412'], list(range(1, 10 if year==20 else 9))+[10,11,12,13])
    if took != 2: return 'not_post' if took==1 else 'unknown_post'
    if c is None: return 'missing_item'
    if c >= 10: return {10:'other',11:'not_race',12:'not_vote',13:'unknown'}[c]
    v = row[party_field(year,c)]
    if v.upper() in MISSING: return 'unknown_party'
    if v in ('Democratic','Republican'): return 'D' if v=='Democratic' else 'R'
    if v not in {'Libertarian','Independent','Conservative','Green','Working Families','Socialist Workers','Liberty','Working Class','Constitution','Independent American','United Utah','Alliance','Moderate','Unity','Center','No Party Preference'}:
        raise ValueError('候选人党派编码未核定')
    return 'other'

def weight(value):
    if value.upper() in MISSING: return None
    try: w=float(value)
    except ValueError: raise ValueError('权重非法') from None
    if not math.isfinite(w) or w<0: raise ValueError('权重非法')
    return w

def member_map(path, id_column, extra=()):
    result={};wave_ids=set()
    for r in projected_rows(path, [id_column,'caseid_22',*BASELINE,*extra]):
        a,b=r[id_column],r['caseid_22']
        if a.upper() in MISSING or b.upper() in MISSING or a in result or b in wave_ids:
            raise ValueError('连接键缺失或重复')
        wave_ids.add(b);result[a]=r
    return result

def build(baseline_path, selected_path):
    source=json.loads((HERE/'source-manifest.json').read_bytes())
    if sha(baseline_path)!=source['baseline']['sha256'] or sha(selected_path)!=source['selected']['sha256']:
        raise ValueError('原件哈希不符')
    selected=member_map(selected_path,'caseid_20')
    extra=['pid7_22','tookpost_20','tookpost_22','CC20_412','CC22_412',*WEIGHTS.values()]
    for y in (20,22):
        for slot in range(1,10 if y==20 else 9):
            extra += [party_field(y,slot),party_field(y,slot,True)]
    baseline=member_map(baseline_path,'caseid',extra)
    if not set(selected)<=set(baseline): raise ValueError('三波存在两波外个案')
    for k,r in selected.items():
        if any(r[c]!=baseline[k][c] for c in (*BASELINE,'caseid_22')):
            raise ValueError('跨文件基线或2022键不一致')
    agg={};totals={g:{c:0 for c in COHORTS} for g in GROUPS}
    candidate_audit={str(y):{'nonmissing_pre_post_disagreement_n':0,'selected_pre_party_missing_n':0} for y in (20,22)}
    for k,r in baseline.items():
        cs=['full','retained' if k in selected else 'omitted']
        states={'pid':(pid(r['pid7_20']),pid(r['pid7_22'])),'house':(house(r,20),house(r,22))}
        for y in (20,22):
            slot=code(r[f'CC{y}_412'], list(range(1,10 if y==20 else 9))+[10,11,12,13])
            if slot is not None and slot<10 and code(r[f'tookpost_{y}'],(1,2))==2:
                pre,post=r[party_field(y,slot)],r[party_field(y,slot,True)]
                if pre.upper() in MISSING: candidate_audit[str(y)]['selected_pre_party_missing_n']+=1
                elif post.upper() not in MISSING and pre!=post: candidate_audit[str(y)]['nonmissing_pre_post_disagreement_n']+=1
        w={m:weight(r[col]) for m,col in WEIGHTS.items()}
        for g in groups(r):
            for cohort in cs:
                totals[g][cohort]+=1
                for m,(a,b) in states.items():
                    key=(g,cohort,m,a,b)
                    v=agg.setdefault(key, {'n':0,'positive_n':0,'weight_missing_n':0,'weight_zero_n':0,'weights':[]})
                    v['n']+=1
                    if w[m] is None: v['weight_missing_n']+=1
                    elif w[m]==0: v['weight_zero_n']+=1
                    else: v['positive_n']+=1;v['weights'].append(w[m])
    cells=[]
    for (g,c,m,a,b),v in sorted(agg.items()):
        ws=v.pop('weights')
        cells.append(dict(group=g,cohort=c,measure=m,before=a,after=b,**v,w=math.fsum(ws),w2=math.fsum(x*x for x in ws)))
    if any(v['nonmissing_pre_post_disagreement_n'] for v in candidate_audit.values()):
        raise ValueError('候选人选前选后党派不同，需核实映射')
    audit={'baseline_n':len(baseline),'retained_n':len(selected),'omitted_n':len(baseline)-len(selected),
           'selected_outside_baseline_n':0,'baseline_field_disagreements':{k:0 for k in BASELINE},'wave22_key_disagreements_n':0,
           'ids_unique_nonmissing':True,'candidate_party_audit':candidate_audit,
           'data_read_scope':'全部政治结局与权重来自两波文件；三波仅读连接键及七个既定2020核验字段，不计算2024结局。'}
    return {'schema_version':1,'source_hashes':{k:source[k]['sha256'] for k in ('baseline','selected')},'totals':totals,'cells':cells,'link_audit':audit}

def row_result(cells, group, cohort, measure):
    cs=[x for x in cells if (x['group'],x['cohort'],x['measure'])==(group,cohort,measure)]
    allowed={'D','R'} if measure=='house' else {'D','I','R'}
    eligible=lambda c:c['before'] in allowed and c['after'] in allowed
    known_out=lambda c:c['before'] in EXCLUDED or c['after'] in EXCLUDED
    est=summarize(cs,allowed)
    nn=lambda p:sum(c['n'] for c in cs if p(c))
    pn=lambda p:sum(c['positive_n'] for c in cs if p(c))
    weight_only=[dict(c,n=c['positive_n']) for c in cs]
    est['unweighted_positive_weight_delta_pp']=summarize(weight_only,allowed)['unweighted_delta_pp']
    est['forward_positive_n']=pn(lambda c:eligible(c) and c['before']!='R' and c['after']=='R')
    est['reverse_positive_n']=pn(lambda c:eligible(c) and c['before']=='R' and c['after']!='R')
    flow={'target_n':nn(lambda c:True),'item_observed_both_n':nn(lambda c:c['before'] in KNOWN and c['after'] in KNOWN),
          'eligible_n':est['n'],'known_ineligible_n':nn(lambda c:not eligible(c) and known_out(c)),
          'unresolved_eligibility_n':nn(lambda c:not eligible(c) and not known_out(c)),
          'any_unknown_item_n':nn(lambda c:c['before'] not in KNOWN or c['after'] not in KNOWN),
          'positive_weight_target_n':pn(lambda c:True),
          'positive_weight_item_observed_both_n':pn(lambda c:c['before'] in KNOWN and c['after'] in KNOWN),
          'positive_weight_eligible_n':est['positive_n'],
          'eligible_missing_weight_n':sum(c['weight_missing_n'] for c in cs if eligible(c)),
          'eligible_zero_weight_n':sum(c['weight_zero_n'] for c in cs if eligible(c))}
    if measure=='house': flow['both_post_questionnaires_n']=nn(lambda c:c['before'] not in {'not_post','unknown_post'} and c['after'] not in {'not_post','unknown_post'})
    assert flow['target_n']==flow['eligible_n']+flow['known_ineligible_n']+flow['unresolved_eligibility_n']
    return {'group':group,'cohort':cohort,'measure':measure,'weight_column':WEIGHTS[measure],'flow':flow,'estimate':est,
            'transitions':[{'before':a,'after':b,'n':nn(lambda c:c['before']==a and c['after']==b),
                            'positive_n':pn(lambda c:c['before']==a and c['after']==b)} for a in sorted(allowed) for b in sorted(allowed)]}

def compute(counts):
    rows=[row_result(counts['cells'],g,c,m) for g in GROUPS for m in WEIGHTS for c in COHORTS]
    contrasts=[]
    for g in GROUPS:
        for m in WEIGHTS:
            by={x['cohort']:x for x in rows if x['group']==g and x['measure']==m}
            assert by['full']['flow']['target_n']==counts['totals'][g]['full']
            for k in by['full']['flow']: assert by['full']['flow'][k]==by['retained']['flow'][k]+by['omitted']['flow'][k]
            out={'group':g,'measure':m}
            for label,key in [('unweighted','unweighted_delta_pp'),('weighted','weighted_delta_pp')]:
                a,b=by['retained']['estimate'][key],by['full']['estimate'][key]
                out[label+'_B_pp']=None if a is None or b is None else a-b
                out[label+'_abs_B_ge_2pp']=None if a is None or b is None else abs(a-b)>=2
            contrasts.append(out)
    return {'target':'已发布两波队列中的同口径早期转移，不是2024效果或因果效应','rows':rows,'contrasts':contrasts}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path);ap.add_argument('--selected',type=Path)
    ap.add_argument('--check',action='store_true');a=ap.parse_args()
    if bool(a.baseline)!=bool(a.selected): ap.error('两个原件路径必须同时提供')
    counts=build(a.baseline,a.selected) if a.baseline else json.loads((HERE/'cells.json').read_bytes())
    outputs={'results.json':compute(counts)}
    if a.baseline: outputs['cells.json']=counts
    for name,v in outputs.items():
        b=encode(v);p=HERE/name
        if a.check:
            if p.read_bytes()!=b: raise ValueError('复算字节不一致：'+name)
        else: p.write_bytes(b)
    print(json.dumps({'check':a.check,'source':'原件' if a.baseline else '匿名格表','totals':counts['totals'],'comparison_rows':18},ensure_ascii=False))

if __name__=='__main__': main()
