"""固定口径流式核算；逐人派生数据只存本地执行目录。"""
import csv, json, math, hashlib, itertools
from pathlib import Path
from collections import Counter, defaultdict
from recode import recode
OUT=Path(__file__).parent;ROOT=OUT.parents[1];RUN=ROOT/'runs/run-323'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def num(v):return None if v.strip() in ('','NA') else float(v)
def integer(v):return None if v.strip() in ('','NA') else int(v)
def group(v,groups):
    return next((str(i) for i,g in enumerate(groups) if v in g),None)
def summarize(rows):
    w=[r['weight'] for r in rows if r['weight'] is not None and r['weight']>0]
    return {'n':len(rows),'weight_n':len(w),'weight_mass':math.fsum(w),'kish_ess':math.fsum(w)**2/math.fsum(x*x for x in w) if w else None}
def build():
    spec=json.loads((OUT/'analysis-spec.json').read_text());assert spec['nuisance_df']==11
    source=RUN/'sources/data.csv';manifest=json.loads((OUT/'measurement_manifest.json').read_text());assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['data_sha256']
    records=[];raw_counts=defaultdict(Counter);seen=set()
    with source.open(encoding='utf-8-sig',newline='') as f:
        for raw in csv.DictReader(f):
            assert raw['V240001'] not in seen;seen.add(raw['V240001'])
            row={k:integer(raw[k]) for k in ['V242095x','V242096x','V241451','V242536','V241201','V241206']}
            r=recode(row);r.pop('reasons');r['case']=raw['V240001']
            sample=integer(raw['V240003']);mode=integer(raw['V240002a']);r['scope']='panel' if sample==1 else 'PAPI' if mode==3 else 'fresh'
            w=num(raw['V240103b']);r['weight']=w if w and w>0 else None
            r['psu']=integer(raw['V240103c']);r['stratum']=integer(raw['V240103d'])
            r['PID']=group(integer(raw['V241227x']),[range(1,4),[4],range(5,8)])
            r['income']=group(integer(raw['V241566x']),[range(1,13),range(13,20),range(20,25),range(25,29)])
            r['owner']=group(integer(raw['V241530']),[[2,3],[1]])
            r['age']=group(integer(raw['V241458x']),[range(18,30),range(30,45),range(45,60),range(60,81)])
            r['sample']=str(sample);r['phone']=str(int(mode==4));r['Y']=1 if r['state']=='R' else 0 if r['state']=='D' else None
            r['early']=int(raw['V241036'])==1
            for field in ['V242337','V242531','V242532']:r[field]=integer(raw[field])
            keys=['Y','E','I','C','PID','income','owner','age','sample','phone']
            r['domain']=r['scope']=='fresh' and r['weight'] is not None and all(r[k] is not None for k in keys)
            r['support']=False;records.append(r)
            for field in [x['variable'] for x in manifest['records'] if x['variable'] not in ['V240001','V240103b','V240103c','V240103d']]:raw_counts[(r['scope'],field)][raw[field]]+=1
    fresh=[r for r in records if r['scope']=='fresh'];domain=[r for r in records if r['domain']]
    pattern=lambda r:tuple(r[k] for k in ['C','PID','income','owner','age','sample','phone'])
    combos=defaultdict(set)
    for r in domain:combos[pattern(r)].add((r['E'],r['I']))
    for r in domain:r['support']=len(combos[pattern(r)])==4
    rows=[]
    def add(table,key,rs):rows.append({'table':table,'cell':key,**summarize(rs)})
    for scope in ['all','panel','PAPI','fresh','post_design','domain','support']:
        rs=records if scope=='all' else [r for r in records if r['scope']==scope] if scope in ['panel','PAPI','fresh'] else [r for r in fresh if r['weight'] is not None] if scope=='post_design' else domain if scope=='domain' else [r for r in domain if r['support']]
        add('denominator',scope,rs)
    for st in ['D','R','other','nonvoter','conflict','unknown']:add('fresh_vote',st,[r for r in fresh if r['state']==st])
    for e,i,y in itertools.product([0,1],[0,1],[0,1]):add('domain_E_I_Y',f'{e},{i},{y}',[r for r in domain if (r['E'],r['I'],r['Y'])==(e,i,y)])
    for e,i,st in itertools.product([0,1,None],[0,1,None],['D','R','other','nonvoter','conflict','unknown']):add('fresh_E_I_vote',f'{e},{i},{st}',[r for r in fresh if (r['E'],r['I'],r['state'])==(e,i,st)])
    for field in ['V242337','V242531','V242532']:
        for value in sorted(set(r[field] for r in fresh)):add('descriptive_item',f'{field}:{value}',[r for r in fresh if r[field]==value])
    for scope in ['panel','PAPI','fresh']:
        for (sc,field),counts in sorted(raw_counts.items()):
            if sc==scope:
                for value,n in sorted(counts.items()):rows.append({'table':'item_raw_codes','cell':f'{sc}:{field}:{value}','n':n,'weight_n':'','weight_mass':'','kish_ess':''})
    with (OUT/'denominator_and_material_identity_tables.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['table','cell','n','weight_n','weight_mass','kish_ess']);w.writeheader();w.writerows(rows)
    with (RUN/'local-analysis-frame.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    diagnostics={'n_total':len(records),'n_fresh':len(fresh),'n_post_design':sum(r['weight'] is not None for r in fresh),'n_domain':len(domain),'n_support':sum(r['support'] for r in domain),'early_ballot_in_fresh':sum(r['early'] for r in fresh),'domain_cells':{x['cell']:x['n'] for x in rows if x['table']=='domain_E_I_Y'},'source_sha256':manifest['data_sha256'],'spec_version':spec['spec_version'],'common_support_rule':spec['common_support_rule']}
    dump(OUT/'diagnostics.json',diagnostics);print(json.dumps(diagnostics,ensure_ascii=False))
if __name__=='__main__':build()
