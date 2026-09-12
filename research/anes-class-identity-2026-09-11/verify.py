"""从CSV原件独立编码，核对所有分母、联合格表、支持域和标准化点值。"""
import csv,json,math,itertools,hashlib
from pathlib import Path
from collections import defaultdict,Counter
OUT=Path(__file__).parent;ROOT=OUT.parents[1];RUN=ROOT/'runs/run-323'
def check():
    raw=list(csv.DictReader((RUN/'sources/data.csv').open(encoding='utf-8-sig',newline='')))
    assert len(raw)==len({r['V240001'] for r in raw})==5521
    a=[];rawcounts=Counter()
    for r in raw:
        n=lambda k:float(r[k]) if r[k].strip() else None
        scope='panel' if n('V240003')==1 else 'PAPI' if n('V240002a')==3 else 'fresh'
        t,v=n('V242095x'),n('V242096x')
        st='unknown'
        if t==0:st='conflict' if v in range(1,7) else 'nonvoter'
        if t==1:st='D' if v==1 else 'R' if v==2 else 'other' if v in range(3,7) else 'unknown'
        fin,ident,cd,cr=[n(k) for k in ['V241451','V242536','V241201','V241206']]
        e=int(fin>=4) if fin in range(1,6) else None;i=int(ident<=2) if ident in range(1,6) else None
        c=('tie' if cd==cr else 'D_higher' if cd<cr else 'R_higher') if cd in range(1,6) and cr in range(1,6) else None
        pid,inc,home,age=[n(k) for k in ['V241227x','V241566x','V241530','V241458x']]
        x=[0 if pid and 1<=pid<=3 else 1 if pid==4 else 2 if pid and 5<=pid<=7 else None,
           0 if inc and 1<=inc<=12 else 1 if inc and 13<=inc<=19 else 2 if inc and 20<=inc<=24 else 3 if inc and 25<=inc<=28 else None,
           1 if home==1 else 0 if home in (2,3) else None,
           0 if age and 18<=age<=29 else 1 if age and 30<=age<=44 else 2 if age and 45<=age<=59 else 3 if age and 60<=age<=80 else None,
           n('V240003'),int(n('V240002a')==4)]
        w=n('V240103b');w=w if w is not None and w>0 else None
        domain=scope=='fresh' and st in ('D','R') and w is not None and None not in [e,i,c]+x
        rec={'scope':scope,'state':st,'E':e,'I':i,'Y':int(st=='R') if st in ('D','R') else None,'w':w,'domain':domain,'pattern':tuple([c]+x),'support':False,'raw':r}
        a.append(rec)
        for k,v in r.items():rawcounts[f'{scope}:{k}:{v}']+=1
    patterns=defaultdict(set)
    for r in a:
        if r['domain']:patterns[r['pattern']].add((r['E'],r['I']))
    for r in a:r['support']=r['domain'] and patterns[r['pattern']]=={(0,0),(0,1),(1,0),(1,1)}
    local={r['case']:r for r in csv.DictReader((RUN/'local-analysis-frame.csv').open(encoding='utf8',newline=''))}
    assert len(local)==len(a)
    for r in a:
        q=local[r['raw']['V240001']]
        for k in ['scope','state']:assert q[k]==r[k]
        for k in ['E','I','Y']:assert (float(q[k]) if q[k] else None)==r[k]
        for k in ['domain','support']:assert (q[k]=='True')==r[k]
        assert (float(q['weight']) if q['weight'] else None)==r['w']
    table=list(csv.DictReader((OUT/'denominator_and_material_identity_tables.csv').open(encoding='utf8',newline='')))
    for row in table:
        t,k=row['table'],row['cell']
        if t=='item_raw_codes':assert int(row['n'])==rawcounts[k];continue
        if t=='denominator':rs=[r for r in a if k=='all' or r['scope']==k or (k=='post_design' and r['scope']=='fresh' and r['w'] is not None) or (k=='domain' and r['domain']) or (k=='support' and r['support'])]
        elif t=='fresh_vote':rs=[r for r in a if r['scope']=='fresh' and r['state']==k]
        elif t=='domain_E_I_Y':rs=[r for r in a if r['domain'] and ','.join(str(r[v]) for v in ['E','I','Y'])==k]
        elif t=='fresh_E_I_vote':rs=[r for r in a if r['scope']=='fresh' and ','.join(str(r[v]) for v in ['E','I','state'])==k]
        elif t=='descriptive_item':f,v=k.split(':');rs=[r for r in a if r['scope']=='fresh' and float(r['raw'][f])==float(v)]
        else:raise AssertionError(t)
        weights=[r['w'] for r in rs if r['w'] is not None];assert len(rs)==int(row['n']),(t,k)
        assert len(weights)==int(row['weight_n'])
        assert math.isclose(math.fsum(weights),float(row['weight_mass']),rel_tol=1e-12,abs_tol=1e-9),(t,k)
        if weights:assert math.isclose(math.fsum(weights)**2/math.fsum(w*w for w in weights),float(row['kish_ess']),rel_tol=1e-12)
    pp=list(csv.DictReader((RUN/'local-standardization.csv').open()))
    values=[[float(r[k]) for k in ['m11','m01','m10','m00']] for r in pp];ww=[float(r['weight']) for r in pp]
    expected=math.fsum(w*(p[0]+p[3]-p[1]-p[2]) for w,p in zip(ww,values))/math.fsum(ww)
    from contrast import contrast
    assert abs(expected-contrast(values,ww))<1e-12
    result=json.loads((OUT/'associational_results.json').read_text(encoding='utf8'));assert abs(expected-result['primary']['estimate'])<1e-12
    assert {r['case'] for r in pp}=={r['raw']['V240001'] for r in a if r['support']}
    return {'passed':True,'independent_raw_records':len(raw),'table_rows_verified':len(table),'standardization_rows':len(pp),'delta_independent':expected,'method':'不导入生产recode/build，从原件独立编码与格表核对；R点值由独立概率内核复算'}
if __name__=='__main__':
    import sys
    result=check()
    if '--write' in sys.argv:(OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))
