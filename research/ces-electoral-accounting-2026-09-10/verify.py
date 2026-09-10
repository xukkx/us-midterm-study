"""独立从原件核对匿名格表和总量，不导入生产分类器或核算内核。"""
import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
STATES=('D','R','O','A','N','U')
SIGN={'D':-1,'R':1,'O':0,'A':0,'N':0}

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(n):return json.loads((HERE/n).read_bytes())
def encode(x):return (json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
def near(a,b):
    if not math.isfinite(a) or not math.isfinite(b) or not math.isclose(a,b,abs_tol=1e-8,rel_tol=1e-12):raise ValueError('独立复算数值不符')

def reference(row,y):
    """用自报×票项决策表取交集；档案只是独立测量维度。"""
    text=lambda k:row[k].strip()
    val=lambda k:None if text(k).upper() in ('','NA','N/A','NAN','NULL','.') else int(float(text(k)))
    took=val(f'tookpost_{y}');sr=val(f'CC{y}_401');hc=val(f'CC{y}_412')
    report='unknown' if took!=2 or sr is None else 'yes' if sr==5 else 'no'
    postlabel='post' if took==2 else 'not_post' if took==1 else 'unknown_post'
    status=text('CL_voter_status' if y==20 else 'TS_voterstatus')
    fv=val('CL_2020gvm' if y==20 else 'TS_g2022')
    filelabel='unmatched' if status in ('NA','','-1') else 'matched_no_record' if fv is None or (y==22 and fv==7) else 'voted'
    disagreement=(report=='no' and filelabel=='voted') or (report=='yes' and filelabel!='voted')
    if took!=2:return 'U',(postlabel,report,filelabel,'False',str(disagreement))
    ballot=hc in range(1,10 if y==20 else 9) or hc==10
    conflict=(report=='no' and ballot) or (report=='yes' and hc==12)
    if ballot and hc!=10:
        field=f'HouseCand{hc}Party_{y}' if not (y==20 and hc==9) else 'HouseCand9Party'
        postfield=f'HouseCand{hc}Party_post_{y}' if not (y==20 and hc==9) else 'HouseCand9Party_post'
        pp=text(field);sp=text(postfield)
        if pp in ('NA','') or (sp not in ('NA','') and sp!=pp):house='U'
        else:house={'Democratic':'D','Republican':'R'}.get(pp,'O')
    else:house={10:'O',11:'A',12:'N',13:'U',None:'U'}[hc]
    decision={(r,h):('N' if r=='no' else h) for r in ('yes','no','unknown') for h in STATES}
    state='U' if conflict else decision[report,house]
    return state,(postlabel,report,filelabel,str(conflict),str(disagreement))

def audit():
    manifest=read('source-manifest.json');source=manifest['sources']['two_wave_csv'];path=ROOT/source['path']
    if sha(path)!=source['sha256']:raise ValueError('独立原件哈希不符')
    cnt=Counter();weights=defaultdict(list);postweights=defaultdict(list);ec=Counter();ew=defaultdict(list);ep=defaultdict(list)
    ids=[set(),set()];direct={m:defaultdict(list) for m in ('unweighted','adult','post')};n=0
    with path.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            for i,k in enumerate(('caseid','caseid_22')):
                if row[k] in ids[i] or row[k] in ('NA',''):raise ValueError('独立连接键检查失败')
                ids[i].add(row[k])
            a,e20=reference(row,20);b,e22=reference(row,22);key=(a,b);ek=e20+e22
            aw=float(row['commonweight_22']);pw=None if row['commonpostweight_22'] in ('NA','') else float(row['commonpostweight_22'])
            cnt[key]+=1;weights[key].append(aw);ec[ek]+=1;ew[ek].append(aw)
            if pw is not None:postweights[key].append(pw);ep[ek].append(pw)
            for mode,w in [('unweighted',1),('adult',aw),('post',pw)]:
                if w is None:continue
                d=direct[mode];d['n'].append(1);d['weights'].append(w)
                aa=list(SIGN.values()) if a=='U' else [SIGN[a]];bb=list(SIGN.values()) if b=='U' else [SIGN[b]]
                deltas=[y-x for x in aa for y in bb]
                d['lower'].append(w*min(deltas));d['upper'].append(w*max(deltas))
                d['before_lower'].append(w*min(aa));d['before_upper'].append(w*max(aa));d['after_lower'].append(w*min(bb));d['after_upper'].append(w*max(bb))
                if a!='U' and b!='U':d['known_n'].append(1);d['known_delta'].append(w*(SIGN[b]-SIGN[a]))
            n+=1
    if n!=11009:raise ValueError('独立原件人数错误')
    saved=read('flow-cells.json')['cells']
    if len(saved)!=36 or len({(c['before'],c['after']) for c in saved})!=36:raise ValueError('格表不完整')
    for c in saved:
        key=c['before'],c['after']
        if c['n']!=cnt[key] or c['post_n']!=len(postweights[key]):raise ValueError('独立格人数不符')
        near(c['adult_w'],math.fsum(weights[key]));near(c['post_w'],math.fsum(postweights[key]))
    names=[f'{k}_{y}' for y in (20,22) for k in ('post_status','self_report','file_status','conflict','file_self_disagreement')]
    with (HERE/'participation-evidence.csv').open(encoding='utf-8',newline='') as f:ers=list(csv.DictReader(f))
    if len(ers)!=len(ec):raise ValueError('参与证据格数不符')
    for r in ers:
        k=tuple(r[c] for c in names)
        if int(r['n'])!=ec[k] or int(r['post_n'])!=len(ep[k]):raise ValueError('参与证据人数不符')
        near(float(r['adult_w']),math.fsum(ew[k]));near(float(r['post_w']),math.fsum(ep[k]))
    result=read('accounting.json')['modes'];proof={}
    for mode,d in direct.items():
        got=result[mode];covered=len(d['n']);totalw=math.fsum(d['weights']);kn=len(d['known_n'])
        if (got['covered_n'],got['known_pair_n'],got['unknown_pair_n'])!=(covered,kn,covered-kn):raise ValueError('独立模式人数不符')
        near(got['weight_sum'],totalw);near(got['known_delta'],math.fsum(d['known_delta']))
        for field,keys in [('delta_bounds',('lower','upper')),('before_bounds',('before_lower','before_upper')),('after_bounds',('after_lower','after_upper'))]:
            for x,k in zip(got[field],keys):near(x,math.fsum(d[k]))
        for x,k in zip(got['per100_bounds'],('lower','upper')):near(x,100*math.fsum(d[k])/totalw)
        near(got['known_delta'],math.fsum(c['known_delta'] for c in got['components'].values()))
        proof[mode]={'covered_n':covered,'known_pair_n':kn,'unknown_pair_n':covered-kn,'known_delta':math.fsum(d['known_delta']),'bounds':[math.fsum(d[k]) for k in ('lower','upper')]}
    return {'passed':True,'method':'直接读取原件，用独立决策表、逐人签名和枚举端点核验；未导入生产build或accounting_kernel。','n':n,'flow_cells_checked':36,'participation_evidence_cells_checked':len(ers),'modes':proof,'meta':read('accounting.json')['meta'],'input_sha256':sha(path)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();out=audit();data=encode(out);p=HERE/'verification.json'
    if args.check:
        if p.read_bytes()!=data:raise ValueError('独立验收报告被修改')
    else:p.write_bytes(data)
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main()
